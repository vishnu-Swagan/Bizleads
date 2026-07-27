"""System-triggered automation runs.

Deliberately a separate router from routers/automations.py, which is the
user-facing CRUD surface. Everything there is authenticated as a signed-in
person and scoped to that person. This endpoint is the opposite: no user is
present, and it must reach every account's due automations.

Mixing those two authentication models in one file is how an endpoint ends up
accidentally reachable by the wrong caller, so they are kept apart.

Why an endpoint at all rather than a scheduler in-process: the API runs on
Render's free tier, which has no cron and sleeps when idle. Nothing inside the
process can wake itself, so `next_run_at` would simply pass unnoticed.
.github/workflows/run-automations.yml calls this hourly instead.

This never sends email. It searches, qualifies within the caller's credit
budget, and drafts into the approval queue for a human.
"""
import asyncio
import hmac
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.automations import Automations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])

# One run must not be able to occupy the worker indefinitely. Anything beyond
# this is picked up on the next hourly tick.
MAX_AUTOMATIONS_PER_TICK = 25


def _verify_secret(provided: str | None) -> None:
    """Constant-time check of the shared secret.

    An unset secret disables the endpoint entirely rather than leaving it
    open. Failing closed matters here: this route runs work on behalf of every
    account, so an accidentally-public version would let anyone spend other
    people's credits.
    """
    expected = os.environ.get("AUTOMATION_CRON_SECRET", "")
    if not expected:
        raise HTTPException(
            status_code=401,
            detail="Scheduled runs are disabled: AUTOMATION_CRON_SECRET is not set.",
        )
    # compare_digest rather than == so a wrong secret cannot be recovered by
    # timing how long the comparison took.
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid automation secret")


@router.post("/run-scheduled")
async def run_scheduled(
    x_automation_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Run every automation that is due, across all accounts."""
    _verify_secret(x_automation_secret)

    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Automations)
        .where(
            Automations.enabled.is_(True),
            Automations.schedule != "manual",
            Automations.next_run_at.isnot(None),
            Automations.next_run_at <= now,
        )
        .order_by(Automations.next_run_at.asc())
        .limit(MAX_AUTOMATIONS_PER_TICK)
    )
    due = list(result.scalars().all())

    if not due:
        return {"ran": 0, "results": [], "checked_at": now.isoformat()}

    # Imported here, not at module scope: the runner pulls in the provider and
    # qualification stack, and a failure there must not unmount this router at
    # import time the way it silently unmounted the automation router before.
    from services.automation_runner import run_automation

    results = []
    for automation in due:
        try:
            outcome = await run_automation(db, automation, automation.user_id)
            results.append({
                "automation_id": automation.id,
                "name": automation.name,
                "ok": True,
                "summary": outcome.get("summary") if isinstance(outcome, dict) else None,
            })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # One account's failure must not stop every other account's run.
            logger.error("Scheduled automation %s failed: %s", automation.id, exc)
            automation.last_run_error = str(exc)[:500]
            automation.last_run_at = now
            results.append({
                "automation_id": automation.id,
                "name": automation.name,
                "ok": False,
                "error": str(exc)[:200],
            })

    followups = await _queue_due_followups(db, now)

    await db.commit()
    return {
        "ran": len(results),
        "succeeded": sum(1 for r in results if r["ok"]),
        "followups_queued": followups,
        "results": results,
        "checked_at": now.isoformat(),
    }


async def _queue_due_followups(db: AsyncSession, now: datetime) -> int:
    """Draft the next touch for leads whose previous email has gone unanswered.

    Most replies to cold outreach come from the second or third message, so a
    first-email-only tool leaves most of its value unclaimed. But a follow-up
    sent to somebody who already replied is the fastest way to look like a
    spammer, so this is deliberately conservative.

    There is no inbox reading here and none is planned, which means we cannot
    actually know who replied. The only honest signal is the lead's pipeline
    stage: a lead a human has moved to Replied, Won or Lost is excluded, and
    an unrecognised stage is also excluded. select_due_followups fails safe on
    everything it cannot determine.

    Drafts go to the approval queue like any other. Nothing is sent here.
    """
    from models.leads import Leads
    from models.outreach_drafts import Outreach_drafts
    from services.outreach_followup import compose_followup, select_due_followups

    # Only leads that have actually been emailed can be followed up, so start
    # from the drafts rather than scanning every lead.
    sent = await db.execute(
        select(Outreach_drafts).where(Outreach_drafts.status.in_(("pending", "sent")))
    )
    drafts_by_lead: dict[int, list] = {}
    for draft in sent.scalars().all():
        drafts_by_lead.setdefault(draft.lead_id, []).append(draft)
    if not drafts_by_lead:
        return 0

    leads_result = await db.execute(
        select(Leads).where(Leads.id.in_(list(drafts_by_lead)))
    )
    leads_by_id = {lead.id: lead for lead in leads_result.scalars().all()}

    candidates = []
    for lead_id, drafts in drafts_by_lead.items():
        lead = leads_by_id.get(lead_id)
        if lead is None:
            continue  # lead deleted; nothing to follow up
        drafts.sort(key=lambda d: (d.sent_at or d.created_at or now, d.id))
        candidates.append({
            "lead": {
                "id": lead.id,
                "user_id": lead.user_id,
                "business_name": lead.business_name,
                "website_url": lead.website_url,
                "website_score": lead.website_score,
                "contact_email": lead.contact_email,
                "findings": lead.findings,
                "pipeline_stage": lead.pipeline_stage,
            },
            "drafts": [
                {
                    "id": d.id,
                    "subject": d.subject,
                    "body_text": d.body_text,
                    "based_on": d.based_on,
                    "status": d.status,
                    "sent_at": d.sent_at,
                    "sequence_step": d.sequence_step,
                }
                for d in drafts
            ],
        })

    queued = 0
    for due in select_due_followups(candidates, now=now):
        lead = due["lead"]
        draft = compose_followup(lead, due["previous"], due["step"])
        if draft is None:
            continue
        db.add(Outreach_drafts(
            user_id=lead["user_id"],
            lead_id=lead["id"],
            automation_id=None,
            to_email=lead["contact_email"],
            subject=draft["subject"],
            body_text=draft["body_text"],
            based_on=draft.get("based_on"),
            status="pending",
            sequence_step=due["step"],
        ))
        queued += 1

    if queued:
        logger.info("Queued %d follow-up draft(s)", queued)
    return queued
