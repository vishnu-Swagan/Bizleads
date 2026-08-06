"""Tenant scoping and write-policy enforcement for generated entity routers.

Every entity router declares one EntityPolicy and routes it through these
helpers. Adding a route without a policy is the bug class this module exists
to prevent, so keep the declaration at module scope where it is visible.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, FrozenSet, Literal, Optional, Type

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.workspaces import Workspaces
from services import account_review
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityPolicy:
    """Declares how one entity table is scoped and what a client may write."""

    model: Type[Any]
    scope: Literal["user", "workspace"]
    writable: FrozenSet[str]
    never_return: FrozenSet[str] = field(default_factory=frozenset)
    allow_create: bool = True
    allow_delete: bool = True

    @property
    def scope_column(self) -> str:
        return "user_id" if self.scope == "user" else "workspace_id"


def filter_writes(payload: Dict[str, Any], policy: EntityPolicy, *, strict: bool) -> Dict[str, Any]:
    """Remove fields the client may not write.

    strict=False (create): silently drop disallowed keys.
    strict=True (update): reject with 400 naming the field, so a deliberate
    privilege-escalation attempt is reported rather than quietly ignored.

    None values are always dropped without error: partial-update payloads carry
    None for every unset field, which is not an attempt to write it.
    """
    cleaned: Dict[str, Any] = {}
    rejected = []

    for key, value in payload.items():
        if value is None:
            continue
        if key in policy.writable:
            cleaned[key] = value
        elif strict:
            rejected.append(key)

    if rejected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field(s) not writable by client: {', '.join(sorted(rejected))}",
        )

    return cleaned


def trial_ended_at(workspace: Workspaces) -> Optional[datetime]:
    """When this workspace's trial expired, or None if it has not.

    None covers four distinct situations that all mean "do not treat this as
    an expired trial": the workspace is on a paid plan, its subscription is no
    longer `trialing`, no end date was ever recorded, or the recorded date is
    unparseable.

    The last two fail OPEN deliberately. This function gates the features the
    product exists to provide, so a blank or corrupt timestamp must degrade to
    "keep working" rather than locking a paying-or-soon-to-pay customer out of
    an account over a bad string. A trial that never ends is a revenue
    problem; a trial that ends wrongly is a support incident and a refund.
    """
    if (workspace.plan or "") != "trial":
        return None
    # An empty status is what pre-existing rows carry, and those are trials.
    if (workspace.subscription_status or "trialing") != "trialing":
        return None

    raw = (workspace.trial_ends_at or "").strip()
    if not raw:
        return None

    try:
        ends = datetime.fromisoformat(raw)
    except ValueError:
        logger.warning(
            "Workspace %s has an unparseable trial_ends_at (%r); treating the "
            "trial as open rather than locking the account out",
            workspace.id, raw,
        )
        return None

    # Rows written before the tz-aware default carry naive timestamps. They
    # were always UTC, so read them as such rather than letting the comparison
    # raise.
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)

    return ends if datetime.now(timezone.utc) >= ends else None


def trial_expired(workspace: Workspaces) -> bool:
    """Whether this workspace's trial has run out. See trial_ended_at."""
    return trial_ended_at(workspace) is not None


async def ensure_workspace_for_user(user: UserResponse, db: AsyncSession) -> Workspaces:
    """Resolve the user's workspace, creating a trial one if absent.

    The only sanctioned creation point. Called from GET /billing/usage and
    POST /discover/run, and from POST /billing/verify-payment to resolve the
    workspace being upgraded, so all call sites behave identically.

    owner_id has no unique constraint (models/workspaces.py only indexes it),
    so two concurrent first requests from the same user can both find nothing
    and both insert, leaving a genuine duplicate row. Ordering by id and
    taking the first result tolerates that duplicate deterministically
    (oldest wins) instead of letting scalar_one_or_none() raise
    MultipleResultsFound and 500 every subsequent request from that user.
    This is a mitigation, not a cure - the real fix is a unique index on
    owner_id, which needs an Alembic migration and belongs with the
    Foundation-tier migration work, not here.
    """
    result = await db.execute(
        select(Workspaces).where(Workspaces.owner_id == user.id).order_by(Workspaces.id.asc()).limit(1)
    )
    workspace = result.scalars().first()
    if workspace:
        return workspace

    now = datetime.utcnow()
    workspace = Workspaces(
        name=f"{user.email or 'User'}'s Workspace",
        slug=user.id[:8],
        owner_id=user.id,
        plan="trial",
        subscription_status="trialing",
        # No credits until an operator grants them. The free allowance is now
        # something a person decides to give, so creating the workspace with
        # 25 already in it would hand out exactly what the review exists to
        # withhold. account_review.approve() sets this on approval.
        monthly_credits=0,
        credits_used=0,
        max_seats=1,
        trial_ends_at=(now + timedelta(days=7)).isoformat(),
        credits_reset_at=(now + timedelta(days=30)).isoformat(),
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)

    # Opened only for workspaces created from here on. Accounts that already
    # existed never get a row and stay allowed — see account_review.
    await account_review.open_pending(
        db, user_id=user.id, email=user.email, workspace_id=workspace.id
    )
    await db.commit()
    return workspace


async def get_current_workspace(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspaces:
    """Resolve the caller's workspace. Never creates; 404 when absent.

    Same duplicate-tolerance as ensure_workspace_for_user: owner_id is
    indexed but not unique, so this takes the lowest-id row deterministically
    rather than raising MultipleResultsFound if a duplicate ever exists. A
    unique index on owner_id (Foundation-tier migration) is the real fix.
    """
    result = await db.execute(
        select(Workspaces).where(Workspaces.owner_id == current_user.id).order_by(Workspaces.id.asc()).limit(1)
    )
    workspace = result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No workspace found for this account")
    return workspace
