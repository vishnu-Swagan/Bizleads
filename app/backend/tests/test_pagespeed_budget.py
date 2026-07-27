"""A deep audit must never cost the user their whole request.

PageSpeed genuinely renders the page, so it takes 10-20 seconds per URL and
sometimes far longer. Qualification runs per lead, so a batch of ten would
occupy minutes while the browser gave up after two — and the credits were
already charged by then. The batch audits while a budget lasts, then settles
for the free heuristic tier.

Degrading is honest, not lossy: evidence_tier records which tier produced each
score, and the response reports how many audits were skipped.
"""
import pytest

from routers import discover
from services import pagespeed


class TestConfiguration:
    def test_the_key_is_read_at_call_time(self, monkeypatch):
        """As a module constant it was captured at import and unreachable to
        a .env loaded later — the bug that already bit the MapBox token and
        the SMTP credentials."""
        monkeypatch.delenv("PAGESPEED_API_KEY", raising=False)
        assert pagespeed.is_pagespeed_configured() is False

        monkeypatch.setenv("PAGESPEED_API_KEY", "a-key-set-after-import")
        assert pagespeed.is_pagespeed_configured() is True

    def test_a_blank_key_does_not_count_as_configured(self, monkeypatch):
        monkeypatch.setenv("PAGESPEED_API_KEY", "   ")
        assert pagespeed.is_pagespeed_configured() is False

    def test_the_per_request_timeout_leaves_room_for_a_batch(self):
        """One slow URL must not be able to consume the whole budget."""
        assert pagespeed.AUDIT_TIMEOUT_SECONDS <= 30


class TestBudget:
    def test_the_budget_fits_inside_the_client_timeout(self):
        """A batch that returns nothing after charging credits is the worst
        possible outcome, so the budget must expire before the client does."""
        CLIENT_TIMEOUT_SECONDS = 120
        assert discover.AUDIT_BUDGET_SECONDS < CLIENT_TIMEOUT_SECONDS

    def test_the_budget_allows_several_audits(self):
        """Too small a budget would make the key pointless."""
        assert discover.AUDIT_BUDGET_SECONDS >= pagespeed.AUDIT_TIMEOUT_SECONDS * 2

    def test_a_full_batch_cannot_exceed_the_client_timeout(self):
        """The scenario that made enabling the key unsafe: ten leads at the
        old 60s timeout was up to ten minutes against a two-minute client."""
        worst_case = discover.AUDIT_BUDGET_SECONDS + pagespeed.AUDIT_TIMEOUT_SECONDS
        assert worst_case < 120, "a batch could still outlive the client"


@pytest.mark.asyncio
async def test_qualification_can_be_asked_to_skip_the_audit(monkeypatch):
    """The switch the budget depends on."""
    called = False

    async def _audit(*args, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr("services.qualification.audit_website", _audit)
    monkeypatch.setattr("services.qualification.is_pagespeed_configured", lambda: True)

    from services.qualification import qualify_website
    await qualify_website("not-a-real-url", allow_audit=False)

    assert called is False, "allow_audit=False still called PageSpeed"
