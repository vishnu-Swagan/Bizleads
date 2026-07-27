"""SMTP configuration must be readable at call time and must never leak.

The settings were module-level constants evaluated at import. That put the
configuration out of reach in exactly the cases that matter: a .env loaded
after first import, a corrected variable that needs a restart to take effect,
and any test that sets credentials.

A bad SMTP_PORT was worse than it looks. int("") raised ValueError during
import, and main.py's router auto-loader swallows import errors as a warning,
so one typo silently removed every outreach endpoint from the running app.
"""
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
