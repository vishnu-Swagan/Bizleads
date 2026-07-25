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

# SMTP Configuration from environment
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"


def is_email_configured() -> bool:
    """Check if SMTP email sending is properly configured."""
    return bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM_EMAIL)


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
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_FROM_EMAIL
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
        if SMTP_USE_TLS and SMTP_PORT == 587:
            # STARTTLS on port 587
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        elif SMTP_PORT == 465:
            # SSL on port 465
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30)
        else:
            # Plain SMTP
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)

        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM_EMAIL, all_recipients, msg.as_string())
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
    """Get the current email configuration status."""
    return {
        "configured": is_email_configured(),
        "host": SMTP_HOST if SMTP_HOST else None,
        "port": SMTP_PORT,
        "from_email": SMTP_FROM_EMAIL if SMTP_FROM_EMAIL else None,
        "use_tls": SMTP_USE_TLS,
        "username_set": bool(SMTP_USERNAME),
        "password_set": bool(SMTP_PASSWORD),
    }