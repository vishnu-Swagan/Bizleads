"""Tenant scoping and write-policy enforcement for generated entity routers.

Every entity router declares one EntityPolicy and routes it through these
helpers. Adding a route without a policy is the bug class this module exists
to prevent, so keep the declaration at module scope where it is visible.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, FrozenSet, Literal, Type

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.workspaces import Workspaces
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


async def ensure_workspace_for_user(user: UserResponse, db: AsyncSession) -> Workspaces:
    """Resolve the user's workspace, creating a trial one if absent.

    The only sanctioned creation point. Called from GET /billing/usage and
    POST /discover/run so the three previously-divergent copies of this logic
    behave identically.
    """
    result = await db.execute(select(Workspaces).where(Workspaces.owner_id == user.id))
    workspace = result.scalar_one_or_none()
    if workspace:
        return workspace

    now = datetime.utcnow()
    workspace = Workspaces(
        name=f"{user.email or 'User'}'s Workspace",
        slug=user.id[:8],
        owner_id=user.id,
        plan="trial",
        subscription_status="trialing",
        monthly_credits=25,
        credits_used=0,
        max_seats=1,
        trial_ends_at=(now + timedelta(days=7)).isoformat(),
        credits_reset_at=(now + timedelta(days=30)).isoformat(),
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def get_current_workspace(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspaces:
    """Resolve the caller's workspace. Never creates; 404 when absent."""
    result = await db.execute(select(Workspaces).where(Workspaces.owner_id == current_user.id))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No workspace found for this account")
    return workspace
