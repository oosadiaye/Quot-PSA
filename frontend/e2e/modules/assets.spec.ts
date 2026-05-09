import { test, expect } from '../fixtures/auth';

test.describe('Fixed Assets & Depreciation', () => {
  test('asset categories and fixed assets list', async ({ authedPage }) => {
    await authedPage.goto('/accounting/asset-categories');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
    await authedPage.goto('/accounting/fixed-assets');
    await expect(authedPage.locator('h1, h2').first()).toBeVisible();
  });

  test('new asset form renders', async ({ authedPage }) => {
    await authedPage.goto('/accounting/fixed-assets/new');
    await expect(authedPage.locator('form')).toBeVisible();
  });
});
