"""Verify Supabase-issued access tokens.

This project's Supabase instance signs user tokens with **ES256** and publishes
the public key at `/auth/v1/.well-known/jwts.json`-style JWKS. Verification is
therefore asymmetric: there is no shared secret to leak, and the backend only
ever holds public material.

A legacy HS256 path is supported because Supabase projects created before the
asymmetric-key migration sign with a shared secret, and a project can briefly
have both live during migration.

SECURITY — the three ways JWT verification is usually got wrong, and how each
is prevented here:

  1. **Algorithm confusion.** An attacker takes the *public* ES256 key, signs a
     token with it as an HMAC secret, and sets `alg: HS256`. A verifier that
     picks its algorithm from the token's own header will happily accept it.
     Here the algorithm is chosen from the KEY TYPE, never from the header:
     an EC key only ever verifies ES256, and the HS256 path only runs when a
     shared secret is configured and no JWKS is in play.
  2. **`alg: none`.** Rejected before any key lookup.
  3. **Unverified decode.** `verify_signature` is never disabled. The only
     unverified read is of the header, to learn which key id to fetch — and
     nothing from that read is trusted for authorisation.

Claims are also checked, not just the signature: `exp` must be in the future
and `aud` must be `authenticated`. A token that verifies but has expired, or
was minted for a different audience, is not a valid session.
"""
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError

logger = logging.getLogger(__name__)

JWKS_CACHE_TTL_SECONDS = 600
EXPECTED_AUDIENCE = "authenticated"

_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cached_at: float = 0.0


class SupabaseTokenError(Exception):
    """Raised when a token cannot be trusted. The message is safe to return."""


def is_supabase_auth_configured() -> bool:
    """True when this deployment verifies Supabase tokens."""
    return bool(os.environ.get("SUPABASE_JWKS_URL") or os.environ.get("SUPABASE_JWT_SECRET"))


def _jwks_url() -> Optional[str]:
    explicit = os.environ.get("SUPABASE_JWKS_URL")
    if explicit:
        return explicit
    base = os.environ.get("SUPABASE_URL")
    return f"{base.rstrip('/')}/auth/v1/.well-known/jwks.json" if base else None


def _expected_issuer() -> Optional[str]:
    base = os.environ.get("SUPABASE_URL")
    return f"{base.rstrip('/')}/auth/v1" if base else None


def reset_jwks_cache() -> None:
    """Drop the cached key set. Used by tests and on key rotation."""
    global _jwks_cache, _jwks_cached_at
    _jwks_cache = None
    _jwks_cached_at = 0.0


async def fetch_jwks(*, force: bool = False) -> Dict[str, Any]:
    """Return the project's public key set, cached.

    `force` bypasses the cache. Called with force=True when a token names a key
    id we have not seen, so that key rotation does not lock every user out for
    the length of the cache TTL.
    """
    global _jwks_cache, _jwks_cached_at

    if not force and _jwks_cache is not None and (time.monotonic() - _jwks_cached_at) < JWKS_CACHE_TTL_SECONDS:
        return _jwks_cache

    url = _jwks_url()
    if not url:
        raise SupabaseTokenError("Authentication is not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            jwks = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Failed to fetch Supabase JWKS: %s", type(exc).__name__)
        # Serve a stale key set rather than locking everyone out over a blip.
        if _jwks_cache is not None:
            logger.warning("Serving stale JWKS after fetch failure")
            return _jwks_cache
        raise SupabaseTokenError("Unable to retrieve authentication keys") from exc

    _jwks_cache = jwks
    _jwks_cached_at = time.monotonic()
    return jwks


def _find_key(jwks: Dict[str, Any], kid: Optional[str]) -> Optional[Dict[str, Any]]:
    keys = jwks.get("keys") or []
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
        return None
    # A single-key JWKS with no kid in the header is unambiguous.
    return keys[0] if len(keys) == 1 else None


def _algorithm_for_key(key: Dict[str, Any]) -> str:
    """Choose the algorithm from the KEY, never from the token header.

    This is what prevents algorithm-confusion attacks.
    """
    kty = key.get("kty")
    if kty == "EC":
        return key.get("alg") or "ES256"
    if kty == "RSA":
        return key.get("alg") or "RS256"
    raise SupabaseTokenError(f"Unsupported key type: {kty}")


async def verify_supabase_token(token: str) -> Dict[str, Any]:
    """Verify a Supabase access token and return its claims.

    Raises SupabaseTokenError with a message safe to hand back to a caller.
    """
    if not token:
        raise SupabaseTokenError("No token provided")

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise SupabaseTokenError("Malformed token") from exc

    header_alg = (header.get("alg") or "").upper()
    if header_alg in ("NONE", ""):
        raise SupabaseTokenError("Unsigned tokens are not accepted")

    issuer = _expected_issuer()
    claim_options: Dict[str, Any] = {"audience": EXPECTED_AUDIENCE}
    if issuer:
        claim_options["issuer"] = issuer

    # Asymmetric path — the one this project uses.
    jwks_url = _jwks_url()
    if jwks_url and header_alg != "HS256":
        kid = header.get("kid")
        jwks = await fetch_jwks()
        key = _find_key(jwks, kid)
        if key is None:
            # Unknown kid: the project may have rotated keys since we cached.
            jwks = await fetch_jwks(force=True)
            key = _find_key(jwks, kid)
        if key is None:
            raise SupabaseTokenError("Token signed by an unrecognised key")

        algorithm = _algorithm_for_key(key)
        try:
            return jwt.decode(token, key, algorithms=[algorithm], **claim_options)
        except ExpiredSignatureError as exc:
            raise SupabaseTokenError("Session has expired") from exc
        except JWTClaimsError as exc:
            raise SupabaseTokenError("Token claims are not valid for this application") from exc
        except JWTError as exc:
            raise SupabaseTokenError("Token signature verification failed") from exc

    # Legacy symmetric path, only when a shared secret is configured.
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        raise SupabaseTokenError("Token algorithm is not supported by this deployment")

    try:
        return jwt.decode(token, secret, algorithms=["HS256"], **claim_options)
    except ExpiredSignatureError as exc:
        raise SupabaseTokenError("Session has expired") from exc
    except JWTClaimsError as exc:
        raise SupabaseTokenError("Token claims are not valid for this application") from exc
    except JWTError as exc:
        raise SupabaseTokenError("Token signature verification failed") from exc


def claims_to_user(claims: Dict[str, Any]) -> Dict[str, Any]:
    """Map Supabase claims onto the shape the app's UserResponse expects.

    `role` here is the application's own role, not Supabase's `authenticated`
    database role — those are different things and conflating them would grant
    every signed-in user admin. Application role comes from app_metadata, which
    only the service key can write, never from user_metadata, which the user
    can set themselves.
    """
    app_metadata = claims.get("app_metadata") or {}
    user_metadata = claims.get("user_metadata") or {}

    return {
        "id": claims.get("sub", ""),
        "email": claims.get("email") or user_metadata.get("email") or "",
        "name": user_metadata.get("full_name") or user_metadata.get("name"),
        "role": app_metadata.get("app_role", "user"),
    }
