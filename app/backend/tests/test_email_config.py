"""SMTP configuration must be readable at call time and must never leak.

The settings were module-level constants evaluated at import. That put the
configuration out of reach in exactly the cases that matter: a .env loaded
after first import, a corrected variable that needs a restart to take effect,
and any test that sets credentials.

A bad SMTP_PORT was worse than it looks. int("") raised ValueError during
import, and main.py's router auto-loader swallows import errors as a warning,
so one typo silently removed every outreach endpoint from the running app.
"""
import json

import pytest

from services import email_sender

SMTP_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "SMTP_USE_TLS")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in SMTP_VARS:
        monkeypatch.delenv(var, raising=False)


def _configure(monkeypatch, **overrides):
    values = {
        "SMTP_USERNAME": "sender@gmail.com",
        "SMTP_PASSWORD": "abcdefghijklmnop",
        "SMTP_FROM_EMAIL": "sender@gmail.com",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_credentials_set_after_import_are_still_picked_up(monkeypatch):
    assert email_sender.is_email_configured() is False
    _configure(monkeypatch)
    assert email_sender.is_email_configured() is True, "config is being read at import, not at call"


def test_a_gmail_app_password_pasted_with_spaces_works(monkeypatch):
    """Google displays App Passwords as 'abcd efgh ijkl mnop'.

    The spaces are display formatting, not part of the secret. Pasting it
    verbatim is the single most common setup failure, and it surfaces as an
    opaque authentication error.
    """
    _configure(monkeypatch, SMTP_PASSWORD="abcd efgh ijkl mnop")

    assert email_sender._config()["password"] == "abcdefghijklmnop"


def test_a_malformed_port_does_not_break_the_module(monkeypatch):
    """A typo here used to unmount every outreach route at import time."""
    _configure(monkeypatch, SMTP_PORT="not-a-number")

    assert email_sender._config()["port"] == 587
    assert email_sender.is_email_configured() is True


def test_status_names_exactly_what_is_missing(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "sender@gmail.com")

    status = email_sender.get_email_config_status()

    assert status["configured"] is False
    assert set(status["missing"]) == {"SMTP_PASSWORD", "SMTP_FROM_EMAIL"}
    assert "SMTP_USERNAME" not in status["missing"]


def test_status_never_returns_the_password(monkeypatch):
    """The status feeds a browser. An App Password there reaches logs and screenshots."""
    _configure(monkeypatch, SMTP_PASSWORD="s3cr3t-app-password")

    status = email_sender.get_email_config_status()

    assert "s3cr3t-app-password" not in str(status)
    assert status["password_set"] is True, "presence must still be reportable"


@pytest.mark.asyncio
async def test_sending_without_configuration_reports_why(monkeypatch):
    result = await email_sender.send_email("owner@business.com", "Hi", "<p>Hi</p>")

    assert result["success"] is False
    assert result["error"] == "email_not_configured"


@pytest.mark.asyncio
async def test_an_invalid_recipient_is_refused_before_connecting(monkeypatch):
    _configure(monkeypatch)

    result = await email_sender.send_email("not-an-email", "Hi", "<p>Hi</p>")

    assert result["success"] is False
    assert result["error"] == "invalid_recipient"


class TestAuthFailureDiagnosis:
    """Gmail answers every credential problem with one opaque rejection.

    "Check your username and password" is close to useless against that: the
    password is usually correct, it is simply the wrong KIND of password.
    These tests keep the specific diagnosis honest.
    """

    def test_an_account_password_is_identified_by_length(self, monkeypatch):
        _configure(monkeypatch, SMTP_PASSWORD="MyRealPassword123!")

        message = email_sender.diagnose_auth_failure()

        assert "18 characters" in message
        assert "App Password" in message

    def test_a_correct_length_app_password_is_not_blamed(self, monkeypatch):
        _configure(monkeypatch, SMTP_PASSWORD="abcdefghijklmnop")

        message = email_sender.diagnose_auth_failure()

        assert "characters" not in message
        assert "apppasswords" in message, "should point at creating a fresh one"

    def test_spaces_do_not_make_a_valid_app_password_look_wrong(self, monkeypatch):
        """Google displays App Passwords with spaces; they are not part of it."""
        _configure(monkeypatch, SMTP_PASSWORD="abcd efgh ijkl mnop")

        assert "characters" not in email_sender.diagnose_auth_failure()

    def test_a_username_that_is_not_an_address_is_named(self, monkeypatch):
        _configure(monkeypatch, SMTP_USERNAME="vishnu")

        message = email_sender.diagnose_auth_failure()

        assert "not a full email address" in message

    def test_a_sender_mismatch_is_named(self, monkeypatch):
        _configure(monkeypatch, SMTP_USERNAME="me@gmail.com",
                   SMTP_FROM_EMAIL="someone-else@gmail.com")

        assert "differ" in email_sender.diagnose_auth_failure()

    def test_a_non_gmail_host_gets_generic_advice(self, monkeypatch):
        """Length rules are Gmail's; other providers must not be misdiagnosed."""
        _configure(monkeypatch, SMTP_HOST="smtp.mailgun.org", SMTP_PASSWORD="short")

        message = email_sender.diagnose_auth_failure()

        assert "App Password" not in message
        assert "smtp.mailgun.org" in message


class TestProviderSelection:
    """Which backend runs must follow configuration, not a separate flag.

    A flag nobody remembers to set is how a pasted API key silently does
    nothing while the old, broken backend keeps failing.
    """

    @pytest.fixture(autouse=True)
    def _clean_resend(self, monkeypatch):
        for var in ("RESEND_API_KEY", "RESEND_FROM_EMAIL", "EMAIL_PROVIDER"):
            monkeypatch.delenv(var, raising=False)

    def test_smtp_is_the_default(self):
        assert email_sender.active_provider() == "smtp"

    def test_a_resend_key_switches_provider_on_its_own(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
        assert email_sender.active_provider() == "resend"

    def test_an_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
        monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
        assert email_sender.active_provider() == "smtp"

    def test_resend_falls_back_to_the_smtp_sender_address(self, monkeypatch):
        """One less variable to set when migrating from SMTP."""
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
        monkeypatch.setenv("SMTP_FROM_EMAIL", "hi@torquetrendsllc.co.site")
        assert email_sender.is_email_configured() is True

    def test_a_key_without_a_sender_is_not_configured(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
        monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
        assert email_sender.is_email_configured() is False
        assert "RESEND_FROM_EMAIL" in email_sender.get_email_config_status()["missing"]

    def test_status_names_the_active_provider(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
        monkeypatch.setenv("RESEND_FROM_EMAIL", "hi@torquetrendsllc.co.site")
        status = email_sender.get_email_config_status()
        assert status["provider"] == "resend"
        assert status["configured"] is True

    def test_the_api_key_never_leaves_the_server(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_super_secret_value")
        monkeypatch.setenv("RESEND_FROM_EMAIL", "hi@torquetrendsllc.co.site")
        assert "re_super_secret_value" not in str(email_sender.get_email_config_status())


class TestResendErrors:
    """Resend's own message names the unverified domain or bad key, so it is
    surfaced rather than replaced with something vaguer."""

    @pytest.fixture(autouse=True)
    def _configured(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
        monkeypatch.setenv("RESEND_FROM_EMAIL", "hi@torquetrendsllc.co.site")

    async def _send_with(self, monkeypatch, status, body):
        import httpx

        def handler(request):
            return httpx.Response(status, json=body)

        original = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            email_sender.httpx, "AsyncClient",
            lambda *a, **k: original(*a, **{**k, "transport": transport}),
        )
        return await email_sender.send_email("owner@business.com", "Hi", "<p>Hi</p>")

    @pytest.mark.asyncio
    async def test_a_successful_send(self, monkeypatch):
        result = await self._send_with(monkeypatch, 200, {"id": "abc"})
        assert result["success"] is True
        assert result["provider"] == "resend"

    @pytest.mark.asyncio
    async def test_an_unverified_domain_says_so(self, monkeypatch):
        result = await self._send_with(
            monkeypatch, 422, {"message": "The domain is not verified."}
        )
        assert result["success"] is False
        assert result["error"] == "invalid_sender"
        assert "verified" in result["message"]

    @pytest.mark.asyncio
    async def test_a_bad_key_says_so(self, monkeypatch):
        result = await self._send_with(monkeypatch, 401, {"message": "Invalid API key"})
        assert result["error"] == "auth_failed"

    @pytest.mark.asyncio
    async def test_rate_limiting_is_distinguished(self, monkeypatch):
        result = await self._send_with(monkeypatch, 429, {})
        assert result["error"] == "rate_limited"


class TestMailercloud:
    """Mailercloud has two traps worth pinning down.

    The API key goes in the Authorization header VERBATIM — a "Bearer "
    prefix, which almost every other API wants, is silently rejected. And the
    API answers HTTP 200 with {"status": "ERROR"} for at least some failures,
    so treating any 2xx as delivered would report sends that never happened.
    """

    @pytest.fixture(autouse=True)
    def _configured(self, monkeypatch):
        for var in ("RESEND_API_KEY", "EMAIL_PROVIDER"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("MAILERCLOUD_API_KEY", "mc_live_key")
        monkeypatch.setenv("MAILERCLOUD_FROM_EMAIL", "hello@torquetrendsllc.co.site")

    async def _send(self, monkeypatch, status, body, capture=None):
        import httpx

        def handler(request):
            if capture is not None:
                capture["headers"] = dict(request.headers)
                capture["body"] = json.loads(request.content)
            return httpx.Response(status, json=body)

        original = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            email_sender.httpx, "AsyncClient",
            lambda *a, **k: original(*a, **{**k, "transport": transport}),
        )
        return await email_sender.send_email(
            "owner@business.com", "Your site on a phone", "<p>Hi</p>", "Hi"
        )

    def test_a_key_selects_it_over_smtp(self):
        assert email_sender.active_provider() == "mailercloud"

    @pytest.mark.asyncio
    async def test_a_successful_send(self, monkeypatch):
        result = await self._send(
            monkeypatch, 200, {"status": "SUCCESS", "statusCode": 1000, "message": "NA"}
        )
        assert result["success"] is True
        assert result["provider"] == "mailercloud"

    @pytest.mark.asyncio
    async def test_the_key_is_sent_without_a_bearer_prefix(self, monkeypatch):
        """This API wants the raw key. 'Bearer ' is a silent 401."""
        capture: dict = {}
        await self._send(monkeypatch, 200, {"status": "SUCCESS"}, capture)

        assert capture["headers"]["authorization"] == "mc_live_key"

    @pytest.mark.asyncio
    async def test_the_payload_matches_the_documented_shape(self, monkeypatch):
        capture: dict = {}
        await self._send(monkeypatch, 200, {"status": "SUCCESS"}, capture)
        body = capture["body"]

        assert body["version"] == "1.0"
        assert body["email"]["from"] == "hello@torquetrendsllc.co.site"
        assert body["email"]["subject"] == "Your site on a phone"
        assert body["email"]["recipients"]["to"] == [{"email": "owner@business.com"}]
        assert body["email"]["text"] == "Hi", "text part improves deliverability"
        assert body["email"]["html"] == "<p>Hi</p>"

    @pytest.mark.asyncio
    async def test_an_error_body_on_http_200_is_not_treated_as_sent(self, monkeypatch):
        """The failure that would quietly lose every email."""
        result = await self._send(
            monkeypatch, 200,
            {"status": "ERROR", "statusCode": 9022, "message": "Unsupported version"},
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_an_unverified_sender_is_named_as_such(self, monkeypatch):
        result = await self._send(
            monkeypatch, 400,
            {"status": "ERROR", "statusCode": 9001, "message": "Sender domain not verified"},
        )
        assert result["error"] == "invalid_sender"
        assert "hello@torquetrendsllc.co.site" in result["message"]

    @pytest.mark.asyncio
    async def test_a_bad_key_is_named_as_such(self, monkeypatch):
        result = await self._send(monkeypatch, 401, {"message": "Invalid API key"})
        assert result["error"] == "auth_failed"
        assert "Bearer" in result["message"], "should warn about the prefix mistake"

    def test_the_api_key_never_reaches_the_browser(self):
        assert "mc_live_key" not in str(email_sender.get_email_config_status())
