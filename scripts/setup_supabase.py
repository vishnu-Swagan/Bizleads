#!/usr/bin/env python3
"""Configure and verify a Supabase project for BizLeads.

Automates the parts that went wrong by hand the first time:

  * the direct database host (db.<ref>.supabase.co) resolves to IPv6 ONLY.
    Most networks — and Render — cannot reach it. The Supavisor pooler is
    IPv4, so this script uses that and probes to find the right region.
  * the database password must be percent-encoded in the URL. An unencoded
    '@' silently truncates the connection string at the wrong place.
  * the pooler username is `postgres.<project-ref>`, not `postgres`.
  * Supabase now signs tokens with ES256 and publishes a JWKS. There is no
    shared secret to configure, and the value labelled "JWT Secret" in some
    dashboards is the public key id, not a credential.

Usage:

    python3 scripts/setup_supabase.py \\
        --url https://<ref>.supabase.co \\
        --anon-key eyJ... \\
        --db-password 'your-password'

Add --write-env to update app/.env, and --migrate to run Alembic afterwards.
Nothing is written or migrated unless you ask for it.
"""
import argparse
import asyncio
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV_PATH = REPO / "app" / ".env"
BACKEND = REPO / "app" / "backend"

# Supavisor clusters. aws-1 is the newer generation; a project lives in exactly
# one, and probing is cheaper than asking the user to find it in the dashboard.
POOLER_CLUSTERS = ("aws-1", "aws-0")
POOLER_REGIONS = (
    "eu-west-2", "eu-west-1", "eu-central-1",
    "us-east-1", "us-east-2", "us-west-1",
    "ap-south-1", "ap-southeast-1", "ap-southeast-2", "sa-east-1",
)

OK, BAD, INFO = "  ✓", "  ✗", "  ·"


def project_ref(url: str) -> str:
    match = re.match(r"https://([a-z0-9]+)\.supabase\.co", url.strip().rstrip("/"))
    if not match:
        sys.exit(f"{BAD} --url must look like https://<project-ref>.supabase.co")
    return match.group(1)


def check_project_live(url: str, anon_key: str) -> bool:
    """A 200 from /auth/v1/settings proves the project exists and the key works."""
    request = urllib.request.Request(
        f"{url.rstrip('/')}/auth/v1/settings", headers={"apikey": anon_key}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            settings = json.load(response)
    except Exception as exc:
        print(f"{BAD} project/anon key check failed: {exc}")
        return False

    print(f"{OK} project is live and the anon key is valid")
    providers = sorted(k for k, v in (settings.get("external") or {}).items() if v)
    print(f"{INFO} auth providers enabled: {providers or 'none'}")
    if not settings.get("mailer_autoconfirm", False):
        print(f"{INFO} email confirmation is ON — new accounts must click the emailed link")
    return True


def check_jwks(url: str) -> bool:
    try:
        with urllib.request.urlopen(
            f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json", timeout=20
        ) as response:
            keys = json.load(response).get("keys", [])
    except Exception as exc:
        print(f"{BAD} JWKS not reachable: {exc}")
        return False

    if not keys:
        print(f"{BAD} JWKS is empty — this project may still use a legacy shared secret")
        return False

    algs = {k.get("alg") for k in keys}
    print(f"{OK} JWKS published, {len(keys)} key(s), alg {', '.join(sorted(a for a in algs if a))}")
    return True


async def find_pooler(ref: str, password: str):
    """Probe the pooler clusters for the one that owns this project.

    A wrong region answers 'tenant not found'; the right one answers either
    success or 'password authentication failed'. That difference is how the
    region is identified without asking the user to hunt for it.
    """
    try:
        import asyncpg
    except ImportError:
        print(f"{BAD} asyncpg not installed — run this from app/backend/.venv")
        return None, None

    encoded = urllib.parse.quote(password, safe="")

    async def probe(cluster, region):
        host = f"{cluster}-{region}.pooler.supabase.com"
        dsn = f"postgresql://postgres.{ref}:{encoded}@{host}:5432/postgres"
        try:
            conn = await asyncio.wait_for(
                asyncpg.connect(dsn, statement_cache_size=0), timeout=12
            )
            await conn.close()
            return host, "connected"
        except Exception as exc:
            text = str(exc)
            if "password authentication failed" in text:
                return host, "wrong-password"
            if "Tenant or user not found" in text or "not found" in text:
                return host, "not-here"
            return host, f"error: {type(exc).__name__}"

    combos = [(c, r) for c in POOLER_CLUSTERS for r in POOLER_REGIONS]
    for host, status in await asyncio.gather(*(probe(c, r) for c, r in combos)):
        if status == "connected":
            print(f"{OK} database reachable via {host}")
            return host, encoded
        if status == "wrong-password":
            print(f"{BAD} found the project at {host} but the password was rejected")
            print(f"{INFO} reset it: Supabase → Settings → Database → Reset database password")
            return None, None

    print(f"{BAD} could not locate the project on any pooler region")
    print(f"{INFO} do NOT use db.{ref}.supabase.co — it is IPv6-only and unreachable from most networks")
    return None, None


def write_env(url, anon_key, host, encoded_password, ref):
    existing = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    keep = [
        line for line in existing.splitlines()
        if line.strip() and not line.startswith("#")
        and not line.split("=")[0] in {
            "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWKS_URL",
            "SUPABASE_JWT_SECRET", "DATABASE_URL",
        }
    ]
    lines = [
        "# Local development secrets. Gitignored — never commit.",
        *keep,
        "",
        "# --- Supabase ---",
        f"SUPABASE_URL={url.rstrip('/')}",
        f"SUPABASE_ANON_KEY={anon_key}",
        f"SUPABASE_JWKS_URL={url.rstrip('/')}/auth/v1/.well-known/jwks.json",
        "# Pooler host: the direct db.<ref>.supabase.co is IPv6-only.",
        "# Password is percent-encoded; an unencoded '@' breaks the URL.",
        f"DATABASE_URL=postgresql+asyncpg://postgres.{ref}:{encoded_password}@{host}:5432/postgres",
    ]
    ENV_PATH.write_text("\n".join(lines) + "\n")
    ENV_PATH.chmod(0o600)
    print(f"{OK} wrote {ENV_PATH} (mode 600)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="https://<project-ref>.supabase.co")
    parser.add_argument("--anon-key", required=True)
    parser.add_argument("--db-password", required=True)
    parser.add_argument("--write-env", action="store_true", help="update app/.env")
    parser.add_argument("--migrate", action="store_true", help="run alembic upgrade head")
    args = parser.parse_args()

    ref = project_ref(args.url)
    print(f"\nProject ref: {ref}\n")

    live = check_project_live(args.url, args.anon_key)
    jwks = check_jwks(args.url)
    host, encoded = asyncio.run(find_pooler(ref, args.db_password))

    if not (live and jwks and host):
        sys.exit("\nSetup incomplete — fix the items marked ✗ above and re-run.\n")

    if args.write_env:
        write_env(args.url, args.anon_key, host, encoded, ref)
    else:
        print(f"{INFO} re-run with --write-env to save this to app/.env")

    if args.migrate:
        if not args.write_env:
            sys.exit(f"{BAD} --migrate requires --write-env")
        print(f"\n{INFO} running migrations…")
        result = subprocess.run(
            [str(BACKEND / ".venv/bin/python"), "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
        )
        if result.returncode != 0:
            sys.exit(f"{BAD} migration failed")
        print(f"{OK} database migrated to head")

    print(f"""
Next, set these where the services read them:

  Render (API)          Vercel (frontend)
  ────────────────      ─────────────────────
  DATABASE_URL          VITE_SUPABASE_URL      = {args.url.rstrip('/')}
  SUPABASE_URL          VITE_SUPABASE_ANON_KEY = <anon key>
  SUPABASE_JWKS_URL     VITE_API_BASE_URL      = https://bizleads.onrender.com
  MAPBOX_ACCESS_TOKEN
  ALLOWED_ORIGINS

DATABASE_URL for Render (copy exactly, password already encoded):
  postgresql+asyncpg://postgres.{ref}:{encoded}@{host}:5432/postgres

Then in the Supabase dashboard:
  Authentication → URL Configuration
    Site URL      https://bizleads-five.vercel.app
    Redirect URLs https://bizleads-five.vercel.app/**, http://localhost:5173/**
  Authentication → Emails — check the templates name this product
""")


if __name__ == "__main__":
    main()
