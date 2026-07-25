"""Verification of Supabase-issued tokens.

Runs fully offline against a generated P-256 keypair, so the attacks below are
proven rather than assumed.

The three tests that matter most:

  * algorithm confusion — signing an HS256 token using the PUBLIC key as the
    HMAC secret. A verifier that takes its algorithm from the token's own
    header accepts this and hands the attacker any identity they ask for. It is
    the single most common way JWT verification is broken.
  * `alg: none` — the unsigned-token bypass.
  * role source — Supabase lets a user write their own `user_metadata` through
    the client SDK. If the application role were read from there, any signed-in
    user could make themselves an admin. It must come from `app_metadata`,
    which only the service key can write.
"""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt

from core.supabase_auth import (
    SupabaseTokenError,
    claims_to_user,
    reset_jwks_cache,
    verify_supabase_token,
)
import core.supabase_auth as supabase_auth

ISSUER = "https://testproject.supabase.co/auth/v1"
KID = "test-key-1"


def _b64(value: int, length: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).decode().rstrip("=")


@pytest.fixture
def keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    numbers = private.public_key().public_numbers()
    jwk = {
        "kty": "EC", "crv": "P-256", "kid": KID, "alg": "ES256", "use": "sig",
        "x": _b64(numbers.x, 32), "y": _b64(numbers.y, 32),
    }
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return {"private_pem": pem, "public_pem": public_pem, "jwk": jwk}


@pytest.fixture(autouse=True)
def configure(monkeypatch, keypair):
    monkeypatch.setenv("SUPABASE_URL", "https://testproject.supabase.co")
    monkeypatch.setenv("SUPABASE_JWKS_URL", f"{ISSUER}/.well-known/jwks.json")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    reset_jwks_cache()

    async def fake_fetch(*, force: bool = False):
        return {"keys": [keypair["jwk"]]}

    monkeypatch.setattr(supabase_auth, "fetch_jwks", fake_fetch)
    yield
    reset_jwks_cache()


def make_token(keypair, **overrides) -> str:
    claims = {
        "sub": "11111111-2222-3333-4444-555555555555",
        "email": "owner@example.test",
        "aud": "authenticated",
        "role": "authenticated",
        "iss": ISSUER,
        "iat": int(time.time()) - 10,
        "exp": int(time.time()) + 3600,
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Test Owner"},
    }
    claims.update(overrides)
    return jwt.encode(claims, keypair["private_pem"], algorithm="ES256", headers={"kid": KID})


class TestValidTokens:
    async def test_a_genuine_token_verifies(self, keypair):
        claims = await verify_supabase_token(make_token(keypair))
        assert claims["sub"] == "11111111-2222-3333-4444-555555555555"
        assert claims["email"] == "owner@example.test"

    async def test_unknown_kid_triggers_a_key_refetch(self, keypair, monkeypatch):
        calls = {"n": 0}

        async def counting_fetch(*, force: bool = False):
            calls["n"] += 1
            # First call returns an empty set, as if we cached before rotation.
            return {"keys": []} if calls["n"] == 1 else {"keys": [keypair["jwk"]]}

        monkeypatch.setattr(supabase_auth, "fetch_jwks", counting_fetch)
        claims = await verify_supabase_token(make_token(keypair))
        assert claims["sub"]
        assert calls["n"] == 2, "should have refetched rather than locking the user out"


class TestForgedTokens:
    async def test_algorithm_confusion_is_rejected(self, keypair):
        # The attack: take the PUBLIC key — which anyone can fetch from the
        # JWKS endpoint — and use its bytes as an HMAC secret, declaring
        # alg:HS256. A verifier that reads its algorithm from the token header
        # will "verify" this successfully and grant whatever the payload claims.
        #
        # Hand-rolled because python-jose refuses to *produce* this forgery.
        # An attacker has no such scruples, so the defence must be tested
        # against the real wire format rather than a library's cooperation.
        import hashlib
        import hmac

        def b64(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).decode().rstrip("=")

        header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
        payload = b64(
            json.dumps(
                {
                    "sub": "attacker",
                    "email": "attacker@evil.test",
                    "aud": "authenticated",
                    "iss": ISSUER,
                    "exp": int(time.time()) + 3600,
                    "app_metadata": {"app_role": "admin"},
                }
            ).encode()
        )
        signing_input = f"{header}.{payload}".encode()
        signature = b64(
            hmac.new(keypair["public_pem"].encode(), signing_input, hashlib.sha256).digest()
        )
        forged = f"{header}.{payload}.{signature}"

        with pytest.raises(SupabaseTokenError):
            await verify_supabase_token(forged)

    async def test_unsigned_tokens_are_rejected(self):
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "attacker", "aud": "authenticated"}).encode()
        ).decode().rstrip("=")

        with pytest.raises(SupabaseTokenError):
            await verify_supabase_token(f"{header}.{payload}.")

    async def test_a_token_signed_by_another_key_is_rejected(self, keypair):
        other = ec.generate_private_key(ec.SECP256R1())
        other_pem = other.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        forged = jwt.encode(
            {"sub": "attacker", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 3600},
            other_pem, algorithm="ES256", headers={"kid": KID},
        )
        with pytest.raises(SupabaseTokenError):
            await verify_supabase_token(forged)

    async def test_garbage_is_rejected(self):
        with pytest.raises(SupabaseTokenError):
            await verify_supabase_token("not-a-jwt")

    async def test_empty_token_is_rejected(self):
        with pytest.raises(SupabaseTokenError):
            await verify_supabase_token("")


class TestClaimChecks:
    async def test_expired_tokens_are_rejected(self, keypair):
        with pytest.raises(SupabaseTokenError, match="expired"):
            await verify_supabase_token(make_token(keypair, exp=int(time.time()) - 60))

    async def test_wrong_audience_is_rejected(self, keypair):
        # A token minted for a different audience is not a session here.
        with pytest.raises(SupabaseTokenError):
            await verify_supabase_token(make_token(keypair, aud="some-other-service"))

    async def test_wrong_issuer_is_rejected(self, keypair):
        with pytest.raises(SupabaseTokenError):
            await verify_supabase_token(make_token(keypair, iss="https://evil.example.com/auth/v1"))


class TestRoleMapping:
    def test_application_role_comes_from_app_metadata(self):
        user = claims_to_user({"sub": "u1", "email": "a@b.test", "app_metadata": {"app_role": "admin"}})
        assert user["role"] == "admin"

    def test_user_metadata_cannot_grant_a_role(self):
        # A user can write their own user_metadata via the Supabase client SDK.
        # Reading role from there would let anyone make themselves an admin.
        user = claims_to_user(
            {"sub": "u1", "email": "a@b.test", "user_metadata": {"app_role": "admin", "role": "admin"}}
        )
        assert user["role"] == "user", "role must never be taken from user-writable metadata"

    def test_supabase_database_role_is_not_the_application_role(self):
        # Every signed-in Supabase user has role "authenticated". Treating that
        # as the app role would make everyone an admin-equivalent.
        user = claims_to_user({"sub": "u1", "email": "a@b.test", "role": "authenticated"})
        assert user["role"] == "user"

    def test_defaults_are_safe_when_claims_are_sparse(self):
        user = claims_to_user({"sub": "u1"})
        assert user["role"] == "user"
        assert user["email"] == ""
