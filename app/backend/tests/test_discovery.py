import pytest
from sqlalchemy import select

import routers.discover as discover
import services.business_search as business_search
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID


async def _seed_workspace(db_session, credits_used=0):
    workspace = Workspaces(
        name="Acme", slug="acme", owner_id=USER_A_ID,
        plan="solo", subscription_status="active",
        monthly_credits=300, credits_used=credits_used, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


@pytest.fixture(autouse=True)
def _forbid_ai_discovery(monkeypatch):
    """Any call to the AI generator during discovery is a test failure.

    Patched in two places on purpose, not redundantly. `business_search` is the
    source module; `discover` is where a future regression would actually land.
    A direct `from services.business_search import generate_search_results` in
    discover.py (the same import style already used for is_mapbox_configured /
    search_places) binds that name into discover's namespace at import time, so
    patching only business_search.generate_search_results would not intercept
    a call made via discover.generate_search_results. Neither discover.*
    target exists today (raising=False is correct for both) - the point is to
    pre-empt a reintroduced import, not to patch something currently present.
    """
    async def _explode(*args, **kwargs):
        raise AssertionError("AI fabrication path was invoked")

    monkeypatch.setattr(business_search, "generate_search_results", _explode)
    monkeypatch.setattr(discover, "discover_businesses", _explode, raising=False)
    monkeypatch.setattr(discover, "generate_search_results", _explode, raising=False)


async def test_unconfigured_provider_returns_setup_state(user_a_client, db_session, monkeypatch):
    workspace = await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: False)

    response = await user_a_client.post("/api/v1/discover/run", json={"country": "United Kingdom"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "provider_unconfigured"
    assert body["results"] == []


async def test_unconfigured_provider_charges_no_credits(user_a_client, db_session, monkeypatch):
    workspace = await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: False)

    await user_a_client.post("/api/v1/discover/run", json={"country": "United Kingdom"})

    refreshed = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert refreshed.credits_used == 0


async def test_zero_matches_returns_no_matches_not_fabrication(user_a_client, db_session, monkeypatch):
    await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: True)

    async def _empty(**kwargs):
        return []

    monkeypatch.setattr(discover, "search_places", _empty)

    response = await user_a_client.post("/api/v1/discover/run", json={"country": "United Kingdom"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_matches"
    assert body["results"] == []


async def test_deep_pass_costs_one_credit(user_a_client, db_session, monkeypatch):
    await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: True)

    response = await user_a_client.post("/api/v1/discover/estimate", json={"pass_type": "deep"})
    assert response.status_code == 200
    assert response.json()["credit_cost"] == 1


async def test_estimate_reports_the_full_provider_yield(user_a_client, db_session, monkeypatch):
    """One credit should buy as many leads as the provider will return.

    The estimate hardcoded a ceiling of 15 while MapBox returns up to 25, so a
    third of every paid search went unused and the estimate under-reported it.
    """
    await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: True)

    response = await user_a_client.post("/api/v1/discover/estimate", json={"category": "Restaurant"})

    assert response.status_code == 200
    assert response.json()["estimated_results"] == discover.MAX_LIMIT


async def test_limit_above_the_provider_ceiling_is_rejected(user_a_client, db_session):
    """`limit` was an unconstrained int — a client could ask for millions."""
    await _seed_workspace(db_session)

    response = await user_a_client.post(
        "/api/v1/discover/run", json={"category": "Restaurant", "limit": 100_000}
    )

    assert response.status_code == 422


async def test_limit_below_one_is_rejected(user_a_client, db_session):
    await _seed_workspace(db_session)

    response = await user_a_client.post(
        "/api/v1/discover/run", json={"category": "Restaurant", "limit": 0}
    )

    assert response.status_code == 422
