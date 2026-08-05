"""Recording what happened, for the operators' console.

One rule governs this module: **observing an action must never break it.**

Every call site here sits inside something a customer is doing — running a
search, saving a lead, sending outreach. If recording the event can raise, then
a bug in the audit trail becomes a failed search for a paying user, and the
feature built to give operators visibility becomes the thing taking the product
down. So `record` swallows everything and logs, and the worst case is a missing
line in a report rather than a 500 on a request somebody paid for.

The second rule follows from the first: recording must not commit the caller's
transaction. `record` flushes its own row and leaves the commit to whoever owns
the unit of work, so an event cannot accidentally persist half of a caller's
partial state.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.activity_events import Activity_events

logger = logging.getLogger(__name__)

# Stable machine values. Grouped here rather than typed as literals at each
# call site, because the console counts on them and a typo at one call site
# would silently produce a category nobody reports on.
SEARCH_RUN = "search.run"
SEARCH_FAILED = "search.failed"
LEAD_SAVED = "lead.saved"
LEAD_QUALIFIED = "lead.qualified"
OUTREACH_DRAFTED = "outreach.drafted"
OUTREACH_SENT = "outreach.sent"
OUTREACH_FAILED = "outreach.failed"
AUTOMATION_RUN = "automation.run"
PLAN_CHANGED = "plan.changed"
CREDITS_SPENT = "credits.spent"
USER_SIGNED_IN = "user.signed_in"

# Payload ceiling. A provider error can be a whole HTML page, and an audit row
# is not the place to store one — the console shows a summary, and an
# unbounded blob here would bloat the table that every admin query scans.
MAX_METADATA_CHARS = 4000


async def record(
    db: AsyncSession,
    action: str,
    *,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    workspace_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[Any] = None,
    summary: str = "",
    status: str = "ok",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one event. Never raises, never commits.

    Returns None in every case, including failure, so no caller can come to
    depend on an event id and thereby make the trail load-bearing.
    """
    try:
        payload = "{}"
        if metadata:
            try:
                payload = json.dumps(metadata, default=str)[:MAX_METADATA_CHARS]
            except (TypeError, ValueError):
                # Something unserialisable was passed. The event itself is
                # still worth keeping — losing the whole line because one
                # field would not encode is the wrong trade.
                payload = json.dumps({"note": "metadata was not serialisable"})

        event = Activity_events(
            action=action,
            user_id=str(user_id) if user_id is not None else None,
            user_email=(user_email or "").lower() or None,
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            summary=summary[:500] if summary else "",
            status=status,
            metadata_json=payload,
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        # Flush rather than commit: surface a schema problem here and now,
        # while leaving the caller's transaction boundary alone.
        await db.flush()
    except Exception:
        logger.exception(
            "Could not record activity %r; continuing without it", action
        )
        # The caller's session may now be in a failed state from the flush,
        # and letting that surface later would break their write instead of
        # ours — which is the exact failure this module exists to avoid.
        try:
            await db.rollback()
        except Exception:
            logger.exception("Could not roll back after a failed activity write")


def window_start(days: int) -> datetime:
    """UTC cutoff for a rolling window, e.g. window_start(7) for the last week.

    Rolling rather than calendar-aligned: "the last 7 days" is what an
    operator means when glancing at a dashboard, and a calendar week makes
    Monday morning look like a collapse in usage every week.
    """
    return datetime.now(timezone.utc) - timedelta(days=days)


def start_of_today() -> datetime:
    """Midnight UTC today. Used for the "today" column specifically."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
