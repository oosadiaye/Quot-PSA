import { test, expect, type Page } from '@playwright/test';
import { bootMock, duplicateCheck, dupMatch, type Handler } from './mockApi';

/**
 * Duplicate lookup on the remaining master-data screens (API mocked).
 * Each case: hint appears while typing → Save is held with a prompt → "Use this one"
 * switches to the existing record without creating anything.
 */

const get = (path: string, body: unknown): Handler => (c) =>
  c.method === 'GET' && c.path === path ? { body } : undefined;

// ── Chart of Accounts ────────────────────────────────────────────────────────
test.describe('Chart of Accounts — add account', () => {
  const existing = dupMatch({ id: 7, code: '22101001', name: 'Motor Vehicle Fuel', level: 'likely', extra: { account_type: 'Expense' } });
  const ACCOUNT_7 = { id: 7, code: '22101001', name: 'Motor Vehicle Fuel', account_type: 'Expense', is_active: true, is_reconciliation: false, reconciliation_type: '', is_postable: true };

  async function openAdd(page: Page) {
    await page.goto('/accounting/coa');
    await page.getByRole('button', { name: 'Add Account' }).click();
    await page.getByPlaceholder('e.g. Petty Cash').fill('Motor Vehicles Fuel');
    await page.locator('form input[required]').first().fill('22109998');
  }

  test('hints, prompts on save, and "Use this one" opens the existing account', async ({ page }) => {
    const api = await bootMock(page, [get('/accounting/accounts/7/', ACCOUNT_7), duplicateCheck('account', [existing], 'GL account')]);
    await openAdd(page);
    const hint = page.getByRole('status').filter({ hasText: 'GL account already exists' });
    await expect(hint).toContainText('22101001');

    await page.getByRole('button', { name: 'Register Account' }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('Motor Vehicle Fuel');
    expect(api.find('POST', '/accounting/accounts/')).toHaveLength(0);

    await dialog.getByRole('button', { name: 'Use this one' }).click();
    await expect(page.getByText('Edit Account Details')).toBeVisible();
    await expect(page.getByPlaceholder('e.g. Petty Cash')).toHaveValue('Motor Vehicle Fuel');
    expect(api.find('POST', '/accounting/accounts/')).toHaveLength(0);
  });

  test('"Create anyway" registers the account', async ({ page }) => {
    const api = await bootMock(page, [duplicateCheck('account', [existing], 'GL account')]);
    await openAdd(page);
    await page.getByRole('button', { name: 'Register Account' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Create anyway' }).click();
    await expect.poll(() => api.find('POST', '/accounting/accounts/').length).toBe(1);
    expect(api.find('POST', '/accounting/accounts/')[0].body).toMatchObject({ code: '22109998', name: 'Motor Vehicles Fuel' });
  });
});

// ── Inventory product ───────────────────────────────────────────────────────
test.describe('Inventory product form', () => {
  const existing = dupMatch({ id: 7, code: 'ITEM-001', name: 'A4 Paper Ream', level: 'likely' });

  async function fill(page: Page) {
    await page.goto('/inventory/new');
    await page.getByPlaceholder('e.g., ITEM-001').fill('ITEM-009');
    await page.getByPlaceholder('Product name').fill('A4 paper reams');
    // Product Category is a required select — pick the first real option.
    await page.locator('form select').first().selectOption({ index: 1 });
  }

  test('prompts on save, and "Use this one" opens the existing product', async ({ page }) => {
    const api = await bootMock(page, [
      get('/inventory/product-categories/', { count: 1, next: null, previous: null, results: [{ id: 1, name: 'Stationery', code: 'STA' }] }),
      duplicateCheck('item', [existing], 'Inventory item'),
    ]);
    await fill(page);
    await expect(page.getByRole('status').filter({ hasText: 'product already exists' })).toContainText('A4 Paper Ream');
    await page.getByRole('button', { name: /^Create$/ }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    expect(api.find('POST', '/inventory/items/')).toHaveLength(0);
    await dialog.getByRole('button', { name: 'Use this one' }).click();
    await expect(page).toHaveURL(/\/inventory\/7$/);
  });
});

// ── TSA / bank account ─────────────────────────────────────────────────────
test.describe('Bank (TSA) account form', () => {
  const existing = dupMatch({ id: 7, code: '0123456789', name: 'Delta State TSA Main', level: 'exact', reasons: ['Same code'] });

  test('an existing account number is flagged, and "Use this one" opens it', async ({ page }) => {
    const api = await bootMock(page, [duplicateCheck('tsa_account', [existing], 'Bank / TSA account')]);
    await page.goto('/accounting/tsa-accounts/new');
    await page.getByPlaceholder('10-digit NUBAN').fill('0123456789');
    await page.getByPlaceholder('bank account name').fill('Delta TSA');
    await page.getByPlaceholder('Bank name (e.g. CBN)').fill('CBN');
    await expect(page.getByRole('status').filter({ hasText: 'bank account already exists' })).toContainText('0123456789');
    await page.getByRole('button', { name: 'Create Bank Account' }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('already exists');
    // Same account number → the server would reject a duplicate, so no "Create anyway".
    await expect(dialog.getByRole('button', { name: 'Create anyway' })).toHaveCount(0);
    expect(api.find('POST', '/accounting/tsa-accounts/')).toHaveLength(0);
    await dialog.getByRole('button', { name: 'Use this one' }).click();
    await expect(page).toHaveURL(/\/accounting\/tsa-accounts\/7\/edit$/);
  });
});

// ── Vendor category / asset category (inline forms) ───────────────────────
test.describe('Vendor category', () => {
  const cat = { id: 7, name: 'Local Suppliers', code: 'VC-001', description: '', reconciliation_account: 1, is_active: true };
  const existing = dupMatch({ id: 7, code: 'VC-001', name: 'Local Suppliers', level: 'likely' });
  const handlers: Handler[] = [
    get('/procurement/vendor-categories/', [cat]),
    get('/accounting/accounts/', { count: 1, next: null, previous: null, results: [{ id: 1, code: '40101001', name: 'Trade Payables' }] }),
    duplicateCheck('vendor_category', [existing], 'Vendor category'),
  ];

  test('"Use this one" switches the dialog to editing the existing category', async ({ page }) => {
    const api = await bootMock(page, handlers);
    await page.goto('/procurement/vendor-categories');
    await page.getByRole('button', { name: /New Category/ }).click();
    await page.getByPlaceholder('e.g. VC-001').fill('VC-009');
    await page.getByPlaceholder('Category name').fill('Local Supplier');
    await page.locator('form select').first().selectOption('1');
    await expect(page.getByRole('status').filter({ hasText: 'vendor category already exists' })).toBeVisible();
    await page.getByRole('button', { name: 'Create Category' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Use this one' }).click();
    await expect(page.getByText('Edit Vendor Category')).toBeVisible();
    await expect(page.getByPlaceholder('Category name')).toHaveValue('Local Suppliers');
    expect(api.find('POST', '/procurement/vendor-categories/')).toHaveLength(0);
  });
});

test.describe('Asset category', () => {
  const cat = { id: 7, name: 'Motor Vehicles', code: 'VEH', is_active: true, depreciation_method: 'Straight-Line', useful_life_years: 5, residual_value: '0', residual_value_type: 'percentage' };
  const existing = dupMatch({ id: 7, code: 'VEH', name: 'Motor Vehicles', level: 'likely' });

  test('"Use this one" switches the form to editing the existing category', async ({ page }) => {
    const api = await bootMock(page, [
      get('/accounting/asset-categories/', [cat]),
      duplicateCheck('asset_category', [existing], 'Asset category'),
    ]);
    await page.goto('/accounting/asset-categories');
    await page.getByRole('button', { name: 'Add Category' }).click();
    await page.getByPlaceholder('e.g. VEH').fill('VEH2');
    await page.getByPlaceholder('e.g. Motor Vehicles').fill('Motor Vehicle');
    await expect(page.getByRole('status').filter({ hasText: 'asset category already exists' })).toBeVisible();

    // Submit past any browser-side required-field validation so the guard runs.
    await page.locator('form').evaluate((f: HTMLFormElement) => { f.noValidate = true; });
    await page.getByRole('button', { name: 'Create Category' }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('Motor Vehicles');
    expect(api.find('POST', '/accounting/asset-categories/')).toHaveLength(0);

    await dialog.getByRole('button', { name: 'Use this one' }).click();
    await expect(page.getByText('Edit Asset Category')).toBeVisible();
    await expect(page.getByPlaceholder('e.g. Motor Vehicles')).toHaveValue('Motor Vehicles');
  });
});
