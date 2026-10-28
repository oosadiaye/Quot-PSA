/**
 * Playwright config for the *mocked-API* specs in `e2e/mocked/`.
 *
 * These specs drive the real SPA in a real browser but answer every
 * `/api/v1/**` call from the test itself (see `e2e/mocked/mockApi.ts`), so they
 * need no backend, tenant, seed data or login — and are fully deterministic.
 * They cover UI behaviour (hints, prompts, adopt-existing flows); the
 * backend half is covered by pytest, and the seeded-stack specs in the other
 * `e2e/` folders cover the integrated path.
 *
 *   npx playwright test --config playwright.mock.config.ts
 *
 * Set E2E_CHROMIUM_PATH to use a system Chromium instead of Playwright's own
 * download (e.g. /opt/pw-browsers/chromium-1243/chrome-linux64/chrome).
 */
import { defineConfig, devices } from '@playwright/test';

const PORT = Number(process.env.E2E_MOCK_PORT ?? 5174);
const BASE = `http://127.0.0.1:${PORT}`;
const API = process.env.E2E_MOCK_API ?? 'http://127.0.0.1:8099';

export default defineConfig({
  testDir: './e2e/mocked',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: BASE,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    launchOptions: process.env.E2E_CHROMIUM_PATH
      ? { executablePath: process.env.E2E_CHROMIUM_PATH, args: ['--no-sandbox'] }
      : { args: ['--no-sandbox'] },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npx vite --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: BASE,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { VITE_API_URL: API },
  },
});
