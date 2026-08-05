"""The operators' console, and who may reach it.

The console reads across every tenant — that is what it is for — which makes
its authorisation gate the highest-consequence check in the application. Every
other endpoint leaks one workspace when it goes wrong. This one leaks all of
them. So the refusal cases are tested first and in more detail than the
happy path.

The separation between ADMIN_EMAILS and UNLIMITED_CREDIT_EMAILS is pinned
here too. Those lists hold the same three addresses today, which is exactly
why a test has to state that one does not imply the other: the day somebody
adds a fourth address to the billing list, nothing should quietly hand them
every customer's data.
"""
import json

import pytest
from sqlalchemy import select

from models.activity_events import Activity_events
from models.auth import User
from models.leads import Leads
from models.workspaces import Workspaces
from services import activity
from services.admin_access import admin_access_configured, is_admin_email
from tests.conftest import USER_A_EMAIL, USER_A_ID, USER_B_EMAIL

ADMIN_ROUTES = [
    "/api/v1/admin/overview",
    "/api/v1/admin/activity",
    "/api/v1/admin/activity/actions",
    "/api/v1/admin/users",
    "/api/v1/admin/workspaces",
    "/api/v1/admin/revenue",
    "/api/v1/admin/health",
    "/api/v1/admin/export/activity.csv",
    "/api/v1/admin/export/users.csv",
    "/api/v1/admin/export/workspaces.csv",
]


@pytest.fixture
def as_admin(monkeypatch):
    """Put the test user on the admin allowlist."""
    monkeypatch.setenv("ADMIN_EMAILS", USER_A_EMAIL)


@pytest.fixture
def no_admins(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)


class TestWhoMayReachTheConsole:
    @pytest.mark.parametrize("route", ADMIN_ROUTES)
    async def test_an_ordinary_account_is_refused_everywhere(
        self, user_a_client, no_admins, route
    ):
        """Parametrised over every route deliberately.

        The failure this guards against is a new admin endpoint shipping
        without the gate, and a test that only covers /overview would not
        notice. The router declares the dependency once for exactly this
        reason; this asserts the declaration is actually in force.
        """
        response = await user_a_client.get(route)
        assert response.status_code == 403

    async def test_an_unauthenticated_caller_is_refused(self, anon_client, no_admins):
        response = await anon_client.get("/api/v1/admin/overview")
        assert response.status_code == 401

    async def test_an_allowlisted_address_is_admitted(self, user_a_client, as_admin):
        response = await user_a_client.get("/api/v1/admin/overview")
        assert response.status_code == 200

    async def test_a_different_account_is_still_refused(
        self, user_b_client, monkeypatch
    ):
        """Being on the list admits you, not everybody."""
        monkeypatch.setenv("ADMIN_EMAILS", USER_A_EMAIL)
        response = await user_b_client.get("/api/v1/admin/overview")
        assert response.status_code == 403

    async def test_nobody_is_admin_when_the_list_is_unset(self, user_a_client, no_admins):
        """Default deny.

        Unset must not mean "open to the first account that finds the URL",
        which is what a truthy-by-default check would produce for anyone
        deploying this without knowing the variable exists.
        """
        assert admin_access_configured() is False
        assert is_admin_email(USER_A_EMAIL) is False
        assert (await user_a_client.get("/api/v1/admin/overview")).status_code == 403

    async def test_matching_ignores_case_and_whitespace(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "  Ops@Example.COM , second@example.com ")
        assert is_admin_email("ops@example.com") is True
        assert is_admin_email("OPS@EXAMPLE.COM") is True
        assert is_admin_email("second@example.com") is True
        assert is_admin_email("third@example.com") is False

    async def test_an_empty_entry_matches_nobody(self, monkeypatch):
        """"a@b.com,," must not admit a token carrying no email at all."""
        monkeypatch.setenv("ADMIN_EMAILS", "a@b.com,,")
        assert is_admin_email("") is False
        assert is_admin_email("a@b.com") is True

    async def test_billing_exemption_does_not_grant_admin(
        self, user_a_client, monkeypatch
    ):
        """The separation that matters.

        entitlements.py removes metering, not authorisation. An address on
        the unlimited-credits list must not reach the console unless it is
        also, separately, on the admin list.
        """
        monkeypatch.setenv("UNLIMITED_CREDIT_EMAILS", USER_A_EMAIL)
        monkeypatch.delenv("ADMIN_EMAILS", raising=False)

        assert (await user_a_client.get("/api/v1/admin/overview")).status_code == 403

    async def test_revoking_takes_effect_without_a_restart(self, user_a_client, monkeypatch):
        """Read at call time, not import time.

        The moment you want to remove somebody's access is not the moment to
        wait for a deploy.
        """
        monkeypatch.setenv("ADMIN_EMAILS", USER_A_EMAIL)
        assert (await user_a_client.get("/api/v1/admin/overview")).status_code == 200

        monkeypatch.setenv("ADMIN_EMAILS", "somebody-else@example.com")
        assert (await user_a_client.get("/api/v1/admin/overview")).status_code == 403


class TestRecordingActivity:
    async def test_an_event_is_stored(self, db_session):
        await activity.record(
            db_session,
            activity.SEARCH_RUN,
            user_id=USER_A_ID,
            user_email=USER_A_EMAIL,
            workspace_id=1,
            summary="Searched dentists in Leeds",
            metadata={"results": 12},
        )
        await db_session.commit()

        row = (await db_session.execute(select(Activity_events))).scalars().one()
        assert row.action == activity.SEARCH_RUN
        assert row.user_email == USER_A_EMAIL
        assert json.loads(row.metadata_json)["results"] == 12
        assert row.status == "ok"

    async def test_unserialisable_metadata_does_not_lose_the_event(self, db_session):
        """The event matters more than one field of its payload."""
        await activity.record(
            db_session,
            activity.LEAD_SAVED,
            user_id=USER_A_ID,
            metadata={"when": object()},
        )
        await db_session.commit()

        row = (await db_session.execute(select(Activity_events))).scalars().one()
        assert row.action == activity.LEAD_SAVED

    async def test_recording_never_raises(self, db_session):
        """Observing an action must not be able to break it.

        A broken audit write here would otherwise turn into a failed search
        for a paying customer — the feature built for visibility taking the
        product down.
        """
        await activity.record(db_session, "x" * 5000, metadata={"a": "b" * 100000})
        # Reaching this line without an exception is the assertion.

    async def test_an_oversized_payload_is_truncated(self, db_session):
        await activity.record(db_session, activity.SEARCH_RUN, metadata={"blob": "z" * 50000})
        await db_session.commit()

        row = (await db_session.execute(select(Activity_events))).scalars().first()
        assert row is not None
        assert len(row.metadata_json) <= activity.MAX_METADATA_CHARS


class TestTheOverview:
    async def test_it_counts_what_happened(self, user_a_client, db_session, as_admin):
        for i in range(3):
            await activity.record(
                db_session, activity.SEARCH_RUN, user_id=USER_A_ID, user_email=USER_A_EMAIL
            )
        await activity.record(
            db_session, activity.SEARCH_FAILED, user_id=USER_A_ID, status="failed"
        )
        await activity.record(db_session, activity.OUTREACH_SENT, user_id=USER_A_ID)
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/admin/overview")).json()

        assert body["today"]["searches"] == 3
        assert body["today"]["searches_failed"] == 1
        assert body["today"]["outreach_sent"] == 1
        assert body["last_7_days"]["searches"] == 3

    async def test_leads_with_an_email_are_counted_separately(
        self, user_a_client, db_session, as_admin
    ):
        """The number that says whether a search produced leads or just rows."""
        db_session.add(Leads(
            user_id=USER_A_ID, business_name="With", category="Cafe",
            location="Leeds", country="UK", contact_email="hi@with.example",
        ))
        db_session.add(Leads(
            user_id=USER_A_ID, business_name="Without", category="Cafe",
            location="Leeds", country="UK", contact_email="",
        ))
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/admin/overview")).json()

        assert body["all_time"]["leads_discovered"] == 2
        assert body["all_time"]["leads_with_email"] == 1

    async def test_active_users_counts_people_not_accounts(
        self, user_a_client, db_session, as_admin
    ):
        """A registered account that never did anything is not an active user."""
        db_session.add(User(id="dormant", email="dormant@example.com", role="user"))
        await activity.record(db_session, activity.SEARCH_RUN, user_id=USER_A_ID)
        await activity.record(db_session, activity.SEARCH_RUN, user_id=USER_A_ID)
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/admin/overview")).json()

        assert body["totals"]["active_users_7d"] == 1


class TestTheActivityFeed:
    async def _seed(self, db_session):
        await activity.record(
            db_session, activity.SEARCH_RUN, user_id=USER_A_ID,
            user_email=USER_A_EMAIL, workspace_id=1, summary="Searched dentists in Leeds",
        )
        await activity.record(
            db_session, activity.OUTREACH_SENT, user_id="user-b",
            user_email=USER_B_EMAIL, workspace_id=2, summary="Sent outreach to a@b.com",
        )
        await activity.record(
            db_session, activity.SEARCH_FAILED, user_id=USER_A_ID,
            user_email=USER_A_EMAIL, status="failed", summary="Search failed: provider down",
        )
        await db_session.commit()

    async def test_newest_first(self, user_a_client, db_session, as_admin):
        await self._seed(db_session)
        items = (await user_a_client.get("/api/v1/admin/activity")).json()["items"]
        assert items[0]["action"] == activity.SEARCH_FAILED

    async def test_filter_by_action(self, user_a_client, db_session, as_admin):
        await self._seed(db_session)
        body = (
            await user_a_client.get(f"/api/v1/admin/activity?action={activity.SEARCH_RUN}")
        ).json()
        assert body["total"] == 1
        assert body["items"][0]["action"] == activity.SEARCH_RUN

    async def test_filter_by_status_finds_failures(self, user_a_client, db_session, as_admin):
        await self._seed(db_session)
        body = (await user_a_client.get("/api/v1/admin/activity?status=failed")).json()
        assert body["total"] == 1

    async def test_filter_by_user(self, user_a_client, db_session, as_admin):
        await self._seed(db_session)
        body = (await user_a_client.get(f"/api/v1/admin/activity?user={USER_B_EMAIL}")).json()
        assert body["total"] == 1
        assert body["items"][0]["user_email"] == USER_B_EMAIL

    async def test_free_text_search(self, user_a_client, db_session, as_admin):
        await self._seed(db_session)
        body = (await user_a_client.get("/api/v1/admin/activity?q=dentists")).json()
        assert body["total"] == 1

    async def test_pagination_reports_the_true_total(self, user_a_client, db_session, as_admin):
        await self._seed(db_session)
        body = (await user_a_client.get("/api/v1/admin/activity?limit=1")).json()
        assert len(body["items"]) == 1
        assert body["total"] == 3

    async def test_available_actions_are_derived_from_the_data(
        self, user_a_client, db_session, as_admin
    ):
        await self._seed(db_session)
        items = (await user_a_client.get("/api/v1/admin/activity/actions")).json()["items"]
        assert {i["action"] for i in items} == {
            activity.SEARCH_RUN, activity.OUTREACH_SENT, activity.SEARCH_FAILED
        }


class TestRevenue:
    async def test_mrr_counts_only_paying_plans(self, user_a_client, db_session, as_admin):
        for plan, owner in (("trial", "o1"), ("solo", "o2"), ("pro", "o3")):
            db_session.add(Workspaces(
                name=f"{plan} ws", slug=plan, owner_id=owner, plan=plan,
                subscription_status="active" if plan != "trial" else "trialing",
                monthly_credits=25, credits_used=0, max_seats=1,
            ))
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/admin/revenue")).json()

        # 29.00 + 79.00, with the trial contributing nothing.
        assert body["mrr"] == 108.0
        assert body["paying_workspaces"] == 2
        assert body["total_workspaces"] == 3

    async def test_the_estimate_is_labelled_as_one(self, user_a_client, db_session, as_admin):
        """It ignores discounts, refunds and failed payments.

        A dashboard number that looks like accounting gets used like
        accounting, so it has to say what it is.
        """
        body = (await user_a_client.get("/api/v1/admin/revenue")).json()
        assert body["mrr_is_estimated"] is True
        assert "Stripe is the source of truth" in body["mrr_note"]


class TestHealth:
    async def test_it_reports_the_failure_rate(self, user_a_client, db_session, as_admin):
        await activity.record(db_session, activity.SEARCH_RUN, user_id=USER_A_ID)
        await activity.record(db_session, activity.SEARCH_RUN, user_id=USER_A_ID)
        await activity.record(db_session, activity.SEARCH_RUN, user_id=USER_A_ID)
        await activity.record(db_session, activity.SEARCH_FAILED, user_id=USER_A_ID, status="failed")
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/admin/health")).json()

        assert body["searches_24h"] == 3
        assert body["searches_failed_24h"] == 1
        assert body["search_failure_rate_24h"] == 25.0

    async def test_recent_failures_are_listed(self, user_a_client, db_session, as_admin):
        await activity.record(
            db_session, activity.SEARCH_FAILED, user_id=USER_A_ID,
            status="failed", summary="Search failed: provider timeout",
        )
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/admin/health")).json()

        assert len(body["recent_failures"]) == 1
        assert "provider timeout" in body["recent_failures"][0]["summary"]


class TestCsvExport:
    async def test_activity_export_has_headers_and_rows(
        self, user_a_client, db_session, as_admin
    ):
        await activity.record(
            db_session, activity.SEARCH_RUN, user_id=USER_A_ID,
            user_email=USER_A_EMAIL, summary="Searched cafes in Leeds",
        )
        await db_session.commit()

        response = await user_a_client.get("/api/v1/admin/export/activity.csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        text = response.text
        assert "When,Action,Status" in text
        assert "Searched cafes in Leeds" in text

    async def test_a_value_containing_a_comma_is_quoted(
        self, user_a_client, db_session, as_admin
    ):
        """Same failure the leads export had: unquoted commas shift columns."""
        await activity.record(
            db_session, activity.SEARCH_RUN, user_id=USER_A_ID,
            summary="Searched dentists in Soho, London",
        )
        await db_session.commit()

        text = (await user_a_client.get("/api/v1/admin/export/activity.csv")).text
        assert '"Searched dentists in Soho, London"' in text

    async def test_a_formula_is_neutralised(self, user_a_client, db_session, as_admin):
        """Error text and business names come off third-party sites."""
        await activity.record(
            db_session, activity.SEARCH_FAILED, user_id=USER_A_ID,
            status="failed", summary='=HYPERLINK("http://evil","x")',
        )
        await db_session.commit()

        text = (await user_a_client.get("/api/v1/admin/export/activity.csv")).text
        assert "'=HYPERLINK" in text

    async def test_export_is_admin_gated_like_everything_else(self, user_a_client, no_admins):
        response = await user_a_client.get("/api/v1/admin/export/users.csv")
        assert response.status_code == 403
