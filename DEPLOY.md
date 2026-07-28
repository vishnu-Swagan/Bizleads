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

Then set these in **Environment** (they are `sync: false` in the blueprint, so they are deliberately not in the repo).

**Required — the app does not work without them:**

| Variable | Where it comes from |
|---|---|
| `DATABASE_URL` | `app/.env` — the **pooler** URL, password percent-encoded |
| `SUPABASE_URL` | `app/.env` |
| `SUPABASE_JWKS_URL` | `app/.env` |
| `MAPBOX_ACCESS_TOKEN` | a **public `pk.`** token, not an `sk.` one |
| `CREDENTIAL_ENCRYPTION_KEY` | generate once (below). Without it **no customer can save a sending identity at all** — there is deliberately no plaintext fallback |

Generate the encryption key once and keep it safe — **rotating it invalidates every stored credential**, and every customer would have to re-enter their password or API key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Feature-gated — each one only disables its own feature:**

| Variable | Unset means |
|---|---|
| `AUTOMATION_CRON_SECRET` | schedules never fire; automations run only when a human presses "Run now". See *Scheduled automations* below — it must match a GitHub secret of the same name |
| `PAGESPEED_API_KEY` | website quality stays on the free heuristic tier instead of real Lighthouse audits. The key is free, no billing card |
| `RESEND_API_KEY` / `SMTP_*` | the operator's own fallback sending account is unavailable. Customers with their own identity are unaffected |
| `ANTHROPIC_API_KEY` / `NVIDIA_API_KEY` | the AI polish buttons report "not configured". The deterministic composer still writes every draft |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | billing is off. See *Stripe* below — do not set one without the other |

Already set for you in the blueprint: `ALLOWED_ORIGINS`, `ENVIRONMENT=production`, `PYTHON_VERSION`, and the SMTP host/port defaults.

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

## Stripe

The webhook now exists (`routers/stripe_webhook.py`, mounted at `/api/v1/payments/webhook`), so billing is safe to enable — **provided you set both keys**. `STRIPE_SECRET_KEY` alone is the dangerous configuration: checkout would succeed while nothing activates, renews or revokes.

1. Add the endpoint at https://dashboard.stripe.com/webhooks pointing to `https://<your-api>/api/v1/payments/webhook`
2. Subscribe it to exactly these six events — the handler acknowledges and ignores anything else:
   `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`
3. Copy the `whsec_...` shown on that screen into `STRIPE_WEBHOOK_SECRET` on Render, and the `sk_...` into `STRIPE_SECRET_KEY`
4. Verify: `curl -X POST https://<your-api>/api/v1/payments/webhook -d '{}'` should return **400 "Missing Stripe-Signature header"**. A **503 "Billing webhook is not configured"** means `STRIPE_WEBHOOK_SECRET` did not reach the process — the endpoint fails closed rather than accepting unsigned billing events.

Start with `sk_test_` keys and Stripe's test-mode webhook until a full subscribe → renew → cancel cycle behaves.

---

## Email sending

Each customer sends from **their own** identity, stored encrypted under `CREDENTIAL_ENCRYPTION_KEY` and configured in-app. The `SMTP_*` / `RESEND_*` variables on Render are only the **operator's fallback**, used by a workspace that has not set up its own. That split is deliberate: one customer's spam complaint must not blacklist a shared domain, replies must reach the customer rather than you, and the Terms name the customer as the legal sender.

Whichever backend is configured is the one that runs — setting `RESEND_API_KEY` switches to Resend automatically, no flag required.

**Resend needs a verified domain.** Until the sending domain is verified in the Resend dashboard, the only address it will deliver to is the one that owns the account — enough to test the pipeline, not enough to reach prospects. An unverified From address is rejected by name, so the error tells you which domain is at fault.

**Gmail SMTP** needs a 16-character App Password from https://myaccount.google.com/apppasswords (2-Step Verification must be on first); a normal account password is always rejected. Gmail caps sending at ~500/day and suspends accounts used for cold outreach, so treat it as a test path only.

Read your provider's acceptable use policy before sending cold outreach through it — transactional providers generally prohibit unsolicited email.

---

## AI writing assistance

Entirely optional. Without a key the AI buttons report "not configured" and the deterministic composer still writes every draft; you lose wording polish, not function.

- **NVIDIA NIM** — free at https://build.nvidia.com, OpenAI-compatible. Set `NVIDIA_API_KEY`; `NVIDIA_MODEL` defaults to `meta/llama-3.3-70b-instruct`.
- **Anthropic** — set `ANTHROPIC_API_KEY`. Preferred when both are set, because it follows the "add no facts" instruction markedly more reliably, and that instruction is the only thing standing between this feature and the invented claims the product exists to avoid.

Verify from a signed-in session: `GET /api/v1/outreach/ai/status` returns `{"available": true, "model": ...}`.

---

## One thing that stays true

Lead fabrication is structurally impossible: the mock-data seeder and the AI business generator were both deleted, and a test asserts they stay deleted. Every lead comes from a licensed provider. The AI writing assistance added later does not weaken this — the model is shown only measured findings and the user's own words, and is instructed to add no claim not already present; a lead with no findings produces no email at all, because the provider is never called.

See `docs/HANDOFF-stop-the-bleeding.md` for everything else still outstanding. Note that its "no Stripe webhook" entry is now out of date — that was the next piece of work it named, and it has since been done.

---

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

To tell the two failure modes apart without opening the Render dashboard, send
a deliberately wrong secret:

```bash
curl -X POST https://<your-api>/api/v1/automations/run-scheduled \
  -H 'X-Automation-Secret: wrong'
```

- `"Scheduled runs are disabled: AUTOMATION_CRON_SECRET is not set."` — the
  Render side is missing.
- `"Invalid automation secret"` — Render has it; the mismatch is on the GitHub
  side, or the two values differ.
