"""Executes one automation run: search, dedupe, qualify, draft.

An Automations row is a saved Discover search plus a schedule. Running it
walks the same pipeline a human would drive by hand from the Discover page —
search, save, qualify, compose — reusing the exact logic those endpoints use
(routers/discover.py's /run and /qualify, services/outreach_composer.py) so
the automated path and the manual path can never quietly diverge.

Two invariants carried over from the endpoints this replaces:

  * Qualification writes NULL, never 0/false, for anything it could not
    measure (see routers/discover.py's /qualify and models/leads.py). A
    scheduled run must not fabricate a verdict any more than a manual one.
  * Qualification cost real credits there and it costs real credits here.
    A runaway schedule must not be able to overspend a workspace's credits;
    this stops qualifying the moment they run out rather than borrowing
    against a month that hasn't started.

The whole thing is wrapped so a network failure, a bad API key, or any other
mid-run exception becomes `last_run_error` on the automation and a returned
result — never an unhandled exception the caller has to guard against. An
automation that fails once must still be inspectable and re-runnable.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.tenancy import ensure_workspace_for_user
from models.automations import Automations
from models.leads import Leads
from models.outreach_drafts import Outreach_drafts
from schemas.auth import UserResponse
from services.leads import LeadsService
from services.discovery_provider import MAX_LIMIT, search_places
from services.outreach_composer import compose_many
from services.qualification import qualify_website
from services.scoring import build_score_breakdown

logger = logging.getLogger(__name__)

# Mirrors routers/discover.py's CREDITS_PER_QUALIFICATION exactly. Kept as its
# own constant rather than imported so this module has no import-time
# dependency on the router package.
CREDITS_PER_QUALIFICATION = 1


def _next_run_at(schedule: str, now: datetime) -> Optional[datetime]:
    """manual never becomes due on its own; daily/weekly do."""
    if schedule == "daily":
        return now + timedelta(days=1)
    if schedule == "weekly":
        return now + timedelta(days=7)
    return None


async def _workspace_for(db: AsyncSession, user_id: str):
    """Resolve (creating if absent) the workspace that pays for this run.

    ensure_workspace_for_user only needs `.id` and `.email` off its `user`
    argument, so a minimal stand-in is enough here — the runner is handed a
    bare user_id, not a full UserResponse, and there is no reason to widen
    run_automation's signature just to thread one through.
    """
    stand_in = UserResponse(id=user_id, email=f"{user_id}@automation.local")
    return await ensure_workspace_for_user(stand_in, db)


async def _existing_lead_keys(db: AsyncSession, user_id: str) -> set:
    result = await db.execute(select(Leads.business_name, Leads.location).where(Leads.user_id == user_id))
    return {
        (name.strip().lower(), (location or "").strip().lower())
        for name, location in result.all()
        if name
    }


def _lead_create_payload(biz: Dict[str, Any], automation: Automations) -> Dict[str, Any]:
    return {
        "business_name": (biz.get("business_name") or "").strip(),
        "category": biz.get("category") or automation.category or "Local Business",
        "location": (biz.get("location") or automation.city or "").strip(),
        "country": biz.get("country") or automation.country or "",
        "website_url": biz.get("website_url") or "",
        "website_score": None,
        "social_score": None,
        "has_website": biz.get("has_website"),
        "social_platforms": "[]",
        "contact_email": biz.get("contact_email") or "",
        "contact_phone": biz.get("contact_phone") or "",
        "pipeline_stage": "new_lead",
        "priority": "medium",
        "notes_count": 0,
        "last_contacted": "",
        "data_source": biz.get("data_source") or "provider",
    }


async def _save_new_leads(
    db: AsyncSession, automation: Automations, user_id: str, raw_results: List[Dict[str, Any]]
) -> tuple[List[Leads], int]:
    """Insert leads not already on file for this user. Everything else counts as a duplicate."""
    existing_keys = await _existing_lead_keys(db, user_id)
    seen_this_run: set = set()
    service = LeadsService(db)

    new_leads: List[Leads] = []
    duplicates = 0

    for biz in raw_results:
        name = (biz.get("business_name") or "").strip()
        location = (biz.get("location") or automation.city or "").strip()
        if not name:
            continue
        key = (name.lower(), location.lower())
        if key in existing_keys or key in seen_this_run:
            duplicates += 1
            continue
        seen_this_run.add(key)

        lead = await service.create(_lead_create_payload(biz, automation), user_id=user_id)
        new_leads.append(lead)

    return new_leads, duplicates


async def _qualify_new_leads(
    db: AsyncSession, automation: Automations, user_id: str, new_leads: List[Leads], workspace
) -> tuple[List[Leads], int, bool]:
    """Qualify up to max_leads_per_run new leads, exactly as POST /qualify does.

    Stops the moment the workspace is out of credits rather than borrowing
    against a future reset — an automation that overspends unattended is the
    exact failure mode the credit check exists to prevent.
    """
    service = LeadsService(db)
    to_qualify = new_leads[: automation.max_leads_per_run]

    qualified: List[Leads] = []
    charged = 0
    exhausted = False

    for lead in to_qualify:
        credits_remaining = workspace.monthly_credits - workspace.credits_used
        if credits_remaining < CREDITS_PER_QUALIFICATION:
            exhausted = True
            break

        measurement = await qualify_website(lead.website_url)
        workspace.credits_used += CREDITS_PER_QUALIFICATION
        charged += CREDITS_PER_QUALIFICATION

        scored = build_score_breakdown(
            {
                "has_website": measurement["has_website"],
                "website_score": measurement["website_score"],
                "social_score": lead.social_score,
                "contact_email": lead.contact_email or None,
                "contact_phone": lead.contact_phone or None,
                "data_source": lead.data_source,
            }
        )

        # Same rule as routers/discover.py's /qualify: persist only what was
        # actually measured. A None score means unmeasurable, and must stay
        # NULL rather than becoming a fabricated 0/false/"[]" verdict.
        update: Dict[str, Any] = {
            "has_website": measurement["has_website"],
            "website_score": measurement["website_score"],
        }
        if measurement["website_url"]:
            update["website_url"] = measurement["website_url"]
        if measurement["website_score"] is not None:
            update["findings"] = json.dumps(measurement["findings"])
            update["qualified_at"] = datetime.now(timezone.utc).isoformat()

        priority = scored["priority_score"]
        if priority is not None:
            update["priority"] = "high" if priority >= 60 else "medium" if priority >= 35 else "low"

        updated = await service.update(lead.id, update, user_id=user_id)
        if updated is not None and measurement["website_score"] is not None:
            qualified.append(updated)

    await db.commit()
    await db.refresh(workspace)
    return qualified, charged, exhausted


async def _draft_for_qualified(
    db: AsyncSession, automation: Automations, user_id: str, qualified_leads: List[Leads]
) -> int:
    """compose_many over the leads this run just qualified, persisted as pending drafts."""
    if not qualified_leads:
        return 0

    lead_dicts = [
        {
            "id": lead.id,
            "business_name": lead.business_name,
            "website_url": lead.website_url,
            "website_score": lead.website_score,
            "contact_email": lead.contact_email,
            "findings": lead.findings,
        }
        for lead in qualified_leads
    ]
    composed = compose_many(lead_dicts, sender_name="", sender_business="")

    drafted = 0
    for draft in composed["drafts"]:
        db.add(
            Outreach_drafts(
                user_id=user_id,
                lead_id=draft["lead_id"],
                automation_id=automation.id,
                to_email=draft["to_email"],
                subject=draft["subject"],
                body_text=draft["body_text"],
                based_on=draft.get("based_on"),
                status="pending",
                sequence_step=1,
            )
        )
        drafted += 1

    if drafted:
        await db.commit()
    return drafted


async def _execute(db: AsyncSession, automation: Automations, user_id: str) -> Dict[str, Any]:
    workspace = await _workspace_for(db, user_id)

    raw_results = await search_places(
        query=automation.query or "",
        location=automation.city or automation.country or "",
        category=automation.category,
        country=automation.country,
        limit=MAX_LIMIT,
    )
    found = len(raw_results)

    new_leads, duplicates = await _save_new_leads(db, automation, user_id, raw_results)

    qualified_leads: List[Leads] = []
    credits_charged = 0
    credit_exhausted = False
    if automation.auto_qualify and new_leads:
        qualified_leads, credits_charged, credit_exhausted = await _qualify_new_leads(
            db, automation, user_id, new_leads, workspace
        )

    drafted = 0
    if automation.auto_draft and qualified_leads:
        drafted = await _draft_for_qualified(db, automation, user_id, qualified_leads)

    summary = (
        f"Found {found}, {len(new_leads)} new, {duplicates} duplicate"
        f"{'s' if duplicates != 1 else ''}, {len(qualified_leads)} qualified, {drafted} drafted."
    )
    if credit_exhausted:
        summary += " Stopped qualifying — out of credits."

    return {
        "found": found,
        "new_leads": len(new_leads),
        "duplicates": duplicates,
        "qualified": len(qualified_leads),
        "drafted": drafted,
        "credits_charged": credits_charged,
        "credit_exhausted": credit_exhausted,
        "summary": summary,
    }


async def run_automation(db: AsyncSession, automation: Automations, user_id: str) -> Dict[str, Any]:
    """Run one automation now. Never raises — a failure becomes last_run_error."""
    now = datetime.now(timezone.utc)

    try:
        outcome = await _execute(db, automation, user_id)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see module docstring
        logger.exception("Automation %s failed", automation.id)
        # A half-finished statement can leave the session unable to run
        # another query until it is rolled back. Rows already committed
        # inside _execute (each lead save/qualify commits as it goes,
        # mirroring the endpoints it reuses) are unaffected by this.
        await db.rollback()
        # rollback() expires every attribute on `automation`. Under an async
        # session that expiry must be resolved with an explicit awaited
        # reload — assigning straight into an expired attribute leaves
        # SQLAlchemy needing to lazily fetch the *other* columns to compute
        # update history, and it cannot do that IO implicitly here.
        await db.refresh(automation)

        automation.last_run_at = now
        automation.next_run_at = _next_run_at(automation.schedule, now)
        automation.last_run_error = str(exc)[:500]
        automation.last_run_summary = f"Run failed: {str(exc)[:200]}"
        await db.commit()
        await db.refresh(automation)

        return {
            "automation_id": automation.id,
            "status": "error",
            "error": automation.last_run_error,
            "summary": automation.last_run_summary,
        }

    automation.last_run_at = now
    automation.next_run_at = _next_run_at(automation.schedule, now)
    automation.last_run_summary = outcome["summary"]
    automation.last_run_error = None
    await db.commit()
    await db.refresh(automation)

    return {
        "automation_id": automation.id,
        "status": "ok",
        **outcome,
    }
