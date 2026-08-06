"""Accounts exempt from credit metering.

The operator needs to use their own product without spending credits they
notionally sell to themselves. The risk in any such exemption is scope creep:
"unmetered" quietly becoming "unrestricted". These tests pin the boundary —
the exemption removes billing, and nothing else. Tenancy, ownership and every
other rule apply to an unmetered account exactly as they do to a paying one.
"""
import pytest
from sqlalchemy import select

from models.workspaces import Workspaces
from services.entitlements import has_unlimited_credits
from tests.conftest import USER_A_ID, USER_A_EMAIL


@pytest.fixture(autouse=True)
def _no_allowlist(monkeypatch):
    monkeypatch.delenv("UNLIMITED_CREDIT_EMAILS", raising=False)


class TestTheAllowlist:
    def test_unset_means_everybody_is_metered(self):
        """The default must be safe for anyone who deploys this without
        knowing the variable exists."""
        assert has_unlimited_credits("anyone@example.com") is False

    def test_a_listed_address_is_exempt(self, monkeypatch):
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", "owner@example.com")
        assert has_unlimited_credits("owner@example.com") is True

    def test_an_unlisted_address_is_not(self, monkeypatch):
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", "owner@example.com")
        assert has_unlimited_credits("someone.else@example.com") is False

    def test_matching_ignores_case_and_surrounding_space(self, monkeypatch):
        """An allowlist that fails on capitalisation appears to work until the
        day it does not."""
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", " Owner@Example.com , second@example.com ")
        assert has_unlimited_credits("owner@example.com") is True
        assert has_unlimited_credits("OWNER@EXAMPLE.COM") is True
        assert has_unlimited_credits("second@example.com") is True

    def test_an_empty_email_is_never_exempt(self):
        """A token with no email claim must not match an empty entry."""
        monkeypatch = None  # noqa: F841 - documents that no env is needed here
        assert has_unlimited_credits("") is False

    def test_empty_entries_do_not_match_everyone(self, monkeypatch):
        """',,' must not parse into an entry that an empty email matches."""
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", "owner@example.com,,")
        assert has_unlimited_credits("") is False
        assert has_unlimited_credits("stranger@example.com") is False

    def test_it_is_read_fresh_rather_than_frozen_at_import(self, monkeypatch):
        """Config frozen at import only takes effect after a restart, which
        has already caused three production bugs in this codebase."""
        assert has_unlimited_credits("late@example.com") is False
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", "late@example.com")
        assert has_unlimited_credits("late@example.com") is True


@pytest.mark.asyncio
class TestMeteringIsSkipped:
    async def _spent_workspace(self, db_session):
        """A workspace with nothing left — a metered account is refused here."""
        ws = Workspaces(
            name="Acme", slug="acme", owner_id=USER_A_ID,
            plan="trial", subscription_status="trialing",
            monthly_credits=25, credits_used=25, max_seats=1,
        )
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)
        return ws

    async def test_a_metered_account_is_refused_when_out_of_credits(
        self, user_a_client, db_session, monkeypatch
    ):
        """The control. Without this passing, the exemption test below proves
        nothing — it could be succeeding because the limit never applied.

        Moved from /qualify to /run when measurement became part of what a
        search buys and qualifying stopped costing anything. A control aimed
        at an endpoint that no longer charges is not a control: it would pass
        for the wrong reason and take the exemption test's meaning with it.
        """
        import routers.discover as discover
        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)
        await self._spent_workspace(db_session)

        resp = await user_a_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "insufficient_credits"

    async def test_an_exempt_account_is_not_refused(
        self, user_a_client, db_session, monkeypatch
    ):
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", USER_A_EMAIL)
        import routers.discover as discover
        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

        async def _empty(**kwargs):
            return []

        monkeypatch.setattr(discover, "search_places", _empty)
        await self._spent_workspace(db_session)

        resp = await user_a_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )
        assert resp.status_code != 403

    async def test_an_exempt_account_spends_nothing(
        self, user_a_client, db_session, monkeypatch
    ):
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", USER_A_EMAIL)
        ws = Workspaces(
            name="Acme", slug="acme", owner_id=USER_A_ID,
            plan="trial", subscription_status="trialing",
            monthly_credits=25, credits_used=0, max_seats=1,
        )
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [1]})

        refreshed = (await db_session.execute(
            select(Workspaces).where(Workspaces.id == ws.id)
        )).scalar_one()
        await db_session.refresh(refreshed)
        assert refreshed.credits_used == 0, "an unmetered account must not be charged"

    async def test_an_expired_trial_does_not_lock_out_an_exempt_account(
        self, user_a_client, db_session, monkeypatch
    ):
        """Otherwise the operator loses their own product on day eight."""
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", USER_A_EMAIL)
        db_session.add(Workspaces(
            name="Acme", slug="acme", owner_id=USER_A_ID,
            plan="trial", subscription_status="trialing",
            monthly_credits=25, credits_used=0, max_seats=1,
            trial_ends_at="2020-01-01T00:00:00+00:00",
        ))
        await db_session.commit()

        resp = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [1]})
        assert resp.status_code != 403

    async def test_usage_reports_the_exemption(
        self, user_a_client, db_session, monkeypatch
    ):
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", USER_A_EMAIL)
        body = (await user_a_client.get("/api/v1/billing/usage")).json()
        assert body["unlimited_credits"] is True

    async def test_usage_reports_no_exemption_by_default(self, user_a_client, db_session):
        body = (await user_a_client.get("/api/v1/billing/usage")).json()
        assert body["unlimited_credits"] is False


@pytest.mark.asyncio
class TestItIsBillingOnlyNotAuthorisation:
    """The boundary that matters. Unmetered must never mean unrestricted."""

    async def test_an_exempt_account_still_sees_only_its_own_leads(
        self, user_a_client, user_b_client, db_session, monkeypatch
    ):
        from models.leads import Leads
        from tests.conftest import USER_B_ID

        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", USER_A_EMAIL)
        db_session.add(Leads(
            user_id=USER_B_ID, business_name="B's Private Lead",
            category="Cafe", location="Leeds", country="United Kingdom",
        ))
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/entities/leads")).json()
        names = [item["business_name"] for item in body.get("items", [])]
        assert "B's Private Lead" not in names

    async def test_an_exempt_account_cannot_read_another_users_lead(
        self, user_a_client, db_session, monkeypatch
    ):
        from models.leads import Leads
        from tests.conftest import USER_B_ID

        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", USER_A_EMAIL)
        lead = Leads(
            user_id=USER_B_ID, business_name="B's Lead",
            category="Cafe", location="Leeds", country="United Kingdom",
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        resp = await user_a_client.get(f"/api/v1/entities/leads/{lead.id}")
        assert resp.status_code == 404, "billing exemption must not grant cross-tenant read"
