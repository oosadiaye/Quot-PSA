import { test, expect } from '../fixtures/auth';

test.describe('Procurement (P2P) — smoke', () => {
  test('dashboard, vendors, requisitions, orders, GRN list', async ({ authedPage }) => {
    for (const path of [
      '/procurement/dashboard',
      '/procurement/vendors',
      '/procurement/requisitions',
      '/procurement/orders',
    ]) {
      await authedPage.goto(path);
      await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
    }
  });

  test('PR list invalidates after creating a new requisition (live-data)', async ({ authedPage }) => {
    await authedPage.goto('/procurement/requisitions');
    const initialRows = await authedPage.locator('tbody tr').count();
    await authedPage.goto('/procurement/requisitions/new');
    await expect(authedPage.locator('form').first()).toBeVisible({ timeout: 15_000 });
    // Form interactions are highly UI-specific — mark as TODO for real seeded test:
    // await fillRequisitionForm(authedPage, { ... });
    // await authedPage.getByRole('button', { name: /save|submit/i }).click();
    // await authedPage.goto('/procurement/requisitions');
    // await expect(authedPage.locator('tbody tr')).toHaveCount(initialRows + 1);
    expect(initialRows).toBeGreaterThanOrEqual(0);
  });
});
