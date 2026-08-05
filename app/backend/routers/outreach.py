"""
BizLeads Outreach Router - PageSpeed audits and email delivery
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from models.leads import Leads
from models.outreach_drafts import Outreach_drafts
from services.pagespeed import is_pagespeed_configured, audit_website, bulk_audit
from services.email_sender import send_email, send_bulk_emails, get_email_config_status
from services.email_identity import resolve_identity
from services.outreach_composer import compose_many, parse_findings
from services.lead_angle import write_angle_note
from services.leads import LeadsService
from services import activity
from services import ai_writer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/outreach", tags=["outreach"])


# --- PageSpeed Audit Endpoints ---

class AuditRequest(BaseModel):
    url: str
    strategy: str = "mobile"  # mobile or desktop


class BulkAuditRequest(BaseModel):
    urls: list[str]
    strategy: str = "mobile"


@router.post("/audit")
async def run_pagespeed_audit(
    data: AuditRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Run a PageSpeed Insights audit on a single website."""
    if not is_pagespeed_configured():
        # Deliberately does not name the environment variable or tell the
        # customer to go and set it. PAGESPEED_API_KEY lives on the API
        # service, so that instruction described work only the operator can
        # do, in a place the customer cannot reach.
        raise HTTPException(
            status_code=503,
            detail="Detailed audits are unavailable right now. Website quality is still measured from the page itself.",
        )

    result = await audit_website(data.url, data.strategy)
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to audit website. Please check the URL is valid and accessible.")

    return result


@router.post("/audit/bulk")
async def run_bulk_audit(
    data: BulkAuditRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Run PageSpeed audits on multiple websites (max 10)."""
    if not is_pagespeed_configured():
        # Same wording as /audit above, for the same reason.
        raise HTTPException(
            status_code=503,
            detail="Detailed audits are unavailable right now. Website quality is still measured from the page itself.",
        )

    if not data.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    results = await bulk_audit(data.urls[:10], data.strategy)
    return {
        "results": results,
        "total_audited": len(results),
        "total_requested": len(data.urls),
    }


# --- Email Outreach Endpoints ---
#
# Every send here resolves the CALLER's own sending identity first (see
# services/email_identity.resolve_identity) rather than reading SMTP_*/
# RESEND_* out of the process environment directly. That environment account
# still exists as a fallback for a workspace that has not configured one of
# its own, but which credentials actually get used is decided per-request,
# per-user - never once at import time for the whole process.

class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    reply_to: Optional[str] = None


class BulkEmailRequest(BaseModel):
    recipients: list[dict]  # Each has 'email', optional 'name', 'business_name'
    subject_template: str
    body_html_template: str
    body_text_template: Optional[str] = None


# Names Settings, not a "Settings > Email" tab that does not exist — the
# email card lives on the Workspace tab. Says "your own" because that is now
# the only option: there is no shared account to fall back to.
_EMAIL_NOT_CONFIGURED_DETAIL = (
    "Set up your own sending account in Settings before sending. Outreach "
    "goes out from your address, using your Gmail or Resend credentials."
)


async def _status_for(db: AsyncSession, user_id: str) -> dict:
    """Config status for one user's resolved identity, never another's.

    Deliberately does NOT fall back to get_email_config_status(identity=None)
    when resolve_identity comes back empty - that would silently report the
    operator's raw environment state (host set, but say password missing) as
    if it were this user's own configuration, which it never was.
    """
    identity = await resolve_identity(db, user_id)
    if identity is None:
        return {
            "configured": False,
            "provider": None,
            "host": None,
            "port": None,
            "from_email": None,
            "use_tls": True,
            "username_set": False,
            "password_set": False,
            "missing": ["email_settings"],
        }
    return get_email_config_status(identity)


@router.post("/send-email")
async def send_outreach_email(
    data: SendEmailRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a single outreach email to a lead, from the caller's own account."""
    identity = await resolve_identity(db, current_user.id)
    if identity is None:
        raise HTTPException(status_code=503, detail=_EMAIL_NOT_CONFIGURED_DETAIL)

    result = await send_email(
        to_email=data.to_email,
        subject=data.subject,
        body_html=data.body_html,
        body_text=data.body_text,
        reply_to=data.reply_to,
        identity=identity,
    )

    # Recorded either way. A send that failed is the event an operator most
    # needs to see, and a trail that logs only successes would report a
    # healthy outreach channel while nothing was arriving.
    await activity.record(
        db,
        activity.OUTREACH_SENT if result["success"] else activity.OUTREACH_FAILED,
        user_id=current_user.id,
        user_email=current_user.email,
        entity_type="email",
        status="ok" if result["success"] else "failed",
        summary=(
            f"Sent outreach to {data.to_email}"
            if result["success"]
            else f"Outreach to {data.to_email} failed: {str(result.get('message'))[:150]}"
        ),
        metadata={"to_email": data.to_email, "subject": data.subject},
    )
    await db.commit()

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("message", "Failed to send email"))

    return result


@router.post("/send-bulk")
async def send_bulk_outreach(
    data: BulkEmailRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send outreach emails to multiple leads using templates, from the caller's own account."""
    identity = await resolve_identity(db, current_user.id)
    if identity is None:
        raise HTTPException(status_code=503, detail=_EMAIL_NOT_CONFIGURED_DETAIL)

    if not data.recipients:
        raise HTTPException(status_code=400, detail="No recipients provided")

    result = await send_bulk_emails(
        recipients=data.recipients,
        subject_template=data.subject_template,
        body_html_template=data.body_html_template,
        body_text_template=data.body_text_template,
        identity=identity,
    )

    sent = result.get("sent", 0) if isinstance(result, dict) else 0
    failed = result.get("failed", 0) if isinstance(result, dict) else 0
    await activity.record(
        db,
        activity.OUTREACH_SENT,
        user_id=current_user.id,
        user_email=current_user.email,
        entity_type="email",
        status="failed" if failed and not sent else "ok",
        summary=f"Bulk outreach: {sent} sent, {failed} failed",
        metadata={"recipients": len(data.recipients), "sent": sent, "failed": failed},
    )
    await db.commit()

    return result


@router.get("/email-status")
async def get_email_status(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the caller's own email configuration status."""
    return await _status_for(db, current_user.id)


@router.get("/status")
async def get_outreach_status(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get overall outreach capabilities status for the caller."""
    email_status = await _status_for(db, current_user.id)
    return {
        "pagespeed": {
            "configured": is_pagespeed_configured(),
            "description": "Website performance audits via Google PageSpeed Insights",
        },
        "email": {
            "description": "SMTP/Gmail/Resend email sending for lead outreach, from your own account",
            **email_status,
        },
    }


# --- Evidence-based drafting ---

class ComposeRequest(BaseModel):
    lead_ids: list[int]
    sender_name: Optional[str] = None
    sender_business: Optional[str] = None


MAX_COMPOSE_PER_CALL = 50


@router.post("/compose")
async def compose_drafts(
    data: ComposeRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Draft outreach for leads, written from their measured findings.

    Costs no credits: the measurement was already paid for at qualification,
    and this only re-reads what was stored. Charging again for rephrasing our
    own data would be indefensible.

    Leads that cannot honestly be written to are returned in `skipped` with a
    reason, never silently dropped — an unqualified lead simply needs
    qualifying, and telling the user that is more useful than a short list
    with no explanation.
    """
    if not data.lead_ids:
        raise HTTPException(status_code=400, detail="No leads selected")

    if len(data.lead_ids) > MAX_COMPOSE_PER_CALL:
        raise HTTPException(
            status_code=400,
            detail=f"Compose at most {MAX_COMPOSE_PER_CALL} leads at a time.",
        )

    service = LeadsService(db)
    leads: list[dict] = []
    not_found: list[int] = []

    for lead_id in data.lead_ids:
        # Scoped to the caller: get_by_id filters by user_id, so one customer
        # cannot draft from another's leads.
        lead = await service.get_by_id(lead_id, user_id=str(current_user.id))
        if lead is None:
            not_found.append(lead_id)
            continue
        leads.append({
            "id": lead.id,
            "business_name": lead.business_name,
            "website_url": lead.website_url,
            "website_score": lead.website_score,
            "contact_email": lead.contact_email,
            "findings": lead.findings,
        })

    result = compose_many(
        leads,
        sender_name=(data.sender_name or "").strip(),
        sender_business=(data.sender_business or "").strip(),
    )
    # Persist every draft into the approval queue.
    #
    # Composing used to return drafts to the browser and keep nothing. The
    # queue was therefore always empty no matter how many times a user pressed
    # "Draft from findings", and a refresh lost the lot — so the two halves of
    # the feature looked broken independently while each worked on its own.
    # The queue is now the single record of a draft; the response still
    # carries them so the UI can show them without a second request.
    for draft in result.get("drafts", []):
        # Re-composing a lead replaces its unsent draft rather than stacking a
        # second one. Two pending emails to the same prospect is the failure
        # nobody notices until both have been sent.
        #
        # Skipped drafts are cleared too. A skipped draft is one the user set
        # aside; a freshly composed one supersedes it, and leaving both would
        # offer to restore a stale version of an email that has already been
        # rewritten.
        existing = await db.execute(
            select(Outreach_drafts).where(
                Outreach_drafts.user_id == str(current_user.id),
                Outreach_drafts.lead_id == draft["lead_id"],
                Outreach_drafts.status.in_(("pending", "skipped")),
            )
        )
        for stale in existing.scalars().all():
            await db.delete(stale)

        row = Outreach_drafts(
            user_id=str(current_user.id),
            lead_id=draft["lead_id"],
            automation_id=None,
            to_email=draft["to_email"],
            subject=draft["subject"],
            body_text=draft["body_text"],
            based_on=draft.get("based_on"),
            status="pending",
            sequence_step=1,
        )
        db.add(row)
        await db.flush()      # assigns the id
        draft["id"] = row.id  # so the UI edits and sends this exact row

    await db.commit()

    result["not_found"] = not_found
    result["email_configured"] = (await resolve_identity(db, current_user.id)) is not None
    result["queued"] = len(result.get("drafts", []))
    return result


# --- AI-assisted wording -----------------------------------------------
#
# See services/ai_writer.py's module docstring for the rule this whole
# surface exists under: AI may improve WORDING, AI must never introduce a
# FACT. `/ai/draft` is grounded only in a lead's own measured findings (the
# same ones services/outreach_composer.py reads) and refuses to run when
# there are none. `/ai/polish` only ever sees text the caller already wrote.
# Both endpoints are auth-gated, user-scoped, and return a clear 503 rather
# than a silent fallback when no provider key is set - a user must never
# mistake the deterministic composer's output for an AI-assisted one.

# Names no environment variable and tells nobody to go and set one. Both keys
# live on the API service, so that instruction described work only the operator
# can do — and it named ANTHROPIC_API_KEY specifically, which stopped being the
# only option when NVIDIA NIM was added. What the customer needs to know is
# that drafting still works without it.
_AI_NOT_CONFIGURED_DETAIL = (
    "AI wording help is not available right now. Drafting from measured "
    "findings still works."
)
_AI_UNAVAILABLE_DETAIL = "AI writing is temporarily unavailable. Please try again shortly."


class AIPolishRequest(BaseModel):
    text: str
    tone: Optional[str] = "professional"


class AIDraftRequest(BaseModel):
    lead_id: int
    tone: Optional[str] = "professional"


@router.post("/ai/polish")
async def ai_polish_text(
    data: AIPolishRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Improve grammar/clarity/tone of text the caller wrote. Never adds a claim."""
    if not ai_writer.is_ai_configured():
        raise HTTPException(status_code=503, detail=_AI_NOT_CONFIGURED_DETAIL)

    if not (data.text or "").strip():
        raise HTTPException(status_code=422, detail="No text provided to polish")

    result = await ai_writer.polish(data.text, tone=(data.tone or "professional").strip() or "professional")
    if result is None:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE_DETAIL)

    return {"text": result["text"], "changed": result["changed"], "ai_available": True}


@router.post("/ai/draft")
async def ai_draft_for_lead(
    data: AIDraftRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-drafted opening email for one lead, grounded only in its own findings.

    404 if the lead does not belong to the caller - `LeadsService.get_by_id`
    is scoped by user_id, so one customer can never draft from another's
    lead. 409 if the lead has not been qualified yet: no findings means no
    honest email, whether the composer or the model would be writing it.
    """
    if not ai_writer.is_ai_configured():
        raise HTTPException(status_code=503, detail=_AI_NOT_CONFIGURED_DETAIL)

    service = LeadsService(db)
    lead = await service.get_by_id(data.lead_id, user_id=str(current_user.id))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    findings = parse_findings(lead.findings)
    if not findings:
        raise HTTPException(
            status_code=409,
            detail="This lead has no measured findings yet. Qualify it first.",
        )

    draft = await ai_writer.draft_for_category(
        business_name=lead.business_name,
        category=lead.category,
        findings=findings,
        tone=(data.tone or "professional").strip() or "professional",
    )
    if draft is None:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE_DETAIL)

    return {
        "lead_id": lead.id,
        "subject": draft["subject"],
        "body_text": draft["body_text"],
        "ai_available": True,
    }


class AIAngleRequest(BaseModel):
    lead_id: int


@router.post("/ai/angle")
async def ai_angle_for_lead(
    data: AIAngleRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Write an internal "how to win this lead" note, and store it.

    Same grounding rule as /ai/draft: only the lead's own measured findings.
    The difference is the audience — this note is read by the person selling
    and is never sent to the prospect, so it may recommend an approach where
    the outreach draft may only state facts.

    Regenerating replaces the previous machine-written note for this lead and
    leaves every human-written note alone.
    """
    if not ai_writer.is_ai_configured():
        raise HTTPException(status_code=503, detail=_AI_NOT_CONFIGURED_DETAIL)

    service = LeadsService(db)
    lead = await service.get_by_id(data.lead_id, user_id=str(current_user.id))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not parse_findings(lead.findings):
        raise HTTPException(
            status_code=409,
            detail="This lead has no measured findings yet. Qualify it first.",
        )

    note = await write_angle_note(db, lead, str(current_user.id))
    if note is None:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE_DETAIL)

    await db.commit()
    return {"lead_id": lead.id, "note": note, "note_type": ai_writer.AI_ANGLE_NOTE_TYPE}


@router.get("/ai/status")
async def ai_status(
    current_user: UserResponse = Depends(get_current_user),
):
    """Whether AI-assisted writing is configured, and which model it uses.

    Reports active_model(), NOT the module's MODEL constant. MODEL is the
    Anthropic model name specifically; returning it meant that with NVIDIA
    configured the UI displayed "claude-sonnet-5" while every request actually
    went to meta/llama-3.3-70b-instruct. active_model() resolves the same
    provider precedence the calls themselves use, so the badge cannot drift
    from what ran.
    """
    return {"available": ai_writer.is_ai_configured(), "model": ai_writer.active_model()}


# --- Draft queue: review, send, or discard what compose/automations produced ---
#
# outreach_drafts holds only body_text (see models/outreach_drafts.py) — there
# is no stored HTML twin. Sending renders a minimal HTML view from the text at
# send time rather than persisting a second copy that could drift from it.

def _text_to_html(body_text: str) -> str:
    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    paragraphs = "".join(
        "<p>" + esc(part).replace("\n", "<br>") + "</p>"
        for part in body_text.split("\n\n")
        if part.strip()
    )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'font-size:15px;line-height:1.6;color:#1f2937">' + paragraphs + "</div>"
    )


def _draft_dict(draft: Outreach_drafts, business_name: Optional[str] = None) -> dict:
    """Serialise a queued draft for the approval UI.

    `based_on` is returned as a JSON STRING, not a parsed array, to match what
    /compose returns for an unsaved draft. The two shapes existed briefly and
    the consequence was silent: the client parses this field, so an array
    arrived as something JSON.parse rejects, the guard caught it, and every
    queued draft reported "0 measured findings" — telling the user the email
    was based on nothing when it was based on three. One field, two shapes, no
    error anywhere.

    `business_name` is joined in by the caller. Without it the queue lists
    email addresses with no indication of which business each belongs to,
    which is unusable for reviewing more than a couple at a time.
    """
    # Validate rather than pass through: a malformed value should degrade to
    # an empty list, not reach the browser and break the badge.
    based_on = "[]"
    if draft.based_on:
        try:
            parsed = json.loads(draft.based_on)
            if isinstance(parsed, list):
                based_on = json.dumps(parsed)
        except (json.JSONDecodeError, ValueError):
            based_on = "[]"

    return {
        "id": draft.id,
        "lead_id": draft.lead_id,
        "automation_id": draft.automation_id,
        "business_name": business_name,
        "to_email": draft.to_email,
        "subject": draft.subject,
        "body_text": draft.body_text,
        "based_on": based_on,
        "status": draft.status,
        "sequence_step": draft.sequence_step,
        "send_error": draft.send_error,
        "sent_at": draft.sent_at.isoformat() if draft.sent_at else None,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }


async def _get_owned_draft(db: AsyncSession, draft_id: int, user_id: str) -> Outreach_drafts:
    result = await db.execute(
        select(Outreach_drafts).where(Outreach_drafts.id == draft_id, Outreach_drafts.user_id == user_id)
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.get("/queue")
async def get_outreach_queue(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """Pending drafts for the caller, newest first.

    Outer-joined to the lead for its business name. An outer join rather than
    an inner one on purpose: a lead deleted after its draft was queued must
    leave the draft visible so the user can discard it, not make it vanish
    from the queue while still counting as pending.
    """
    result = await db.execute(
        select(Outreach_drafts, Leads.business_name)
        .outerjoin(Leads, Leads.id == Outreach_drafts.lead_id)
        .where(Outreach_drafts.user_id == current_user.id, Outreach_drafts.status == "pending")
        .order_by(Outreach_drafts.id.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()

    # Skipped drafts ride along rather than needing a second request. They are
    # set aside, not gone, so the queue has to be able to offer them back —
    # and a "3 skipped" line the user can act on is the only thing that stops
    # Skip from feeling like a quieter Discard.
    skipped_result = await db.execute(
        select(Outreach_drafts, Leads.business_name)
        .outerjoin(Leads, Leads.id == Outreach_drafts.lead_id)
        .where(Outreach_drafts.user_id == current_user.id, Outreach_drafts.status == "skipped")
        .order_by(Outreach_drafts.id.desc())
        .limit(limit)
    )

    return {
        "items": [_draft_dict(draft, business_name) for draft, business_name in rows],
        "total": len(rows),
        "skipped": [
            _draft_dict(draft, business_name)
            for draft, business_name in skipped_result.all()
        ],
    }


@router.post("/queue/{draft_id}/send")
async def send_queued_draft(
    draft_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send one queued draft. The customer is legally the sender under the
    Terms — this is a human clicking send on a draft they reviewed, never an
    automatic dispatch."""
    draft = await _get_owned_draft(db, draft_id, current_user.id)
    if draft.status != "pending":
        raise HTTPException(status_code=400, detail=f"Draft is already {draft.status}, not pending")

    identity = await resolve_identity(db, current_user.id)
    if identity is None:
        raise HTTPException(status_code=503, detail=_EMAIL_NOT_CONFIGURED_DETAIL)

    result = await send_email(
        to_email=draft.to_email,
        subject=draft.subject,
        body_html=_text_to_html(draft.body_text),
        body_text=draft.body_text,
        identity=identity,
    )

    if result.get("success"):
        draft.status = "sent"
        draft.sent_at = datetime.now(timezone.utc)
        draft.send_error = None
    else:
        draft.status = "failed"
        draft.send_error = result.get("message", "Failed to send email")

    await db.commit()
    await db.refresh(draft)
    return _draft_dict(draft)


@router.post("/queue/{draft_id}/discard")
async def discard_queued_draft(
    draft_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    draft = await _get_owned_draft(db, draft_id, current_user.id)
    if draft.status != "pending":
        raise HTTPException(status_code=400, detail=f"Draft is already {draft.status}, not pending")

    draft.status = "discarded"
    await db.commit()
    await db.refresh(draft)
    return _draft_dict(draft)


@router.post("/queue/{draft_id}/skip")
async def skip_queued_draft(
    draft_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a draft aside without sending or destroying it.

    Distinct from discard on purpose. Discard is a verdict — this prospect is
    not worth writing to — and is final. Skip is "not now": the draft leaves
    the queue so it stops demanding a decision, and can be restored.

    Without this the only way to clear a draft you did not want to send today
    was to discard it, which meant re-composing later to get it back. A
    reversible action is the right default for a bulk review surface, where a
    misclick costs nothing to undo and everything to redo.
    """
    draft = await _get_owned_draft(db, draft_id, current_user.id)
    if draft.status != "pending":
        raise HTTPException(status_code=400, detail=f"Draft is already {draft.status}, not pending")

    draft.status = "skipped"
    await db.commit()
    await db.refresh(draft)
    return _draft_dict(draft)


@router.post("/queue/{draft_id}/restore")
async def restore_skipped_draft(
    draft_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Put a skipped draft back in the queue.

    Only `skipped` can be restored. A sent draft cannot be un-sent, and
    restoring a discarded one would undo a decision the user made
    deliberately — if they want it back, re-composing writes it from the same
    findings anyway.
    """
    draft = await _get_owned_draft(db, draft_id, current_user.id)
    if draft.status != "skipped":
        raise HTTPException(status_code=400, detail=f"Draft is {draft.status}, not skipped")

    draft.status = "pending"
    await db.commit()
    await db.refresh(draft)
    return _draft_dict(draft)


@router.post("/queue/send-all")
async def send_all_queued_drafts(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send every pending draft. One recipient's failure must not stop the rest."""
    identity = await resolve_identity(db, current_user.id)
    if identity is None:
        raise HTTPException(status_code=503, detail=_EMAIL_NOT_CONFIGURED_DETAIL)

    result = await db.execute(
        select(Outreach_drafts).where(
            Outreach_drafts.user_id == current_user.id, Outreach_drafts.status == "pending"
        )
    )
    drafts = result.scalars().all()

    sent = 0
    failed = 0
    results = []
    for draft in drafts:
        try:
            send_result = await send_email(
                to_email=draft.to_email,
                subject=draft.subject,
                body_html=_text_to_html(draft.body_text),
                body_text=draft.body_text,
                identity=identity,
            )
        except Exception as exc:  # noqa: BLE001 - one bad recipient must not abort the batch
            send_result = {"success": False, "message": str(exc)[:300]}

        if send_result.get("success"):
            draft.status = "sent"
            draft.sent_at = datetime.now(timezone.utc)
            draft.send_error = None
            sent += 1
        else:
            draft.status = "failed"
            draft.send_error = send_result.get("message", "Failed to send email")
            failed += 1
        results.append({"id": draft.id, "status": draft.status})

    await db.commit()
    return {"sent": sent, "failed": failed, "total": len(drafts), "results": results}
