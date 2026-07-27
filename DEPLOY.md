# Deploying BizLeads

Three services: **Vercel** (frontend), **Render** (backend), **Supabase** (Postgres + auth).
Supabase cannot host the backend — it has no Python runtime.

Do these in order. Render must come first because Vercel needs its URL.

---

## 0. Before you start

| | |
|---|---|
| Repo | https://github.com/vishnu-Swagan/Bizleads |
| Supabase project | already created, database already migrated |
| Values you need | in your local `app/.env` — never commit it |

Templates for every variable: `app/backend/.env.example`, `app/frontend/.env.example`.

---

## 1. Render — backend

New → **Blueprint** → pick the repo. Render reads `render.yaml` from the repo root and finds the service in `app/backend`.

Then set these four in **Environment** (they are `sync: false` in the blueprint, so they are deliberately not in the repo):

| Variable | Where it comes from |
|---|---|
| `DATABASE_URL` | `app/.env` — the **pooler** URL, password percent-encoded |
| `SUPABASE_URL` | `app/.env` |
| `SUPABASE_JWKS_URL` | `app/.env` |
| `MAPBOX_ACCESS_TOKEN` | a **public `pk.`** token, not an `sk.` one |

Already set for you in the blueprint: `ALLOWED_ORIGINS`, `ENVIRONMENT=production`, `PYTHON_VERSION`.

**Region is `frankfurt`** — Render has no UK region, and Frankfurt is its closest option to your London (`eu-west-2`) database.

Deploy, then check `https://<your-service>.onrender.com/health` returns `{"status":"healthy"}`.

> **Free tier sleeps after 15 minutes idle.** The first request afterwards takes ~50s to wake. Fine for evaluation; upgrade before showing it to a customer.

---

## 2. Vercel — frontend

Import the repo, then **set Root Directory to `app/frontend`**.

This is the step that breaks silently if you skip it. The build config and the pnpm lockfile both live in `app/frontend`; from the repo root Vercel finds neither, fails to detect pnpm, and the build either errors or produces an empty site.

Environment variables:

| Variable | Value |
|---|---|
| `VITE_SUPABASE_URL` | your Supabase URL |
| `VITE_SUPABASE_ANON_KEY` | the anon key (public by design) |
| `VITE_API_BASE_URL` | your Render URL from step 1 |

---

## 3. Close the CORS loop

Back on Render, set `ALLOWED_ORIGINS` to your actual Vercel URL.

If this does not match, **every browser call fails** while the API looks perfectly healthy when you curl it. It is the most common way this deployment breaks.

A bare `*` is rejected at startup with a logged warning — combined with credentialed requests it would reopen the any-origin hole this codebase was audited for.

---

## 4. Supabase — auth URLs

**Authentication → URL Configuration**

- Site URL: your Vercel URL
- Additional redirect URLs: `http://localhost:5173` for local dev

Without this, confirmation and password-reset emails send people to the wrong place.

Email auth is already enabled with confirmation on (`mailer_autoconfirm: false`), so new accounts must click the emailed link before they can sign in.

---

## 5. Migrations

The database is **already migrated** to head (`d8e2f4a6b1c3`).

For future migrations, run them yourself against the production database before deploying code that needs them:

```bash
cd app/backend
DATABASE_URL='<production pooler url>' .venv/bin/python -m alembic upgrade head
```

`render.yaml` deliberately has no auto-migrate step. A migration that runs automatically on every deploy will eventually run a destructive one on a database nobody backed up.

---

## Verifying it works

1. `GET /health` on Render → `{"status":"healthy"}`
2. Open the Vercel URL → landing page renders
3. Go to `/app/dashboard` → sign-in gate appears (this is correct)
4. Sign up, confirm via email, sign in
5. Discover → pick a city and category → real businesses appear

If step 5 returns "No discovery provider connected", `MAPBOX_ACCESS_TOKEN` is missing or invalid on Render. That message is deliberate: the app will not invent businesses to fill a gap.

---

## Two things not to do

**Do not enable Stripe.** There is still no webhook, so a customer who cancels keeps access indefinitely. The code path exists and will work if you set `STRIPE_SECRET_KEY` — that is the risk.

Lead fabrication is structurally impossible: the mock-data seeder and the AI business generator were both deleted, and a test asserts they stay deleted. Every lead comes from a licensed provider.

See `docs/HANDOFF-stop-the-bleeding.md` for everything else still outstanding.

## Scheduled automations

An automation is a saved search that runs on a schedule, saves the new
businesses it finds, qualifies them, and drafts outreach from what it measured.
**It never sends.** Drafts land in the approval queue for a human, because the
customer is the legal sender of every message under the Terms, and unattended
cold email is how a sending domain gets blacklisted.

Render's free tier has no cron and sleeps when idle, so nothing inside the
process can wake itself to honour a schedule. `.github/workflows/run-automations.yml`
calls the API hourly instead. To enable it:

1. Generate a secret: `openssl rand -hex 32`
2. Render → Environment → add `AUTOMATION_CRON_SECRET` with that value
3. GitHub → Settings → Secrets and variables → Actions → new repository secret,
   same name, same value

Until both sides match, the endpoint returns 401 and no schedule fires. Nothing
else is affected — "Run now" still works from the Automations page, and the
approval queue behaves normally.

To verify: GitHub → Actions → "Run scheduled automations" → Run workflow. A
free-tier instance can take about a minute to wake, which the workflow retries
around.
