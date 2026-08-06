"""Discovery measures every result it returns.

Discovery used to hand back listing rows and leave the measuring to a separate
Qualify step. That step was not an optional refinement: no listing provider
supplies an email address — google_places.py returns "" and mapbox_places.py
returns None — so an unqualified lead had nobody to write to. The user paid a
credit for a search and received rows they could not act on until they paid
again, per lead, to find out the one thing they needed.

These tests pin the properties that folding measurement into discovery must
preserve:

  - every result is measured, and what the page says reaches the response;
  - a page that yields nothing never blanks data the listing did supply;
  - one dead host does not fail a search the user has already been charged for;
  - "could not measure" stays distinguishable from "measured, nothing wrong";
  - the PageSpeed budget still degrades to the free tier instead of hanging.

The measurement itself is always stubbed. A test that reached the network
would be measuring somebody else's uptime.
"""
import asyncio
from time import monotonic

import pytest

import routers.discover as discover
import services.discovery_measure as discovery_measure
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID


async def _seed_workspace(db_session, owner_id=USER_A_ID, credits_used=0, monthly=25):
    ws = Workspaces(
        name="Acme", slug=owner_id[:8], owner_id=owner_id, plan="trial",
        subscription_status="trialing", monthly_credits=monthly,
        credits_used=credits_used, max_seats=1,
    )
    db_session.add(ws)
    await db_session.commit()
    await db_session.refresh(ws)
    return ws


def _listing(**overrides):
    """One business as a provider returns it: no email, sometimes a phone."""
    row = {
        "business_name": "Acme Cafe",
        "category": "Cafe",
        "location": "Leeds",
        "country": "United Kingdom",
        "website_url": "https://acme-cafe.example",
        "contact_email": "",
        "contact_phone": "+44 113 496 0000",
        "full_address": "",
        "has_website": None,
        "website_score": None,
        "social_score": None,
        "data_source": "provider",
    }
    row.update(overrides)
    return row


def _measurement(**overrides):
    """What qualify_website returns for a readable page."""
    payload = {
        "has_website": True,
        "website_url": "https://acme-cafe.example",
        "website_score": 42,
        "website_state": "moderate",
        "audit": None,
        "findings": [
            {"id": "no_viewport", "label": "Not mobile-friendly", "penalty": 30,
             "evidence": "No viewport meta", "category": "mobile"},
        ],
        "contact_email": "hello@acme-cafe.example",
        "contact_phone": "+44 113 496 1234",
        "postal_address": "1 Briggate, Leeds LS1",
        "social_links": ["facebook", "instagram"],
        "evidence_tier": "heuristic",
        "audit_available": False,
        "evidence": {},
    }
    payload.update(overrides)
    return payload


def _stub_search(monkeypatch, rows):
    # Without this /run returns its provider-unconfigured setup state and
    # never searches, so every assertion below would read an empty list.
    monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

    async def fake(**kwargs):
        # Return copies so a test cannot be fooled by measure_results
        # mutating the same objects the assertions later read from.
        return [dict(r) for r in rows]

    monkeypatch.setattr(discover, "search_places", fake)


def _stub_measurement(monkeypatch, handler):
    async def fake(url, **kwargs):
        return handler(url, **kwargs)

    monkeypatch.setattr(discovery_measure, "qualify_website", fake)


async def _run_discovery(client, **payload):
    body = {"country": "United Kingdom", "city": "Leeds", "category": "Cafe", "limit": 5}
    body.update(payload)
    return await client.post("/api/v1/discover/run", json=body)


class TestEveryResultIsMeasured:
    async def test_the_page_supplies_the_email_the_listing_never_had(
        self, user_a_client, db_session, monkeypatch
    ):
        """The whole point. A listing has no email; the site does."""
        await _seed_workspace(db_session)
        _stub_search(monkeypatch, [_listing()])
        _stub_measurement(monkeypatch, lambda url, **kw: _measurement())

        response = await _run_discovery(user_a_client)

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["contact_email"] == "hello@acme-cafe.example"

    async def test_scores_and_findings_reach_the_caller(
        self, user_a_client, db_session, monkeypatch
    ):
        await _seed_workspace(db_session)
        _stub_search(monkeypatch, [_listing()])
        _stub_measurement(monkeypatch, lambda url, **kw: _measurement())

        result = (await _run_discovery(user_a_client)).json()["results"][0]

        assert result["website_score"] == 42
        assert result["has_website"] is True
        assert result["evidence_tier"] == "heuristic"
        assert [f["label"] for f in result["findings"]] == ["Not mobile-friendly"]
        # A measured lead is rankable, so the UI must not be told to ask for
        # a qualification pass that no longer exists.
        assert result["qualification_required"] is False

    async def test_the_page_wins_over_the_listing_for_phone_and_address(
        self, user_a_client, db_session, monkeypatch
    ):
        await _seed_workspace(db_session)
        _stub_search(monkeypatch, [_listing()])
        _stub_measurement(monkeypatch, lambda url, **kw: _measurement())

        result = (await _run_discovery(user_a_client)).json()["results"][0]

        assert result["contact_phone"] == "+44 113 496 1234"
        assert result["full_address"] == "1 Briggate, Leeds LS1"

    async def test_every_result_is_measured_not_just_the_first(
        self, user_a_client, db_session, monkeypatch
    ):
        await _seed_workspace(db_session)
        rows = [_listing(business_name=f"Cafe {i}", website_url=f"https://c{i}.example")
                for i in range(6)]
        _stub_search(monkeypatch, rows)

        seen = []

        def handler(url, **kwargs):
            seen.append(url)
            return _measurement(website_url=url)

        _stub_measurement(monkeypatch, handler)

        results = (await _run_discovery(user_a_client)).json()["results"]

        assert len(seen) == 6
        assert all(r["contact_email"] == "hello@acme-cafe.example" for r in results)


class TestMeasurementNeverMakesALeadWorse:
    async def test_an_empty_page_result_does_not_blank_the_listing_phone(
        self, user_a_client, db_session, monkeypatch
    ):
        """A site that publishes no phone must not erase the one Mapbox gave.

        Otherwise measuring a lead is strictly worse than not measuring it,
        and the user loses a working phone number by searching.
        """
        await _seed_workspace(db_session)
        _stub_search(monkeypatch, [_listing()])
        _stub_measurement(
            monkeypatch,
            lambda url, **kw: _measurement(contact_phone=None, postal_address=None),
        )

        result = (await _run_discovery(user_a_client)).json()["results"][0]

        assert result["contact_phone"] == "+44 113 496 0000"

    async def test_one_dead_host_does_not_fail_the_whole_search(
        self, user_a_client, db_session, monkeypatch
    ):
        """The credit is already spent. Losing 5 good rows to 1 bad host is theft."""
        await _seed_workspace(db_session)
        rows = [_listing(business_name="Good", website_url="https://good.example"),
                _listing(business_name="Bad", website_url="https://bad.example")]
        _stub_search(monkeypatch, rows)

        def handler(url, **kwargs):
            if "bad" in url:
                raise RuntimeError("connection reset")
            return _measurement()

        _stub_measurement(monkeypatch, handler)

        response = await _run_discovery(user_a_client)

        assert response.status_code == 200
        results = {r["business_name"]: r for r in response.json()["results"]}
        assert len(results) == 2
        # The failed one keeps what the listing gave it...
        assert results["Bad"]["contact_phone"] == "+44 113 496 0000"
        assert results["Bad"]["website_score"] is None
        # ...and the healthy one is unaffected by its neighbour.
        assert results["Good"]["contact_email"] == "hello@acme-cafe.example"


class TestUnmeasurableStaysDistinctFromClean:
    async def test_an_unreadable_site_reports_no_findings_rather_than_none_found(
        self, user_a_client, db_session, monkeypatch
    ):
        """website_score None means "could not read it".

        Recording findings of [] there would assert "checked, nothing wrong"
        about a site nobody could open — the exact false clean bill of health
        the qualify endpoint already refuses to give.
        """
        await _seed_workspace(db_session)
        _stub_search(monkeypatch, [_listing()])
        _stub_measurement(
            monkeypatch,
            lambda url, **kw: _measurement(
                website_score=None, website_state="unreachable", findings=[],
            ),
        )

        result = (await _run_discovery(user_a_client)).json()["results"][0]

        assert result["website_score"] is None
        assert result["findings"] is None
        assert "qualified_at" not in result or result["qualified_at"] is None

    async def test_a_measured_clean_site_is_timestamped_and_keeps_its_empty_list(
        self, user_a_client, db_session, monkeypatch
    ):
        await _seed_workspace(db_session)
        _stub_search(monkeypatch, [_listing()])
        _stub_measurement(
            monkeypatch,
            lambda url, **kw: _measurement(website_score=95, findings=[]),
        )

        result = (await _run_discovery(user_a_client)).json()["results"][0]

        assert result["findings"] == []
        assert result["qualified_at"]


class TestTheAuditBudget:
    async def test_leads_past_the_budget_drop_to_the_free_tier(
        self, user_a_client, db_session, monkeypatch
    ):
        """PageSpeed costs 10-20s per lead, so it cannot run for every result.

        Once the budget is gone the rest are still measured, just without the
        audit — which is why evidence_tier exists.
        """
        await _seed_workspace(db_session)
        rows = [_listing(business_name=f"Cafe {i}", website_url=f"https://c{i}.example")
                for i in range(4)]
        _stub_search(monkeypatch, rows)
        # Nothing may audit: the budget is already spent before the first call.
        monkeypatch.setattr(discovery_measure, "DISCOVERY_AUDIT_BUDGET_SECONDS", -1.0)

        audit_flags = []

        def handler(url, **kwargs):
            audit_flags.append(kwargs.get("allow_audit"))
            return _measurement()

        _stub_measurement(monkeypatch, handler)

        response = await _run_discovery(user_a_client)

        assert response.status_code == 200
        assert audit_flags == [False, False, False, False]

    async def test_measurements_run_concurrently_not_in_series(
        self, user_a_client, db_session, monkeypatch
    ):
        """Serial measurement is the thing that made this infeasible.

        Eight 50ms measurements must overlap. In series they would take 400ms;
        the generous ceiling here keeps the test from flaking on a loaded
        machine while still failing outright if concurrency is lost.
        """
        await _seed_workspace(db_session)
        rows = [_listing(business_name=f"Cafe {i}", website_url=f"https://c{i}.example")
                for i in range(8)]
        _stub_search(monkeypatch, rows)

        async def slow(url, **kwargs):
            await asyncio.sleep(0.05)
            return _measurement()

        monkeypatch.setattr(discovery_measure, "qualify_website", slow)

        started = monotonic()
        response = await _run_discovery(user_a_client)
        elapsed = monotonic() - started

        assert response.status_code == 200
        assert elapsed < 0.30, f"measurements appear to be serial ({elapsed:.2f}s)"


class TestChargingIsUnchanged:
    async def test_a_search_still_costs_one_credit_with_measurement_included(
        self, user_a_client, db_session, monkeypatch
    ):
        """Measurement folded into discovery must not fold its old per-lead
        charge in with it: one search, one credit, however many leads it
        measured."""
        workspace = await _seed_workspace(db_session)
        rows = [_listing(business_name=f"Cafe {i}", website_url=f"https://c{i}.example")
                for i in range(5)]
        _stub_search(monkeypatch, rows)
        _stub_measurement(monkeypatch, lambda url, **kw: _measurement())

        response = await _run_discovery(user_a_client)

        assert response.status_code == 200
        assert response.json()["credits_charged"] == 1
        await db_session.refresh(workspace)
        assert workspace.credits_used == 1
