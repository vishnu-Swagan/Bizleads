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


FABRICATION_FUNCTIONS = ("generate_search_results", "discover_businesses", "extract_json_block")


def test_the_fabrication_path_does_not_exist():
    """Discovery must have no way to invent a business.

    These functions asked a language model to produce businesses matching a
    search and returned them as leads: plausible names, plausible websites,
    none of them real. They are deleted, not merely uncalled — dead code that
    fabricates leads is an invitation to call it.

    Asserts against the source files, not runtime attributes: the autouse
    fixture below installs tripwires under these same names, so `hasattr`
    would report the tripwire and pass no matter what the code says.
    """
    import ast
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    for module in ("services/business_search.py", "routers/discover.py"):
        tree = ast.parse((backend / module).read_text())
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        for name in FABRICATION_FUNCTIONS:
            assert name not in defined | imported, (
                f"{module} defines or imports {name}. Discovery must return "
                f"only businesses a licensed provider actually returned."
            )


@pytest.fixture(autouse=True)
def _forbid_ai_discovery(monkeypatch):
    """Fail loudly if a fabrication function is reintroduced and then called.

    The module-level functions are gone, so there is nothing left to patch.
    This installs tripwires under the names a regression would most likely
    reuse: `discover` is where a reintroduced
    `from services.business_search import generate_search_results` would bind
    the name, which patching the source module alone would not intercept.
    """
    async def _explode(*args, **kwargs):
        raise AssertionError("AI fabrication path was invoked")

    for name in FABRICATION_FUNCTIONS:
        monkeypatch.setattr(business_search, name, _explode, raising=False)
        monkeypatch.setattr(discover, name, _explode, raising=False)


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
