"""Encrypt customer sending credentials at rest.

These are other people's mail passwords and API keys. A database backup, a
support query, a stray log line or a SQL-injection bug anywhere in the
application must not hand somebody the ability to send mail as a customer.

Fernet (AES-128-CBC with an HMAC) is used rather than anything hand-rolled:
it is authenticated, so a tampered ciphertext fails loudly instead of
decrypting to garbage that gets used as a password.

The key comes from CREDENTIAL_ENCRYPTION_KEY. If it is absent the module
refuses to store anything rather than falling back to plaintext — a fallback
that "works" is exactly how credentials end up unencrypted in production
without anyone noticing.
"""
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class CredentialEncryptionUnavailable(RuntimeError):
    """Raised when credentials cannot be encrypted, so they are not stored."""


def generate_key() -> str:
    """A new key, for operators setting this up."""
    return Fernet.generate_key().decode()


def _cipher() -> Fernet:
    raw = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise CredentialEncryptionUnavailable(
            "CREDENTIAL_ENCRYPTION_KEY is not set, so email credentials cannot be "
            "stored securely. Generate one with "
            "`python -c \'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\'` and set it in the environment."
        )
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        raise CredentialEncryptionUnavailable(
            "CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key (44 url-safe "
            "base64 characters)."
        ) from exc


def is_available() -> bool:
    """Whether credentials can be stored at all, for a clear setup error."""
    try:
        _cipher()
        return True
    except CredentialEncryptionUnavailable:
        return False


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a secret. None and empty stay None — absent, not encrypted-empty."""
    if not plaintext:
        return None
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt a stored secret.

    Returns None when the value cannot be read — a rotated key, or a tampered
    row. Callers treat that as "not configured", which fails closed: no email
    is sent rather than one sent with a corrupted credential.
    """
    if not ciphertext:
        return None
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, CredentialEncryptionUnavailable, ValueError):
        # Deliberately never logs the ciphertext or any part of the secret.
        logger.error("Stored credential could not be decrypted; treating as unset")
        return None
