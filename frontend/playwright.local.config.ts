/**
 * Playwright config for running specs against a live local dev stack.
 *
 * The default `playwright.config.ts` runs `global-setup.ts`, which logs in
 * as `E2E_USER` and throws if that fails. That is right for CI, where the
 * environment is seeded to match. It is wrong on a developer machine
 * carrying real tenant data, where the seeded e2e account may not exist —
 * and a global setup that throws takes every spec down with it, which
 * reads as "the tests are broken" rather than "this box has different
 * data".
 *
 * So this config skips global setup and expects `e2e/.auth/storage.json`
 * to have been prepared already (see `scripts/seed-e2e-auth.mjs`).
 *
 *   npx playwright test --config playwright.local.config.ts
 *
 * Ports default to the local stack rather than CI's: the Quot PSE backend
 * runs on 8032, and the SPA must be served from 127.0.0.1 because CORS
 * allows that origin and because `localhost` can resolve to a different
 * project's dev server on the same port number.
 */
import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const FRONTEND_URL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173';
const STORAGE_PATH = path.resolve(__dirname, 'e2e/.auth/storage.json');

export default defineConfig({
    testDir: './e2e',
    fullyParallel: false,
    forbidOnly: false,
    retries: 0,
    workers: 1,
    reporter: [['list']],
    use: {
        baseURL: FRONTEND_URL,
        storageState: STORAGE_PATH,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        actionTimeout: 15_000,
        navigationTimeout: 30_000,
    },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
