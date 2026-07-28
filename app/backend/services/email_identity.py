"""Resolve which sending identity a workspace's outreach goes out under.

One rule, no exceptions: every account sends under its own credentials, or it
does not send. There is no shared account and no fallback.

An earlier version fell back to the operator's environment-configured account
for users with no Email_configs row. See resolve_identity for why that was
removed — briefly, it meant every customer who had not opened Settings sent
outreach from the operator's address, which is the shared-domain-reputation
problem this whole feature exists to prevent.

The operator is not special. Their own account configures a sending identity
through the same Settings screen every customer uses. SMTP_* and RESEND_* on
the API service no longer participate in customer sends at all.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.email_configs import Email_configs
from services import credential_crypto
from services.email_sender import EmailIdentity, is_email_configured

logger = logging.getLogger(__name__)


def identity_from_config_row(config: Email_configs) -> EmailIdentity:
    """Decrypt one Email_configs row into a ready-to-use EmailIdentity.

    A failed decrypt (see credential_crypto.decrypt) becomes an empty secret,
    not an exception — the resulting identity is simply unconfigured, which
    is_email_configured() reports honestly and every send path already
    treats as "cannot send" rather than crashing.
    """
    if config.provider == "resend":
        return EmailIdentity(
            provider="resend",
            from_email=config.from_email or "",
            from_name=config.from_name or "",
            resend_api_key=credential_crypto.decrypt(config.resend_api_key_encrypted) or "",
        )
    return EmailIdentity(
        provider="smtp",
        from_email=config.from_email or "",
        from_name=config.from_name or "",
        smtp_host=config.smtp_host or "",
        smtp_port=config.smtp_port or 587,
        smtp_username=config.smtp_username or "",
        smtp_password=credential_crypto.decrypt(config.smtp_password_encrypted) or "",
        smtp_use_tls=bool(config.smtp_use_tls),
    )


async def resolve_identity(db: AsyncSession, user_id: str) -> Optional[EmailIdentity]:
    """The identity to send this user's outreach as, or None.

    There is no fallback. Every account sends under its own credentials or it
    does not send.

    This used to fall back to the operator's environment-configured account
    when a user had no Email_configs row, which meant any customer who never
    opened Settings sent outreach from the OPERATOR'S address. The
    consequences all pointed one way: spam complaints accrued to the
    operator's domain, replies landed in the operator's inbox where the
    customer never saw them, and the Terms named the customer as the legal
    sender of a message from an address they do not own and cannot
    authenticate. The per-customer identity feature existed precisely to
    prevent that, and the fallback quietly reinstated it for exactly the
    users least likely to notice — the ones who had configured nothing.

    Failing closed is the only safe direction here. An unconfigured account
    that cannot send is an onboarding step; an unconfigured account that
    sends as somebody else is a deliverability incident for the operator and
    a compliance one for the customer.

    * A row that decrypts to something usable -> that identity.
    * A row that is incomplete or undecryptable (rotated
      CREDENTIAL_ENCRYPTION_KEY, tampered row) -> None.
    * No row at all -> None.
    """
    result = await db.execute(select(Email_configs).where(Email_configs.user_id == user_id))
    config = result.scalar_one_or_none()

    if config is None:
        return None

    identity = identity_from_config_row(config)
    return identity if is_email_configured(identity) else None
