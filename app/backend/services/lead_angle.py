"""Write and store the AI "how to win this lead" note.

One place, two callers: the Qualify pass generates a note automatically for
every lead it measures, and the Notes tab regenerates one on demand. Those two
paths must produce identical rows — same note_type, same replace-don't-stack
behaviour — so the logic lives here rather than being written twice and
drifting.

Everything here degrades to "no note" rather than raising. A note is a
convenience on top of the measurement; failing to write one must never fail
the qualification that paid for the measurement, and must never leave a
half-written row behind.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.lead_notes import Lead_notes
from services import ai_writer

logger = logging.getLogger(__name__)


def parse_findings(raw: Optional[str]) -> List[Dict[str, Any]]:
    """Decode a lead's stored findings, treating anything malformed as none.

    Deliberately collapses "never measured" (NULL) and "measured clean" ("[]")
    into the same empty list, because for this module's one question — is
    there anything to build an angle from? — the answer is no either way.
    Callers that need to tell those apart must not use this.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


async def write_angle_note(db: AsyncSession, lead, user_id: str) -> Optional[str]:
    """Generate an angle note for `lead` and store it, replacing any previous one.

    Returns the note text, or None when no note could honestly be written:
    no measured findings, no configured provider, or a failed model call.

    Does NOT commit. The caller owns the transaction — Qualify batches many
    leads into one commit, and committing here would fragment that into a
    write per lead.
    """
    findings = parse_findings(getattr(lead, "findings", None))
    if not findings:
        return None

    try:
        note = await ai_writer.suggest_angle(
            business_name=lead.business_name,
            category=lead.category or "",
            findings=findings,
            location=lead.location or "",
        )
    except Exception as exc:
        # ai_writer already degrades to None on every failure it anticipates.
        # This catches the ones it does not, because an angle note is never
        # worth failing a paid qualification over.
        logger.warning("Angle note failed for lead %s: %s", lead.id, exc)
        return None

    if not note:
        return None

    # Replace rather than stack. Regenerating after a re-qualify should leave
    # one current note, not a pile of near-identical ones nobody prunes.
    # Scoped by user_id as well as lead_id so this can never delete a row
    # belonging to somebody else even if a lead id were ever reused.
    existing = await db.execute(
        select(Lead_notes).where(
            Lead_notes.lead_id == lead.id,
            Lead_notes.user_id == str(user_id),
            Lead_notes.note_type == ai_writer.AI_ANGLE_NOTE_TYPE,
        )
    )
    for stale in existing.scalars().all():
        await db.delete(stale)

    db.add(
        Lead_notes(
            user_id=str(user_id),
            lead_id=lead.id,
            content=note,
            note_type=ai_writer.AI_ANGLE_NOTE_TYPE,
        )
    )
    return note
