"""The operators' console.

Everything here is read-only and admin-gated. Read-only is a deliberate
constraint rather than an unfinished state: an admin API that can also mutate
customer data is the most dangerous surface in the application, and nothing an
operator needs for daily visibility requires a write. When something here does
need to change data, it should arrive as a named endpoint with its own test
about who may call it — not as a generic update that happens to be behind the
admin gate.

Every route depends on get_admin_user, which admits either a verified
role=admin token or an address on the ADMIN_EMAILS allowlist. That dependency
is declared on the router itself rather than repeated per route, because the
failure mode of the per-route style is a new endpoint that quietly ships
without it.

These queries read across every tenant by design — that is the point of an
operators' console — which is exactly why the gate matters more here than
anywhere else in the codebase.
"""
import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_admin_user
from models.activity_events import Activity_events
from models.auth import User
from models.leads import Leads
from models.search_jobs import Search_jobs
from models.workspaces import Workspaces
from services import activity
from services.admin_access import admin_access_configured
from services.discovery_provider import (
    active_provider_slug,
    is_discovery_configured,
    is_google_places_configured,
    is_mapbox_configured,
)
from services.entitlements import has_unlimited_credits
from services.pagespeed import is_pagespeed_configured
from services import ai_writer

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(get_admin_user)],
)

# Monthly prices in pence/cents, mirroring routers/payments.py. Duplicated
# rather than imported to avoid a circular import between two routers; the
# revenue view asserts against these, so a drift shows up as a failing test
# rather than a wrong number on a dashboard.
PLAN_PRICES = {"trial": 0, "solo": 2900, "pro": 7900, "agency": 19900}
PLAN_NAMES = {"trial": "Trial", "solo": "Solo", "pro": "Pro", "agency": "Agency"}

MAX_PAGE_SIZE = 200


async def _count(db: AsyncSession, model, *conditions) -> int:
    """COUNT(*) over one model with optional filters."""
    stmt = select(func.count()).select_from(model)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    return int((await db.execute(stmt)).scalar() or 0)


async def _sum(db: AsyncSession, column, *conditions) -> int:
    stmt = select(func.coalesce(func.sum(column), 0))
    if conditions:
        stmt = stmt.where(and_(*conditions))
    return int((await db.execute(stmt)).scalar() or 0)


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Headline numbers for today, the last 7 days and the last 30 days.

    Three windows rather than one because a single number cannot answer the
    question an operator is actually asking. Today alone is noise before
    lunchtime; 30 days alone hides an outage that started this morning.
    """
    today = activity.start_of_today()
    week = activity.window_start(7)
    month = activity.window_start(30)

    async def window(since: Optional[datetime]) -> Dict[str, int]:
        ev = [] if since is None else [Activity_events.created_at >= since]
        lead = [] if since is None else [Leads.created_at >= since]
        usr = [] if since is None else [User.created_at >= since]

        searches = await _count(db, Activity_events, Activity_events.action == activity.SEARCH_RUN, *ev)
        failed = await _count(db, Activity_events, Activity_events.action == activity.SEARCH_FAILED, *ev)
        sent = await _count(db, Activity_events, Activity_events.action == activity.OUTREACH_SENT, *ev)
        leads_found = await _count(db, Leads, *lead)
        # An address is the difference between a lead and a row, so it is
        # tracked as its own number rather than inferred from the lead count.
        with_email = await _count(
            db, Leads, Leads.contact_email.isnot(None), Leads.contact_email != "", *lead
        )
        signups = await _count(db, User, *usr)
        credits = await _sum(
            db,
            Search_jobs.credits_charged,
            *([] if since is None else [Search_jobs.created_at >= since]),
        )

        return {
            "searches": searches,
            "searches_failed": failed,
            "leads_discovered": leads_found,
            "leads_with_email": with_email,
            "outreach_sent": sent,
            "signups": signups,
            "credits_spent": credits,
        }

    total_workspaces = await _count(db, Workspaces)
    total_users = await _count(db, User)
    # "Active" means did something, not merely exists. A count of registered
    # accounts flatters every dashboard it appears on.
    active_7d = int(
        (
            await db.execute(
                select(func.count(func.distinct(Activity_events.user_id))).where(
                    Activity_events.created_at >= week,
                    Activity_events.user_id.isnot(None),
                )
            )
        ).scalar()
        or 0
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "today": await window(today),
        "last_7_days": await window(week),
        "last_30_days": await window(month),
        "all_time": await window(None),
        "totals": {
            "users": total_users,
            "workspaces": total_workspaces,
            "active_users_7d": active_7d,
        },
        "admin_access_configured": admin_access_configured(),
    }


def _activity_filters(
    action: Optional[str], status: Optional[str], user: Optional[str],
    workspace_id: Optional[int], q: Optional[str], days: Optional[int],
) -> List[Any]:
    conditions: List[Any] = []
    if action:
        conditions.append(Activity_events.action == action)
    if status:
        conditions.append(Activity_events.status == status)
    if user:
        needle = f"%{user.lower()}%"
        conditions.append(
            or_(
                func.lower(Activity_events.user_email).like(needle),
                func.lower(Activity_events.user_id).like(needle),
            )
        )
    if workspace_id is not None:
        conditions.append(Activity_events.workspace_id == workspace_id)
    if q:
        needle = f"%{q.lower()}%"
        conditions.append(
            or_(
                func.lower(Activity_events.summary).like(needle),
                func.lower(Activity_events.metadata_json).like(needle),
            )
        )
    if days:
        conditions.append(Activity_events.created_at >= activity.window_start(days))
    return conditions


@router.get("/activity")
async def activity_feed(
    db: AsyncSession = Depends(get_db),
    action: Optional[str] = None,
    status: Optional[str] = None,
    user: Optional[str] = Query(None, description="Match on email or user id"),
    workspace_id: Optional[int] = None,
    q: Optional[str] = Query(None, description="Free text over summary and payload"),
    days: Optional[int] = Query(None, ge=1, le=365),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
) -> Dict[str, Any]:
    """The trail, newest first, with the filters the console offers."""
    conditions = _activity_filters(action, status, user, workspace_id, q, days)

    total = await _count(db, Activity_events, *conditions) if conditions else await _count(db, Activity_events)

    stmt = select(Activity_events)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(Activity_events.created_at.desc(), Activity_events.id.desc())
    stmt = stmt.offset(skip).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    return {
        "items": [_event_dict(row) for row in rows],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


def _event_dict(row: Activity_events) -> Dict[str, Any]:
    try:
        payload = json.loads(row.metadata_json or "{}")
    except (TypeError, ValueError):
        # A row whose payload will not parse is still a real event; showing
        # it without its detail beats hiding that it happened.
        payload = {}

    return {
        "id": row.id,
        "action": row.action,
        "status": row.status,
        "user_id": row.user_id,
        "user_email": row.user_email,
        "workspace_id": row.workspace_id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "summary": row.summary,
        "metadata": payload,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/activity/actions")
async def activity_actions(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Which kinds of event exist, and how many of each in the last 30 days.

    Drives the filter dropdown from the data rather than a hardcoded list, so
    a newly instrumented action appears without a frontend change.
    """
    since = activity.window_start(30)
    rows = (
        await db.execute(
            select(Activity_events.action, func.count().label("count"))
            .where(Activity_events.created_at >= since)
            .group_by(Activity_events.action)
            .order_by(func.count().desc())
        )
    ).all()
    return {"items": [{"action": a, "count": int(c)} for a, c in rows]}


@router.get("/users")
async def users(
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
) -> Dict[str, Any]:
    """Every account, with what it has actually done."""
    conditions = []
    if q:
        needle = f"%{q.lower()}%"
        conditions.append(
            or_(func.lower(User.email).like(needle), func.lower(User.name).like(needle))
        )

    total = await _count(db, User, *conditions)

    stmt = select(User)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(User.created_at.desc().nullslast()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for u in rows:
        leads_count = await _count(db, Leads, Leads.user_id == u.id)
        searches = await _count(
            db, Activity_events,
            Activity_events.user_id == u.id,
            Activity_events.action == activity.SEARCH_RUN,
        )
        last_seen = (
            await db.execute(
                select(func.max(Activity_events.created_at)).where(Activity_events.user_id == u.id)
            )
        ).scalar()
        workspace = (
            await db.execute(
                select(Workspaces).where(Workspaces.owner_id == u.id).order_by(Workspaces.id.asc()).limit(1)
            )
        ).scalars().first()

        items.append({
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "last_activity": last_seen.isoformat() if last_seen else None,
            "leads": leads_count,
            "searches": searches,
            "plan": workspace.plan if workspace else None,
            "workspace_id": workspace.id if workspace else None,
            # Shown so an operator can tell at a glance why one account's
            # numbers do not move the revenue figures.
            "unmetered": has_unlimited_credits(u.email or ""),
        })

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/workspaces")
async def workspaces(
    db: AsyncSession = Depends(get_db),
    plan: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
) -> Dict[str, Any]:
    conditions = [Workspaces.plan == plan] if plan else []
    total = await _count(db, Workspaces, *conditions)

    stmt = select(Workspaces)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(Workspaces.created_at.desc().nullslast()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for w in rows:
        leads_count = await _count(db, Leads, Leads.user_id == w.owner_id)
        items.append({
            "id": w.id,
            "name": w.name,
            "owner_id": w.owner_id,
            "plan": w.plan,
            "plan_name": PLAN_NAMES.get(w.plan or "trial", w.plan),
            "subscription_status": w.subscription_status,
            "monthly_credits": w.monthly_credits,
            "credits_used": w.credits_used,
            "credits_remaining": max(0, (w.monthly_credits or 0) - (w.credits_used or 0)),
            "max_seats": w.max_seats,
            "trial_ends_at": w.trial_ends_at,
            "stripe_customer_id": w.stripe_customer_id,
            "leads": leads_count,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        })

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/revenue")
async def revenue(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Subscription mix and what it is worth per month.

    MRR here is list price times paying workspaces. It is a floor, not an
    accounting figure: it knows nothing about discounts, refunds, failed
    payments or annual billing, and it must not be reported as revenue. It is
    the number that answers "roughly how big is the paying base" — Stripe is
    the source of truth for anything a person would act on financially.
    """
    rows = (
        await db.execute(
            select(Workspaces.plan, func.count().label("count")).group_by(Workspaces.plan)
        )
    ).all()

    by_plan = []
    mrr_pence = 0
    paying = 0
    for plan, count in rows:
        key = plan or "trial"
        price = PLAN_PRICES.get(key, 0)
        count = int(count)
        if price:
            mrr_pence += price * count
            paying += count
        by_plan.append({
            "plan": key,
            "plan_name": PLAN_NAMES.get(key, key),
            "workspaces": count,
            "monthly_price": price / 100,
            "monthly_value": (price * count) / 100,
        })
    by_plan.sort(key=lambda p: p["monthly_price"])

    trialing = await _count(db, Workspaces, Workspaces.subscription_status == "trialing")
    active = await _count(db, Workspaces, Workspaces.subscription_status == "active")
    cancelled = await _count(db, Workspaces, Workspaces.subscription_status == "canceled")
    total_workspaces = await _count(db, Workspaces)

    return {
        "by_plan": by_plan,
        "mrr": mrr_pence / 100,
        "paying_workspaces": paying,
        "total_workspaces": total_workspaces,
        "conversion_rate": round((paying / total_workspaces) * 100, 1) if total_workspaces else 0.0,
        "subscription_status": {
            "trialing": trialing,
            "active": active,
            "canceled": cancelled,
        },
        "mrr_is_estimated": True,
        "mrr_note": (
            "List price times paying workspaces. Ignores discounts, refunds, failed "
            "payments and annual billing. Stripe is the source of truth."
        ),
    }


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """What is configured, and what has been going wrong.

    Providers report configuration rather than reachability. A live probe on
    every dashboard load would spend the operator's API quota to answer a
    question the error counts below already answer better.
    """
    day = activity.window_start(1)
    week = activity.window_start(7)

    recent_failures = (
        await db.execute(
            select(Activity_events)
            .where(Activity_events.status == "failed", Activity_events.created_at >= week)
            .order_by(Activity_events.created_at.desc())
            .limit(25)
        )
    ).scalars().all()

    searches_24h = await _count(
        db, Activity_events,
        Activity_events.action == activity.SEARCH_RUN,
        Activity_events.created_at >= day,
    )
    failed_24h = await _count(
        db, Activity_events,
        Activity_events.action == activity.SEARCH_FAILED,
        Activity_events.created_at >= day,
    )
    attempted = searches_24h + failed_24h

    return {
        "providers": {
            "discovery_configured": is_discovery_configured(),
            "discovery_provider": active_provider_slug(),
            "google_places": is_google_places_configured(),
            "mapbox": is_mapbox_configured(),
            "pagespeed": is_pagespeed_configured(),
            "ai_writer": ai_writer.is_ai_configured(),
            "ai_model": ai_writer.active_model() if ai_writer.is_ai_configured() else None,
            "stripe": bool(os.environ.get("STRIPE_SECRET_KEY", "").strip()),
            "stripe_webhook": bool(os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()),
        },
        "searches_24h": searches_24h,
        "searches_failed_24h": failed_24h,
        "search_failure_rate_24h": round((failed_24h / attempted) * 100, 1) if attempted else 0.0,
        "failures_7d": await _count(
            db, Activity_events, Activity_events.status == "failed", Activity_events.created_at >= week
        ),
        "recent_failures": [_event_dict(row) for row in recent_failures],
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
    }


# ---------- CSV export ----------

def _csv_response(filename: str, headers: List[str], rows: List[List[Any]]) -> StreamingResponse:
    """Stream a CSV with the same safety rules as the leads export.

    Formula-leading values are prefixed, because this data includes business
    names and error text read off third-party websites, and a spreadsheet
    executes =... on open. An operator exporting an audit trail should not be
    running a prospect's payload.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

    def safe(value: Any) -> str:
        if value is None:
            return ""
        text = str(value)
        if text[:1] in ("=", "@", "\t", "\r"):
            return f"'{text}"
        if text[:1] in ("+", "-") and not all(c in "0123456789 ().-+" for c in text):
            return f"'{text}"
        return text

    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe(cell) for cell in row])

    # The BOM keeps Excel from mangling non-ASCII business names.
    payload = "﻿" + buffer.getvalue()
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/activity.csv")
async def export_activity(
    db: AsyncSession = Depends(get_db),
    action: Optional[str] = None,
    status: Optional[str] = None,
    user: Optional[str] = None,
    workspace_id: Optional[int] = None,
    q: Optional[str] = None,
    days: Optional[int] = Query(None, ge=1, le=365),
    limit: int = Query(5000, ge=1, le=50000),
):
    """Export the trail as it is currently filtered.

    The limit is high but finite: an unbounded export of an append-only table
    is a way to run the database out of memory from a URL.
    """
    conditions = _activity_filters(action, status, user, workspace_id, q, days)
    stmt = select(Activity_events)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(Activity_events.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    return _csv_response(
        "bizleads-activity.csv",
        ["When", "Action", "Status", "User", "Workspace", "Entity", "Entity ID", "Summary", "Details"],
        [
            [
                r.created_at.isoformat() if r.created_at else "",
                r.action, r.status, r.user_email or r.user_id or "",
                r.workspace_id or "", r.entity_type or "", r.entity_id or "",
                r.summary or "", r.metadata_json or "",
            ]
            for r in rows
        ],
    )


@router.get("/export/users.csv")
async def export_users(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(User).order_by(User.created_at.desc().nullslast()))).scalars().all()
    out = []
    for u in rows:
        leads_count = await _count(db, Leads, Leads.user_id == u.id)
        workspace = (
            await db.execute(
                select(Workspaces).where(Workspaces.owner_id == u.id).order_by(Workspaces.id.asc()).limit(1)
            )
        ).scalars().first()
        out.append([
            u.email, u.name or "", u.role,
            u.created_at.isoformat() if u.created_at else "",
            u.last_login.isoformat() if u.last_login else "",
            workspace.plan if workspace else "", leads_count,
        ])

    return _csv_response(
        "bizleads-users.csv",
        ["Email", "Name", "Role", "Signed Up", "Last Login", "Plan", "Leads"],
        out,
    )


@router.get("/export/workspaces.csv")
async def export_workspaces(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(Workspaces).order_by(Workspaces.created_at.desc().nullslast()))
    ).scalars().all()

    return _csv_response(
        "bizleads-workspaces.csv",
        ["ID", "Name", "Owner", "Plan", "Status", "Credits Used", "Credits Total",
         "Seats", "Trial Ends", "Stripe Customer", "Created"],
        [
            [
                w.id, w.name, w.owner_id, w.plan, w.subscription_status,
                w.credits_used, w.monthly_credits, w.max_seats, w.trial_ends_at,
                w.stripe_customer_id or "",
                w.created_at.isoformat() if w.created_at else "",
            ]
            for w in rows
        ],
    )
