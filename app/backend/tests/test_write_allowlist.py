import pytest
from sqlalchemy import select

from models.provider_connections import Provider_connections
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID, USER_B_ID

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


# ---------- provider_connections ----------

async def test_config_json_is_never_returned(user_a_client, db_session):
    workspace = await _seed_workspace(db_session)
    connection = Provider_connections(
        workspace_id=workspace.id,
        provider_type="discovery",
        provider_name="mapbox",
        status="connected",
        config_json='{"token": "secret-value"}',
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)

    listed = await user_a_client.get("/api/v1/entities/provider_connections")
    assert listed.status_code == 200
    assert "secret-value" not in listed.text

    fetched = await user_a_client.get(f"/api/v1/entities/provider_connections/{connection.id}")
    assert fetched.status_code == 200
    assert "secret-value" not in fetched.text


async def test_config_json_is_still_writable(user_a_client, db_session):
    # config_json is write-only, not entirely blocked: a future integrations
    # settings page needs to set it, so PUT must still accept it - it just
    # never comes back in a response body.
    workspace = await _seed_workspace(db_session)
    connection = Provider_connections(
        workspace_id=workspace.id, provider_type="discovery", provider_name="mapbox",
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)

    response = await user_a_client.put(
        f"/api/v1/entities/provider_connections/{connection.id}",
        json={"config_json": '{"token": "new-value"}'},
    )
    assert response.status_code == 200
    assert "new-value" not in response.text

    refreshed = (await db_session.execute(
        select(Provider_connections).where(Provider_connections.id == connection.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert refreshed.config_json == '{"token": "new-value"}'


async def test_provider_connections_anonymous_is_rejected(anon_client):
    assert (await anon_client.get("/api/v1/entities/provider_connections")).status_code == 401
    assert (await anon_client.get("/api/v1/entities/provider_connections/1")).status_code == 401
    assert (await anon_client.post("/api/v1/entities/provider_connections", json={})).status_code == 401
    assert (await anon_client.put("/api/v1/entities/provider_connections/1", json={})).status_code == 401
    assert (await anon_client.delete("/api/v1/entities/provider_connections/1")).status_code == 401


@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/entities/provider_connections/batch"),
    ("put", "/api/v1/entities/provider_connections/batch"),
    ("delete", "/api/v1/entities/provider_connections/batch"),
])
async def test_provider_connections_batch_is_forbidden(user_a_client, method, path):
    body = {"ids": []} if method == "delete" else {"items": []}
    response = await user_a_client.request(method.upper(), path, json=body)
    assert response.status_code == 403


@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/entities/provider_connections/batch"),
    ("put", "/api/v1/entities/provider_connections/batch"),
    ("delete", "/api/v1/entities/provider_connections/batch"),
])
async def test_provider_connections_batch_requires_auth_before_403(anon_client, method, path):
    # Batch is 403 for an authenticated caller and 401 for an anonymous one:
    # the auth dependency must run before the hardcoded rejection.
    body = {"ids": []} if method == "delete" else {"items": []}
    response = await anon_client.request(method.upper(), path, json=body)
    assert response.status_code == 401


async def test_provider_connections_cross_tenant_read_is_404(user_a_client, user_b_client, db_session):
    workspace_a = await _seed_workspace(db_session, owner_id=USER_A_ID)
    await _seed_workspace(db_session, owner_id=USER_B_ID)
    connection = Provider_connections(
        workspace_id=workspace_a.id, provider_type="discovery", provider_name="mapbox",
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)

    response = await user_b_client.get(f"/api/v1/entities/provider_connections/{connection.id}")
    assert response.status_code == 404


async def test_provider_connections_cross_tenant_write_is_404(user_a_client, user_b_client, db_session):
    workspace_a = await _seed_workspace(db_session, owner_id=USER_A_ID)
    await _seed_workspace(db_session, owner_id=USER_B_ID)
    connection = Provider_connections(
        workspace_id=workspace_a.id, provider_type="discovery", provider_name="mapbox",
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)

    put_response = await user_b_client.put(
        f"/api/v1/entities/provider_connections/{connection.id}", json={"provider_name": "hijacked"}
    )
    assert put_response.status_code == 404

    delete_response = await user_b_client.delete(f"/api/v1/entities/provider_connections/{connection.id}")
    assert delete_response.status_code == 404

    refreshed = (await db_session.execute(
        select(Provider_connections).where(Provider_connections.id == connection.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert refreshed.provider_name == "mapbox", "cross-tenant write mutated the row despite the 404"


async def test_provider_connections_update_rejects_unwritable_field(user_a_client, db_session):
    workspace = await _seed_workspace(db_session)
    connection = Provider_connections(
        workspace_id=workspace.id, provider_type="discovery", provider_name="mapbox",
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)

    response = await user_a_client.put(
        f"/api/v1/entities/provider_connections/{connection.id}", json={"error_count": 999}
    )
    assert response.status_code == 400
    assert "error_count" in response.json()["detail"]


async def test_provider_connections_create_silently_drops_unwritable_field(user_a_client, db_session):
    await _seed_workspace(db_session)
    response = await user_a_client.post(
        "/api/v1/entities/provider_connections",
        json={
            "workspace_id": 999999,  # not in policy.writable - must not smuggle a foreign workspace
            "provider_type": "discovery",
            "provider_name": "mapbox",
            "error_count": 5,  # not in policy.writable either
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["workspace_id"] != 999999
    assert body.get("error_count") in (None, 0)


# ---------- offer_profiles ----------

async def test_offer_profiles_anonymous_is_rejected(anon_client):
    assert (await anon_client.get("/api/v1/entities/offer_profiles")).status_code == 401
    assert (await anon_client.get("/api/v1/entities/offer_profiles/1")).status_code == 401
    assert (await anon_client.post("/api/v1/entities/offer_profiles", json={})).status_code == 401
    assert (await anon_client.put("/api/v1/entities/offer_profiles/1", json={})).status_code == 401
    assert (await anon_client.delete("/api/v1/entities/offer_profiles/1")).status_code == 401


@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/entities/offer_profiles/batch"),
    ("put", "/api/v1/entities/offer_profiles/batch"),
    ("delete", "/api/v1/entities/offer_profiles/batch"),
])
async def test_offer_profiles_batch_is_forbidden(user_a_client, method, path):
    body = {"ids": []} if method == "delete" else {"items": []}
    response = await user_a_client.request(method.upper(), path, json=body)
    assert response.status_code == 403


@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/entities/offer_profiles/batch"),
    ("put", "/api/v1/entities/offer_profiles/batch"),
    ("delete", "/api/v1/entities/offer_profiles/batch"),
])
async def test_offer_profiles_batch_requires_auth_before_403(anon_client, method, path):
    body = {"ids": []} if method == "delete" else {"items": []}
    response = await anon_client.request(method.upper(), path, json=body)
    assert response.status_code == 401


async def test_offer_profiles_cross_tenant_read_is_404(user_a_client, user_b_client, db_session):
    workspace_a = await _seed_workspace(db_session, owner_id=USER_A_ID)
    await _seed_workspace(db_session, owner_id=USER_B_ID)
    create_response = await user_a_client.post(
        "/api/v1/entities/offer_profiles", json={"workspace_id": workspace_a.id, "services": "seo"}
    )
    assert create_response.status_code == 201
    profile_id = create_response.json()["id"]

    response = await user_b_client.get(f"/api/v1/entities/offer_profiles/{profile_id}")
    assert response.status_code == 404


async def test_offer_profiles_update_cannot_move_workspace(user_a_client, db_session):
    workspace_a = await _seed_workspace(db_session, owner_id=USER_A_ID)
    other_workspace = await _seed_workspace(db_session, owner_id=USER_B_ID)
    create_response = await user_a_client.post(
        "/api/v1/entities/offer_profiles", json={"workspace_id": workspace_a.id, "services": "seo"}
    )
    assert create_response.status_code == 201
    profile_id = create_response.json()["id"]

    response = await user_a_client.put(
        f"/api/v1/entities/offer_profiles/{profile_id}",
        json={"workspace_id": other_workspace.id, "services": "ppc"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == workspace_a.id, "workspace_id must be immovable via PUT"
    assert body["services"] == "ppc"
