from models.leads import Leads
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID, USER_B_ID


async def _seed_lead(db_session, owner_id):
    lead = Leads(
        user_id=owner_id, business_name="Acme Cafe", category="Cafe",
        location="Leeds", country="United Kingdom",
        contact_email="owner@acme.test", contact_phone="+44 113 000 0000",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


async def test_user_b_cannot_read_user_a_lead(user_a_client, user_b_client, db_session):
    lead = await _seed_lead(db_session, USER_A_ID)

    mine = await user_a_client.get(f"/api/v1/entities/leads/{lead.id}")
    assert mine.status_code == 200

    theirs = await user_b_client.get(f"/api/v1/entities/leads/{lead.id}")
    assert theirs.status_code == 404
    assert "owner@acme.test" not in theirs.text


async def test_user_b_cannot_update_user_a_lead(user_b_client, db_session):
    lead = await _seed_lead(db_session, USER_A_ID)
    response = await user_b_client.put(
        f"/api/v1/entities/leads/{lead.id}", json={"business_name": "Hijacked"}
    )
    assert response.status_code == 404


async def test_user_b_cannot_delete_user_a_lead(user_b_client, db_session):
    lead = await _seed_lead(db_session, USER_A_ID)
    assert (await user_b_client.delete(f"/api/v1/entities/leads/{lead.id}")).status_code == 404


async def test_lead_list_excludes_other_tenants(user_a_client, user_b_client, db_session):
    await _seed_lead(db_session, USER_A_ID)
    await _seed_lead(db_session, USER_B_ID)

    listed = await user_a_client.get("/api/v1/entities/leads")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert all(item["user_id"] == USER_A_ID for item in items)


async def test_user_b_cannot_read_user_a_workspace(user_a_client, user_b_client, db_session):
    workspace = Workspaces(
        name="A Corp", slug="acorp", owner_id=USER_A_ID,
        plan="agency", subscription_status="active",
        monthly_credits=5000, credits_used=0, max_seats=10,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)

    assert (await user_b_client.get(f"/api/v1/entities/workspaces/{workspace.id}")).status_code == 404


async def test_user_b_cannot_update_user_a_workspace(user_b_client, db_session):
    # Task 4 review finding: GET was covered but PUT was not. A workspace
    # scoped by owner_id must reject a cross-tenant write with the same 404
    # (never a 403, which would confirm the row exists) as the read path.
    workspace = Workspaces(
        name="A Corp", slug="acorp", owner_id=USER_A_ID,
        plan="agency", subscription_status="active",
        monthly_credits=5000, credits_used=0, max_seats=10,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)

    response = await user_b_client.put(
        f"/api/v1/entities/workspaces/{workspace.id}", json={"name": "Hijacked"}
    )
    assert response.status_code == 404
