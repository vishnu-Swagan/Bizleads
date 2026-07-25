# BizLeads — Stop-the-Bleeding Remediation

**Date:** 2026-07-25
**Status:** Approved for planning
**Source:** `AUDIT-2026-07-25.md`

---

## 1. Purpose

Close the exploitable security, billing-integrity and data-honesty defects found in the audit, so the codebase is safe to keep building on. This is the smallest coherent unit of work that moves the project from *publicly exploitable* to *incomplete*.

It is explicitly **not** an attempt to complete Phase A.

### Success criteria

1. No API route serves or mutates tenant data without authentication.
2. An authenticated user cannot read or write another user's records, or escalate their own plan, credits or subscription state through any API route.
3. No code path returns AI-fabricated businesses as live results, or writes them to the leads table.
4. Existing fabricated rows are identifiable in the UI without being destroyed.
5. `verify-payment` cannot be forged with a foreign session, and cannot be replayed to reset credit usage.
6. Every one of the above is covered by an automated test that fails if the defect returns.

---

## 2. Non-goals

Deferred to the Foundation tier and beyond. Listing them so this document cannot be misread as "billing is fixed" or "Phase A is done":

- **Stripe webhooks and subscription lifecycle.** After this work, a customer who cancels in Stripe still retains access indefinitely. This is the largest known remaining defect.
- `workspace_id` tenancy on leads, plus workspace roles, seats and invitations. Scoping stays per-user.
- Trial expiry and seat-limit enforcement.
- Async job queue, partial results, cancellation.
- Evidence persistence, canonical business table, deduplication, persisted scores.
- Making the deep pass actually run audits (here it is only stopped from overcharging).
- Admin console, legal pages, email verification, password reset.

---

## 3. Architecture

One new module: `backend/dependencies/tenancy.py`.

### 3.1 Workspace resolution

`select(Workspaces).where(Workspaces.owner_id == current_user.id)` is currently duplicated five times across `routers/payments.py` and `routers/discover.py`, and the copies disagree — three auto-create a workspace on miss, one 404s. This is a latent bug independent of security.

Replace with:

- `get_current_workspace(current_user, db) -> Workspaces` — a FastAPI dependency. Resolves the caller's workspace; raises 404 if absent. Never creates.
- `ensure_workspace_for_user(current_user, db) -> Workspaces` — a service function. Resolves or creates. Called from exactly two places: `GET /billing/usage` and `POST /discover/run`.

### 3.2 EntityPolicy

```python
@dataclass(frozen=True)
class EntityPolicy:
    model: type
    scope: Literal["user", "workspace"]
    writable: frozenset[str]
    never_return: frozenset[str] = frozenset()
    allow_create: bool = True
    allow_delete: bool = True
```

Each entity router declares one policy at module level.

### 3.3 Helpers

- `apply_scope(stmt, policy, principal)` — appends the ownership filter to a SELECT.
- `filter_writes(payload, policy, *, strict: bool)` — removes non-writable keys.
  - `strict=False` (create): drop silently.
  - `strict=True` (update): raise `HTTPException(400)` **naming the rejected field**. A client that deliberately sends `plan: "agency"` is told no rather than silently ignored.
- `strip_never_return(obj, policy)` — removes write-only fields from response payloads.

### 3.4 Policy table

| Router | Scope | Client may write | Server-only |
|---|---|---|---|
| `workspaces` | own row (`owner_id`) | `name`, `settings_json` | `plan`, `monthly_credits`, `credits_used`, `subscription_status`, `stripe_customer_id`, `stripe_subscription_id`, `max_seats`, `trial_ends_at`, `credits_reset_at`, `slug`, `owner_id` |
| `credit_ledger` | workspace | *nothing* (read-only) | all — append-only from server paths |
| `search_jobs` | workspace | *nothing* (read-only) | created by `/discover/run` |
| `workspace_members` | workspace | *nothing* (read-only) | no invitation flow exists yet |
| `provider_connections` | workspace | `provider_type`, `provider_name`, `config_json` | `config_json` is in `never_return` — write-only, never serialised back |
| `offer_profiles` | workspace | all fields | — genuinely user-owned data |
| `leads` | user | unchanged | — only `/all` is removed |
| `lead_notes` | user | unchanged | — only `/all` is removed |
| `ai_interaction_logs` | user | *nothing* (read-only) | — only `/all` is removed |

Rationale for the two non-obvious rows: `provider_connections.config_json` stays writable so a future integrations settings page needs no redesign, but never leaves the server. `workspace_members` is read-only because there is no invitation flow to write against — making it writable now would be designing for a feature that does not exist.

### 3.5 Rejected alternatives

- **Delete the six routers.** Nothing consumes them, so this was free and closes the whole bug class. Rejected by the project owner in favour of preserving them for a future admin UI.
- **Deny-by-default middleware on `/api/v1/entities/*`.** Cannot express row-level ownership, so it complements rather than replaces per-router scoping. Held as an optional backstop if routers are regenerated.
- **Reusing `core/mask_crypto.py`** for `config_json`. It defaults to a hardcoded key (`"Mgx@FunctionSea"`) when `MASK_KEY` is unset, and is currently dead code. Not adopted; `never_return` is used instead.

---

## 4. Changes

### 4.1 Authentication and scoping

Apply `get_current_user` plus the policy helpers to all routes in: `workspaces`, `workspace_members`, `credit_ledger`, `provider_connections`, `offer_profiles`, `search_jobs`. Approximately 54 routes.

### 4.2 Delete `/all` routes

Remove from `routers/leads.py:159`, `routers/lead_notes.py`, `routers/ai_interaction_logs.py`. Verified unused — the frontend calls `.query`, which maps to `GET ""`.

### 4.3 CORS

`main.py:92` — replace `allow_origin_regex=r".*"` with an explicit list from an `ALLOWED_ORIGINS` env var (comma-separated), retaining `allow_credentials=True`. Default to localhost dev origins.

**Highest deployment risk in this tier.** If the deployed frontend origin is not in the list, the app breaks in production. Must appear in the handoff notes.

### 4.4 aihub

Add `get_current_user` to `/gentxt`, `/genimg`, `/genvideo`, `/genaudio`, `/transcribe`, `/analyzepdf`. Safe: internal callers use `AIHubService()` as a Python object, not over HTTP.

### 4.5 verify-payment

`routers/payments.py:268`:

1. Reject if `session.metadata.get("user_id") != current_user.id` → 403.
2. Require `session.payment_status == "paid"` in addition to `status == "complete"`.
3. Idempotency: look for a `Credit_ledger` row with `reference_id == session.id`. If present, return current workspace state and mutate nothing.
4. On first application only: set plan, credits, seats, Stripe IDs, and write the ledger row. **Never** reset `credits_used` on a repeat call.

This starts populating `credit_ledger` for its intended purpose without pulling the full ledger redesign into this tier.

### 4.6 Mock data seeding

Gate `initialize_mock_data()` (`main.py:72`) behind `SEED_MOCK_DATA=true`, default off. Not deleted — the Atoms template may be regenerated against it.

### 4.7 `data_source` on leads

New nullable column, Alembic migration.

- Values: `provider`, `ai_generated`, `mock`, `manual`. NULL renders as "Unverified".
- Backfill: rows exactly matching the eight records in `backend/mock_data/leads.json` (business name **and** `user_id == "1466317"`) → `mock`. All other existing rows left NULL.
- Nothing is deleted.
- Going forward, `saveAsLead` passes the source through from the discovery response.

### 4.8 Close all three fabrication paths

1. **`routers/discover.py`** — remove the AI fallback branch. Reorder so the provider-configured check happens *before* the job row is created and credits are deducted, so an unconfigured provider costs nothing. A configured provider returning zero matches still charges, because the provider call was genuinely made.
2. **`routers/search.py`** — delete `POST /businesses`, which calls `generate_search_results` directly with no provider attempt and no credit charge. Its only consumer, `pages/Search.tsx`, is no longer routed by `App.tsx`.
3. **`routers/automation.py`** — delete `POST /generate-leads`, which AI-generates businesses and writes them straight into the leads table. Its UI is orphaned, and the behaviour is precisely what the master prompt was written to eliminate.

### 4.9 Deep-pass overcharge

`discover.py:121` — the deep pass costs 3 credits and runs identical code to the 1-credit quick pass (`audit_website` is imported at line 21 and never called). Set deep to 1 credit until it does more work, and adjust the `/filters` label accordingly.

---

## 5. UI

Two surfaces. The existing design system (shadcn/ui + Tailwind, slate neutrals, indigo-600 primary) is reused unchanged — no new design system.

**Discover — provider unconfigured.** A `Card` using the compound `CardHeader`/`CardContent` pattern, naming the missing provider and linking to Settings. Must be visually distinct from the zero-matches state: one means "you have no data source", the other means "widen your filters". Conflating them is how the fallback was rationalised originally.

**Discover — zero matches.** Separate empty state with filter-widening suggestions. Never a blank region.

**`data_source` badge** on Leads and Lead Detail. Existing `Badge` component: green for `provider`, amber for NULL/unverified, slate for `mock`. Colour is never the only signal — each badge carries text plus a `title` explaining what the source means, because this badge determines whether a phone number should be trusted.

**Toasts** get `role="alert"` so errors are announced, not merely rendered red.

---

## 6. Error handling

- Disallowed writes → 400 naming the offending field.
- The structured error shape already used for insufficient credits (`discover.py:126`) is extended to `provider_unconfigured`, so the frontend switches on an `error` code rather than string-matching messages.
- Cross-tenant access returns **404, not 403** — do not confirm that another tenant's row exists.
- Not changed, but must appear in the handoff: `main.py:158` returns full stack traces when `ENVIRONMENT=dev`. That variable must not be `dev` in production.

---

## 7. Testing

`pytest` + `pytest-asyncio` + `httpx` against FastAPI's `TestClient`, in `backend/tests/`. Dev dependencies in a separate `requirements-dev.txt` so production installs are unchanged.

Test DB: in-memory SQLite via `aiosqlite`, schema built with `Base.metadata.create_all` rather than Alembic, since the migrations are Postgres-flavoured.

**Known gap:** the `data_source` migration itself is therefore not covered. It is verified by hand against real Postgres before shipping.

Two client fixtures: `anon_client` (no dependency override, so 401s are genuine) and `user_client(user)` (overrides `get_current_user`, avoiding JWT minting).

### Cases

1. **Anonymous access** — parametrized across every route in the six routers → 401; the three deleted `/all` paths → 404. Parametrization is the point: it catches the route someone forgets.
2. **Cross-tenant** — user A creates a record; user B attempts read/update/delete by ID → 404.
3. **Write allowlist** — authenticated PUT of `plan` / `monthly_credits` / `subscription_status` on the caller's *own* workspace → 400, with the DB value asserted unchanged. This proves auth alone would have been insufficient.
4. **Write-only field** — `config_json` never appears in any `provider_connections` response body.
5. **verify-payment** — foreign `session_id` → 403; replaying a valid one leaves credits unchanged and creates no duplicate ledger row. `stripe.checkout.Session.retrieve` is monkeypatched.
6. **Fabrication guard** — provider unconfigured → zero credits charged, `provider_unconfigured` status, empty results, and the AI service monkeypatched to raise if invoked at all. This is the highest-value test in the suite; it fails loudly if a fallback is ever reintroduced.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| `ALLOWED_ORIGINS` misconfigured in production breaks the app | Localhost default; explicit handoff note; verify before deploy |
| `MAPBOX_ACCESS_TOKEN` unset means Discover legitimately returns nothing | Intended behaviour, but confirm the token is set or the app appears broken |
| SQLite-vs-Postgres divergence hides a defect | Schema is simple (Integer/String/Boolean/DateTime); migration hand-verified |
| Backfill mis-tags an edited seed row | Exact match on name **and** synthetic `user_id`; nothing deleted, so mistakes are reversible |
| ~54 route edits, one missed | Parametrized anonymous-access test enumerates routes rather than trusting review |

---

## 9. State after this work

**Fixed:** unauthenticated data access, privilege escalation via entity CRUD, cross-tenant reads, payment forgery and replay, AI fabrication in all three code paths, unlabelled fake data, deep-pass overcharge, wide-open CORS.

**Still broken, by design of this scope:** no Stripe webhook, so cancellations never revoke access; tenancy is per-user rather than per-workspace; trials never expire; seats unenforced; discovery is synchronous; no evidence persistence or deduplication; no admin console; no legal pages.

The correct next tier is Foundation, and within it the webhook is the highest priority.
