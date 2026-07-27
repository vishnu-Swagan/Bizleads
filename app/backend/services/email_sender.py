"""
SMTP Email Sender service for outreach delivery.
Supports Gmail, custom SMTP servers, and standard SMTP with TLS/SSL.
"""
import os
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger(__name__)

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


def is_email_configured() -> bool:
    """Check if SMTP email sending is properly configured."""
    c = _config()
    return bool(c["host"] and c["username"] and c["password"] and c["from_email"])


async def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
) -> dict:
    """
    Send an email via SMTP.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        body_html: HTML body content
        body_text: Plain text body (fallback)
        reply_to: Reply-to address
        cc: CC recipients
        bcc: BCC recipients

    Returns:
        Dict with status and details
    """
    if not is_email_configured():
        return {
            "success": False,
            "error": "email_not_configured",
            "message": "SMTP email is not configured. Please set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM_EMAIL.",
        }

    if not to_email or "@" not in to_email:
        return {
            "success": False,
            "error": "invalid_recipient",
            "message": f"Invalid recipient email: {to_email}",
        }

    try:
        # Create message
        c = _config()
        msg = MIMEMultipart("alternative")
        msg["From"] = c["from_email"]
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
        if c["use_tls"] and c["port"] == 587:
            # STARTTLS on port 587
            server = smtplib.SMTP(c["host"], c["port"], timeout=30)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        elif c["port"] == 465:
            # SSL on port 465
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(c["host"], c["port"], context=context, timeout=30)
        else:
            # Plain SMTP
            server = smtplib.SMTP(c["host"], c["port"], timeout=30)

        server.login(c["username"], c["password"])
        server.sendmail(c["from_email"], all_recipients, msg.as_string())
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
            "message": "SMTP authentication failed. Check your username and password (use App Password for Gmail).",
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
) -> dict:
    """
    Send emails to multiple recipients with template substitution.

    Args:
        recipients: List of dicts with 'email' and optional 'name', 'business_name' fields
        subject_template: Subject with {name}, {business_name} placeholders
        body_html_template: HTML body with placeholders
        body_text_template: Plain text body with placeholders

    Returns:
        Summary of send results
    """
    if not is_email_configured():
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

        # Template substitution
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


def get_email_config_status() -> dict:
    """Report configuration state for the Settings screen.

    Deliberately returns no secret: the host, port and sender address are
    needed to diagnose a misconfiguration, but the username and password are
    reported only as booleans. Echoing an App Password back to the browser
    would put it in logs, screenshots and support threads.
    """
    c = _config()
    return {
        "configured": is_email_configured(),
        "host": c["host"] or None,
        "port": c["port"],
        "from_email": c["from_email"] or None,
        "use_tls": c["use_tls"],
        "username_set": bool(c["username"]),
        "password_set": bool(c["password"]),
        # Which specific fields are absent, so the UI can say what to fix
        # rather than only that something is wrong.
        "missing": [
            name
            for name, value in (
                ("SMTP_HOST", c["host"]),
                ("SMTP_USERNAME", c["username"]),
                ("SMTP_PASSWORD", c["password"]),
                ("SMTP_FROM_EMAIL", c["from_email"]),
            )
            if not value
        ],
    }