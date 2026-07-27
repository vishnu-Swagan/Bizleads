"""Per-customer email sending settings.

Each workspace configures its own SMTP or Resend credentials here instead of
relying on the operator's shared environment-configured account. See
models/email_configs.py and services/email_identity.py for the full
reasoning; this router is just the CRUD surface plus a way to prove the
credentials actually work before an automation queues a hundred emails
against them.

Every endpoint is scoped to the caller (current_user.id) and nothing here
ever returns a stored secret — only whether one is set.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.email_configs import Email_configs
from schemas.auth import UserResponse
from services import credential_crypto
from services.email_identity import identity_from_config_row
from services.email_sender import is_email_configured, send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings/email", tags=["email-settings"])


class EmailConfigUpdate(BaseModel):
    provider: Optional[str] = None  # "smtp" | "resend"
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    # Secrets: an omitted or empty string means "keep what is already
    # stored", never "clear it". A settings form that wipes a password
    # because the user did not retype it is a bug, not a security feature -
    # the only way to actually remove a secret is DELETE the whole config.
    smtp_password: Optional[str] = None
    resend_api_key: Optional[str] = None


async def _get_own_config(db: AsyncSession, user_id: str) -> Optional[Email_configs]:
    result = await db.execute(select(Email_configs).where(Email_configs.user_id == user_id))
    return result.scalar_one_or_none()


def _config_out(config: Optional[Email_configs]) -> dict:
    """Serialise for the Settings screen. Never includes a secret value."""
    encryption_available = credential_crypto.is_available()
    if config is None:
        return {
            "provider": "smtp",
            "from_email": None,
            "from_name": None,
            "smtp_host": None,
            "smtp_port": 587,
            "smtp_username": None,
            "smtp_use_tls": True,
            "smtp_password_set": False,
            "resend_api_key_set": False,
            "verified_at": None,
            "last_error": None,
            "encryption_available": encryption_available,
        }
    return {
        "provider": config.provider,
        "from_email": config.from_email,
        "from_name": config.from_name,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_username": config.smtp_username,
        "smtp_use_tls": config.smtp_use_tls,
        "smtp_password_set": bool(config.smtp_password_encrypted),
        "resend_api_key_set": bool(config.resend_api_key_encrypted),
        "verified_at": config.verified_at.isoformat() if config.verified_at else None,
        "last_error": config.last_error,
        "encryption_available": encryption_available,
    }


@router.get("")
async def get_email_settings(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The caller's own sending configuration. Never includes a secret."""
    config = await _get_own_config(db, current_user.id)
    return _config_out(config)


@router.put("")
async def put_email_settings(
    data: EmailConfigUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the caller's own sending configuration."""
    if not credential_crypto.is_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Email credentials cannot be stored: CREDENTIAL_ENCRYPTION_KEY is not "
                "configured on the server. Ask the operator to set it before saving "
                "sending credentials."
            ),
        )

    if data.provider is not None and data.provider not in ("smtp", "resend"):
        raise HTTPException(status_code=400, detail="provider must be 'smtp' or 'resend'")

    config = await _get_own_config(db, current_user.id)
    if config is None:
        config = Email_configs(user_id=current_user.id)
        db.add(config)

    if data.provider is not None:
        config.provider = data.provider
    if data.from_email is not None:
        config.from_email = data.from_email.strip() or None
    if data.from_name is not None:
        config.from_name = data.from_name.strip() or None
    if data.smtp_host is not None:
        config.smtp_host = data.smtp_host.strip() or None
    if data.smtp_port is not None:
        config.smtp_port = data.smtp_port
    if data.smtp_username is not None:
        config.smtp_username = data.smtp_username.strip() or None
    if data.smtp_use_tls is not None:
        config.smtp_use_tls = data.smtp_use_tls

    # Only overwrite a secret when a real, non-empty value was sent.
    if data.smtp_password:
        config.smtp_password_encrypted = credential_crypto.encrypt(data.smtp_password)
    if data.resend_api_key:
        config.resend_api_key_encrypted = credential_crypto.encrypt(data.resend_api_key)

    # Settings just changed, so whatever was verified before no longer
    # applies to what is stored now. NULL means untested, same discipline as
    # the model's own docstring - distinct from tested-and-failed.
    config.verified_at = None
    config.last_error = None

    await db.commit()
    await db.refresh(config)
    return _config_out(config)


@router.post("/test")
async def test_email_settings(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a real test email to the CALLER'S OWN account address.

    Never an arbitrary address: accepting a destination here would turn this
    endpoint into an open relay for anyone with a login, using precisely the
    credentials this whole feature exists to keep customers from misusing on
    each other's behalf.
    """
    if not credential_crypto.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email credentials cannot be read: CREDENTIAL_ENCRYPTION_KEY is not configured on the server.",
        )

    config = await _get_own_config(db, current_user.id)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail="No email configuration saved yet. Save your sending settings before testing them.",
        )

    if not current_user.email or "@" not in current_user.email:
        raise HTTPException(status_code=400, detail="Your account has no valid email address to send the test to.")

    identity = identity_from_config_row(config)
    if not is_email_configured(identity):
        raise HTTPException(status_code=400, detail="Your email configuration is incomplete.")

    result = await send_email(
        to_email=current_user.email,
        subject="Test email from your sending account",
        body_html="<p>This confirms your email sending account is configured correctly.</p>",
        body_text="This confirms your email sending account is configured correctly.",
        identity=identity,
    )

    if result.get("success"):
        config.verified_at = datetime.now(timezone.utc)
        config.last_error = None
    else:
        config.last_error = result.get("message", "Failed to send test email")

    await db.commit()
    await db.refresh(config)

    return {
        "success": bool(result.get("success")),
        "message": result.get("message"),
        "verified_at": config.verified_at.isoformat() if config.verified_at else None,
        "last_error": config.last_error,
    }


@router.delete("")
async def delete_email_settings(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the caller's own sending configuration."""
    config = await _get_own_config(db, current_user.id)
    if config is None:
        return {"deleted": False}

    await db.delete(config)
    await db.commit()
    return {"deleted": True}
