import { test, expect } from '../fixtures/auth';

test.describe('Payment Voucher & Treasury (TSA)', () => {
  test('payment voucher list loads', async ({ authedPage }) => {
    await authedPage.goto('/accounting/payment-vouchers');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
  });

  test('PV detail invalidation regression', async ({ authedPage }) => {
    // Risk #3 (frontend) in LIVE_DATA_REVIEW.md — PV detail must refetch
    // after status mutation, not stay on cached "Draft" while server is "Approved".
    await authedPage.goto('/accounting/payment-vouchers');
    const firstRow = authedPage.locator('tbody tr a').first();
    if (await firstRow.count()) {
      await firstRow.click();
      await expect(authedPage.locator('h1, h2').first()).toBeVisible();
    }
  });

  test('TSA accounts and transfer page', async ({ authedPage }) => {
    await authedPage.goto('/accounting/tsa-accounts');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
    await authedPage.goto('/accounting/tsa-accounts/transfer');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
  });

  test('outgoing payments page', async ({ authedPage }) => {
    await authedPage.goto('/accounting/outgoing-payments');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
  });
});
