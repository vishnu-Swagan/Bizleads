import { test, expect } from '@playwright/test';

/**
 * Audit criterion 1, at the UI layer: an anonymous visitor must not reach
 * application content.
 *
 * These specs stub NOTHING. With no session, the SDK's auth call fails and
 * AppShell renders its gate — which is the real production code path, not a
 * simulated one. This file is the honest counterweight to the stubbed specs.
 */

const APP_ROUTES = [
  '/app/dashboard',
  '/app/discover',
  '/app/leads',
  '/app/pipeline',
  '/app/analytics',
  '/app/automations',
];

/** Sidebar labels from AppShell — none may render for an anonymous visitor. */
const NAV_LABELS = ['Dashboard', 'Discover', 'Leads', 'Pipeline', 'Analytics', 'Automations'];

test.describe('anonymous access to /app/*', () => {
  for (const route of APP_ROUTES) {
    test(`${route} shows the sign-in gate, not app content`, async ({ page }) => {
      await page.goto(route);

      await expect(page.getByText('Sign in to access your workspace')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();

      // The gate replaces the shell entirely — no navigation should be reachable.
      for (const label of NAV_LABELS) {
        await expect(page.getByRole('link', { name: label })).toHaveCount(0);
      }
    });
  }

  test('the leads page leaks no lead data before sign-in', async ({ page }) => {
    // Guards the defect class the audit found: contact details reachable
    // without authentication. Asserted on rendered content, not just status.
    await page.goto('/app/leads');

    await expect(page.getByText('Sign in to access your workspace')).toBeVisible();
    await expect(page.getByRole('table')).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: 'Source' })).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText('@');
  });
});
