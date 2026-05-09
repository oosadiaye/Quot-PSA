import { test, expect } from '../fixtures/auth';

test.describe('RBAC / Governance pages', () => {
  for (const [name, path] of [
    ['user management', '/user-management'],
    ['fiscal year', '/settings/fiscal-year'],
    ['bank accounts', '/settings/bank-accounts'],
    ['accounting settings', '/settings/accounting'],
    ['budget check rules', '/settings/accounting/budget-check-rules'],
  ] as const) {
    test(`${name} loads`, async ({ authedPage }) => {
      await authedPage.goto(path);
      await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
    });
  }
});
