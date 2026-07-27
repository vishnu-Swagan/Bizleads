"""Website qualification findings must persist on the lead, not just ride
along in the response body.

Before this, POST /api/v1/discover/qualify computed `findings` and returned
them to the caller, then threw them away — nothing in the update dict passed
to LeadsService.update() stored them. A page refresh, or coming back later,
lost the specific "here is what's wrong with this site" evidence.

The property worth guarding, same as website_score/has_website before it: NULL
(never qualified) and "[]" (qualified, found nothing wrong) are different
facts and must not collapse into each other.
"""
import json

import pytest
from sqlalchemy import select

import routers.discover as discover
from models.leads import Leads
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

    async def fake(url):
        return payload

    monkeypatch.setattr(discover, "qualify_website", fake)
    return payload


class TestFindingsSurviveAQualifyCall:
    async def test_findings_are_stored_on_the_lead(self, user_a_client, db_session, monkeypatch):
        stubbed = _stub_qualify(monkeypatch)
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session)

        response = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})
        assert response.status_code == 200

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)

        assert row.findings is not None
        assert json.loads(row.findings) == stubbed["findings"]
        assert row.qualified_at is not None

    async def test_qualified_at_looks_like_an_iso_timestamp(self, user_a_client, db_session, monkeypatch):
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session)

        await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)

        from datetime import datetime
        # Raises if it isn't a real ISO timestamp.
        datetime.fromisoformat(row.qualified_at)


class TestNullVsEmptyListStayDistinct:
    async def test_never_qualified_lead_has_null_findings(self, db_session):
        lead = await _seed_lead(db_session)
        assert lead.findings is None
        assert lead.qualified_at is None

    async def test_a_clean_bill_of_health_is_stored_as_empty_list_not_null(
        self, user_a_client, db_session, monkeypatch
    ):
        # The site was genuinely analysed and nothing was wrong with it —
        # website_score is a real number, findings is genuinely [].
        _stub_qualify(monkeypatch, findings=[], website_score=95, website_state="healthy")
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session)

        await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)

        # "[]" (a string), not NULL — this is an asserted result, not silence.
        assert row.findings == "[]"
        assert row.findings is not None
        assert row.qualified_at is not None


class TestUnmeasurableSiteLeavesNull:
    async def test_an_unmeasurable_site_does_not_get_a_fabricated_findings_list(
        self, user_a_client, db_session, monkeypatch
    ):
        # Mirrors TestUnmeasurableStaysNull in test_qualify_endpoint.py: the
        # measurement could not run at all (invalid/blocked state). No score
        # was established, so findings/qualified_at must stay NULL — writing
        # "[]" here would assert "checked, found nothing wrong" for a lead
        # nobody actually analysed.
        _stub_qualify(
            monkeypatch,
            has_website=None, website_score=None, website_state="unknown",
            website_url=None, findings=[],
        )
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session, website_url="", website_score=None)

        response = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})
        assert response.status_code == 200

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)

        assert row.findings is None, "an unmeasured lead must not get a fabricated findings list"
        assert row.qualified_at is None, "an unmeasured lead must not look qualified"

    async def test_a_parked_domain_leaves_findings_null(self, user_a_client, db_session, monkeypatch):
        # A parked domain is a real, definite result (has_website True, state
        # "parked") but qualify_website never runs the heuristic analysis for
        # it, so website_score stays None. findings must follow website_score,
        # not has_website.
        _stub_qualify(
            monkeypatch,
            has_website=True, website_score=None, website_state="parked",
            website_url="https://acme-cafe.example", findings=[],
        )
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session)

        await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        row = (await db_session.execute(select(Leads).where(Leads.id == lead.id))).scalar_one()
        await db_session.refresh(row)

        assert row.findings is None
        assert row.qualified_at is None


class TestLeadApiReturnsTheFields:
    async def test_get_lead_returns_findings_and_qualified_at(
        self, user_a_client, db_session, monkeypatch
    ):
        _stub_qualify(monkeypatch)
        await _seed_workspace(db_session)
        lead = await _seed_lead(db_session)
        await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [lead.id]})

        response = await user_a_client.get(f"/api/v1/entities/leads/{lead.id}")

        assert response.status_code == 200
        body = response.json()
        assert "findings" in body
        assert "qualified_at" in body
        assert json.loads(body["findings"])[0]["id"] == "no_viewport"
        assert body["qualified_at"] is not None

    async def test_a_freshly_created_lead_returns_null_findings(self, user_a_client):
        payload = {
            "business_name": "The Allotment Vegan Eatery",
            "category": "Restaurant",
            "location": "Northern Quarter, Manchester",
            "country": "United Kingdom",
            "website_url": "",
            "website_score": None,
            "social_score": None,
            "has_website": None,
            "social_platforms": "[]",
            "contact_email": "",
            "contact_phone": "",
            "pipeline_stage": "new_lead",
            "priority": "high",
            "notes_count": 0,
            "last_contacted": "",
            "data_source": "provider",
            "findings": None,
            "qualified_at": None,
        }

        response = await user_a_client.post("/api/v1/entities/leads", json=payload)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["findings"] is None
        assert body["qualified_at"] is None
