"""Trials that actually end.

trial_ends_at was written at signup and read by nothing, so every trial ran
forever — which competes directly with the plans this product sells.

The gate is deliberately narrow. It covers the two passes that spend credits
and call third-party providers; a customer's own saved leads stay readable,
because holding somebody's data hostage is a worse product than an honest
paywall on new work.

It also fails OPEN on anything it cannot determine. A trial that never ends
costs revenue; a trial that ends wrongly costs a customer and a refund.
"""
from datetime import datetime, timedelta, timezone

import pytest

from dependencies.tenancy import trial_ended_at, trial_expired
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID


def _workspace(**overrides) -> Workspaces:
    defaults = dict(
        id=1, name="Acme", slug="acme", owner_id=USER_A_ID,
        plan="trial", subscription_status="trialing",
        monthly_credits=25, credits_used=0, max_seats=1,
        trial_ends_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    )
    defaults.update(overrides)
    return Workspaces(**defaults)


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class TestWhenATrialCountsAsExpired:
    def test_a_trial_still_running_is_not_expired(self):
        assert trial_expired(_workspace()) is False

    def test_a_trial_past_its_end_date_is_expired(self):
        assert trial_expired(_workspace(trial_ends_at=_ago(1))) is True

    def test_the_end_date_is_reported_back(self):
        ended = trial_ended_at(_workspace(trial_ends_at=_ago(3)))
        assert ended is not None
        assert ended < datetime.now(timezone.utc)


class TestItNeverGatesSomebodyItShouldNot:
    def test_a_paid_plan_is_never_treated_as_an_expired_trial(self):
        """The date is left behind on upgrade; reading it on a paid plan would
        lock out the customer who just paid."""
        for plan in ("solo", "pro", "agency"):
            ws = _workspace(plan=plan, subscription_status="active", trial_ends_at=_ago(30))
            assert trial_expired(ws) is False, f"{plan} was gated"

    def test_an_active_subscription_on_the_trial_plan_is_not_gated(self):
        ws = _workspace(subscription_status="active", trial_ends_at=_ago(30))
        assert trial_expired(ws) is False


class TestItFailsOpen:
    """Every branch here is a case where the answer is unknown. Unknown must
    mean "keep working" — the opposite choice locks people out of accounts
    over a bad string."""

    def test_a_blank_end_date_does_not_expire(self):
        assert trial_expired(_workspace(trial_ends_at="")) is False

    def test_a_null_end_date_does_not_expire(self):
        assert trial_expired(_workspace(trial_ends_at=None)) is False

    def test_an_unparseable_end_date_does_not_expire(self):
        assert trial_expired(_workspace(trial_ends_at="whenever")) is False

    def test_a_naive_timestamp_is_read_as_utc_rather_than_raising(self):
        """Rows written before the tz-aware default carry naive timestamps.
        Comparing naive to aware raises TypeError, which would 500 every
        search rather than gating one trial."""
        naive_past = (datetime.now(timezone.utc) - timedelta(days=2)).replace(tzinfo=None)
        assert trial_expired(_workspace(trial_ends_at=naive_past.isoformat())) is True

        naive_future = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None)
        assert trial_expired(_workspace(trial_ends_at=naive_future.isoformat())) is False

    def test_an_empty_subscription_status_is_treated_as_a_trial(self):
        """Pre-existing rows carry '' rather than 'trialing'; they are trials
        and must still be gated, or the rule quietly exempts every old
        account."""
        assert trial_expired(_workspace(subscription_status="", trial_ends_at=_ago(1))) is True


@pytest.mark.asyncio
class TestTheEndpointsRefuse:
    async def _expired_workspace(self, db_session, user_id=USER_A_ID):
        ws = Workspaces(
            name="Acme", slug="acme", owner_id=user_id,
            plan="trial", subscription_status="trialing",
            monthly_credits=25, credits_used=0, max_seats=1,
            trial_ends_at=_ago(2),
        )
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)
        return ws

    async def test_discover_refuses_with_a_named_error(self, user_a_client, db_session):
        await self._expired_workspace(db_session)
        resp = await user_a_client.post(
            "/api/v1/discover/run", json={"query": "cafe", "city": "Leeds", "limit": 5},
        )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["error"] == "trial_expired"
        assert detail["upgrade_url"] == "/app/settings/billing"

    async def test_qualify_refuses_too(self, user_a_client, db_session):
        await self._expired_workspace(db_session)
        resp = await user_a_client.post("/api/v1/discover/qualify", json={"lead_ids": [1]})
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "trial_expired"

    async def test_saved_leads_stay_readable(self, user_a_client, db_session):
        """The paywall is on new work, not on data the customer already has."""
        await self._expired_workspace(db_session)
        assert (await user_a_client.get("/api/v1/entities/leads")).status_code == 200

    async def test_usage_reports_the_expiry_rather_than_leaving_it_inferred(
        self, user_a_client, db_session
    ):
        await self._expired_workspace(db_session)
        body = (await user_a_client.get("/api/v1/billing/usage")).json()
        assert body["trial_expired"] is True

    async def test_a_live_trial_is_not_refused(self, user_a_client, db_session):
        ws = Workspaces(
            name="Acme", slug="acme", owner_id=USER_A_ID,
            plan="trial", subscription_status="trialing",
            monthly_credits=25, credits_used=0, max_seats=1,
            trial_ends_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        )
        db_session.add(ws)
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/billing/usage")).json()
        assert body["trial_expired"] is False
