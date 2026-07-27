"""The scheduled-run endpoint must fail closed.

Unlike every other route, no user is present here — it runs work on behalf of
every account. An accidentally-open version would let anyone spend other
people's credits, so the secret check is the only thing standing between this
endpoint and that. These tests exist to keep it standing.
"""
import pytest

from routers import automation_cron


@pytest.fixture(autouse=True)
def _no_secret_by_default(monkeypatch):
    monkeypatch.delenv("AUTOMATION_CRON_SECRET", raising=False)


class TestItFailsClosed:
    def test_an_unset_secret_disables_the_endpoint(self):
        """Absent config must disable, never open.

        The dangerous reading of "no secret configured" is "no check needed".
        """
        with pytest.raises(Exception) as exc:
            automation_cron._verify_secret("anything")
        assert "401" in str(exc.value) or "disabled" in str(exc.value).lower()

    def test_an_unset_secret_rejects_even_an_empty_header(self, monkeypatch):
        with pytest.raises(Exception):
            automation_cron._verify_secret(None)

    def test_a_wrong_secret_is_rejected(self, monkeypatch):
        monkeypatch.setenv("AUTOMATION_CRON_SECRET", "correct-horse-battery-staple")
        with pytest.raises(Exception):
            automation_cron._verify_secret("wrong")

    def test_a_missing_header_is_rejected_when_configured(self, monkeypatch):
        monkeypatch.setenv("AUTOMATION_CRON_SECRET", "correct-horse-battery-staple")
        with pytest.raises(Exception):
            automation_cron._verify_secret(None)

    def test_a_prefix_of_the_secret_is_rejected(self, monkeypatch):
        """Guards against a comparison that stops at the shorter string."""
        monkeypatch.setenv("AUTOMATION_CRON_SECRET", "correct-horse-battery-staple")
        with pytest.raises(Exception):
            automation_cron._verify_secret("correct-horse")

    def test_the_correct_secret_passes(self, monkeypatch):
        monkeypatch.setenv("AUTOMATION_CRON_SECRET", "correct-horse-battery-staple")
        automation_cron._verify_secret("correct-horse-battery-staple")  # must not raise


class TestTheRouteIsReachable:
    async def test_it_rejects_an_unauthenticated_caller(self, anon_client):
        """No Supabase session is involved, so only the secret can admit it."""
        response = await anon_client.post("/api/v1/automations/run-scheduled")
        assert response.status_code == 401

    async def test_a_signed_in_user_still_cannot_call_it_without_the_secret(self, user_a_client):
        """Being logged in must not substitute for the system secret."""
        response = await user_a_client.post("/api/v1/automations/run-scheduled")
        assert response.status_code == 401


def test_a_single_tick_is_bounded():
    """One run must not be able to occupy the worker indefinitely."""
    assert 0 < automation_cron.MAX_AUTOMATIONS_PER_TICK <= 100
