"""Follow-up outreach: the second and third touch, never the fourth.

Most replies to cold outreach come from the second or third email, not the
first - so a tool that only ever sends one email leaves most of its own
value on the table. But a follow-up sent to someone who already replied, or
sent past the point where persistence turns into harassment, is the fastest
way to get a sending domain blocked.

This module has one job and refuses to do anything beyond it:

  * WHEN to send a follow-up - a pure, deterministic schedule with a hard
    stop at step 3, gated on the lead's `pipeline_stage`. There is no inbox
    reading in this product, so `pipeline_stage` is the only honest signal
    that a human has taken the conversation over. Anything that is not
    unambiguously an early, un-replied-to stage is treated as "do not touch"
    - fail safe, not fail open.

  * WHAT the follow-up says - short, references the original concretely
    (never restates it), and never invents a fact. It reuses the exact same
    measured findings (`parse_findings`, `FINDING_COPY`) the first email was
    built from, imported from services.outreach_composer rather than
    duplicated here, so there is exactly one table of what a finding means.

Like the composer, this writes drafts for a human to review and send. It
never sends anything and it never reads a mailbox.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.outreach_composer import FINDING_COPY, _domain, _header_safe, parse_findings

# Step -> days that must have elapsed since the previous send before this
# step becomes due. Step 1 is the original email (services.outreach_composer)
# and is not represented here. There is deliberately no step 4: a third
# unanswered follow-up has already made the point, and a fourth is
# persistence tipping into harassment.
FOLLOWUP_STEPS: Dict[int, int] = {
    2: 4,
    3: 9,
}

MAX_FOLLOWUP_STEP = max(FOLLOWUP_STEPS)

# Stages a lead can be in and still receive an automated follow-up. Both are
# states the app itself sets without any human having spoken to the lead:
# `new_lead` is the starting stage, and `contacted` is what the app flips a
# lead to the moment the first outreach is sent (see routers/automation.py).
# Every other stage - `replied`, `qualified`, `won`, `lost`, or anything this
# module has never heard of - means either a human moved the lead by hand or
# the value is unrecognised. Either way: fail safe, do not follow up.
SAFE_TO_FOLLOW_UP = {"new_lead", "contacted"}


def _default_followup_subject(business: str) -> str:
    return "Following up - " + business


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _simple_html(paragraphs: List[str]) -> str:
    """Same plain, unstyled-newsletter look as the composer's HTML output."""
    body = "".join("<p>" + _escape(p) + "</p>" for p in paragraphs if p)
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'font-size:15px;line-height:1.6;color:#1f2937">' + body + "</div>"
    )


def _top_finding(lead: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The single most severe known finding, or None if there is nothing to say.

    Mirrors the ranking the composer uses for its subject line - highest
    penalty first, unknown finding ids dropped - without duplicating
    FINDING_COPY itself.
    """
    findings = [f for f in parse_findings(lead.get("findings")) if f.get("id") in FINDING_COPY]
    if not findings:
        return None
    return max(findings, key=lambda f: f.get("penalty", 0))


def compose_followup(
    lead: Dict[str, Any],
    previous: Dict[str, Any],
    step: int,
) -> Optional[Dict[str, str]]:
    """Draft follow-up `step` for `lead`, referencing `previous`, or None.

    None is the correct answer whenever the follow-up cannot be grounded in a
    real measurement: an unrecognised step, or a lead with no findings left
    to point at. A follow-up with nothing to reference is exactly the "just
    bumping this" filler this product refuses to send.
    """
    if step not in FOLLOWUP_STEPS:
        return None

    top = _top_finding(lead)
    if top is None:
        return None
    copy = FINDING_COPY[top["id"]]

    if not isinstance(previous, dict):
        previous = {}

    business = _header_safe(lead.get("business_name") or "") or "your business"
    site = _domain(lead.get("website_url"))

    original_subject = _header_safe(previous.get("subject") or "")
    subject = "Re: " + original_subject if original_subject else _default_followup_subject(business)

    greeting = "Hi again,"

    if step == 2:
        # Short. Points back at the single worst finding again - not a
        # restatement of the whole first email - and offers something
        # concrete: the rest of the list we already measured, not a new claim.
        opener = (
            "Following up on my note about " + site + " - the main thing I "
            "flagged was that " + copy["headline"] + ". " + copy["impact"]
        )
        offer = (
            "Happy to send over the full list of what I found, and roughly "
            "what each one would take to fix, if that's useful."
        )
        close = "Let me know either way."
        paragraphs = [greeting, opener, offer, close]
    else:
        # Step 3: shortest of all, explicitly the last message, and easy to
        # decline - no pressure, no false urgency, just an exit.
        opener = "Last one from me - " + copy["headline"] + " on " + site + "."
        close = (
            "I'll leave it there. If this isn't useful just ignore this "
            "message and I won't follow up again."
        )
        paragraphs = [greeting, opener, close]

    body_text = "\n\n".join(p for p in paragraphs if p)
    body_html = _simple_html(paragraphs)

    return {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "based_on": json.dumps([top["id"]]),
    }


def _coerce_utc(value: Any) -> Optional[datetime]:
    """Normalise a datetime-ish value to timezone-aware UTC, or None.

    Handles the three shapes this value realistically arrives in: an aware
    datetime, a naive datetime (assumed UTC - every timestamp this app writes
    is UTC), or an ISO-8601 string. Anything else, including a string that
    doesn't parse, yields None rather than raising - callers treat that as
    "cannot tell, so do not act."
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def select_due_followups(
    leads_with_drafts: List[Dict[str, Any]],
    *,
    now: datetime,
) -> List[Dict[str, Any]]:
    """Pure scheduling decision: which leads are due a follow-up right now.

    No DB access and no side effects - callers pass in exactly what they
    have loaded, and get back exactly the ones that pass every rule. Every
    rule here is a reason to skip; none is a reason to send. When in doubt,
    the lead is left alone.
    """
    now_dt = _coerce_utc(now)
    if now_dt is None:
        return []

    due: List[Dict[str, Any]] = []

    for item in leads_with_drafts:
        lead = item.get("lead") or {}
        drafts = item.get("drafts") or []
        if not drafts:
            continue

        # Fail safe on any stage we don't explicitly recognise as untouched
        # by a human, including pipeline_stage being missing entirely.
        if lead.get("pipeline_stage") not in SAFE_TO_FOLLOW_UP:
            continue

        # Never stack a new draft on top of one still waiting to be sent.
        if any(d.get("status") == "pending" for d in drafts):
            continue

        latest = drafts[-1]
        if latest.get("status") != "sent":
            continue

        sent_dt = _coerce_utc(latest.get("sent_at"))
        if sent_dt is None:
            continue

        current_step = latest.get("sequence_step") or 1
        try:
            current_step = int(current_step)
        except (TypeError, ValueError):
            continue

        next_step = current_step + 1
        if next_step > MAX_FOLLOWUP_STEP:
            continue
        days_required = FOLLOWUP_STEPS.get(next_step)
        if days_required is None:
            continue

        if now_dt - sent_dt < timedelta(days=days_required):
            continue

        due.append({"lead": lead, "previous": latest, "step": next_step})

    return due
