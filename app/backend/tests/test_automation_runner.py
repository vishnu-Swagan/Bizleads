"""Scheduled lead automation: services/automation_runner.py and routers/automations.py.

An automation is a saved Discover search plus a schedule. Running it must
behave exactly like a human doing the same three things by hand from the
Discover and Outreach pages: search, save only what's new, qualify up to a
budget without overspending, and draft — never send — outreach for whatever
it just qualified. The properties worth guarding are the same ones the manual
endpoints guard: tenancy, credit accounting, and that an unmeasurable site is
recorded as NULL rather than a fabricated 0/false.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from models.automations import Automations
from models.leads import Leads
from models.outreach_drafts import Outreach_drafts
from models.workspaces import Workspaces
from services import automation_runner
from tests.conftest import USER_A_ID, USER_B_ID


# ---------- Fixtures / helpers ----------

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


async def _seed_automation(db_session, owner_id=USER_A_ID, **overrides):
    fields = {
        "user_id": owner_id, "name": "Leeds cafes", "city": "Leeds",
        "country": "United Kingdom", "category": "Cafe", "query": "",
        "auto_qualify": True, "auto_draft": True, "max_leads_per_run": 10,
        "schedule": "manual", "enabled": True,
    }
    fields.update(overrides)
    automation = Automations(**fields)
    db_session.add(automation)
    await db_session.commit()
    await db_session.refresh(automation)
    return automation


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


def _biz(name, **overrides):
    biz = {
        "business_name": name,
        "category": "Cafe",
        "location": "Leeds",
        "country": "United Kingdom",
        "website_url": "https://example.com/" + name.lower().replace(" ", "-"),
        "has_website": True,
        "contact_email": name.lower().replace(" ", "") + "@example.com",
        "contact_phone": "+441234567890",
        "data_source": "provider",
    }
    biz.update(overrides)
    return biz


def _stub_search(monkeypatch, businesses):
    async def fake(*, query="", location="", category=None, country=None, limit=25):
        return businesses

    monkeypatch.setattr(automation_runner, "search_places", fake)


def _stub_qualify(monkeypatch, **result):
    """Same shape as tests/test_qualify_endpoint.py's stub — a measured,
    findable-defect lead by default so compose_many has something to say."""
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

    monkeypatch.setattr(automation_runner, "qualify_website", fake)
    return payload


def _stub_search_raises(monkeypatch, message="mapbox is down"):
    async def fake(*, query="", location="", category=None, country=None, limit=25):
        raise RuntimeError(message)

    monkeypatch.setattr(automation_runner, "search_places", fake)


# ---------- Search + dedupe ----------

class TestSearchAndDedupe:
    async def test_new_leads_saved_and_duplicates_skipped(self, db_session, monkeypatch):
        await _seed_workspace(db_session)
        await _seed_lead(db_session, business_name="Acme Cafe", location="Leeds")
        automation = await _seed_automation(db_session, auto_qualify=False, auto_draft=False)

        _stub_search(monkeypatch, [
            _biz("Acme Cafe", location="LEEDS"),   # duplicate, case-insensitive
            _biz("Bean There"),
            _biz("Bean There"),                     # duplicate within the same run
            _biz("Third Wave Coffee"),
        ])

        result = await automation_runner.run_automation(db_session, automation, USER_A_ID)

        assert result["status"] == "ok"
        assert result["new_leads"] == 2
        assert result["duplicates"] == 2

        rows = (await db_session.execute(select(Leads).where(Leads.user_id == USER_A_ID))).scalars().all()
        assert len(rows) == 3, "1 pre-existing + 2 newly saved"
        names = {r.business_name for r in rows}
        assert names == {"Acme Cafe", "Bean There", "Third Wave Coffee"}

    async def test_max_leads_per_run_respected(self, db_session, monkeypatch):
        await _seed_workspace(db_session, monthly=100)
        automation = await _seed_automation(db_session, max_leads_per_run=1, auto_draft=False)

        _stub_search(monkeypatch, [_biz("Cafe One"), _biz("Cafe Two"), _biz("Cafe Three")])
        _stub_qualify(monkeypatch)

        result = await automation_runner.run_automation(db_session, automation, USER_A_ID)

        assert result["new_leads"] == 3
        assert result["qualified"] == 1
        assert result["credits_charged"] == 1

        rows = (await db_session.execute(select(Leads).where(Leads.user_id == USER_A_ID))).scalars().all()
        qualified_count = sum(1 for r in rows if r.qualified_at is not None)
        assert qualified_count == 1, "only the leads within max_leads_per_run may be qualified"


# ---------- Credits ----------

class TestCredits:
    async def test_credit_exhaustion_stops_qualification_without_overspending(self, db_session, monkeypatch):
        ws = await _seed_workspace(db_session, credits_used=24, monthly=25)  # 1 credit left
        automation = await _seed_automation(db_session, max_leads_per_run=5, auto_draft=False)

        _stub_search(monkeypatch, [_biz("Cafe One"), _biz("Cafe Two"), _biz("Cafe Three")])
        _stub_qualify(monkeypatch)

        result = await automation_runner.run_automation(db_session, automation, USER_A_ID)

        assert result["qualified"] == 1
        assert result["credits_charged"] == 1
        assert result["credit_exhausted"] is True
        assert "out of credits" in result["summary"].lower()

        refreshed = (await db_session.execute(select(Workspaces).where(Workspaces.id == ws.id))).scalar_one()
        await db_session.refresh(refreshed)
        assert refreshed.credits_used == 25, "must never exceed the monthly allowance"


# ---------- Drafting ----------

class TestDrafting:
    async def test_drafts_created_with_status_pending(self, db_session, monkeypatch):
        await _seed_workspace(db_session, monthly=100)
        automation = await _seed_automation(db_session)

        _stub_search(monkeypatch, [_biz("Cafe One")])
        _stub_qualify(monkeypatch)

        result = await automation_runner.run_automation(db_session, automation, USER_A_ID)

        assert result["qualified"] == 1
        assert result["drafted"] == 1

        drafts = (await db_session.execute(select(Outreach_drafts).where(Outreach_drafts.user_id == USER_A_ID))).scalars().all()
        assert len(drafts) == 1
        draft = drafts[0]
        assert draft.status == "pending"
        assert draft.sequence_step == 1
        assert draft.automation_id == automation.id
        assert draft.to_email == "cafeone@example.com"
        assert draft.body_text

    async def test_no_draft_without_a_contact_email(self, db_session, monkeypatch):
        await _seed_workspace(db_session, monthly=100)
        automation = await _seed_automation(db_session)

        _stub_search(monkeypatch, [_biz("Cafe One", contact_email="")])
        _stub_qualify(monkeypatch)

        result = await automation_runner.run_automation(db_session, automation, USER_A_ID)

        assert result["qualified"] == 1
        assert result["drafted"] == 0


# ---------- Failure handling ----------

class TestFailureHandling:
    async def test_a_failure_records_last_run_error_rather_than_raising(self, db_session, monkeypatch):
        await _seed_workspace(db_session)
        automation = await _seed_automation(db_session)
        _stub_search_raises(monkeypatch, message="mapbox is down")

        result = await automation_runner.run_automation(db_session, automation, USER_A_ID)

        assert result["status"] == "error"
        assert "mapbox is down" in result["error"]

        row = (await db_session.execute(select(Automations).where(Automations.id == automation.id))).scalar_one()
        await db_session.refresh(row)
        assert row.last_run_error is not None
        assert "mapbox is down" in row.last_run_error
        assert row.last_run_at is not None


# ---------- Scheduling ----------

class TestScheduling:
    @pytest.mark.parametrize("schedule", ["daily", "weekly", "manual"])
    async def test_next_run_at_set_correctly_per_schedule(self, db_session, monkeypatch, schedule):
        await _seed_workspace(db_session)
        automation = await _seed_automation(db_session, schedule=schedule, auto_qualify=False, auto_draft=False)
        _stub_search(monkeypatch, [])

        before = datetime.now(timezone.utc)
        result = await automation_runner.run_automation(db_session, automation, USER_A_ID)
        after = datetime.now(timezone.utc)

        assert result["status"] == "ok"
        row = (await db_session.execute(select(Automations).where(Automations.id == automation.id))).scalar_one()
        await db_session.refresh(row)

        # SQLite has no real tz-aware datetime type, so a value that round
        # trips through it comes back naive even though it was written
        # tz-aware. Re-attach UTC before comparing against the tz-aware
        # bounds rather than assuming the storage engine preserved it.
        next_run_at = row.next_run_at
        if next_run_at is not None and next_run_at.tzinfo is None:
            next_run_at = next_run_at.replace(tzinfo=timezone.utc)

        if schedule == "daily":
            assert before + timedelta(days=1) <= next_run_at <= after + timedelta(days=1)
        elif schedule == "weekly":
            assert before + timedelta(days=7) <= next_run_at <= after + timedelta(days=7)
        else:
            assert next_run_at is None


# ---------- Tenancy, via the HTTP layer ----------

class TestTenancy:
    async def test_another_users_automation_is_not_visible_or_runnable(
        self, db_session, user_a_client, user_b_client
    ):
        await _seed_workspace(db_session, owner_id=USER_A_ID)
        automation = await _seed_automation(db_session, owner_id=USER_A_ID)

        get_resp = await user_b_client.get(f"/api/v1/automations/{automation.id}")
        assert get_resp.status_code == 404

        run_resp = await user_b_client.post(f"/api/v1/automations/{automation.id}/run")
        assert run_resp.status_code == 404

        list_resp = await user_b_client.get("/api/v1/automations")
        assert list_resp.status_code == 200
        assert list_resp.json()["items"] == []

        # It is still there for its owner, untouched.
        owner_resp = await user_a_client.get(f"/api/v1/automations/{automation.id}")
        assert owner_resp.status_code == 200

    async def test_run_due_only_runs_the_calling_users_automations(
        self, db_session, user_a_client, user_b_client, monkeypatch
    ):
        _stub_search(monkeypatch, [])
        await _seed_workspace(db_session, owner_id=USER_A_ID)
        await _seed_workspace(db_session, owner_id=USER_B_ID)

        due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await _seed_automation(
            db_session, owner_id=USER_A_ID, schedule="daily", next_run_at=due_at, auto_qualify=False, auto_draft=False,
        )
        await _seed_automation(
            db_session, owner_id=USER_B_ID, schedule="daily", next_run_at=due_at, auto_qualify=False, auto_draft=False,
        )

        resp = await user_a_client.post("/api/v1/automations/run-due")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ran"] == 1, "must run only the calling user's due automation"
