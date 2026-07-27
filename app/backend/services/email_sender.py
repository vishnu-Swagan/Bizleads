"""Email delivery, over SMTP or an HTTP provider.

Two backends, one interface. Which one runs is decided by what is configured,
not by a flag somebody has to remember to set: if RESEND_API_KEY is present
Resend is used, otherwise SMTP. EMAIL_PROVIDER overrides that when both are
configured.

Why a second backend at all: SMTP means holding a long-lived password, and
Gmail in particular rejects normal account passwords, requires 2-Step
Verification before an App Password can even be created, caps sending at a few
hundred a day, and suspends accounts used for outreach. An HTTP API sidesteps
the credential mess entirely and survives networks that block outbound SMTP
ports, which several hosts do.

Every send is against an explicit, resolved `EmailIdentity` rather than
whatever happens to be in the process environment. That used to be the only
option: every workspace's outreach left from the one address in
SMTP_*/RESEND_* env vars, which is fine for a single operator and wrong the
moment this product has more than one customer — one customer's spam
complaint would blacklist the shared domain for everyone else, replies would
land in the operator's inbox instead of the customer's, and the Terms name
the customer as the sender.

The environment variables still matter, though: they are the OPERATOR'S OWN
sending account, kept as the fallback used only when a workspace has not
configured one of its own (see `_environment_identity()` below, and
services/email_identity.py which is where that fallback decision actually
gets made). `identity=None` on every public function means "use that
fallback" and exists for two reasons: it is what the operator's own account
uses, and it is what every test in tests/test_email_config.py already
exercises — preserving that behaviour matters more than a purely-explicit
signature.
"""
import os
import logging
import smtplib
import ssl

import httpx
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EmailIdentity:
    """One workspace's (or the operator's) resolved sending identity.

    Everything a send needs, already decided: which provider, and that
    provider's credentials. Never constructed with secrets read from
    anywhere other than services/email_identity.py (per-workspace, decrypted
    from models.email_configs) or `_environment_identity()` below (the
    operator's own fallback) — nothing in this module reaches into the
    database or the environment except that one function.
    """

    provider: str = "smtp"  # "smtp" | "resend"
    from_email: str = ""
    from_name: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    resend_api_key: str = ""

def _config() -> dict:
    """Read SMTP settings at call time, never at import.

    These were module-level constants evaluated when the module was first
    imported. That made the configuration unreachable in two situations that
    both matter: a .env file loaded after the first import (local development
    and Alembic), and any test that sets credentials via monkeypatch. It also
    meant a corrected environment variable could not take effect without a
    full process restart.

    SMTP_PORT is parsed defensively: a non-numeric value used to raise
    ValueError at import, which the router auto-loader swallows as a warning,
    silently removing every outreach endpoint from the running application.
    """
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        logger.error(
            "SMTP_PORT is not a number (%r); falling back to 587",
            os.environ.get("SMTP_PORT"),
        )
        port = 587

    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com").strip(),
        "port": port,
        # Gmail App Passwords are shown as "abcd efgh ijkl mnop". Pasting that
        # verbatim fails authentication; the spaces are display formatting, not
        # part of the secret. Stripping them here turns the single most common
        # setup mistake into a non-event.
        "username": os.environ.get("SMTP_USERNAME", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", "").replace(" ", "").strip(),
        "from_email": os.environ.get("SMTP_FROM_EMAIL", "").strip(),
        "use_tls": os.environ.get("SMTP_USE_TLS", "true").strip().lower() == "true",
    }


RESEND_ENDPOINT = "https://api.resend.com/emails"


def _resend_config() -> dict:
    return {
        "api_key": os.environ.get("RESEND_API_KEY", "").strip(),
        # Resend refuses any From address on a domain you have not verified,
        # so this is separate from the SMTP sender rather than shared.
        "from_email": (
            os.environ.get("RESEND_FROM_EMAIL")
            or os.environ.get("SMTP_FROM_EMAIL", "")
        ).strip(),
    }


def active_provider() -> str:
    """Which backend will actually send.

    Inferred from configuration rather than requiring a flag, so a key pasted
    into the dashboard takes effect without a second setting nobody documents.
    """
    explicit = os.environ.get("EMAIL_PROVIDER", "").strip().lower()
    if explicit in ("smtp", "resend"):
        return explicit
    if _resend_config()["api_key"]:
        return "resend"
    return "smtp"


def _environment_identity() -> EmailIdentity:
    """The operator's own sending account, read from the process environment.

    This is the fallback path, and ONLY the fallback path: it exists for the
    operator's own default account, used when a workspace has not configured
    a sending identity of its own (see services/email_identity.resolve_identity,
    which is where that decision is actually made — this function only builds
    the EmailIdentity, it does not decide when to use it).
    """
    if active_provider() == "resend":
        r = _resend_config()
        return EmailIdentity(provider="resend", from_email=r["from_email"], resend_api_key=r["api_key"])
    c = _config()
    return EmailIdentity(
        provider="smtp",
        from_email=c["from_email"],
        smtp_host=c["host"],
        smtp_port=c["port"],
        smtp_username=c["username"],
        smtp_password=c["password"],
        smtp_use_tls=c["use_tls"],
    )


def is_email_configured(identity: Optional[EmailIdentity] = None) -> bool:
    """Whether the given identity has everything its provider needs.

    `identity=None` means the operator's own environment-configured account —
    see the fallback note in the module docstring.
    """
    identity = identity or _environment_identity()
    if identity.provider == "resend":
        return bool(identity.resend_api_key and identity.from_email)
    return bool(identity.smtp_host and identity.smtp_username and identity.smtp_password and identity.from_email)


async def _send_via_resend(
    identity: EmailIdentity,
    to_email: str,
    subject: str,
    body_html: str,
    body_text: Optional[str],
    reply_to: Optional[str],
    cc: Optional[list[str]],
    bcc: Optional[list[str]],
) -> dict:
    """Send through Resend's HTTP API, using the given identity's credentials."""
    payload: dict = {
        "from": identity.from_email,
        "to": [to_email],
        "subject": subject,
        "html": body_html,
    }
    if body_text:
        payload["text"] = body_text
    if reply_to:
        payload["reply_to"] = reply_to
    if cc:
        payload["cc"] = cc
    if bcc:
        payload["bcc"] = bcc

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                RESEND_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {identity.resend_api_key}"},
            )
    except httpx.HTTPError as exc:
        logger.error("Resend request failed: %s", type(exc).__name__)
        return {"success": False, "error": "network_error",
                "message": f"Could not reach Resend: {type(exc).__name__}"}

    if response.status_code in (200, 201):
        logger.info("Email sent via Resend to %s", to_email)
        return {"success": True, "message": f"Email sent to {to_email}",
                "to": to_email, "subject": subject, "provider": "resend"}

    # Resend's own message is more specific than anything we could infer, so
    # it is surfaced rather than replaced — it names the unverified domain or
    # the invalid key directly.
    detail = ""
    try:
        detail = (response.json() or {}).get("message", "")
    except (ValueError, AttributeError):
        detail = response.text[:200]

    if response.status_code in (401, 403):
        return {"success": False, "error": "auth_failed",
                "message": f"Resend rejected the API key. {detail}".strip()}
    if response.status_code == 422:
        return {"success": False, "error": "invalid_sender",
                "message": (
                    f"Resend refused the sender address. {detail} "
                    "The From domain must be verified in your Resend dashboard."
                ).strip()}
    if response.status_code == 429:
        return {"success": False, "error": "rate_limited",
                "message": "Resend rate limit reached. Try again shortly."}

    return {"success": False, "error": "send_failed",
            "message": f"Resend returned {response.status_code}. {detail}".strip()}


async def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    identity: Optional[EmailIdentity] = None,
) -> dict:
    """
    Send an email via SMTP or Resend, using `identity`'s credentials.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        body_html: HTML body content
        body_text: Plain text body (fallback)
        reply_to: Reply-to address
        cc: CC recipients
        bcc: BCC recipients
        identity: The resolved sending identity to send as. Callers should
            pass the result of services.email_identity.resolve_identity() so
            a workspace's own credentials are used and its own reputation is
            on the line, not the operator's. When omitted, this falls back
            to the OPERATOR'S OWN environment-configured account — see the
            module docstring. That fallback is deliberate and exists for two
            reasons: it is the operator's own default sending account, and
            every test in tests/test_email_config.py already depends on
            being able to call this without an identity.

    Returns:
        Dict with status and details
    """
    using_env = identity is None
    identity = identity or _environment_identity()

    if not is_email_configured(identity):
        if identity.provider == "resend":
            if using_env:
                missing = "RESEND_API_KEY" if not identity.resend_api_key else "RESEND_FROM_EMAIL"
                message = f"Resend is not configured. Set {missing}."
            else:
                missing = "API key" if not identity.resend_api_key else "From address"
                message = f"Resend sending account is not configured. Missing: {missing}."
            return {"success": False, "error": "email_not_configured", "message": message}
        if using_env:
            message = "SMTP email is not configured. Please set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM_EMAIL."
        else:
            message = "SMTP sending account is not fully configured. Please set the host, username, password and From address."
        return {
            "success": False,
            "error": "email_not_configured",
            "message": message,
        }

    if not to_email or "@" not in to_email:
        return {
            "success": False,
            "error": "invalid_recipient",
            "message": f"Invalid recipient email: {to_email}",
        }

    # Dispatch AFTER validation so both backends reject a bad recipient
    # identically, and neither burns a network call on one.
    if identity.provider == "resend":
        return await _send_via_resend(
            identity, to_email, subject, body_html, body_text, reply_to, cc, bcc
        )

    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["From"] = identity.from_email
        msg["To"] = to_email
        msg["Subject"] = subject

        if reply_to:
            msg["Reply-To"] = reply_to

        if cc:
            msg["Cc"] = ", ".join(cc)

        # Add plain text part
        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Add HTML part
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        # Build recipient list
        all_recipients = [to_email]
        if cc:
            all_recipients.extend(cc)
        if bcc:
            all_recipients.extend(bcc)

        # Send via SMTP
        if identity.smtp_use_tls and identity.smtp_port == 587:
            # STARTTLS on port 587
            server = smtplib.SMTP(identity.smtp_host, identity.smtp_port, timeout=30)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        elif identity.smtp_port == 465:
            # SSL on port 465
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(identity.smtp_host, identity.smtp_port, context=context, timeout=30)
        else:
            # Plain SMTP
            server = smtplib.SMTP(identity.smtp_host, identity.smtp_port, timeout=30)

        server.login(identity.smtp_username, identity.smtp_password)
        server.sendmail(identity.from_email, all_recipients, msg.as_string())
        server.quit()

        logger.info(f"Email sent successfully to {to_email}: {subject}")
        return {
            "success": True,
            "message": f"Email sent to {to_email}",
            "to": to_email,
            "subject": subject,
        }

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {e}")
        return {
            "success": False,
            "error": "auth_failed",
            # Gmail returns one opaque rejection for every credential problem,
            # so the useful diagnosis has to come from inspecting what was
            # actually configured. "Check your username and password" sends
            # people round in circles re-typing a correct password.
            "message": diagnose_auth_failure(None if using_env else identity),
        }
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"Recipient refused: {e}")
        return {
            "success": False,
            "error": "recipient_refused",
            "message": f"Recipient email was refused: {to_email}",
        }
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return {
            "success": False,
            "error": "smtp_error",
            "message": f"Email sending failed: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Email sending error: {e}")
        return {
            "success": False,
            "error": "unknown_error",
            "message": f"Failed to send email: {str(e)}",
        }


async def send_bulk_emails(
    recipients: list[dict],
    subject_template: str,
    body_html_template: str,
    body_text_template: Optional[str] = None,
    identity: Optional[EmailIdentity] = None,
) -> dict:
    """
    Send emails to multiple recipients with template substitution.

    Args:
        recipients: List of dicts with 'email' and optional 'name', 'business_name' fields
        subject_template: Subject with {name}, {business_name} placeholders (not SQL -
            these are plain str.format() templates over trusted, operator-authored text)
        body_html_template: HTML body with placeholders
        body_text_template: Plain text body with placeholders
        identity: The resolved sending identity to send as (see send_email).
            Omitted means the operator's own environment-configured account.

    Returns:
        Summary of send results
    """
    identity = identity or _environment_identity()
    if not is_email_configured(identity):
        return {
            "success": False,
            "error": "email_not_configured",
            "message": "SMTP email is not configured.",
            "sent": 0,
            "failed": 0,
        }

    sent = 0
    failed = 0
    errors = []

    for recipient in recipients[:50]:  # Limit to 50 per batch
        email = recipient.get("email", "")
        name = recipient.get("name", "there")
        business_name = recipient.get("business_name", "your business")

        # Template substitution (plain string formatting, not SQL)
        subject = subject_template.format(
            name=name, business_name=business_name, email=email
        )
        body_html = body_html_template.format(
            name=name, business_name=business_name, email=email
        )
        body_text = None
        if body_text_template:
            body_text = body_text_template.format(
                name=name, business_name=business_name, email=email
            )

        result = await send_email(
            to_email=email,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            identity=identity,
        )

        if result["success"]:
            sent += 1
        else:
            failed += 1
            errors.append({"email": email, "error": result.get("message", "Unknown error")})

    return {
        "success": sent > 0,
        "sent": sent,
        "failed": failed,
        "total": len(recipients[:50]),
        "errors": errors[:5],  # Return first 5 errors
    }


def get_email_config_status(identity: Optional[EmailIdentity] = None) -> dict:
    """Report configuration state for the Settings screen.

    Deliberately returns no secret: the host, port and sender address are
    needed to diagnose a misconfiguration, but the username and password are
    reported only as booleans. Echoing an App Password back to the browser
    would put it in logs, screenshots and support threads.

    `identity=None` reports on the operator's own environment-configured
    account (see module docstring); the "missing" list then names the actual
    env vars to set, exactly as it always has. Passed an explicit workspace
    identity, "missing" instead names the field, since there is no env var
    for a customer to set.
    """
    using_env = identity is None
    identity = identity or _environment_identity()
    configured = is_email_configured(identity)

    if identity.provider == "resend":
        missing_fields = (
            (("RESEND_API_KEY", identity.resend_api_key), ("RESEND_FROM_EMAIL", identity.from_email))
            if using_env
            else (("api_key", identity.resend_api_key), ("from_email", identity.from_email))
        )
        return {
            "configured": configured,
            "provider": "resend",
            "host": "api.resend.com",
            "port": 443,
            "from_email": identity.from_email or None,
            "use_tls": True,
            "username_set": bool(identity.resend_api_key),
            "password_set": bool(identity.resend_api_key),
            "missing": [name for name, value in missing_fields if not value],
        }

    missing_fields = (
        (
            ("SMTP_HOST", identity.smtp_host),
            ("SMTP_USERNAME", identity.smtp_username),
            ("SMTP_PASSWORD", identity.smtp_password),
            ("SMTP_FROM_EMAIL", identity.from_email),
        )
        if using_env
        else (
            ("smtp_host", identity.smtp_host),
            ("smtp_username", identity.smtp_username),
            ("smtp_password", identity.smtp_password),
            ("from_email", identity.from_email),
        )
    )
    return {
        "configured": configured,
        "provider": "smtp",
        "host": identity.smtp_host or None,
        "port": identity.smtp_port,
        "from_email": identity.from_email or None,
        "use_tls": identity.smtp_use_tls,
        "username_set": bool(identity.smtp_username),
        "password_set": bool(identity.smtp_password),
        # Which specific fields are absent, so the UI can say what to fix
        # rather than only that something is wrong.
        "missing": [name for name, value in missing_fields if not value],
    }


# Google shows App Passwords as four groups of four, e.g. "abcd efgh ijkl mnop".
GMAIL_APP_PASSWORD_LENGTH = 16


def diagnose_auth_failure(identity: Optional[EmailIdentity] = None) -> str:
    """Explain a rejected login from what is actually configured.

    Gmail answers every credential problem with the same opaque error, so the
    generic "check your username and password" is close to useless — the
    password is usually right, it is simply the wrong KIND of password. These
    checks name the specific mistake instead.

    `identity=None` diagnoses the operator's own environment-configured
    account, exactly as before.
    """
    identity = identity or _environment_identity()
    host = identity.smtp_host or ""
    username, password = identity.smtp_username, identity.smtp_password
    from_email = identity.from_email
    is_google = "gmail" in host.lower() or "google" in host.lower()

    problems = []

    if username and "@" not in username:
        problems.append(
            f"SMTP_USERNAME is '{username}', which is not a full email address. "
            "It must be the whole address, e.g. you@gmail.com."
        )

    if is_google and password and len(password) != GMAIL_APP_PASSWORD_LENGTH:
        problems.append(
            f"SMTP_PASSWORD is {len(password)} characters. A Gmail App Password is "
            f"exactly {GMAIL_APP_PASSWORD_LENGTH} letters (Google displays it as four "
            "groups of four; spaces are stripped automatically). A password of any "
            "other length is almost certainly your normal account password, which "
            "Gmail always rejects for SMTP."
        )

    if is_google and username and from_email and username.lower() != from_email.lower():
        problems.append(
            f"SMTP_USERNAME ({username}) and SMTP_FROM_EMAIL ({from_email}) differ. "
            "Gmail only lets you send as the account you authenticated with, unless the "
            "address is a verified alias."
        )

    if problems:
        return "Gmail rejected the login. " + " ".join(problems)

    if is_google:
        return (
            "Gmail rejected the login, and the settings look superficially correct. "
            "The usual causes are: the App Password was created on a different Google "
            "account than SMTP_USERNAME; 2-Step Verification was turned off afterwards, "
            "which revokes every App Password; or the App Password was revoked. "
            "Create a fresh one at https://myaccount.google.com/apppasswords and try again."
        )

    return (
        "The mail server rejected the login. Check the username and password for "
        f"{host or 'the SMTP host'}, and that the account permits SMTP access."
    )
