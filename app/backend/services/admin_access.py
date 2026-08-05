"""Who may reach the operators' console.

Kept deliberately separate from services/entitlements.py. That module grants a
BILLING exemption and says so in its own docstring: it "removes metering, not
authorisation". Reusing its allowlist here would quietly convert "this account
is not charged" into "this account can read every customer's data" — a
privilege escalation introduced by tidiness, and exactly the kind of coupling
that is invisible until someone adds a fourth address to the billing list
without realising what else it hands them.

So: two lists, two variables, two decisions.

Admission is by either route:

  * the verified JWT carries role=admin — the pre-existing mechanism, driven
    by Supabase app_metadata and still honoured; or
  * the verified email is in ADMIN_EMAILS.

The allowlist exists because the original bootstrap in services/auth.py
supports exactly one administrator (a single admin_user_id / admin_user_email
pair), and a team of three cannot share one.

Matching on the email claim is safe for the same reason it is safe in
entitlements.py: the token's signature is checked against the published JWKS,
and Supabase runs with mailer_autoconfirm off, so an address cannot be claimed
without receiving mail at it. Matching an unverified claim would make this a
way in rather than a way of recognising who is already trusted.
"""
import logging
import os
from typing import Set

logger = logging.getLogger(__name__)

_ENV_VAR = "ADMIN_EMAILS"


def _admin_emails() -> Set[str]:
    """Parse the allowlist on every call.

    Read at call time rather than import time so revoking someone's access
    takes effect on the next request instead of the next deploy. For an
    authorisation list that difference matters: the moment you want to remove
    somebody is not the moment to wait for a build.
    """
    raw = os.environ.get(_ENV_VAR, "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def is_admin_email(email: str) -> bool:
    """Whether this verified address belongs to an operator.

    Case- and whitespace-insensitive, because an allowlist that fails on
    capitalisation appears to work until the day it does not.
    """
    if not email:
        return False
    return email.strip().lower() in _admin_emails()


def admin_access_configured() -> bool:
    """Whether anybody is on the allowlist.

    Unset means nobody, which is the right default for anyone who deploys
    this without knowing the variable exists: the console then refuses
    everyone rather than opening to the first account that finds the URL.
    """
    return bool(_admin_emails())
