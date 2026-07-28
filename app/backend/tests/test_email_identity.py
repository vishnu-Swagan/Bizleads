"""Per-customer email sending: the settings CRUD, and identity resolution.

Everything here exists to keep one promise: outreach leaves under the
customer's own credentials and reputation, never silently borrowed from
another customer or from the operator's own account when the customer never
asked for that. See models/email_configs.py, services/email_identity.py and
routers/email_settings.py for the reasoning; these tests hold the promise to
account.
"""
import pytest
from sqlalchemy import select

from models.email_configs import Email_configs
from services import credential_crypto
from services.email_identity import resolve_identity
from tests.conftest import USER_A, USER_A_ID, USER_B_ID

EMAIL_SETTINGS_URL = "/api/v1/settings/email"
EMAIL_TEST_URL = "/api/v1/settings/email/test"


@pytest.fixture(autouse=True)
def _no_env_fallback_leaks_in(monkeypatch):
    """Every test in this file reasons about ONE identity source at a time.

    Without this, a stray operator SMTP_* var left over from another test
    module (or a real .env loaded in dev) could make a "no config" scenario
    look configured, or blur which identity a test is actually exercising.
    """
    for var in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL", "SMTP_USE_TLS", "RESEND_API_KEY",
        "RESEND_FROM_EMAIL", "EMAIL_PROVIDER", "CREDENTIAL_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def _enable_encryption(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", credential_crypto.generate_key())


async def _save_smtp_config(client, **overrides):
    payload = {
        "provider": "smtp",
        "from_email": "outreach@acme.test",
        "smtp_host": "smtp.acme-mail.test",
        "smtp_port": 587,
        "smtp_username": "outreach@acme.test",
        "smtp_password": "s3cr3t-app-password",
    }
    payload.update(overrides)
    return await client.put(EMAIL_SETTINGS_URL, json=payload)


# ---------- Secrets: encrypted at rest, never returned ----------

async def test_secret_is_encrypted_at_rest_and_never_returned_by_get(
    user_a_client, db_session, monkeypatch
):
    _enable_encryption(monkeypatch)

    put_response = await _save_smtp_config(user_a_client)
    assert put_response.status_code == 200
    assert "s3cr3t-app-password" not in put_response.text
    assert put_response.json()["smtp_password_set"] is True

    row = (
        await db_session.execute(select(Email_configs).where(Email_configs.user_id == USER_A_ID))
    ).scalar_one()
    assert row.smtp_password_encrypted is not None
    assert "s3cr3t-app-password" not in row.smtp_password_encrypted
    # It really is encrypted, not just base64 or passthrough - it round-trips
    # through the same decrypt every sender uses, and only through that.
    assert credential_crypto.decrypt(row.smtp_password_encrypted) == "s3cr3t-app-password"

    get_response = await user_a_client.get(EMAIL_SETTINGS_URL)
    assert get_response.status_code == 200
    assert "s3cr3t-app-password" not in get_response.text
    body = get_response.json()
    assert body["smtp_password_set"] is True
    assert "smtp_password" not in body
    assert "resend_api_key" not in body


# ---------- PUT keeps what was not retyped ----------

async def test_put_without_a_password_keeps_the_stored_one(user_a_client, db_session, monkeypatch):
    _enable_encryption(monkeypatch)

    await _save_smtp_config(user_a_client, smtp_password="original-app-password")
    row = (
        await db_session.execute(select(Email_configs).where(Email_configs.user_id == USER_A_ID))
    ).scalar_one()
    original_encrypted = row.smtp_password_encrypted
    assert original_encrypted is not None

    # A settings-form save that only changes the display name, and does not
    # retype the password, must not wipe it.
    update_response = await user_a_client.put(EMAIL_SETTINGS_URL, json={"from_name": "Acme Outreach"})
    assert update_response.status_code == 200

    await db_session.refresh(row)
    assert row.smtp_password_encrypted == original_encrypted
    assert credential_crypto.decrypt(row.smtp_password_encrypted) == "original-app-password"
    assert row.from_name == "Acme Outreach"


async def test_put_with_an_empty_password_string_also_keeps_the_stored_one(
    user_a_client, db_session, monkeypatch
):
    _enable_encryption(monkeypatch)

    await _save_smtp_config(user_a_client, smtp_password="original-app-password")

    # An empty string is what a form field submits when left blank - must be
    # treated the same as "omitted", not as "clear the secret".
    update_response = await user_a_client.put(EMAIL_SETTINGS_URL, json={"smtp_password": ""})
    assert update_response.status_code == 200

    row = (
        await db_session.execute(select(Email_configs).where(Email_configs.user_id == USER_A_ID))
    ).scalar_one()
    assert credential_crypto.decrypt(row.smtp_password_encrypted) == "original-app-password"


# ---------- Tenant isolation ----------

async def test_a_user_cannot_read_or_overwrite_another_users_config(
    user_a_client, user_b_client, db_session, monkeypatch
):
    _enable_encryption(monkeypatch)

    await _save_smtp_config(
        user_a_client, from_email="a@acme.test", smtp_username="a@acme.test",
        smtp_password="user-a-secret",
    )

    # B has configured nothing yet, and must not see any trace of A's config.
    b_view = await user_b_client.get(EMAIL_SETTINGS_URL)
    assert b_view.status_code == 200
    b_body = b_view.json()
    assert b_body["from_email"] is None
    assert b_body["smtp_password_set"] is False
    assert "user-a-secret" not in b_view.text
    assert "a@acme.test" not in b_view.text

    # B saving settings must create/update ONLY B's own row.
    b_put = await user_b_client.put(
        EMAIL_SETTINGS_URL,
        json={"provider": "smtp", "from_email": "hijacked@evil.test", "smtp_password": "attacker-pass"},
    )
    assert b_put.status_code == 200

    a_row = (
        await db_session.execute(select(Email_configs).where(Email_configs.user_id == USER_A_ID))
    ).scalar_one()
    assert a_row.from_email == "a@acme.test", "user B's write leaked into user A's row"
    assert credential_crypto.decrypt(a_row.smtp_password_encrypted) == "user-a-secret"

    rows = (await db_session.execute(select(Email_configs))).scalars().all()
    assert {row.user_id for row in rows} == {USER_A_ID, USER_B_ID}


# ---------- There is no fallback ----------

async def test_a_user_with_no_config_cannot_send_at_all(db_session, monkeypatch):
    """The operator's account is never substituted for a customer's.

    This previously asserted the opposite: no row fell back to the
    environment identity. That meant every customer who had not opened
    Settings sent outreach from the operator's address — spam complaints
    against the operator's domain, replies into the operator's inbox, and a
    customer named as legal sender of mail from an address they do not own.

    A fully configured operator environment is set here precisely because the
    old behaviour would have used it. Nothing may.
    """
    monkeypatch.setenv("SMTP_HOST", "smtp.operator.test")
    monkeypatch.setenv("SMTP_USERNAME", "operator@operator.test")
    monkeypatch.setenv("SMTP_PASSWORD", "abcdefghijklmnop")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "operator@operator.test")

    assert await resolve_identity(db_session, "some-user-with-no-row") is None


async def test_a_resend_environment_is_not_borrowed_either(db_session, monkeypatch):
    """The same rule, via the other provider — RESEND_API_KEY is not a
    shared sending account any more than SMTP_PASSWORD is."""
    monkeypatch.setenv("RESEND_API_KEY", "re_operator_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "operator@operator.test")

    assert await resolve_identity(db_session, "some-user-with-no-row") is None


async def test_no_config_and_no_environment_resolves_to_none(db_session):
    identity = await resolve_identity(db_session, "some-user-with-no-row")
    assert identity is None


async def test_an_incomplete_own_config_resolves_to_none(
    db_session, monkeypatch
):
    """A half-configured account sends nothing rather than something.

    Now that there is no fallback at all, this and the no-row case reach the
    same answer by different routes — which is the point. Both are kept
    because they guard different branches, and a future change that
    reintroduced a fallback would break exactly one of them first."""
    monkeypatch.setenv("SMTP_HOST", "smtp.operator.test")
    monkeypatch.setenv("SMTP_USERNAME", "operator@operator.test")
    monkeypatch.setenv("SMTP_PASSWORD", "abcdefghijklmnop")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "operator@operator.test")

    # A row exists for this user, but is missing a password.
    db_session.add(Email_configs(
        user_id=USER_A_ID, provider="smtp", from_email="a@acme.test",
        smtp_host="smtp.acme-mail.test", smtp_username="a@acme.test",
    ))
    await db_session.commit()

    identity = await resolve_identity(db_session, USER_A_ID)
    assert identity is None


# ---------- /test never sends anywhere but the caller's own address ----------

async def test_the_test_endpoint_only_ever_sends_to_the_callers_own_address(
    user_a_client, monkeypatch
):
    _enable_encryption(monkeypatch)
    await _save_smtp_config(user_a_client)

    captured = {}

    async def fake_send_email(**kwargs):
        captured.update(kwargs)
        return {"success": True, "message": "sent"}

    monkeypatch.setattr("routers.email_settings.send_email", fake_send_email)

    # Even a body trying to smuggle a different destination is ignored - the
    # endpoint takes no recipient parameter at all.
    response = await user_a_client.post(EMAIL_TEST_URL, json={"to_email": "attacker@evil.test"})

    assert response.status_code == 200
    assert captured["to_email"] == USER_A.email
    assert captured["to_email"] != "attacker@evil.test"


async def test_successful_test_sets_verified_at_and_clears_last_error(
    user_a_client, db_session, monkeypatch
):
    _enable_encryption(monkeypatch)
    await _save_smtp_config(user_a_client)

    row = (
        await db_session.execute(select(Email_configs).where(Email_configs.user_id == USER_A_ID))
    ).scalar_one()
    row.last_error = "a stale failure from before"
    await db_session.commit()

    async def fake_success(**kwargs):
        return {"success": True, "message": "Email sent"}

    monkeypatch.setattr("routers.email_settings.send_email", fake_success)

    response = await user_a_client.post(EMAIL_TEST_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["verified_at"] is not None
    assert body["last_error"] is None

    await db_session.refresh(row)
    assert row.verified_at is not None
    assert row.last_error is None


async def test_a_failed_test_records_last_error_without_setting_verified_at(
    user_a_client, db_session, monkeypatch
):
    _enable_encryption(monkeypatch)
    await _save_smtp_config(user_a_client)

    async def fake_failure(**kwargs):
        return {"success": False, "error": "auth_failed", "message": "Gmail rejected the login."}

    monkeypatch.setattr("routers.email_settings.send_email", fake_failure)

    response = await user_a_client.post(EMAIL_TEST_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["last_error"] == "Gmail rejected the login."
    assert body["verified_at"] is None

    row = (
        await db_session.execute(select(Email_configs).where(Email_configs.user_id == USER_A_ID))
    ).scalar_one()
    assert row.last_error == "Gmail rejected the login."
    assert row.verified_at is None


async def test_test_endpoint_requires_a_saved_config_first(user_a_client, monkeypatch):
    _enable_encryption(monkeypatch)

    response = await user_a_client.post(EMAIL_TEST_URL)
    assert response.status_code == 404


# ---------- Fails closed without CREDENTIAL_ENCRYPTION_KEY ----------

async def test_put_fails_closed_when_encryption_key_is_missing(user_a_client):
    response = await _save_smtp_config(user_a_client)
    assert response.status_code == 503
    assert "CREDENTIAL_ENCRYPTION_KEY" in response.text


async def test_get_reports_encryption_unavailable_rather_than_erroring(user_a_client):
    response = await user_a_client.get(EMAIL_SETTINGS_URL)
    assert response.status_code == 200
    assert response.json()["encryption_available"] is False


async def test_test_endpoint_fails_closed_when_encryption_key_is_missing(
    user_a_client, db_session, monkeypatch
):
    # Save a config while encryption is available...
    _enable_encryption(monkeypatch)
    await _save_smtp_config(user_a_client)

    # ...then the key is rotated out from under the running process.
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)

    response = await user_a_client.post(EMAIL_TEST_URL)
    assert response.status_code == 503
