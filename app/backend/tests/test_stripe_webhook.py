"""The billing webhook decides who has paid access, so it must fail closed.

Without signature verification this endpoint is a free-subscription vending
machine: anyone could POST a fabricated "payment succeeded" event and grant
themselves the Agency plan. These tests exist to keep that door shut.

They also cover the three ways money and access diverged before this existed:
a customer who closes the tab after paying, a renewal that never resets
credits, and a cancellation that never revokes anything.
"""
import json

import pytest

from routers import stripe_webhook


class TestSignatureVerification:
    def test_an_unset_secret_disables_the_endpoint(self, monkeypatch):
        """Absent config must disable, never accept anything."""
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)

        with pytest.raises(Exception) as exc:
            stripe_webhook._verify(b"{}", "sig")
        assert "503" in str(exc.value) or "not configured" in str(exc.value).lower()

    def test_a_missing_signature_header_is_rejected(self, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

        with pytest.raises(Exception):
            stripe_webhook._verify(b"{}", None)

    def test_a_forged_signature_is_rejected(self, monkeypatch):
        """The whole security model in one test."""
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

        with pytest.raises(Exception):
            stripe_webhook._verify(
                json.dumps({"type": "invoice.paid"}).encode(), "t=1,v1=forged"
            )

    async def test_the_route_rejects_an_anonymous_forgery(self, anon_client, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

        response = await anon_client.post(
            "/api/v1/payments/webhook",
            json={"type": "checkout.session.completed"},
            headers={"Stripe-Signature": "t=1,v1=forged"},
        )

        assert response.status_code == 400, "a forged event must never be applied"


class TestEntitlements:
    """Plan changes must move credits, seats AND the period together."""

    class _Workspace:
        plan = "trial"
        monthly_credits = 25
        max_seats = 1
        credits_used = 19
        credits_reset_at = ""
        id = 1

    def test_upgrading_grants_the_new_plan(self):
        ws = self._Workspace()

        stripe_webhook._apply_plan(ws, "pro")

        assert (ws.plan, ws.monthly_credits, ws.max_seats) == ("pro", 1500, 3)

    def test_a_new_period_starts_unused(self):
        """The renewal bug: month two charged the card and left the customer
        at zero credits because nothing reset usage."""
        ws = self._Workspace()
        ws.credits_used = 300

        stripe_webhook._apply_plan(ws, "solo")

        assert ws.credits_used == 0
        assert ws.credits_reset_at, "a period with no end date never resets again"

    def test_an_unknown_plan_changes_nothing(self):
        """Better to leave entitlements alone than to guess at them."""
        ws = self._Workspace()

        stripe_webhook._apply_plan(ws, "enterprise-custom")

        assert (ws.plan, ws.monthly_credits, ws.credits_used) == ("trial", 25, 19)

    @pytest.mark.parametrize("plan,credits,seats", [
        ("solo", 300, 1), ("pro", 1500, 3), ("agency", 5000, 10),
    ])
    def test_every_sold_plan_has_entitlements(self, plan, credits, seats):
        """A plan sold on the pricing page with no entitlements here would
        take the customer's money and grant them nothing."""
        assert stripe_webhook.PLAN_ENTITLEMENTS[plan] == {"credits": credits, "seats": seats}


class TestEventCoverage:
    @pytest.mark.parametrize("event", [
        "checkout.session.completed",   # customer closed the tab after paying
        "invoice.paid",                 # renewal
        "invoice.payment_failed",       # card declined
        "customer.subscription.deleted",  # cancellation
        "customer.subscription.updated",
    ])
    def test_the_events_that_change_access_are_handled(self, event):
        assert event in stripe_webhook.HANDLED_EVENTS
