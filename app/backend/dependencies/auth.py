import hashlib
import logging
from datetime import datetime
from typing import Optional

from core.auth import AccessTokenError, decode_access_token
from core.supabase_auth import (
    SupabaseTokenError,
    claims_to_user,
    is_supabase_auth_configured,
    verify_supabase_token,
)
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from schemas.auth import UserResponse
from services.admin_access import is_admin_email

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def _looks_like_supabase_token(token: str) -> bool:
    """Best-effort issuer sniff, used only to choose which error to report.

    Never used to decide whether to trust a token — that is always the
    verifier's job. Reads the unverified payload, so nothing here may be
    treated as authoritative.
    """
    import base64
    import json

    try:
        payload = token.split(".")[1]
        decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:
        return False
    return "supabase" in str(decoded.get("iss", "")).lower() or decoded.get("aud") == "authenticated"


async def get_bearer_token(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> str:
    """Extract bearer token from Authorization header."""
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials

    logger.debug("Authentication required for request %s %s", request.method, request.url.path)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication credentials were not provided")


async def get_current_user(token: str = Depends(get_bearer_token)) -> UserResponse:
    """Resolve the caller from their bearer token.

    Two issuers are accepted during the migration off Atoms Cloud:

      * Supabase — tried first when configured, verified against the project's
        published ES256 JWKS (see core/supabase_auth).
      * Atoms Cloud — the original app-issued HS256 token.

    Both are fully verified; neither is trusted on the strength of its own
    header. When Supabase auth is configured and the token is a Supabase token,
    a failure there is returned as-is rather than silently retried against the
    legacy path, so a bad Supabase token cannot be mistaken for a legacy one.
    """
    if is_supabase_auth_configured():
        try:
            claims = await verify_supabase_token(token)
        except SupabaseTokenError as exc:
            # Only fall through when this is plainly not a Supabase token —
            # otherwise report the real reason.
            if _looks_like_supabase_token(token):
                logger.info("Supabase token rejected: %s", exc)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
            logger.debug("Not a Supabase token, trying legacy issuer")
        else:
            user = claims_to_user(claims)
            if not user["id"]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token"
                )
            return UserResponse(
                id=user["id"], email=user["email"], name=user["name"], role=user["role"], last_login=None
            )

    try:
        payload = decode_access_token(token)
    except AccessTokenError as exc:
        # Log error type only, not the full exception which may contain sensitive token data
        logger.warning("Token validation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")

    last_login_raw = payload.get("last_login")
    last_login = None
    if isinstance(last_login_raw, str):
        try:
            last_login = datetime.fromisoformat(last_login_raw)
        except ValueError:
            # Log user hash instead of actual user ID to avoid exposing sensitive information
            user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()[:8] if user_id else "unknown"
            logger.debug("Failed to parse last_login for user hash: %s", user_hash)

    return UserResponse(
        id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name"),
        role=payload.get("role", "user"),
        last_login=last_login,
    )


async def get_admin_user(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Ensure the caller is an operator.

    Two routes in, because the original one does not scale past a single
    person: role=admin on the verified token (set in Supabase app_metadata,
    and what services/auth.py's single-admin bootstrap produces), or
    membership of the ADMIN_EMAILS allowlist.

    The refusal is logged with the address that was refused. An admin console
    is the highest-value target in the application, and a 403 here is worth
    knowing about — an unexplained one is either a misconfiguration locking
    the team out, or somebody finding a URL they should not have.
    """
    if current_user.role == "admin" or is_admin_email(current_user.email):
        return current_user

    logger.warning(
        "Refused admin access to %s (role=%s)", current_user.email or "unknown", current_user.role
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
