"""Resolve which sending identity a workspace's outreach goes out under.

The one decision that matters for the whole per-customer-email feature lives
here: does this send use the workspace's OWN credentials, or does it fall
back to the operator's shared environment-configured account?

The rule is narrow on purpose — fall back ONLY when the workspace has no
Email_configs row at all. If a row exists but is incomplete, or its secret
cannot be decrypted (a rotated CREDENTIAL_ENCRYPTION_KEY, a tampered row),
this returns None rather than quietly sending through the operator's own
account instead. Falling back there would defeat the entire point: outreach
the customer never authorized would go out through the operator's mailbox,
on the operator's reputation, which is exactly the shared-domain-blacklist
problem this feature exists to prevent.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.email_configs import Email_configs
from services import credential_crypto
from services.email_sender import EmailIdentity, _environment_identity, is_email_configured

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
    """The identity to send this user's outreach as.

    * A row exists and decrypts to something usable -> that, always. This is
      the whole point: the customer's outreach leaves under the customer's
      own credentials and reputation, not the operator's.
    * No row exists at all -> the operator's own environment-configured
      account, IF that is itself usable. This is the one deliberate
      fallback, for workspaces that have not set up their own sending
      account yet (including the operator's own default workspace).
    * A row exists but is incomplete or undecryptable -> None. Never silently
      substitute the operator's account for a workspace that tried to
      configure its own and got it wrong; that would send email the
      workspace did not authorize, from an address it does not expect.
    * No row, and the environment fallback isn't usable either -> None.
    """
    result = await db.execute(select(Email_configs).where(Email_configs.user_id == user_id))
    config = result.scalar_one_or_none()

    if config is None:
        env_identity = _environment_identity()
        return env_identity if is_email_configured(env_identity) else None

    identity = identity_from_config_row(config)
    return identity if is_email_configured(identity) else None
