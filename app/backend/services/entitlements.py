"""Accounts that are not metered.

The operator needs to use their own product without spending credits they
notionally sell to themselves — demos, support reproductions, checking that a
change actually works in production. This is that exemption, and nothing more:
it removes metering, not authorisation. An unmetered account still sees only
its own leads and its own drafts, because every query is scoped by user_id
independently of anything here.

Configured with UNLIMITED_CREDIT_EMAILS rather than a constant in the source.
This repository is public, so a hardcoded address publishes it, and changing
who is exempt should not require a deploy. Unset — the default — means
everybody is metered, which is the right behaviour for anyone who runs this
without knowing the variable exists.

Matching is on the email in the verified JWT. That is safe here because the
token's signature is checked against the published JWKS and Supabase is
configured with mailer_autoconfirm off, so an address cannot be claimed
without receiving mail at it. Matching on an unverified claim would make this
a privilege-escalation path rather than a billing exemption.
"""
import logging
import os
from typing import Set

logger = logging.getLogger(__name__)

_ENV_VAR = "UNLIMITED_CREDIT_EMAILS"


def _unlimited_emails() -> Set[str]:
    """Parse the allowlist fresh on every call.

    Read at call time, not import time, for the same reason the AI provider
    keys are: a value frozen at import only takes effect after a restart, and
    that has already caused three production bugs in this codebase.
    """
    raw = os.environ.get(_ENV_VAR, "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def has_unlimited_credits(email: str) -> bool:
    """Whether this account is exempt from credit metering.

    Case- and whitespace-insensitive, because an allowlist that silently fails
    on "Vishnu@..." versus "vishnu@..." is worse than no allowlist: it appears
    to work until the day it does not.
    """
    if not email:
        return False
    return email.strip().lower() in _unlimited_emails()
