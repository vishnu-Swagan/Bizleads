import { test, expect } from '../fixtures';

/**
 * Every public page must fit every screen we claim to support.
 *
 * The widths below are real device classes, not round numbers: 320 is the
 * narrowest phone still in use (iPhone SE 1st gen / Galaxy Fold cover), 768
 * and 820 are the iPad breakpoints where a layout most often breaks by
 * sitting exactly on the boundary, and 2560 catches containers that stretch
 * text to an unreadable measure instead of capping it.
 *
 * The assertion is measured, not eyeballed: documentElement.scrollWidth must
 * not exceed clientWidth. A screenshot review cannot catch a 3px overflow,
 * and 3px of overflow is still a page that jiggles sideways on a phone.
 */

const VIEWPORTS = [
  { name: 'Galaxy Fold / SE1', width: 320, height: 653 },
  { name: 'iPhone SE', width: 375, height: 667 },
  { name: 'iPhone 14 Pro', width: 393, height: 852 },
  { name: 'iPhone 14 Plus', width: 430, height: 932 },
  { name: 'iPad mini portrait', width: 768, height: 1024 },
  { name: 'iPad Air portrait', width: 820, height: 1180 },
  { name: 'iPad landscape', width: 1024, height: 768 },
  { name: 'Laptop', width: 1440, height: 900 },
  { name: 'Wide desktop', width: 2560, height: 1440 },
];

const PUBLIC_PAGES = [
  { path: '/', name: 'landing' },
  { path: '/pricing', name: 'pricing' },
  { path: '/terms', name: 'terms' },
  { path: '/privacy', name: 'privacy' },
  { path: '/cookies', name: 'cookies' },
  { path: '/subprocessors', name: 'sub-processors' },
  { path: '/login', name: 'sign in' },
];

for (const vp of VIEWPORTS) {
  test.describe(`${vp.name} — ${vp.width}px`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    for (const page_ of PUBLIC_PAGES) {
      test(`${page_.name} fits the viewport`, async ({ page }) => {
        await page.goto(page_.path);
        await expect(page.getByRole('heading').first()).toBeVisible();

        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        // 1px tolerance absorbs sub-pixel rounding at fractional zoom levels.
        expect(overflow, `${page_.name} scrolls sideways at ${vp.width}px`).toBeLessThanOrEqual(1);
      });
    }
  });
}

test.describe('legal pages are readable and reachable', () => {
  test('the footer links to every policy from the landing page', async ({ page }) => {
    await page.goto('/');
    const footer = page.getByRole('contentinfo');

    for (const name of ['Terms of Service', 'Privacy Policy', 'Cookies', 'Sub-processors']) {
      await expect(footer.getByRole('link', { name })).toBeVisible();
    }
  });

  test('body text is at least 16px so mobile browsers do not zoom on focus', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/terms');

    const size = await page
      .locator('main p')
      .first()
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(size).toBeGreaterThanOrEqual(16);
  });

  test('the signup form presents the terms before the account is created', async ({ page }) => {
    await page.goto('/login?mode=signup');

    const consent = page.getByText(/By creating an account you agree/i);
    await expect(consent).toBeVisible();
    await expect(consent.getByRole('link', { name: 'Terms of Service' })).toBeVisible();
    await expect(consent.getByRole('link', { name: 'Privacy Policy' })).toBeVisible();
  });

  test('the copyright year is current, not hardcoded', async ({ page }) => {
    await page.goto('/');
    const year = new Date().getFullYear();
    await expect(page.getByRole('contentinfo')).toContainText(`© ${year}`);
  });
});

test.describe('the legal pages are complete and publishable', () => {
  const LEGAL_PAGES = ['/terms', '/privacy', '/cookies', '/subprocessors'];

  for (const path of LEGAL_PAGES) {
    test(`${path} contains no placeholder or empty clause`, async ({ page }) => {
      await page.goto(path);
      const body = await page.locator('main').innerText();

      // A published policy showing "[TODO: ...]" invites exactly the scrutiny
      // it is meant to withstand, and reads as unfinished to any customer.
      expect(body, 'placeholder text is live').not.toContain('TODO');
      // Conditional clauses must omit themselves, never render a hole.
      expect(body, 'empty bracket from an unset value').not.toMatch(/\[\s*\]|\(\s*\)/);
      expect(body, 'dangling label from an unset value').not.toMatch(
        /registration number\s*[,.)]/i,
      );
    });
  }

  test('the terms carry the clauses that limit exposure', async ({ page }) => {
    await page.goto('/terms');
    const body = await page.locator('main').innerText();

    // Each of these is load-bearing: losing one silently changes what the
    // company is exposed to, and nothing else in the suite would notice.
    for (const clause of [
      'binding individual arbitration',
      'CLASS, COLLECTIVE',
      'opt out of arbitration',
      'ONE HUNDRED US DOLLARS',
      'indemnify, defend',
      'RENEWS AUTOMATICALLY',
      'legal, tax, marketing or professional advice',
      'Severability',
    ]) {
      expect(body, `missing protective clause: ${clause}`).toContain(clause);
    }
  });

  test('signup discloses arbitration, not just the terms link', async ({ page }) => {
    await page.goto('/login?mode=signup');
    await expect(page.getByText(/individual arbitration/i)).toBeVisible();
    await expect(page.getByText(/opt out of/i)).toBeVisible();
  });

  test('the contracting entity is named, not the trading name alone', async ({ page }) => {
    await page.goto('/terms');
    await expect(page.locator('main')).toContainText('Torque Trends LLC');
    await expect(page.locator('main')).toContainText('Lexington, KY 40507');
  });
});
