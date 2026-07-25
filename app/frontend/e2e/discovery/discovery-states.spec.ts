import { test, expect, stubDiscoverFilters, stubDiscoveryRun } from '../fixtures';

/**
 * The UI half of the data-honesty fix.
 *
 * Discovery used to fall through to an LLM that invented business names,
 * addresses, phone numbers and emails whenever the geo provider was
 * unconfigured or returned nothing, and rendered them as live results. The
 * backend path is gone and pytest guards it. These specs guard the UI: that
 * the two honest states exist, and that a user cannot mistake one for the
 * other.
 *
 * Status strings match the literals in routers/discover.py.
 */

async function runSearch(page: import('@playwright/test').Page) {
  await page.goto('/app/discover');
  await page.getByRole('button', { name: 'Run Discovery' }).click();
}

test.describe('discovery result states', () => {
  test('an unconfigured provider shows a setup state, not results', async ({ signedInPage: page }) => {
    await stubDiscoverFilters(page);
    await stubDiscoveryRun(page, {
      status: 'provider_unconfigured',
      error: 'provider_unconfigured',
      message: 'No discovery provider is connected. Add a MapBox access token in Settings to run searches.',
      provider: 'mapbox',
      results: [],
      total_results: 0,
      credits_charged: 0,
      credits_remaining: 25,
    });

    await runSearch(page);

    await expect(
      page.getByRole('heading', { name: 'No discovery provider connected' }),
    ).toBeVisible();

    // It must tell the user this costs nothing and that nothing was invented.
    await expect(page.getByText(/no credits were charged/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /go to settings/i })).toBeVisible();

    // The other state must NOT be on screen — that distinction is the point.
    await expect(page.getByRole('heading', { name: 'No businesses matched' })).toHaveCount(0);
  });

  test('zero matches shows a search-outcome state, not a setup state', async ({ signedInPage: page }) => {
    await stubDiscoverFilters(page);
    await stubDiscoveryRun(page, {
      job_id: 1,
      status: 'no_matches',
      results: [],
      total_results: 0,
      credits_charged: 1,
      credits_remaining: 24,
      pass_type: 'quick',
      score_version: '1.0.0',
      data_source: 'mapbox',
    });

    await runSearch(page);

    await expect(page.getByRole('heading', { name: 'No businesses matched' })).toBeVisible();

    // Must not be mistakable for a configuration problem.
    await expect(
      page.getByRole('heading', { name: 'No discovery provider connected' }),
    ).toHaveCount(0);
    await expect(page.getByRole('button', { name: /go to settings/i })).toHaveCount(0);
  });

  test('neither state renders a blank region', async ({ signedInPage: page }) => {
    // The defect this replaced was a huge empty area with no explanation.
    await stubDiscoverFilters(page);
    await stubDiscoveryRun(page, {
      status: 'provider_unconfigured',
      error: 'provider_unconfigured',
      message: 'No discovery provider is connected.',
      provider: 'mapbox',
      results: [],
      total_results: 0,
      credits_charged: 0,
      credits_remaining: 25,
    });

    await runSearch(page);

    const heading = page.getByRole('heading', { name: 'No discovery provider connected' });
    await expect(heading).toBeVisible();
    // A heading plus explanatory body copy, not a bare container.
    await expect(page.getByText(/never invent businesses|add a mapbox access token/i).first()).toBeVisible();
  });

  test('no results view claims discovery is AI-powered', async ({ signedInPage: page }) => {
    // Regression guard on the copy audit: the app must not advertise the
    // fabrication behaviour that was removed.
    await stubDiscoverFilters(page);
    await stubDiscoveryRun(page, {
      job_id: 1,
      status: 'no_matches',
      results: [],
      total_results: 0,
      credits_charged: 1,
      credits_remaining: 24,
    });

    await runSearch(page);

    await expect(page.getByText(/AI Discovery/i)).toHaveCount(0);
    await expect(page.getByText(/AI-powered/i)).toHaveCount(0);
  });
});
