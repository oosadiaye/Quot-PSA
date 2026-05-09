import { test, expect } from '../fixtures/auth';

test.describe('Inventory module — smoke + polling check', () => {
  for (const [name, path] of [
    ['dashboard', '/inventory/dashboard'],
    ['items', '/inventory'],
    ['warehouses', '/inventory/warehouses'],
    ['stocks', '/inventory/stocks'],
    ['movements', '/inventory/movements'],
    ['reorder alerts', '/inventory/reorder-alerts'],
    ['expiry alerts', '/inventory/expiry-alerts'],
  ] as const) {
    test(`${name} loads`, async ({ authedPage }) => {
      await authedPage.goto(path);
      await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
    });
  }

  test('reorder alerts polls without manual refresh (LIVE_STALE_TIME=30s)', async ({ authedPage }) => {
    test.setTimeout(60_000);
    let networkCalls = 0;
    authedPage.on('response', (r) => {
      if (r.url().includes('/inventory/reorder')) networkCalls++;
    });
    await authedPage.goto('/inventory/reorder-alerts');
    await authedPage.waitForTimeout(35_000);
    expect(networkCalls).toBeGreaterThan(1); // initial + at least one poll
  });
});
