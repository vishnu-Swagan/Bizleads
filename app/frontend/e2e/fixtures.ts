import { test as base, expect, type Page } from '@playwright/test';

/**
 * A note on Golden Rule 10 ("mock external services only, never your own app").
 *
 * The `signedIn` fixture below stubs this app's own auth endpoint, and the
 * discovery specs stub its own discovery endpoint. That is a deliberate,
 * bounded exception, for two reasons:
 *
 *   1. The states under test are server states the UI must render honestly —
 *      "no provider configured" and "provider ran, matched nothing". Producing
 *      them against a live backend means unsetting MAPBOX_ACCESS_TOKEN mid-run.
 *   2. The backend side of that contract is already covered by 97 pytest tests,
 *      including a guard that fails if the AI-fabrication fallback is ever
 *      reintroduced. What pytest cannot reach is whether the UI *renders* those
 *      states distinguishably — which is exactly what these specs assert.
 *
 * The contract is pinned on both sides: the status strings below are the same
 * literals the backend returns in `routers/discover.py`. If either side changes
 * them, one of the two suites fails.
 *
 * Keep every stub in this file so the mocked surface stays visible in one place.
 * `e2e/security/auth-gate.spec.ts` deliberately stubs nothing.
 */

/** Must match VITE_SUPABASE_URL's project ref — supabase-js keys storage by it. */
export const SUPABASE_PROJECT_REF = 'qpgoffrgqongaxubsgau';

/**
 * A Supabase user as /auth/v1/user returns it.
 *
 * `app_metadata.app_role` is what grants the application role. `user_metadata`
 * is deliberately left without one: it is user-writable through the client
 * SDK, so anything read from it must never confer privilege.
 */
export const SUPABASE_USER = {
  id: 'e2e-user',
  aud: 'authenticated',
  role: 'authenticated',
  email: 'e2e@example.test',
  email_confirmed_at: '2026-01-01T00:00:00Z',
  app_metadata: { provider: 'email', providers: ['email'] },
  user_metadata: { full_name: 'E2E User' },
  created_at: '2026-01-01T00:00:00Z',
};

export const TEST_USER = {
  id: 'e2e-user',
  email: 'e2e@example.test',
  name: 'E2E User',
  role: 'user',
  last_login: null,
};

/** Mirrors GET /api/v1/discover/filters. */
export const DISCOVER_FILTERS = {
  mapbox_connected: false,
  pagespeed_connected: false,
  countries: ['United Kingdom', 'United States'],
  categories: ['Cafe', 'Plumber'],
  website_states: [
    { value: 'all', label: 'All States' },
    { value: 'no_website', label: 'No Website' },
  ],
  pass_types: [
    { value: 'quick', label: 'Quick Discovery (1 credit)', description: 'Entity resolution and basic scoring' },
  ],
};

type Fixtures = {
  /** A page whose session resolves to TEST_USER, so /app/* renders instead of the sign-in gate. */
  signedInPage: Page;
};

export const test = base.extend<Fixtures>({
  signedInPage: async ({ page }, use) => {
    // Auth is Supabase now, not the Atoms SDK. Two things are needed to look
    // signed in, and both are required — a stubbed user endpoint with no stored
    // session yields no access token to send, and a stored session with no
    // stubbed endpoint fails verification against the real project.
    //
    // 1. A persisted session, under the key supabase-js actually reads.
    await page.addInitScript(
      ({ ref, user }) => {
        const session = {
          access_token: 'e2e-fake-access-token',
          refresh_token: 'e2e-fake-refresh-token',
          token_type: 'bearer',
          expires_in: 3600,
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          user,
        };
        window.localStorage.setItem(`sb-${ref}-auth-token`, JSON.stringify(session));
      },
      { ref: SUPABASE_PROJECT_REF, user: SUPABASE_USER },
    );

    // 2. supabase-js validates the session against /auth/v1/user.
    await page.route('**/auth/v1/user**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SUPABASE_USER),
      }),
    );

    // Token refresh, in case the client decides the session needs renewing
    // mid-test. Without this a refresh attempt hits the real project and the
    // test becomes network-dependent and flaky.
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'e2e-fake-access-token',
          refresh_token: 'e2e-fake-refresh-token',
          token_type: 'bearer',
          expires_in: 3600,
          user: SUPABASE_USER,
        }),
      }),
    );

    // Mark the guided tutorial as already completed. This is real app state,
    // not a mock — it is exactly what a returning user's browser holds. Without
    // it, GuidedTutorial renders a full-screen backdrop (`fixed inset-0 z-[60]`)
    // that intercepts every pointer event, so nothing on the page is clickable.
    await page.addInitScript(() => {
      window.localStorage.setItem('bizleads_tutorial_completed', 'true');
    });

    await use(page);
  },
});

export { expect };

/** Stub GET /api/v1/discover/filters — Discover fetches this on mount. */
export async function stubDiscoverFilters(page: Page) {
  await page.route('**/api/v1/discover/filters*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(DISCOVER_FILTERS),
    }),
  );
}

/** Stub POST /api/v1/discover/run with a given backend response body. */
export async function stubDiscoveryRun(page: Page, body: Record<string, unknown>) {
  await page.route('**/api/v1/discover/run*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    }),
  );
}

/** Stub the leads list query with the given rows. */
export async function stubLeads(page: Page, items: Array<Record<string, unknown>>) {
  await page.route('**/api/v1/entities/leads*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items, total: items.length, skip: 0, limit: 200 }),
    }),
  );
}

/** Minimal lead row; override what a given test cares about. */
export function makeLead(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    user_id: TEST_USER.id,
    business_name: 'Acme Cafe',
    category: 'Cafe',
    location: 'Leeds',
    country: 'United Kingdom',
    website_url: '',
    website_score: 0,
    social_score: 0,
    has_website: false,
    social_platforms: '[]',
    contact_email: '',
    contact_phone: '',
    pipeline_stage: 'new_lead',
    priority: 'medium',
    notes_count: 0,
    last_contacted: '',
    data_source: null,
    ...overrides,
  };
}
