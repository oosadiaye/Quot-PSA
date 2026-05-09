import { test as base, expect, Page } from '@playwright/test';

export const E2E_USER = process.env.E2E_USER ?? 'admin@example.com';
export const E2E_PASSWORD = process.env.E2E_PASSWORD ?? 'Admin@1234';
export const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8000';

/**
 * Browser auth comes from `storageState` written by `global-setup.ts`.
 * `authedPage` simply asserts we landed on a non-login page.
 */
export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    await page.goto('/');
    // If storageState restored properly, we are NOT on /login.
    await expect(page).not.toHaveURL(/\/login/, { timeout: 10_000 });
    await use(page);
  },
});

export { expect };
