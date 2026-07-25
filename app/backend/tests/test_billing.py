from types import SimpleNamespace

import pytest
from sqlalchemy import select

import routers.payments as payments
from models.credit_ledger import Credit_ledger
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID


def _fake_session(user_id, session_id="cs_test_1", status="complete", payment_status="paid"):
    return SimpleNamespace(
        id=session_id, status=status, payment_status=payment_status,
        customer="cus_1", subscription="sub_1",
        metadata={"user_id": user_id, "plan": "solo"},
    )


@pytest.fixture(autouse=True)
def _stripe_configured(monkeypatch):
    monkeypatch.setattr(payments.stripe, "api_key", "sk_test_dummy", raising=False)


async def _seed_workspace(db_session):
    workspace = Workspaces(
        name="Acme", slug="acme", owner_id=USER_A_ID,
        plan="trial", subscription_status="trialing",
        monthly_credits=25, credits_used=20, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


async def test_usage_creates_trial_workspace_for_new_user(user_a_client, db_session):
    # No workspace exists yet for USER_A_ID; the endpoint must create one with
    # the same trial defaults ensure_workspace_for_user establishes elsewhere,
    # and the response shape must be unchanged.
    response = await user_a_client.get("/api/v1/billing/usage")
    assert response.status_code == 200

    body = response.json()
    assert body["plan"] == "trial"
    assert body["plan_name"] == "Trial"
    assert body["subscription_status"] == "trialing"
    assert body["credits_total"] == 25
    assert body["credits_used"] == 0
    assert body["credits_remaining"] == 25
    assert body["max_seats"] == 1
    assert body["trial_ends_at"]
    assert body["credits_reset_at"]

    workspaces = (await db_session.execute(
        select(Workspaces).where(Workspaces.owner_id == USER_A_ID)
    )).scalars().all()
    assert len(workspaces) == 1, "usage endpoint did not create exactly one workspace"


async def test_usage_does_not_create_second_workspace_on_repeat_call(user_a_client, db_session):
    first = await user_a_client.get("/api/v1/billing/usage")
    assert first.status_code == 200
    first_workspace_id = first.json()["workspace_id"]

    second = await user_a_client.get("/api/v1/billing/usage")
    assert second.status_code == 200
    assert second.json()["workspace_id"] == first_workspace_id

    workspaces = (await db_session.execute(
        select(Workspaces).where(Workspaces.owner_id == USER_A_ID)
    )).scalars().all()
    assert len(workspaces) == 1, "repeat call to /billing/usage created a duplicate workspace"


async def test_foreign_session_is_rejected(user_a_client, db_session, monkeypatch):
    await _seed_workspace(db_session)
    monkeypatch.setattr(
        payments.stripe.checkout.Session, "retrieve",
        lambda session_id: _fake_session("someone-else"),
    )
    response = await user_a_client.post("/api/v1/billing/verify-payment", json={"session_id": "cs_test_1"})
    assert response.status_code == 403


async def test_unpaid_session_does_not_activate(user_a_client, db_session, monkeypatch):
    workspace = await _seed_workspace(db_session)
    monkeypatch.setattr(
        payments.stripe.checkout.Session, "retrieve",
        lambda session_id: _fake_session(USER_A_ID, payment_status="unpaid"),
    )
    response = await user_a_client.post("/api/v1/billing/verify-payment", json={"session_id": "cs_test_1"})

    assert response.status_code == 200
    assert response.json()["status"] != "active"

    refreshed = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert refreshed.plan == "trial", "unpaid session upgraded the plan"
    assert refreshed.subscription_status == "trialing"

    ledger_rows = (await db_session.execute(
        select(Credit_ledger).where(Credit_ledger.reference_id == "cs_test_1")
    )).scalars().all()
    assert ledger_rows == [], "unpaid session wrote a ledger row"


async def test_replay_does_not_reset_credits(user_a_client, db_session, monkeypatch):
    workspace = await _seed_workspace(db_session)
    monkeypatch.setattr(
        payments.stripe.checkout.Session, "retrieve",
        lambda session_id: _fake_session(USER_A_ID),
    )

    first = await user_a_client.post("/api/v1/billing/verify-payment", json={"session_id": "cs_test_1"})
    assert first.status_code == 200

    # Burn credits, then replay the same session.
    refreshed = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    refreshed.credits_used = 250
    await db_session.commit()

    second = await user_a_client.post("/api/v1/billing/verify-payment", json={"session_id": "cs_test_1"})
    assert second.status_code == 200

    final = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    await db_session.refresh(final)
    assert final.credits_used == 250, "replay reset credit usage"

    ledger_rows = (await db_session.execute(
        select(Credit_ledger).where(Credit_ledger.reference_id == "cs_test_1")
    )).scalars().all()
    assert len(ledger_rows) == 1, "replay created a duplicate ledger row"
