"""BizLeads Automations Router — scheduled Discover searches that draft outreach.

An Automations row is a saved Discover search plus a schedule. Running it
(POST /{id}/run, or in bulk via POST /run-due) drives services/automation_runner.py,
which reuses the same search/qualify/compose logic the manual Discover and
Outreach pages use. It never sends email on its own — see
services/outreach_composer.py and models/automations.py for why.

Every route is scoped to the caller: automations are looked up by
(id, user_id) together, so one user can neither see nor run another's.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.automations import Automations
from schemas.auth import UserResponse
from services.automation_runner import run_automation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])

VALID_SCHEDULES = {"manual", "daily", "weekly"}


def _initial_next_run_at(schedule: str) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    if schedule == "daily":
        return now + timedelta(days=1)
    if schedule == "weekly":
        return now + timedelta(days=7)
    return None


def _validate_schedule(schedule: Optional[str]) -> None:
    if schedule is not None and schedule not in VALID_SCHEDULES:
        raise HTTPException(
            status_code=400,
            detail=f"schedule must be one of {sorted(VALID_SCHEDULES)}, got {schedule!r}",
        )


def _validate_max_leads(value: Optional[int]) -> None:
    if value is not None and value < 1:
        raise HTTPException(status_code=400, detail="max_leads_per_run must be at least 1")


# ---------- Pydantic Schemas ----------
# Every nullable field is declared Optional[...] rather than `x: str = None` —
# in Pydantic v2 a bare `= None` default does not widen the type, so an
# explicit `null` in the request body is rejected with 422 even though
# omitting the key works. See tests/test_save_lead_contract.py for the bug
# this codebase already hit once from getting this wrong.
class AutomationCreate(BaseModel):
    name: str
    city: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    query: Optional[str] = None
    website_state: Optional[str] = "all"
    auto_qualify: bool = True
    auto_draft: bool = True
    max_leads_per_run: int = Field(default=10, ge=1)
    schedule: str = "manual"
    enabled: bool = True


class AutomationUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    query: Optional[str] = None
    website_state: Optional[str] = None
    auto_qualify: Optional[bool] = None
    auto_draft: Optional[bool] = None
    max_leads_per_run: Optional[int] = None
    schedule: Optional[str] = None
    enabled: Optional[bool] = None


class AutomationResponse(BaseModel):
    id: int
    user_id: str
    name: str
    city: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    query: Optional[str] = None
    website_state: Optional[str] = None
    auto_qualify: bool
    auto_draft: bool
    max_leads_per_run: int
    schedule: str
    enabled: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_run_summary: Optional[str] = None
    last_run_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AutomationListResponse(BaseModel):
    items: List[AutomationResponse]
    total: int


class RunDueResponse(BaseModel):
    ran: int
    results: List[dict]


# ---------- Helpers ----------
async def _get_owned(db: AsyncSession, automation_id: int, user_id: str) -> Automations:
    result = await db.execute(
        select(Automations).where(Automations.id == automation_id, Automations.user_id == user_id)
    )
    automation = result.scalar_one_or_none()
    if automation is None:
        # Same not-found-not-forbidden shape as the rest of the app: a
        # request for someone else's automation looks identical to a request
        # for one that never existed.
        raise HTTPException(status_code=404, detail="Automation not found")
    return automation


# ---------- Routes ----------
@router.get("", response_model=AutomationListResponse)
async def list_automations(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Automations).where(Automations.user_id == current_user.id).order_by(Automations.id.desc())
    )
    items = result.scalars().all()
    return {"items": items, "total": len(items)}


@router.post("", response_model=AutomationResponse, status_code=201)
async def create_automation(
    data: AutomationCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_schedule(data.schedule)

    automation = Automations(
        user_id=current_user.id,
        name=data.name,
        city=data.city,
        country=data.country,
        category=data.category,
        query=data.query,
        website_state=data.website_state or "all",
        auto_qualify=data.auto_qualify,
        auto_draft=data.auto_draft,
        max_leads_per_run=data.max_leads_per_run,
        schedule=data.schedule,
        enabled=data.enabled,
        next_run_at=_initial_next_run_at(data.schedule),
    )
    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    return automation


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    automation_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned(db, automation_id, current_user.id)


@router.patch("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    automation_id: int,
    data: AutomationUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    automation = await _get_owned(db, automation_id, current_user.id)

    # exclude_unset, not exclude_none: a field the client omitted must be left
    # alone, but one sent explicitly as null (e.g. clearing `query`) must take
    # effect. Collapsing those two cases — as a plain `if v is not None`
    # filter would — makes a field impossible to clear via PATCH.
    updates = data.model_dump(exclude_unset=True)
    if "schedule" in updates:
        _validate_schedule(updates["schedule"])
    if "max_leads_per_run" in updates:
        _validate_max_leads(updates["max_leads_per_run"])

    schedule_changed = "schedule" in updates and updates["schedule"] != automation.schedule

    for key, value in updates.items():
        setattr(automation, key, value)

    # A schedule change re-anchors the countdown from now, rather than
    # leaving whatever next_run_at the old schedule happened to compute.
    if schedule_changed:
        automation.next_run_at = _initial_next_run_at(automation.schedule)

    await db.commit()
    await db.refresh(automation)
    return automation


@router.delete("/{automation_id}")
async def delete_automation(
    automation_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    automation = await _get_owned(db, automation_id, current_user.id)
    await db.delete(automation)
    await db.commit()
    return {"message": "Automation deleted", "id": automation_id}


@router.post("/{automation_id}/run")
async def run_automation_now(
    automation_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    automation = await _get_owned(db, automation_id, current_user.id)
    return await run_automation(db, automation, current_user.id)


@router.post("/run-due", response_model=RunDueResponse)
async def run_due_automations(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run every enabled automation of the caller's whose next_run_at is due.

    Scoped to the calling user only — this is meant to be hit by that user's
    own scheduler/cron trigger, not a global sweep, so it never touches rows
    belonging to anyone else.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Automations).where(
            Automations.user_id == current_user.id,
            Automations.enabled.is_(True),
            Automations.next_run_at.isnot(None),
            Automations.next_run_at <= now,
        )
    )
    due = result.scalars().all()

    results = []
    for automation in due:
        outcome = await run_automation(db, automation, current_user.id)
        results.append(outcome)

    return {"ran": len(results), "results": results}
