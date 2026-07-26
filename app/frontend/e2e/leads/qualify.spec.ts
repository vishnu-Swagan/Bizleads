import { test, expect, stubLeads, makeLead } from '../fixtures';

/**
 * The Qualify action closes the lead-gen loop: discovery returns unranked
 * leads, and this is the only way a user can trigger the measurement that
 * ranks them.
 *
 * The Web Score cell must keep three states apart. Collapsing them would
 * report a lead nobody has measured as one confirmed to have no website —
 * the defect this codebase exists to prevent, surfacing in the UI layer.
 */

const MEASURED = { website_score: 68, has_website: true };
const NO_WEBSITE = { website_score: null, has_website: false };
const UNMEASURED = { website_score: null, has_website: null };

test.describe('web score column', () => {
  test('a measured lead shows its score', async ({ signedInPage: page }) => {
    await stubLeads(page, [makeLead({ business_name: 'Measured Cafe', ...MEASURED })]);
    await page.goto('/app/leads');

    await expect(page.getByRole('cell', { name: '68/100' })).toBeVisible();
  });

  test('a lead confirmed to have no website says so', async ({ signedInPage: page }) => {
    await stubLeads(page, [makeLead({ business_name: 'Siteless Ltd', ...NO_WEBSITE })]);
    await page.goto('/app/leads');

    await expect(page.getByText('No website')).toBeVisible();
    // Not a Qualify prompt: this one HAS been measured, the answer was "none".
    await expect(page.getByRole('button', { name: /qualify/i })).toHaveCount(0);
  });

  test('an unmeasured lead offers Qualify rather than claiming a verdict', async ({
    signedInPage: page,
  }) => {
    await stubLeads(page, [makeLead({ business_name: 'Unknown Cafe', ...UNMEASURED })]);
    await page.goto('/app/leads');

    await expect(page.getByRole('button', { name: 'Qualify', exact: true })).toBeVisible();
    // Crucially it must NOT read "No website" — nobody has looked yet.
    await expect(page.getByText('No website')).toHaveCount(0);
  });

  test('the three states are distinguishable in one table', async ({ signedInPage: page }) => {
    await stubLeads(page, [
      makeLead({ id: 1, business_name: 'Measured', ...MEASURED }),
      makeLead({ id: 2, business_name: 'Siteless', ...NO_WEBSITE }),
      makeLead({ id: 3, business_name: 'Unknown', ...UNMEASURED }),
    ]);
    await page.goto('/app/leads');

    await expect(page.getByRole('cell', { name: '68/100' })).toBeVisible();
    await expect(page.getByText('No website')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Qualify', exact: true })).toBeVisible();
  });
});

test.describe('qualify action', () => {
  test('bulk button counts only unmeasured leads', async ({ signedInPage: page }) => {
    await stubLeads(page, [
      makeLead({ id: 1, business_name: 'A', ...MEASURED }),
      makeLead({ id: 2, business_name: 'B', ...UNMEASURED }),
      makeLead({ id: 3, business_name: 'C', ...UNMEASURED }),
    ]);
    await page.goto('/app/leads');

    await expect(page.getByRole('button', { name: /Qualify 2 unmeasured/ })).toBeVisible();
  });

  test('bulk button is hidden when everything is measured', async ({ signedInPage: page }) => {
    await stubLeads(page, [makeLead({ business_name: 'Done', ...MEASURED })]);
    await page.goto('/app/leads');

    await expect(page.getByRole('button', { name: /unmeasured/ })).toHaveCount(0);
  });

  test('clicking Qualify posts the lead id and refreshes', async ({ signedInPage: page }) => {
    await stubLeads(page, [makeLead({ id: 7, business_name: 'Unknown Cafe', ...UNMEASURED })]);

    let posted: any = null;
    await page.route('**/api/v1/discover/qualify', async (route) => {
      posted = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          qualified: [
            {
              lead_id: 7,
              business_name: 'Unknown Cafe',
              website_score: 42,
              findings: [{ label: 'Not mobile-friendly', evidence: 'No viewport meta' }],
            },
          ],
          not_found: [],
          credits_charged: 1,
          credits_remaining: 24,
        }),
      });
    });

    await page.goto('/app/leads');
    await page.getByRole('button', { name: 'Qualify', exact: true }).click();

    await expect.poll(() => posted?.lead_ids).toEqual([7]);
    // The finding is surfaced, not just the fact that something happened.
    await expect(page.getByText(/Not mobile-friendly/)).toBeVisible();
  });

  test('clicking Qualify does not open the lead detail page', async ({ signedInPage: page }) => {
    // The row is itself a link; without stopPropagation the click navigates
    // away mid-request and the user never sees the result.
    await stubLeads(page, [makeLead({ id: 7, ...UNMEASURED })]);
    await page.route('**/api/v1/discover/qualify', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ qualified: [], not_found: [], credits_charged: 0, credits_remaining: 25 }),
      }),
    );

    await page.goto('/app/leads');
    await page.getByRole('button', { name: 'Qualify', exact: true }).click();

    await expect(page).toHaveURL(/\/app\/leads$/);
  });

  test('running out of credits reports why', async ({ signedInPage: page }) => {
    await stubLeads(page, [makeLead({ id: 7, ...UNMEASURED })]);
    await page.route('**/api/v1/discover/qualify', (route) =>
      route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: {
            error: 'insufficient_credits',
            message: 'Qualifying 1 lead(s) requires 1 credit(s). You have 0 remaining.',
          },
        }),
      }),
    );

    await page.goto('/app/leads');
    await page.getByRole('button', { name: 'Qualify', exact: true }).click();

    await expect(page.getByText(/You have 0 remaining/)).toBeVisible();
  });
});
