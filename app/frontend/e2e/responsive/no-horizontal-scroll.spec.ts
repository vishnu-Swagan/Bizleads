import { test, expect, stubLeads, makeLead } from '../fixtures';

/**
 * The page body must never scroll horizontally.
 *
 * The leads table sat in an `overflow-hidden` container: on a narrow screen
 * the right-hand columns — Web Score and the Qualify button, the two things
 * the product exists to show — were clipped with no way to reach them. The
 * detail panel was pinned to 400px, wider than a 375px iPhone SE viewport.
 *
 * Measuring scrollWidth against clientWidth is the assertion that would have
 * caught both; a screenshot review would not.
 */

const PHONES = [
  { name: 'iPhone SE', width: 375, height: 667 },
  { name: 'Pixel 5', width: 393, height: 851 },
];

const LEADS = [
  makeLead({ id: 1, business_name: 'A Very Long Business Name Ltd', website_score: 68, has_website: true }),
  makeLead({ id: 2, business_name: 'Another Lengthy Trading Company', website_score: null, has_website: null }),
];

for (const phone of PHONES) {
  test.describe(`${phone.name} (${phone.width}px)`, () => {
    test.use({ viewport: { width: phone.width, height: phone.height } });

    test('the leads page does not overflow the viewport', async ({ signedInPage: page }) => {
      await stubLeads(page, LEADS);
      await page.goto('/app/leads');
      await expect(page.getByText('A Very Long Business Name Ltd')).toBeVisible();

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, 'page body scrolls sideways').toBeLessThanOrEqual(1);
    });

    test('the leads table scrolls within itself instead of clipping columns', async ({
      signedInPage: page,
    }) => {
      await stubLeads(page, LEADS);
      await page.goto('/app/leads');

      const wrapper = page.locator('div.overflow-x-auto').filter({ has: page.locator('table') }).first();
      await expect(wrapper).toBeVisible();

      // Whatever the table's width, the container must be able to reach it.
      const reachable = await wrapper.evaluate((el) => {
        const style = getComputedStyle(el);
        return style.overflowX === 'auto' || style.overflowX === 'scroll';
      });
      expect(reachable, 'columns are clipped, not scrollable').toBe(true);
    });

    test('the discover page does not overflow the viewport', async ({ signedInPage: page }) => {
      await page.goto('/app/discover');
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, 'page body scrolls sideways').toBeLessThanOrEqual(1);
    });
  });
}
