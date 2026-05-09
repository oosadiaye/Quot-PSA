import { test, expect } from '../fixtures/auth';
import { fetchAppropriation } from '../fixtures/api';

test.describe('Budget — appropriations, warrants, virements', () => {
  test('appropriations list', async ({ authedPage }) => {
    await authedPage.goto('/budget/appropriations');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
    await expect(authedPage.locator('table, [role="grid"]').first()).toBeVisible({ timeout: 10_000 });
  });

  test('warrants list and warrant detail', async ({ authedPage }) => {
    await authedPage.goto('/budget/warrants');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
  });

  test('execution and warrant utilization reports', async ({ authedPage }) => {
    await authedPage.goto('/budget/execution-report');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
    await authedPage.goto('/budget/warrant-utilization');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
  });

  test('LIVE-DATA INVARIANT: cached_total_committed equals live aggregate', async () => {
    const apprId = Number(process.env.E2E_APPROPRIATION_ID ?? 55);
    const a = await fetchAppropriation(apprId);
    // DRF DecimalField serialises to string — coerce before numeric compare.
    const cached = Number(a.cached_total_committed ?? 0);
    const live = Number(a.total_committed_live ?? 0);
    // Risk #1 in LIVE_DATA_REVIEW.md — this assertion catches drift.
    expect(cached).toBeCloseTo(live, 2);
  });
});
