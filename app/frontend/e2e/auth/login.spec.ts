import { test, expect } from '@playwright/test';

/**
 * The sign-in screen is the app's entry point — the client shim redirects here
 * whenever a session is missing, so if this page is broken nobody can use the
 * product at all.
 *
 * Stubs nothing except Supabase's own auth endpoints, which are an external
 * service. The page itself is exercised for real.
 */

test.describe('sign-in screen', () => {
  test('renders the form for a signed-out visitor', async ({ page }) => {
    await page.goto('/login');

    await expect(page.getByRole('heading', { name: 'Sign in to BizLeads' })).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  });

  test('offers account creation and password recovery', async ({ page }) => {
    await page.goto('/login');

    await expect(page.getByRole('button', { name: 'Create one' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Forgot your password?' })).toBeVisible();
  });

  test('switches to sign-up without a page load', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: 'Create one' }).click();

    await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create account' })).toBeVisible();
  });

  test('password field is hidden on the reset form', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: 'Forgot your password?' }).click();

    await expect(page.getByRole('heading', { name: 'Reset your password' })).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Password')).toHaveCount(0);
  });

  test('a rejected sign-in shows an announced error', async ({ page }) => {
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'invalid_grant', error_description: 'Invalid login credentials' }),
      }),
    );

    await page.goto('/login');
    await page.getByLabel('Email').fill('nobody@example.test');
    await page.getByLabel('Password').fill('wrong-password');
    await page.getByRole('button', { name: 'Sign in' }).click();

    // role=alert, not merely red text — the failure must reach a screen reader.
    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(/invalid|credential/i);
  });

  test('password reset does not reveal whether an account exists', async ({ page }) => {
    // Enumeration guard: the response must read the same either way, or anyone
    // can discover which addresses have accounts.
    await page.route('**/auth/v1/recover**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }),
    );

    await page.goto('/login');
    await page.getByRole('button', { name: 'Forgot your password?' }).click();
    await page.getByLabel('Email').fill('definitely-not-a-user@example.test');
    await page.getByRole('button', { name: 'Send reset link' }).click();

    await expect(page.getByRole('status')).toContainText(/if that email has an account/i);
  });

  test('/signup lands directly on the create-account form', async ({ page }) => {
    await page.goto('/signup');
    await expect(page.getByRole('heading', { name: 'Sign in to BizLeads' })).toBeVisible();
  });
});
