import { test, expect, stubLeads, makeLead } from '../fixtures';

/**
 * The provenance badge is the only thing telling a user whether a lead's
 * phone number is safe to act on. Two properties matter and are asserted
 * separately:
 *
 *   1. Every data_source value renders its own distinct LABEL. Colour is
 *      never the only signal — an assertion on a class name would pass while
 *      the accessibility requirement failed, so these assert on text.
 *   2. An unrecognised or absent value falls back to "Unverified" rather
 *      than rendering nothing, because a blank cell reads as "fine".
 *
 * Labels match the map in pages/app/Leads.tsx.
 */

const CASES: Array<{ dataSource: string | null; label: string }> = [
  { dataSource: 'provider', label: 'Verified source' },
  { dataSource: 'manual', label: 'Added manually' },
  { dataSource: 'ai_generated', label: 'AI-generated — unverified' },
  { dataSource: 'mock', label: 'Sample data' },
  { dataSource: null, label: 'Unverified' },
];

test.describe('lead provenance badge', () => {
  for (const { dataSource, label } of CASES) {
    test(`data_source=${dataSource ?? 'null'} renders "${label}"`, async ({ signedInPage: page }) => {
      await stubLeads(page, [makeLead({ business_name: 'Acme Cafe', data_source: dataSource })]);

      await page.goto('/app/leads');

      await expect(page.getByRole('cell', { name: label })).toBeVisible();
    });
  }

  test('an unrecognised data_source falls back to Unverified, not blank', async ({ signedInPage: page }) => {
    await stubLeads(page, [makeLead({ business_name: 'Odd Origin', data_source: 'scraped_somehow' })]);

    await page.goto('/app/leads');

    await expect(page.getByRole('cell', { name: 'Unverified' })).toBeVisible();
  });

  test('the badge carries an explanatory title, not colour alone', async ({ signedInPage: page }) => {
    await stubLeads(page, [makeLead({ data_source: 'ai_generated' })]);

    await page.goto('/app/leads');

    const badge = page.getByText('AI-generated — unverified');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute('title', /may not exist|verify before contacting/i);
  });

  test('rows of differing provenance are distinguishable in one table', async ({ signedInPage: page }) => {
    await stubLeads(page, [
      makeLead({ id: 1, business_name: 'Real Cafe', data_source: 'provider' }),
      makeLead({ id: 2, business_name: 'Invented Cafe', data_source: 'ai_generated' }),
    ]);

    await page.goto('/app/leads');

    await expect(page.getByRole('cell', { name: 'Verified source' })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'AI-generated — unverified' })).toBeVisible();
  });
});
