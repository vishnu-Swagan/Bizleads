import pytest
from fastapi import HTTPException
from sqlalchemy import select

from dependencies.tenancy import EntityPolicy, ensure_workspace_for_user, filter_writes, get_current_workspace
from models.workspaces import Workspaces
from services import account_review
from schemas.auth import UserResponse

WORKSPACE_POLICY = EntityPolicy(
    model=Workspaces,
    scope="user",
    writable=frozenset({"name", "settings_json"}),
    never_return=frozenset({"stripe_customer_id"}),
)


def test_filter_writes_keeps_allowed_fields():
    result = filter_writes({"name": "Acme"}, WORKSPACE_POLICY, strict=True)
    assert result == {"name": "Acme"}


def test_filter_writes_drops_silently_on_create():
    result = filter_writes({"name": "Acme", "plan": "agency"}, WORKSPACE_POLICY, strict=False)
    assert result == {"name": "Acme"}


def test_filter_writes_rejects_privileged_field_on_update():
    with pytest.raises(HTTPException) as exc:
        filter_writes({"plan": "agency"}, WORKSPACE_POLICY, strict=True)
    assert exc.value.status_code == 400
    assert "plan" in exc.value.detail


def test_filter_writes_ignores_none_values():
    result = filter_writes({"name": "Acme", "plan": None}, WORKSPACE_POLICY, strict=True)
    assert result == {"name": "Acme"}


async def test_ensure_workspace_for_user_creates_with_trial_defaults(db_session):
    user = UserResponse(id="user-new", email="new@example.com", role="user")

    workspace = await ensure_workspace_for_user(user, db_session)

    assert workspace.owner_id == "user-new"
    assert workspace.plan == "trial"
    assert workspace.subscription_status == "trialing"
    # No credits at creation. The free allowance is granted by an operator on
    # approval, so creating the workspace with 25 already in it would hand out
    # exactly what the review exists to withhold.
    assert workspace.monthly_credits == 0
    assert workspace.max_seats == 1

    # And the review is opened at the same moment, or nobody would know to
    # grant them.
    approval = await account_review.get_approval(db_session, "user-new")
    assert approval is not None
    assert approval.status == account_review.STATUS_PENDING


async def test_ensure_workspace_for_user_is_idempotent(db_session):
    user = UserResponse(id="user-repeat", email="repeat@example.com", role="user")

    first = await ensure_workspace_for_user(user, db_session)
    second = await ensure_workspace_for_user(user, db_session)

    assert first.id == second.id

    result = await db_session.execute(select(Workspaces).where(Workspaces.owner_id == "user-repeat"))
    assert len(result.scalars().all()) == 1


async def test_get_current_workspace_resolves_existing_workspace(db_session):
    user = UserResponse(id="user-existing", email="existing@example.com", role="user")
    created = await ensure_workspace_for_user(user, db_session)

    resolved = await get_current_workspace(current_user=user, db=db_session)

    assert resolved.id == created.id


async def test_get_current_workspace_raises_404_when_absent(db_session):
    user = UserResponse(id="user-absent", email="absent@example.com", role="user")

    with pytest.raises(HTTPException) as exc:
        await get_current_workspace(current_user=user, db=db_session)

    assert exc.value.status_code == 404


async def test_duplicate_workspaces_resolve_to_lowest_id_without_raising(db_session):
    # Regression test for the race in ensure_workspace_for_user: owner_id has
    # no unique constraint, so two concurrent first requests can both insert.
    # This must fail against scalar_one_or_none(), which raises
    # MultipleResultsFound when more than one row matches.
    user = UserResponse(id="user-dup", email="dup@example.com", role="user")

    older = Workspaces(name="Older", slug="older", owner_id="user-dup", plan="trial")
    db_session.add(older)
    await db_session.commit()
    await db_session.refresh(older)

    newer = Workspaces(name="Newer", slug="newer", owner_id="user-dup", plan="trial")
    db_session.add(newer)
    await db_session.commit()
    await db_session.refresh(newer)

    assert older.id < newer.id

    via_ensure = await ensure_workspace_for_user(user, db_session)
    via_get_current = await get_current_workspace(current_user=user, db=db_session)

    assert via_ensure.id == older.id
    assert via_get_current.id == older.id
