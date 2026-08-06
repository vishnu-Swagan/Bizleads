"""The signup gate, the multi-account signals, and the admin actions.

Two properties matter more than the rest and are tested hardest.

**Nobody who already works stops working.** A signup gate that retroactively
suspended existing customers would be a far worse outcome than a few
unreviewed legacy accounts, so "no approval row" must mean allowed, forever.

**The signals accuse nobody.** A shared IP is a reason to look, not a finding
of guilt: offices, families, universities and anyone behind corporate NAT
share addresses legitimately. Nothing here may block an account on its own.

The VPN case is asserted as *not configured* rather than as working, because
detecting a VPN needs a reputation provider and this codebase does not have
one. Asserting a stub returns False would encode a claim nothing establishes.
"""
import json

import pytest
from sqlalchemy import select

from models.account_approvals import Account_approvals
from models.account_signals import Account_signals
from models.auth import User
from models.leads import Leads
from models.workspaces import Workspaces
from services import account_review
from tests.conftest import USER_A_EMAIL, USER_A_ID, USER_B_ID


@pytest.fixture
def as_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", USER_A_EMAIL)


async def _pending(db_session, user_id=USER_B_ID, email="new@example.com", credits=0):
    ws = Workspaces(
        name="New", slug=user_id[:8], owner_id=user_id, plan="trial",
        subscription_status="trialing", monthly_credits=credits, credits_used=0, max_seats=1,
    )
    db_session.add(ws)
    db_session.add(User(id=user_id, email=email, role="user"))
    await db_session.commit()
    await db_session.refresh(ws)

    approval = await account_review.open_pending(
        db_session, user_id=user_id, email=email, workspace_id=ws.id
    )
    await db_session.commit()
    return ws, approval


class TestExistingAccountsAreNotDisturbed:
    def test_no_approval_row_means_allowed(self):
        """The property that keeps this from being a self-inflicted outage."""
        assert account_review.access_state(None) == "allowed"

    async def test_a_legacy_account_can_still_search(self, user_a_client, db_session, monkeypatch):
        """An account that predates the gate has no row and must be untouched."""
        db_session.add(Workspaces(
            name="Legacy", slug="legacy", owner_id=USER_A_ID, plan="trial",
            subscription_status="trialing", monthly_credits=25, credits_used=0, max_seats=1,
        ))
        await db_session.commit()

        import routers.discover as discover
        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

        async def _empty(**kwargs):
            return []

        monkeypatch.setattr(discover, "search_places", _empty)

        response = await user_a_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )
        assert response.status_code == 200


class TestTheGate:
    async def test_a_clean_signup_is_approved_without_waiting(
        self, user_b_client, db_session, monkeypatch
    ):
        """The default. Holding an ordinary customer makes the queue the
        bottleneck on growth, and most of them do not come back to find out
        whether anybody got round to them."""
        ws, _ = await _pending(db_session)

        import routers.discover as discover
        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

        async def _empty(**kwargs):
            return []

        monkeypatch.setattr(discover, "search_places", _empty)

        response = await user_b_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )

        assert response.status_code == 200
        approval = await account_review.get_approval(db_session, USER_B_ID)
        await db_session.refresh(approval)
        assert approval.status == account_review.STATUS_APPROVED
        await db_session.refresh(ws)
        assert ws.monthly_credits == account_review.FREE_CREDITS

    async def test_a_flagged_signup_still_waits(self, user_b_client, db_session, monkeypatch):
        """Only the suspicious ones reach the queue, which is what keeps it
        small enough to actually be worked."""
        await _pending(db_session)

        import routers.discover as discover
        # Pin the address the request reports, then put three other accounts
        # on it. Assessment reads the address off the request, so seeding
        # signals without pinning it would flag nothing.
        monkeypatch.setattr(discover, "describe", lambda request: ("203.0.113.50", None, None))
        for i in range(3):
            await account_review.record_signal(
                db_session, user_id=f"farm{i}", email=f"farm{i}@example.com", ip="203.0.113.50"
            )
        await db_session.commit()

        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

        response = await user_b_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )

        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "account_pending_approval"

    async def test_holding_everything_can_be_switched_on(
        self, user_b_client, db_session, monkeypatch
    ):
        """A business decision, reversible without a deploy."""
        monkeypatch.setenv("HOLD_ALL_SIGNUPS_FOR_REVIEW", "true")
        await _pending(db_session)

        import routers.discover as discover
        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

        response = await user_b_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )

        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "account_pending_approval"

    async def test_a_pending_account_is_refused_and_told_why(
        self, user_b_client, db_session, monkeypatch
    ):
        monkeypatch.setenv("HOLD_ALL_SIGNUPS_FOR_REVIEW", "true")
        await _pending(db_session)

        import routers.discover as discover
        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

        response = await user_b_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["error"] == "account_pending_approval"
        assert "25" in detail["message"]

    async def test_a_blocked_account_is_told_it_is_blocked_not_pending(
        self, user_b_client, db_session, monkeypatch
    ):
        """Saying "pending review" to somebody blocked leaves them refreshing
        a page that will never change."""
        _, approval = await _pending(db_session)
        approval.status = account_review.STATUS_BLOCKED
        await db_session.commit()

        import routers.discover as discover
        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

        response = await user_b_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )

        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "account_blocked"

    async def test_an_approved_account_proceeds(self, user_b_client, db_session, monkeypatch):
        # Credits granted alongside the status, because that is what approval
        # does. Setting only the status leaves a workspace that clears the
        # gate and is then refused for a zero balance — correct behaviour,
        # but not what this test is about.
        ws, approval = await _pending(db_session)
        approval.status = account_review.STATUS_APPROVED
        ws.monthly_credits = account_review.FREE_CREDITS
        await db_session.commit()

        import routers.discover as discover
        monkeypatch.setattr(discover, "is_discovery_configured", lambda: True)

        async def _empty(**kwargs):
            return []

        monkeypatch.setattr(discover, "search_places", _empty)

        response = await user_b_client.post(
            "/api/v1/discover/run", json={"country": "United Kingdom"}
        )
        assert response.status_code == 200


class TestTheSignals:
    async def test_one_address_is_recorded_once_per_account(self, db_session):
        """The table holds the edge, not one row per request."""
        for _ in range(3):
            await account_review.record_signal(
                db_session, user_id=USER_A_ID, email=USER_A_EMAIL, ip="203.0.113.9"
            )
        await db_session.commit()

        rows = (await db_session.execute(select(Account_signals))).scalars().all()
        assert len(rows) == 1
        assert rows[0].hits == 3

    async def test_several_accounts_on_one_address_are_flagged(self, db_session):
        for i in range(3):
            await account_review.record_signal(
                db_session, user_id=f"u{i}", email=f"u{i}@example.com", ip="203.0.113.9"
            )
        await db_session.commit()

        risk = await account_review.assess(
            db_session, user_id="u3", email="u3@example.com", ip="203.0.113.9"
        )

        assert risk["severity"] == "high"
        assert any(f["code"] == "shared_ip" for f in risk["flags"])

    async def test_two_accounts_on_one_address_is_only_a_low_note(self, db_session):
        """A couple at home must not be reported as a farm."""
        await account_review.record_signal(
            db_session, user_id="u1", email="one@example.com", ip="203.0.113.9"
        )
        await db_session.commit()

        risk = await account_review.assess(
            db_session, user_id="u2", email="two@example.com", ip="203.0.113.9"
        )

        assert risk["severity"] == "low"
        assert all(f["code"] != "shared_ip" for f in risk["flags"])

    async def test_a_lone_account_is_clean(self, db_session):
        risk = await account_review.assess(
            db_session, user_id="solo", email="solo@example.com", ip="203.0.113.1"
        )
        assert risk["severity"] == "clean"
        assert risk["flags"] == []

    async def test_a_disposable_address_is_flagged(self, db_session):
        risk = await account_review.assess(
            db_session, user_id="x", email="throwaway@mailinator.com", ip="203.0.113.2"
        )
        assert risk["severity"] == "high"
        assert any(f["code"] == "disposable_email" for f in risk["flags"])

    async def test_vpn_detection_reports_that_it_is_not_configured(self, monkeypatch):
        """Not "clean" — a check that never ran must not read as a pass."""
        monkeypatch.delenv("IP_REPUTATION_API_KEY", raising=False)
        result = account_review.vpn_check("203.0.113.5")
        assert result["configured"] is False
        assert result["is_vpn"] is None

    async def test_a_flagged_signup_reaches_the_activity_trail(self, db_session):
        """This is the notification: the trail is where operators already look."""
        for i in range(3):
            await account_review.record_signal(
                db_session, user_id=f"f{i}", email=f"f{i}@example.com", ip="198.51.100.7"
            )
        await db_session.commit()

        await account_review.flag_if_suspicious(
            db_session, user_id="f9", email="f9@example.com", ip="198.51.100.7"
        )
        await db_session.commit()

        from models.activity_events import Activity_events
        rows = (
            await db_session.execute(
                select(Activity_events).where(
                    Activity_events.action == account_review.ACCOUNT_FLAGGED
                )
            )
        ).scalars().all()

        assert len(rows) == 1
        assert rows[0].status == "failed"
        assert "share this IP" in rows[0].summary

    async def test_a_clean_signup_raises_no_alert(self, db_session):
        """An alert on every shared office connection trains people to ignore
        all of them."""
        await account_review.flag_if_suspicious(
            db_session, user_id="quiet", email="quiet@example.com", ip="198.51.100.99"
        )
        await db_session.commit()

        from models.activity_events import Activity_events
        rows = (await db_session.execute(select(Activity_events))).scalars().all()
        assert rows == []


class TestAdminDecisions:
    async def test_approving_grants_the_free_credits(self, user_a_client, db_session, as_admin):
        ws, _ = await _pending(db_session)

        response = await user_a_client.post(
            f"/api/v1/admin/approvals/{USER_B_ID}/approve", json={"reason": "looks fine"}
        )

        assert response.status_code == 200
        assert response.json()["credits_granted"] == account_review.FREE_CREDITS

        await db_session.refresh(ws)
        assert ws.monthly_credits == account_review.FREE_CREDITS

    async def test_approving_twice_does_not_grant_twice(
        self, user_a_client, db_session, as_admin
    ):
        ws, _ = await _pending(db_session)

        await user_a_client.post(f"/api/v1/admin/approvals/{USER_B_ID}/approve", json={})
        await user_a_client.post(f"/api/v1/admin/approvals/{USER_B_ID}/approve", json={})

        await db_session.refresh(ws)
        assert ws.monthly_credits == account_review.FREE_CREDITS

    async def test_the_decision_records_who_made_it(self, user_a_client, db_session, as_admin):
        await _pending(db_session)

        await user_a_client.post(
            f"/api/v1/admin/approvals/{USER_B_ID}/approve", json={"reason": "verified by phone"}
        )

        approval = await account_review.get_approval(db_session, USER_B_ID)
        await db_session.refresh(approval)
        assert approval.decided_by == USER_A_EMAIL
        assert approval.reason == "verified by phone"
        assert approval.decided_at is not None

    async def test_blocking_then_unblocking(self, user_a_client, db_session, as_admin):
        await _pending(db_session)

        await user_a_client.post(f"/api/v1/admin/approvals/{USER_B_ID}/block", json={})
        approval = await account_review.get_approval(db_session, USER_B_ID)
        await db_session.refresh(approval)
        assert account_review.access_state(approval) == "blocked"

        await user_a_client.post(f"/api/v1/admin/approvals/{USER_B_ID}/unblock", json={})
        await db_session.refresh(approval)
        assert account_review.access_state(approval) == "allowed"

    async def test_a_legacy_account_can_still_be_blocked(
        self, user_a_client, db_session, as_admin
    ):
        """Otherwise the oldest accounts are the only ones that cannot be
        suspended, which is the wrong way round."""
        db_session.add(User(id="legacy-user", email="legacy@example.com", role="user"))
        await db_session.commit()

        response = await user_a_client.post(
            "/api/v1/admin/approvals/legacy-user/block", json={"reason": "abuse"}
        )

        assert response.status_code == 200
        approval = await account_review.get_approval(db_session, "legacy-user")
        assert account_review.access_state(approval) == "blocked"

    async def test_a_non_admin_cannot_approve_anybody(self, user_b_client, db_session, monkeypatch):
        monkeypatch.delenv("ADMIN_EMAILS", raising=False)
        await _pending(db_session)

        response = await user_b_client.post(
            f"/api/v1/admin/approvals/{USER_B_ID}/approve", json={}
        )
        assert response.status_code == 403

    async def test_approvals_list_shows_the_evidence(self, user_a_client, db_session, as_admin):
        await _pending(db_session)
        for i in range(3):
            await account_review.record_signal(
                db_session, user_id=f"n{i}", email=f"n{i}@example.com", ip="198.51.100.4"
            )
        await account_review.record_signal(
            db_session, user_id=USER_B_ID, email="new@example.com", ip="198.51.100.4"
        )
        await db_session.commit()

        body = (await user_a_client.get("/api/v1/admin/approvals?status=pending")).json()

        assert body["total"] == 1
        assert body["free_credits"] == account_review.FREE_CREDITS
        assert body["items"][0]["risk"]["severity"] == "high"


class TestDeletion:
    async def test_it_requires_the_email_typed_back(self, user_a_client, db_session, as_admin):
        """There is no undo, so a `true` flag is not enough of a guard."""
        await _pending(db_session)

        response = await user_a_client.request(
            "DELETE", f"/api/v1/admin/accounts/{USER_B_ID}",
            json={"confirm_email": "wrong@example.com"},
        )

        assert response.status_code == 400
        assert (await db_session.execute(select(User).where(User.id == USER_B_ID))).scalars().first()

    async def test_it_removes_the_account_and_its_data(
        self, user_a_client, db_session, as_admin
    ):
        await _pending(db_session)
        db_session.add(Leads(
            user_id=USER_B_ID, business_name="Doomed", category="Cafe",
            location="Leeds", country="UK",
        ))
        await db_session.commit()

        response = await user_a_client.request(
            "DELETE", f"/api/v1/admin/accounts/{USER_B_ID}",
            json={"confirm_email": "new@example.com", "reason": "requested"},
        )

        assert response.status_code == 200
        assert (await db_session.execute(select(User).where(User.id == USER_B_ID))).scalars().first() is None
        assert (await db_session.execute(select(Leads).where(Leads.user_id == USER_B_ID))).scalars().all() == []
        assert (await db_session.execute(
            select(Workspaces).where(Workspaces.owner_id == USER_B_ID)
        )).scalars().all() == []

    async def test_the_trail_outlives_the_account(self, user_a_client, db_session, as_admin):
        """Which is why activity_events stores an email, not a foreign key."""
        await _pending(db_session)

        await user_a_client.request(
            "DELETE", f"/api/v1/admin/accounts/{USER_B_ID}",
            json={"confirm_email": "new@example.com", "reason": "spam"},
        )

        from models.activity_events import Activity_events
        rows = (
            await db_session.execute(
                select(Activity_events).where(Activity_events.action == "account.deleted")
            )
        ).scalars().all()

        assert len(rows) == 1
        assert json.loads(rows[0].metadata_json)["email"] == "new@example.com"

    async def test_an_admin_cannot_delete_themselves(self, user_a_client, db_session, as_admin):
        db_session.add(User(id=USER_A_ID, email=USER_A_EMAIL, role="user"))
        await db_session.commit()

        response = await user_a_client.request(
            "DELETE", f"/api/v1/admin/accounts/{USER_A_ID}",
            json={"confirm_email": USER_A_EMAIL},
        )

        assert response.status_code == 400
        assert "your own account" in response.json()["detail"]
