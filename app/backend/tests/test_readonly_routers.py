import pytest

from models.workspaces import Workspaces
from tests.conftest import USER_A_ID

READONLY_PREFIXES = [
    "/api/v1/entities/credit_ledger",
    "/api/v1/entities/search_jobs",
    "/api/v1/entities/workspace_members",
]

# Schema-valid bodies, so the request reaches the handler and the assertion
# tests our 403 rather than FastAPI's request validation.
VALID_CREATE_BODIES = [
    ("/api/v1/entities/credit_ledger", {"workspace_id": 1, "amount": 10, "balance_after": 10, "action": "test"}),
    ("/api/v1/entities/search_jobs", {"user_id": "user-a", "workspace_id": 1}),
    ("/api/v1/entities/workspace_members", {"workspace_id": 1}),
]


async def _seed_workspace(db_session):
    workspace = Workspaces(
        name="Acme", slug="acme", owner_id=USER_A_ID,
        plan="trial", subscription_status="trialing",
        monthly_credits=25, credits_used=0, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


@pytest.mark.parametrize("prefix", READONLY_PREFIXES)
async def test_anonymous_is_rejected(anon_client, prefix):
    assert (await anon_client.get(prefix)).status_code == 401


@pytest.mark.parametrize("prefix,body", VALID_CREATE_BODIES)
async def test_create_is_forbidden(user_a_client, db_session, prefix, body):
    await _seed_workspace(db_session)
    response = await user_a_client.post(prefix, json=body)
    assert response.status_code == 403


@pytest.mark.parametrize("prefix", READONLY_PREFIXES)
async def test_delete_is_forbidden(user_a_client, db_session, prefix):
    await _seed_workspace(db_session)
    assert (await user_a_client.delete(f"{prefix}/1")).status_code == 403
