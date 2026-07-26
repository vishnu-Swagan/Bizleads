# Handoff — Stop-the-Bleeding Remediation

**Branch:** `security/stop-the-bleeding` (22 commits, `d9d5785..9e3ae6f`)
**Date:** 2026-07-25
**Source audit:** `AUDIT-2026-07-25.md` · **Spec:** `docs/superpowers/specs/2026-07-25-bizleads-security-remediation-design.md`

Backend: 97 tests passing. Frontend: builds and typechecks clean apart from one pre-existing error in an orphaned file.

---

## 1. Deploy gates — do these before shipping

| # | Gate | Why it matters |
|---|---|---|
| 1 | **`ALLOWED_ORIGINS` must contain the production frontend origin**, comma-separated. | The wide-open CORS policy is gone. If this is unset or wrong, the app breaks entirely in production. A bare `*` is now rejected with a logged warning, because `*` plus `allow_credentials=True` would re-open the original hole. |
| 2 | **Run the Alembic migration against real Postgres**: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`. | Migration `c7d1e2f3a4b5` (adds `leads.data_source`) has **never been executed**. No Postgres was reachable during this work, and a SQLite run was deliberately not substituted — SQLite's `ALTER TABLE` differs materially. The test suite builds tables via `create_all`, so it does not exercise the migration. |
| 3 | ~~`SEED_MOCK_DATA` must remain unset.~~ **Resolved.** | The seeder and its eight fabricated leads were deleted, along with the AI business generator. `test_the_fabrication_path_does_not_exist` fails if either returns. |
| 4 | **`ENVIRONMENT` must not be `dev`.** | `main.py`'s exception handler returns full stack traces when it is. |
| 5 | **`MAPBOX_ACCESS_TOKEN` must be set**, or Discover legitimately returns its setup state for every search. | This is now correct behaviour, not a bug — see §2. |

---

## 2. What changed, in one paragraph

Every API route that served or mutated tenant data now requires authentication and is scoped to its owner — six entity routers, nine `/all` dump endpoints deleted, cross-tenant access returns 404 rather than confirming a row exists. Plan, credit and subscription columns are server-only; a client that tries to write one gets a 400 naming the field. `verify-payment` now binds a checkout session to its purchaser and is single-use, killing a replay that reset credit usage to zero on demand. And discovery no longer invents businesses: all three code paths that returned LLM-fabricated names, addresses, phones and emails as live results are gone, an unconfigured provider now returns an honest setup state and charges nothing, and existing leads carry a provenance badge.

---

## 3. Still broken — deliberately out of scope

These were non-goals of this tier, listed here so nothing reads as more finished than it is.

- **No Stripe webhook.** A customer who cancels in Stripe keeps access indefinitely. This is the largest remaining defect and the correct next piece of work.
- **Tenancy is per-user, not per-workspace.** `leads` has no `workspace_id`, so team seats, roles and shared pipelines cannot work as specified.
- **Trials never expire; seats are unenforced.** `trial_ends_at` and `max_seats` are stored and never read.
- **Discovery is synchronous.** No queue, no partial results, no cancellation.
- **No evidence persistence, deduplication, or persisted scores.** Discovery results live only in one HTTP response; a saved lead loses its scoring.
- **No admin console, legal pages, email verification, or password reset.**
- **The deep pass does not audit.** It no longer overcharges (was 3 credits for identical work, now 1), but it still runs the same code as the quick pass.

---

## 4. Known issues carried forward

**Concurrent double-application race in `verify-payment`.** `Credit_ledger.reference_id` is indexed but not unique, so two simultaneous first-time applications of the same session can both pass the idempotency check. Assessed as materially narrower than the exploit it replaced: it needs an attacker already holding a legitimately paid session firing concurrent duplicates, and no code path computes a credit balance from the ledger — balances come from `workspaces.monthly_credits/credits_used`, so there is no reachable credit gain. The probe now takes the first row rather than asserting uniqueness, so a duplicate degrades to a harmless extra audit row instead of permanently 500ing the endpoint. **Real fix:** a Postgres partial unique index on `reference_id` (the column defaults to `''`, so a plain constraint would fail) — Foundation-tier work.

**New users hit a 404 on workspace-scoped list endpoints** before they have run a search or opened billing, because `get_current_workspace` resolves rather than creates. Unreachable in the shipped product today — nothing in the frontend calls those six routers — but it becomes visible the moment an admin UI is built on them.

**`pnpm run build` does not work on this machine.** pnpm's wrapper re-runs a dependency check that trips its supply-chain freshness policy (~57 lockfile entries, mostly `@radix-ui`, were published inside the cutoff window). Use `./node_modules/.bin/vite build` and `./node_modules/.bin/tsc --noEmit -p tsconfig.app.json` instead. Note that `vite build` transpiles via esbuild and does **not** typecheck — `tsc` is the real gate.

**One pre-existing typecheck error** in `src/pages/Dashboard.tsx` — the orphaned legacy dashboard `App.tsx` no longer routes to. It must be deleted before any CI typecheck gate is added, or the gate will fail on day one.

**Deferred minor cleanups:** dead imports in `routers/search.py`; five drifting workspace-seeding helpers across test files; the `text-xs` on the Source table header rendering it smaller than its siblings; a no-op `containerAriaLabel` on the sonner wrapper; 17 `f"Internal server error: {str(e)}"` responses that leak exception text regardless of `ENVIRONMENT`.

---

## 5. One thing worth knowing about the process

Fourteen defects were caught by review that the implementing agents did not catch themselves, and **most of them were defects in the plan rather than in the implementation**. The ones that would have been most expensive to discover later:

- Test fixtures that made both clients resolve to the same user — the entire cross-tenant suite would have passed while testing nothing.
- `ALLOWED_ORIGINS=*` reintroducing credentialed-wildcard CORS, which is exactly what an operator reaches for during an incident.
- A regression guard that patched the wrong namespace, so a future re-introduction of the AI fallback would have returned fabricated businesses with a green test suite.
- The mock-seeding gate covering `main.py` but not `lambda_handler.py` — found only by the final whole-branch review, because no per-task review could see across entrypoints.

If this branch is extended, keep the review gate.
