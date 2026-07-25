"""Guards on the first code that fetches attacker-influenceable URLs server-side.

A prospect's website field is not trusted input. Without the SSRF guards in
services/website_check.py, our own server would fetch our own internal network
on request and hand back the response — including the cloud metadata endpoint,
which turns SSRF into credential theft.

These tests run entirely offline: literal IPs and `localhost` resolve without
network access, so the blocking behaviour is provable in CI.
"""
import pytest

from services.website_check import (
    assert_url_is_publicly_routable,
    check_website,
    normalise_candidate_url,
    _looks_parked,
)


class TestUrlNormalisation:
    @pytest.mark.parametrize(
        "raw,expected_host",
        [
            ("example.com", "example.com"),
            ("https://example.com", "example.com"),
            ("http://example.com/path", "example.com"),
            ("  example.com  ", "example.com"),
        ],
    )
    def test_usable_values_become_absolute_urls(self, raw, expected_host):
        result = normalise_candidate_url(raw)
        assert result is not None
        assert expected_host in result
        assert result.startswith(("http://", "https://"))

    @pytest.mark.parametrize("raw", [None, "", "   ", "not a url", "localhost", "javascript:alert(1)"])
    def test_unusable_values_return_none(self, raw):
        # None means "cannot be a website", which is different from a website
        # that fails to load. Callers must keep those apart.
        assert normalise_candidate_url(raw) is None

    def test_non_http_schemes_are_rejected(self):
        assert normalise_candidate_url("file:///etc/passwd") is None
        assert normalise_candidate_url("gopher://example.com") is None


class TestSsrfGuard:
    @pytest.mark.parametrize(
        "url,label",
        [
            ("http://127.0.0.1/", "loopback"),
            ("http://127.0.0.1:8000/api/v1/entities/workspaces", "our own API"),
            ("http://localhost/", "loopback by name"),
            ("http://10.0.0.1/", "private class A"),
            ("http://192.168.1.1/", "private class C"),
            ("http://172.16.0.1/", "private class B"),
            ("http://169.254.169.254/latest/meta-data/", "cloud metadata endpoint"),
            ("http://0.0.0.0/", "unspecified"),
            ("http://[::1]/", "IPv6 loopback"),
        ],
    )
    async def test_internal_targets_are_refused(self, url, label):
        reason = await assert_url_is_publicly_routable(url)
        assert reason is not None, f"{label} was allowed: {url}"

    async def test_non_http_scheme_is_refused(self):
        assert await assert_url_is_publicly_routable("file:///etc/passwd") is not None

    async def test_unresolvable_host_is_refused(self):
        reason = await assert_url_is_publicly_routable(
            "http://this-domain-should-not-exist-bizleads-test.invalid/"
        )
        assert reason is not None


class TestCheckWebsiteRefusesInternalTargets:
    async def test_metadata_endpoint_is_blocked_not_fetched(self):
        result = await check_website("http://169.254.169.254/latest/meta-data/")

        assert result["state"] == "blocked"
        # Crucially NOT False. We refused to look, so we do not know — claiming
        # "no website" here would be a fabricated verdict.
        assert result["has_website"] is None
        assert result["status_code"] is None

    async def test_own_api_is_blocked(self):
        result = await check_website("http://127.0.0.1:8000/api/v1/entities/leads")
        assert result["state"] == "blocked"
        assert result["has_website"] is None

    async def test_unusable_input_is_invalid_not_absent(self):
        result = await check_website(None)

        assert result["state"] == "invalid"
        assert result["has_website"] is None, "no candidate URL is not evidence of no website"


class TestParkedDetection:
    @pytest.mark.parametrize(
        "body",
        [
            "<html><body>This domain is parked and may be for sale.</body></html>",
            "<html><body><h1>Buy this domain</h1></body></html>",
            "<html><body>Welcome to nginx!</body></html>",
            "<html><body>Coming soon</body></html>",
            "<html><body>Apache2 Ubuntu Default Page</body></html>",
        ],
    )
    def test_placeholder_pages_are_parked(self, body):
        assert _looks_parked(body, "https://example.com") is True

    def test_a_real_page_is_not_parked(self):
        body = (
            "<html><body>"
            + "<h1>Riverside Cafe</h1><p>Open daily from 8am. Book a table, see our menu, "
            "find us on Deansgate. We serve breakfast, lunch and coffee roasted in-house. "
            "Call us on 0113 000 0000 or email hello@example.com to enquire about events.</p>"
            * 4
            + "</body></html>"
        )
        assert _looks_parked(body, "https://example.com") is False

    def test_near_empty_response_is_parked(self):
        assert _looks_parked("", "https://example.com") is True

    def test_marker_scan_beats_the_length_heuristic(self):
        # A long parking page must still be caught.
        body = "<html><body>" + ("filler content " * 200) + "domain is for sale</body></html>"
        assert _looks_parked(body, "https://example.com") is True
