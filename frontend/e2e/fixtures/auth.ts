import { test as base, expect, Page } from '@playwright/test';

export const E2E_USER = process.env.E2E_USER ?? 'admin@example.com';
export const E2E_PASSWORD = process.env.E2E_PASSWORD ?? 'Admin@1234';
export const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8000';

/**
 * Browser auth comes from `storageState` written by `global-setup.ts`.
 * `authedPage` simply asserts we landed on a non-login page.
 */
/** Auth keys global-setup seeds. Mirrored into sessionStorage below. */
const AUTH_KEYS = [
  'authToken', 'user', 'tenantDomain', 'tenantInfo',
  'tenantPermissions', 'activeTenant',
];

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    // Playwright's storageState carries localStorage only — sessionStorage
    // is per-context and always starts empty. global-setup seeds both, but
    // only the localStorage half survives into storage.json, and the SPA
    // reads its token from sessionStorage (localStorage is XSS-readable for
    // the life of the browser profile). Without this mirror every spec
    // lands on "Your session expired".
    //
    // addInitScript runs before any page script on every navigation, so the
    // token is in place by the time the app boots.
    await page.addInitScript((keys: string[]) => {
      for (const k of keys) {
        const v = localStorage.getItem(k);
        if (v !== null && sessionStorage.getItem(k) === null) {
          sessionStorage.setItem(k, v);
        }
      }
    }, AUTH_KEYS);

    // '/' is the login entry point and redirects there even for an
    // authenticated session, so it cannot tell us whether auth worked.
    // Land on the authenticated home instead: staying put means the
    // restored session was accepted, being bounced means it was not.
    await page.goto('/dashboard');
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15_000 });
    await use(page);
  },
});

export { expect };
