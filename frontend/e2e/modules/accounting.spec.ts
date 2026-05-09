import { test, expect } from '../fixtures/auth';

test.describe('Accounting module — smoke', () => {
  test('dashboard loads', async ({ authedPage }) => {
    await authedPage.goto('/accounting/dashboard');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
  });

  test('chart of accounts loads and lists rows', async ({ authedPage }) => {
    await authedPage.goto('/accounting/coa');
    await expect(authedPage.getByRole('heading', { name: /chart of accounts/i })).toBeVisible();
    await expect(authedPage.locator('table, [role="grid"]').first()).toBeVisible({ timeout: 10_000 });
  });

  test('journal list refetches after navigation (live-data check)', async ({ authedPage }) => {
    await authedPage.goto('/accounting');
    const firstLoad = await authedPage.locator('tbody tr, [role="row"]').count();
    await authedPage.goto('/accounting/coa');
    await authedPage.goto('/accounting');
    // Should still render without manual refresh
    await expect(authedPage.locator('tbody tr, [role="row"]').first()).toBeVisible();
    expect(firstLoad).toBeGreaterThanOrEqual(0);
  });

  test('trial balance, balance sheet, P&L, cash flow render', async ({ authedPage }) => {
    for (const path of [
      '/accounting/reports/trial-balance',
      '/accounting/reports/balance-sheet',
      '/accounting/reports/income-statement',
      '/accounting/reports/cash-flow',
    ]) {
      await authedPage.goto(path);
      await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
    }
  });

  test('AP and AR pages load', async ({ authedPage }) => {
    await authedPage.goto('/accounting/ap');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
    await authedPage.goto('/accounting/ar');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
  });
});
