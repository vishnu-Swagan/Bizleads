"""POST /api/v1/discover/qualify — Pass 2, exposed to the app.

Discovery returns identity but not web presence, so a fresh lead is unranked.
This endpoint is the only way a lead acquires a definite has_website value, and
the only way priority_score stops being None. Without it the scoring engine is
unreachable from the product.

The properties worth guarding are tenancy (you cannot measure someone else's
leads), credit accounting, and — most importantly — that an unmeasurable site
is persisted as NULL rather than as zero.
"""
import pytest
from sqlalchemy import select

import routers.discover as discover
from models.leads import Leads
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID, USER_B_ID


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


async def _seed_lead(db_session, owner_id=USER_A_ID, **overrides):
    fields = {
        "user_id": owner_id, "business_name": "Acme Cafe", "category": "Cafe",
        "location": "Leeds", "country": "United Kingdom",
        "website_url": "https://acme-cafe.example", "data_source": "provider",
    }
    fields.update(overrides)
    lead = Leads(**fields)
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


def _stub_qualify(monkeypatch, **result):
    """Replace the measurement so tests never touch the network."""
    payload = {
        "has_website": True, "website_url": "https://acme-cafe.example",
        "website_score": 42, "website_state": "moderate", "audit": None,
        "findings": [{"id": "no_viewport", "label": "Not mobile-friendly",
                      "penalty": 30, "evidence": "No viewport meta", "category": "mobile"}],
        "evidence_tier": "heuristic", "audit_available": False, "evidence": {},
    }
    payload.update(result)

    # **kwargs so the stub keeps matching qualify_website as it gains
    # keyword-only options (allow_audit, and whatever follows). A stub with a
    # frozen signature turns every future parameter into eleven unrelated
    # test failures that say nothing about the change.
    async def fake(url, **kwargs):
        return payload

    monkeypatch.setattr(discover, "qualify_website", fake)
    return payload


class TestAuthAndTenancy:
    async def test_anonymous_is_rejected(self, anon_client):
        response = await anon_client.post("/api/v1/discover/qualify", json={"lead_ids": [1]})
        assert response.status_code == 401

    async def test_another_users_lead_is_not_measured(self, user_b_client, db_session, monkeypatch):
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session, owner_id=USER_B_ID)
        lead = await _seed_lead(db_session, owner_id=USER_A_ID)

        response = await user_b_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        assert response.status_code == 200
        body = response.json()
        assert body["qualified"] == []
        assert lead.id in body["not_found"]
        # And nothing was charged for work not done.
        assert body["credits_charged"] == 0

    async def test_another_users_lead_is_not_modified(self, user_b_client, db_session, monkeypatch):
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session, owner_id=USER_B_ID)
        lead = await _seed_lead(db_session, owner_id=USER_A_ID, website_score=None)

        await user_b_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)
        assert row.website_score is None


class TestMeasurement:
    async def test_a_measured_lead_becomes_ranked(self, user_a_client, db_session, monkeypatch):
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session)

        response = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        assert response.status_code == 200
        result = response.json()["qualified"][0]
        assert result["has_website"] is True
        assert result["website_score"] == 42
        assert result["priority_score"] is not None, "a measured lead must be rankable"
        assert result["qualification_required"] is False

    async def test_findings_are_returned_for_the_pitch(self, user_a_client, db_session, monkeypatch):
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session)

        response = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        findings = response.json()["qualified"][0]["findings"]
        assert findings, "the specific problems are the sellable output"
        assert findings[0]["evidence"], "a finding without evidence is just a label"

    async def test_measurement_is_persisted(self, user_a_client, db_session, monkeypatch):
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session, website_score=None)

        await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)
        assert row.website_score == 42
        assert row.has_website is True


class TestUnmeasurableStaysNull:
    async def test_an_unreachable_site_is_stored_as_null_not_zero(
        self, user_a_client, db_session, monkeypatch
    ):
        # The defect this codebase exists to prevent: writing 0/false for a
        # value nobody established. A lead we could not measure must stay
        # unmeasured, not be recorded as "confirmed to have no website".
        _stub_qualify(
            monkeypatch,
            has_website=None, website_score=None, website_state="unknown",
            website_url=None, findings=[],
        )
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session, website_url="", website_score=None)

        response = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        result = response.json()["qualified"][0]
        assert result["priority_score"] is None
        assert result["qualification_required"] is True

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)
        assert row.website_score is None, "unmeasured must not become 0"
        assert row.has_website is None, "unmeasured must not become False"


class TestCreditsAndLimits:
    async def test_credits_are_charged_per_lead(self, user_a_client, db_session, monkeypatch):
        _stub_qualify(monkeypatch)
        ws = await _seed_workspace(db_session)
        leads = [await _seed_lead(db_session) for _ in range(3)]

        response = await user_a_client.post(
            "/api/v1/discover/qualify", json={"lead_ids": [l.id for l in leads]}
        )

        # Free since discovery started measuring every result it returns.
        # Charging again to re-measure a lead would bill twice for work the
        # search already paid for.
        assert response.json()["credits_charged"] == 0
        refreshed = (await db_session.execute(select(Workspaces).where(Workspaces.id == ws.id))).scalar_one()
        await db_session.refresh(refreshed)
        assert refreshed.credits_used == 0

    async def test_an_empty_balance_does_not_block_measuring(
        self, user_a_client, db_session, monkeypatch
    ):
        """Replaces a test asserting the opposite.

        A zero balance used to refuse this endpoint. That check outlived its
        purpose the moment measuring stopped costing anything, and while it
        survived it produced the worst version of the bug: accounts exempt
        from metering, and new accounts starting at zero pending approval,
        were both refused work that was free.
        """
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session, credits_used=25, monthly=25)
        lead = await _seed_lead(db_session, website_score=None)

        response = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        assert response.status_code == 200
        assert response.json()["credits_charged"] == 0

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)
        assert row.website_score is not None, "it should have been measured"

    async def test_batch_size_is_capped(self, user_a_client, db_session, monkeypatch):
        # Each lead is at least one outbound request; an uncapped batch would
        # fan one call out into hundreds of fetches against third parties.
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session, monthly=1000)

        response = await user_a_client.post(
            "/api/v1/discover/qualify", json={"lead_ids": list(range(1, 26))}
        )

        assert response.status_code == 400
        assert "at most" in response.json()["detail"]

    async def test_empty_request_is_rejected(self, user_a_client, db_session):
        await _seed_workspace(db_session)
        response = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": []})
        assert response.status_code == 400
