"""Support requests: the operators' queue for whoever works on the product.

Two audiences, two authentication schemes, one queue.

The operators reach this through the admin console with their normal session.
Whoever is doing the engineering reaches it with a shared secret, because they
are working from a terminal and have no account in this application — the same
arrangement the scheduled-automation endpoint already uses.

What this is NOT is a live chat. Nobody is sitting in the application waiting
for a message. Requests are read when somebody next sits down to work, and
every piece of copy in the UI says so. Building it to look like a chat would
promise a reply that is not coming, and an operator watching a box for an
answer that never arrives is worse off than one who was told plainly when to
expect it.
"""
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_admin_user
from models.support_tickets import Support_messages, Support_tickets
from schemas.auth import UserResponse
from services import activity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/support", tags=["support"])

OPEN = "open"
IN_PROGRESS = "in_progress"
RESOLVED = "resolved"
CLOSED = "closed"

VALID_STATUSES = {OPEN, IN_PROGRESS, RESOLVED, CLOSED}
VALID_PRIORITIES = {"low", "normal", "high"}

# Statuses that still want somebody's attention. Used by the engineer-side
# pull so a session gets the work rather than the archive.
ACTIVE_STATUSES = (OPEN, IN_PROGRESS)

_SECRET_VAR = "SUPPORT_AGENT_SECRET"


def _verify_agent_secret(provided: Optional[str]) -> None:
    """Constant-time check of the shared secret.

    Unset disables the engineer-side endpoints entirely rather than leaving
    them open. Failing closed matters: these read every request the operators
    have filed, which routinely contain descriptions of what is broken and
    how — a useful map for anybody who should not have it.
    """
    expected = os.environ.get(_SECRET_VAR, "")
    if not expected:
        raise HTTPException(
            status_code=401,
            detail=f"Agent access is disabled: {_SECRET_VAR} is not set.",
        )
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid support agent secret")


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    priority: str = "normal"
    kind: str = ""
    area: str = ""


class MessageCreate(BaseModel):
    body: str = Field(min_length=1)


class StatusUpdate(BaseModel):
    status: str


def _ticket_dict(ticket: Support_tickets, messages: Optional[List[Support_messages]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": ticket.id,
        "title": ticket.title,
        "body": ticket.body,
        "status": ticket.status,
        "priority": ticket.priority,
        "kind": ticket.kind,
        "area": ticket.area,
        "created_by_email": ticket.created_by_email,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
    }
    if messages is not None:
        payload["messages"] = [
            {
                "id": m.id,
                "author_type": m.author_type,
                "author": m.author,
                "body": m.body,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    return payload


async def _messages_for(db: AsyncSession, ticket_id: int) -> List[Support_messages]:
    return list(
        (
            await db.execute(
                select(Support_messages)
                .where(Support_messages.ticket_id == ticket_id)
                .order_by(Support_messages.created_at.asc(), Support_messages.id.asc())
            )
        ).scalars().all()
    )


async def _get_ticket(db: AsyncSession, ticket_id: int) -> Support_tickets:
    ticket = (
        await db.execute(select(Support_tickets).where(Support_tickets.id == ticket_id))
    ).scalars().first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="No such request")
    return ticket


# ---------- Operator side (admin session) ----------

@router.get("", dependencies=[Depends(get_admin_user)])
async def list_tickets(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    conditions = []
    if status == "active":
        conditions.append(Support_tickets.status.in_(ACTIVE_STATUSES))
    elif status:
        conditions.append(Support_tickets.status == status)

    total_stmt = select(func.count()).select_from(Support_tickets)
    if conditions:
        total_stmt = total_stmt.where(and_(*conditions))
    total = int((await db.execute(total_stmt)).scalar() or 0)

    stmt = select(Support_tickets)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    # Newest first, and never by priority: a queue that reorders itself is how
    # everything becomes high priority.
    stmt = stmt.order_by(Support_tickets.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for ticket in rows:
        count = int(
            (
                await db.execute(
                    select(func.count()).select_from(Support_messages)
                    .where(Support_messages.ticket_id == ticket.id)
                )
            ).scalar()
            or 0
        )
        payload = _ticket_dict(ticket)
        payload["message_count"] = count
        items.append(payload)

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "open_count": int(
            (
                await db.execute(
                    select(func.count()).select_from(Support_tickets)
                    .where(Support_tickets.status.in_(ACTIVE_STATUSES))
                )
            ).scalar()
            or 0
        ),
        "agent_access_configured": bool(os.environ.get(_SECRET_VAR, "").strip()),
    }


@router.get("/{ticket_id}", dependencies=[Depends(get_admin_user)])
async def get_ticket(ticket_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    ticket = await _get_ticket(db, ticket_id)
    return _ticket_dict(ticket, await _messages_for(db, ticket_id))


@router.post("", status_code=201)
async def create_ticket(
    data: TicketCreate,
    db: AsyncSession = Depends(get_db),
    admin: UserResponse = Depends(get_admin_user),
) -> Dict[str, Any]:
    if data.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {sorted(VALID_PRIORITIES)}")

    ticket = Support_tickets(
        title=data.title.strip(),
        body=(data.body or "").strip(),
        priority=data.priority,
        kind=(data.kind or "").strip(),
        area=(data.area or "").strip(),
        status=OPEN,
        created_by=admin.id,
        created_by_email=admin.email,
    )
    db.add(ticket)
    await db.flush()

    await activity.record(
        db, "support.raised", user_id=admin.id, user_email=admin.email,
        entity_type="support_ticket", entity_id=ticket.id,
        summary=f"Raised support request: {ticket.title}",
        metadata={"priority": ticket.priority, "area": ticket.area},
    )
    await db.commit()
    await db.refresh(ticket)

    return _ticket_dict(ticket, [])


@router.post("/{ticket_id}/messages", status_code=201)
async def add_message(
    ticket_id: int,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    admin: UserResponse = Depends(get_admin_user),
) -> Dict[str, Any]:
    ticket = await _get_ticket(db, ticket_id)

    message = Support_messages(
        ticket_id=ticket.id,
        author_type="operator",
        author=admin.email or admin.id,
        body=data.body.strip(),
    )
    db.add(message)
    # A reply on something already called done reopens it. Otherwise the
    # follow-up "this is still happening" lands in an archive nobody reads.
    if ticket.status in (RESOLVED, CLOSED):
        ticket.status = OPEN
        ticket.resolved_at = None
    ticket.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return _ticket_dict(ticket, await _messages_for(db, ticket.id))


@router.post("/{ticket_id}/status", dependencies=[Depends(get_admin_user)])
async def set_status(
    ticket_id: int, data: StatusUpdate, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    if data.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")

    ticket = await _get_ticket(db, ticket_id)
    ticket.status = data.status
    ticket.resolved_at = (
        datetime.now(timezone.utc) if data.status in (RESOLVED, CLOSED) else None
    )
    ticket.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return _ticket_dict(ticket, await _messages_for(db, ticket.id))


# ---------- Engineer side (shared secret) ----------
#
# Deliberately not behind get_admin_user: whoever is working on the product is
# doing so from a terminal and has no account here. Same arrangement as the
# scheduled-automation endpoint, and the same failure mode if the secret is
# unset — closed, not open.

@router.get("/agent/queue")
async def agent_queue(
    x_support_secret: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Every request still wanting attention, with its full thread.

    Returns the whole conversation rather than a summary, because the thread
    is usually where the actual requirement is: the title says "export is
    wrong" and the third message says which column.
    """
    _verify_agent_secret(x_support_secret)

    rows = (
        await db.execute(
            select(Support_tickets)
            .where(Support_tickets.status.in_(ACTIVE_STATUSES))
            .order_by(Support_tickets.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    return {
        "items": [_ticket_dict(t, await _messages_for(db, t.id)) for t in rows],
        "count": len(rows),
    }


@router.post("/agent/{ticket_id}/reply")
async def agent_reply(
    ticket_id: int,
    data: MessageCreate,
    x_support_secret: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, description="Optionally set the status with the reply"),
) -> Dict[str, Any]:
    """Post an outcome back onto a request, optionally moving its status."""
    _verify_agent_secret(x_support_secret)

    ticket = await _get_ticket(db, ticket_id)

    db.add(Support_messages(
        ticket_id=ticket.id,
        author_type="engineer",
        author="engineering",
        body=data.body.strip(),
    ))

    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
        ticket.status = status
        ticket.resolved_at = (
            datetime.now(timezone.utc) if status in (RESOLVED, CLOSED) else None
        )

    ticket.updated_at = datetime.now(timezone.utc)

    await activity.record(
        db, "support.replied", user_email="engineering",
        entity_type="support_ticket", entity_id=ticket.id,
        summary=f"Replied to support request: {ticket.title}",
        metadata={"status": ticket.status},
    )
    await db.commit()

    return _ticket_dict(ticket, await _messages_for(db, ticket.id))
