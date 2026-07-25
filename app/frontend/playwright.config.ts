import { defineConfig, devices } from '@playwright/test';

/**
 * Set PLAYWRIGHT_BASE_URL to point at an already-running app; otherwise
 * Playwright starts the Vite dev server itself.
 *
 * Do NOT point this at the deployed instance. Several of these specs stub
 * API responses, and the deployment currently exposes unauthenticated write
 * endpoints — a run against it could mutate real data.
 */
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],

  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        // Invoke vite directly. `pnpm run dev` fails in this repo: pnpm's
        // wrapper re-runs a dependency check that trips its supply-chain
        // freshness policy on ~57 lockfile entries.
        command: './node_modules/.bin/vite --port 5173 --strictPort',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
