"""Cross-tenant isolation tests for the five workspace_id-scoped routers.

Kept separate from test_tenant_isolation.py (which covers the two user_id /
owner_id-scoped routers, leads and workspaces) because these five need a
different seeding shape: two workspaces owned by two different users, then a
row in each, rather than a single owner_id column on the row itself.

get_current_workspace (dependencies/tenancy.py) resolves "the caller's
workspace" purely from the authenticated user's own owner_id - it never looks
at anything in the request path. So the cross-tenant scenario here is not
"user B guesses user A's workspace_id" (the routers don't even accept one);
it's "user B, resolved into their own workspace, requests a row that belongs
to user A's workspace" - and the router's job is to compare the row's
workspace_id against the caller's own workspace.id and 404 on mismatch.

Covers three findings deferred from earlier task reviews:
  - Task 5 review: credit_ledger, search_jobs, workspace_members had no
    committed cross-tenant coverage (written once, confirmed passing, then
    deleted before commit). Each gets a GET /{id} 404 test plus a GET ""
    list-exclusion test that asserts on content, not just status.
  - Task 6 review: offer_profiles had read-only cross-tenant coverage; PUT
    and DELETE cross-tenant 404 tests were missing.
  - Task 6 review: provider_connections already has cross-tenant read/write
    404 coverage (tests/test_write_allowlist.py) - not duplicated here - but
    lacked a test that config_json specifically never appears in a
    cross-tenant response body.
"""
from sqlalchemy import select

from models.credit_ledger import Credit_ledger
from models.offer_profiles import Offer_profiles
from models.provider_connections import Provider_connections
from models.search_jobs import Search_jobs
from models.workspace_members import Workspace_members
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID, USER_B_ID


async def _seed_workspace(db_session, owner_id, slug):
    workspace = Workspaces(
        name="Acme", slug=slug, owner_id=owner_id,
        plan="trial", subscription_status="trialing",
        monthly_credits=25, credits_used=0, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


async def _seed_two_workspaces(db_session):
    workspace_a = await _seed_workspace(db_session, USER_A_ID, "a-corp")
    workspace_b = await _seed_workspace(db_session, USER_B_ID, "b-corp")
    return workspace_a, workspace_b


# ---------- credit_ledger ----------

async def test_credit_ledger_cross_tenant_read_is_404(user_a_client, user_b_client, db_session):
    workspace_a, _workspace_b = await _seed_two_workspaces(db_session)
    row = Credit_ledger(
        workspace_id=workspace_a.id, amount=500, balance_after=500,
        action="credit", description="owner-a-confidential-payout",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    mine = await user_a_client.get(f"/api/v1/entities/credit_ledger/{row.id}")
    assert mine.status_code == 200

    theirs = await user_b_client.get(f"/api/v1/entities/credit_ledger/{row.id}")
    assert theirs.status_code == 404
    assert "owner-a-confidential-payout" not in theirs.text


async def test_credit_ledger_list_excludes_other_tenants(user_a_client, user_b_client, db_session):
    workspace_a, workspace_b = await _seed_two_workspaces(db_session)
    row_a = Credit_ledger(
        workspace_id=workspace_a.id, amount=500, balance_after=500,
        action="credit", description="owner-a-row",
    )
    row_b = Credit_ledger(
        workspace_id=workspace_b.id, amount=750, balance_after=750,
        action="credit", description="owner-b-row",
    )
    db_session.add_all([row_a, row_b])
    await db_session.commit()
    await db_session.refresh(row_a)
    await db_session.refresh(row_b)

    listed = await user_b_client.get("/api/v1/entities/credit_ledger")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == row_b.id
    assert all(item["workspace_id"] == workspace_b.id for item in items)
    assert "owner-a-row" not in listed.text


# ---------- search_jobs ----------

async def test_search_jobs_cross_tenant_read_is_404(user_a_client, user_b_client, db_session):
    workspace_a, _workspace_b = await _seed_two_workspaces(db_session)
    job = Search_jobs(
        user_id=USER_A_ID, workspace_id=workspace_a.id, status="failed",
        error_message="owner-a-confidential-error",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    mine = await user_a_client.get(f"/api/v1/entities/search_jobs/{job.id}")
    assert mine.status_code == 200

    theirs = await user_b_client.get(f"/api/v1/entities/search_jobs/{job.id}")
    assert theirs.status_code == 404
    assert "owner-a-confidential-error" not in theirs.text


async def test_search_jobs_list_excludes_other_tenants(user_a_client, user_b_client, db_session):
    workspace_a, workspace_b = await _seed_two_workspaces(db_session)
    job_a = Search_jobs(
        user_id=USER_A_ID, workspace_id=workspace_a.id, status="queued",
        error_message="owner-a-job",
    )
    job_b = Search_jobs(
        user_id=USER_B_ID, workspace_id=workspace_b.id, status="queued",
        error_message="owner-b-job",
    )
    db_session.add_all([job_a, job_b])
    await db_session.commit()
    await db_session.refresh(job_a)
    await db_session.refresh(job_b)

    listed = await user_b_client.get("/api/v1/entities/search_jobs")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == job_b.id
    assert all(item["workspace_id"] == workspace_b.id for item in items)
    assert "owner-a-job" not in listed.text


# ---------- workspace_members ----------

async def test_workspace_members_cross_tenant_read_is_404(user_a_client, user_b_client, db_session):
    workspace_a, _workspace_b = await _seed_two_workspaces(db_session)
    member = Workspace_members(
        workspace_id=workspace_a.id, role="member",
        invited_email="owner-a-secret@acme.test", status="active",
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)

    mine = await user_a_client.get(f"/api/v1/entities/workspace_members/{member.id}")
    assert mine.status_code == 200

    theirs = await user_b_client.get(f"/api/v1/entities/workspace_members/{member.id}")
    assert theirs.status_code == 404
    assert "owner-a-secret@acme.test" not in theirs.text


async def test_workspace_members_list_excludes_other_tenants(user_a_client, user_b_client, db_session):
    workspace_a, workspace_b = await _seed_two_workspaces(db_session)
    member_a = Workspace_members(
        workspace_id=workspace_a.id, invited_email="owner-a-member@acme.test",
    )
    member_b = Workspace_members(
        workspace_id=workspace_b.id, invited_email="owner-b-member@acme.test",
    )
    db_session.add_all([member_a, member_b])
    await db_session.commit()
    await db_session.refresh(member_a)
    await db_session.refresh(member_b)

    listed = await user_b_client.get("/api/v1/entities/workspace_members")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == member_b.id
    assert all(item["workspace_id"] == workspace_b.id for item in items)
    assert "owner-a-member@acme.test" not in listed.text


# ---------- provider_connections ----------
# Cross-tenant read/write 404s are already covered by
# test_provider_connections_cross_tenant_read_is_404 and
# test_provider_connections_cross_tenant_write_is_404 in
# tests/test_write_allowlist.py - not duplicated here. This adds the missing
# angle: config_json must not leak into a cross-tenant response either.

async def test_provider_connections_config_json_absent_from_cross_tenant_response(
    user_a_client, user_b_client, db_session
):
    workspace_a, _workspace_b = await _seed_two_workspaces(db_session)
    connection = Provider_connections(
        workspace_id=workspace_a.id, provider_type="discovery", provider_name="mapbox",
        config_json='{"token": "owner-a-secret-token"}',
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)

    theirs = await user_b_client.get(f"/api/v1/entities/provider_connections/{connection.id}")
    assert theirs.status_code == 404
    assert "owner-a-secret-token" not in theirs.text
    assert "config_json" not in theirs.text

    listed = await user_b_client.get("/api/v1/entities/provider_connections")
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert "owner-a-secret-token" not in listed.text
    assert "config_json" not in listed.text


# ---------- offer_profiles ----------
# test_offer_profiles_cross_tenant_read_is_404 already exists in
# tests/test_write_allowlist.py; PUT and DELETE cross-tenant coverage was
# missing (Task 6 review finding).

async def test_offer_profiles_cross_tenant_update_is_404(user_a_client, user_b_client, db_session):
    workspace_a, _workspace_b = await _seed_two_workspaces(db_session)
    create_response = await user_a_client.post(
        "/api/v1/entities/offer_profiles", json={"workspace_id": workspace_a.id, "services": "seo"}
    )
    assert create_response.status_code == 201
    profile_id = create_response.json()["id"]

    response = await user_b_client.put(
        f"/api/v1/entities/offer_profiles/{profile_id}", json={"services": "hijacked"}
    )
    assert response.status_code == 404

    refreshed = (await db_session.execute(
        select(Offer_profiles).where(Offer_profiles.id == profile_id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert refreshed.services == "seo", "cross-tenant write mutated the row despite the 404"


async def test_offer_profiles_cross_tenant_delete_is_404(user_a_client, user_b_client, db_session):
    workspace_a, _workspace_b = await _seed_two_workspaces(db_session)
    create_response = await user_a_client.post(
        "/api/v1/entities/offer_profiles", json={"workspace_id": workspace_a.id, "services": "seo"}
    )
    assert create_response.status_code == 201
    profile_id = create_response.json()["id"]

    response = await user_b_client.delete(f"/api/v1/entities/offer_profiles/{profile_id}")
    assert response.status_code == 404

    refreshed = (await db_session.execute(
        select(Offer_profiles).where(Offer_profiles.id == profile_id)
    )).scalar_one_or_none()
    assert refreshed is not None, "cross-tenant delete removed the row despite the 404"
