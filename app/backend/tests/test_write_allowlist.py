import pytest
from sqlalchemy import select

from models.workspaces import Workspaces
from tests.conftest import USER_A_ID

PRIVILEGED_FIELDS = ["plan", "monthly_credits", "subscription_status", "max_seats"]


async def _seed_workspace(db_session, owner_id=USER_A_ID):
    workspace = Workspaces(
        name="Acme", slug="acme", owner_id=owner_id,
        plan="trial", subscription_status="trialing",
        monthly_credits=25, credits_used=0, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


async def test_anonymous_cannot_list_workspaces(anon_client):
    response = await anon_client.get("/api/v1/entities/workspaces")
    assert response.status_code == 401


async def test_owner_can_rename_own_workspace(user_a_client, db_session):
    workspace = await _seed_workspace(db_session)
    response = await user_a_client.put(
        f"/api/v1/entities/workspaces/{workspace.id}", json={"name": "Renamed"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


@pytest.mark.parametrize("field,value", [
    ("plan", "agency"),
    ("monthly_credits", 999999),
    ("subscription_status", "active"),
    ("max_seats", 100),
])
async def test_privileged_fields_are_rejected(user_a_client, db_session, field, value):
    workspace = await _seed_workspace(db_session)
    response = await user_a_client.put(
        f"/api/v1/entities/workspaces/{workspace.id}", json={field: value}
    )
    assert response.status_code == 400
    assert field in response.json()["detail"]

    refreshed = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert getattr(refreshed, field) != value, f"{field} was mutated despite 400"
