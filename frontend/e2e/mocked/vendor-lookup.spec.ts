import { test, expect } from '@playwright/test';
import { bootMock, duplicateCheck, dupMatch, type Handler } from './mockApi';

const CATEGORIES: Handler = (c) =>
  c.method === 'GET' && c.path === '/procurement/vendor-categories/'
    ? { body: [{ id: 1, name: 'Local', code: 'LOC', reconciliation_account: 1, is_active: true }] }
    : undefined;

const EXISTING_VENDOR = {
  id: 7, name: 'Acme Nigeria Limited', code: 'V001', category: 1, tax_id: 'TIN-1', email: '', phone: '',
  address: '', is_active: true, registration_number: '', registration_fiscal_year: null, expiry_date: null,
  bank_name: '', bank_account_number: '', bank_sort_code: '',
};
const GET_VENDOR_7: Handler = (c) =>
  c.method === 'GET' && c.path === '/procurement/vendors/7/' ? { body: EXISTING_VENDOR } : undefined;

const likely = dupMatch({ id: 7, code: 'V001', name: 'Acme Nigeria Limited', level: 'likely', reasons: ['Same name'] });

async function openNewVendor(page: import('@playwright/test').Page) {
  await page.goto('/procurement/vendors');
  await page.getByRole('button', { name: /Add New Vendor/ }).click();
  await expect(page.getByPlaceholder('Enter vendor name')).toBeVisible();
}
async function fillVendor(page: import('@playwright/test').Page, name: string, code: string) {
  await page.getByPlaceholder('Enter vendor name').fill(name);
  await page.getByPlaceholder('e.g. VND-001').fill(code);
  await page.locator('form select').first().selectOption('1');
}

test.describe('Vendor create form', () => {
  test('hints while typing, prompts on save, and "Use this one" opens the existing vendor', async ({ page }) => {
    const api = await bootMock(page, [CATEGORIES, GET_VENDOR_7, duplicateCheck('vendor', [likely], 'Vendor')]);
    await openNewVendor(page);
    await fillVendor(page, 'ACME Nig. Ltd', 'V999');

    const hint = page.getByRole('status').filter({ hasText: 'vendor already exists' });
    await expect(hint).toBeVisible();
    await expect(hint).toContainText('Acme Nigeria Limited');

    await page.getByRole('button', { name: 'Save Vendor' }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    expect(api.find('POST', '/procurement/vendors/')).toHaveLength(0);

    await dialog.getByRole('button', { name: 'Use this one' }).click();
    // The "new vendor" form switches to editing the existing record.
    await expect(page.getByRole('heading', { name: 'Edit Vendor' })).toBeVisible();
    await expect(page.getByPlaceholder('Enter vendor name')).toHaveValue('Acme Nigeria Limited');
    expect(api.find('GET', '/procurement/vendors/7/')).toHaveLength(1);
    expect(api.find('POST', '/procurement/vendors/')).toHaveLength(0);
  });

  test('"Create anyway" creates the vendor', async ({ page }) => {
    const api = await bootMock(page, [CATEGORIES, duplicateCheck('vendor', [likely], 'Vendor')]);
    await openNewVendor(page);
    await fillVendor(page, 'ACME Nig. Ltd', 'V999');
    await page.getByRole('button', { name: 'Save Vendor' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Create anyway' }).click();
    await expect.poll(() => api.find('POST', '/procurement/vendors/').length).toBe(1);
    expect(api.find('POST', '/procurement/vendors/')[0].body).toMatchObject({ name: 'ACME Nig. Ltd', code: 'V999', category: 1 });
  });

  test('"Go back" keeps the form and saves nothing', async ({ page }) => {
    const api = await bootMock(page, [CATEGORIES, duplicateCheck('vendor', [likely], 'Vendor')]);
    await openNewVendor(page);
    await fillVendor(page, 'ACME Nig. Ltd', 'V999');
    await page.getByRole('button', { name: 'Save Vendor' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Go back' }).click();
    await expect(page.getByRole('alertdialog')).toHaveCount(0);
    await expect(page.getByPlaceholder('Enter vendor name')).toHaveValue('ACME Nig. Ltd');
    expect(api.find('POST', '/procurement/vendors/')).toHaveLength(0);
  });

  test('a unique vendor is created without any prompt', async ({ page }) => {
    const api = await bootMock(page, [CATEGORIES, duplicateCheck('vendor', [], 'Vendor')]);
    await openNewVendor(page);
    await fillVendor(page, 'Totally New Supplies', 'V123');
    await page.getByRole('button', { name: 'Save Vendor' }).click();
    await expect.poll(() => api.find('POST', '/procurement/vendors/').length).toBe(1);
    await expect(page.getByRole('alertdialog')).toHaveCount(0);
  });
});

test('CSV import skips vendors that already exist and reports them', async ({ page }) => {
  const api = await bootMock(page, [
    CATEGORIES,
    // "Acme Nig Ltd" is already on file; anything else is new.
    (c) => c.method === 'POST' && c.path === '/core/duplicate-check/' && c.body?.entity === 'vendor'
      ? { body: { entity: 'vendor', label: 'Vendor', matches: /acme/i.test(c.body.values?.name ?? '') ? [likely] : [] } }
      : undefined,
  ]);
  await page.goto('/procurement/vendors');
  const csv = [
    'name,code,category,tax_id,email,phone',
    'Acme Nig Ltd,V500,1,,,',
    'Zed Supplies,V501,1,,,',
  ].join('\n');
  await page.locator('input[type="file"]').setInputFiles({ name: 'vendors.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });

  await expect(page.getByText(/1 skipped as duplicates/)).toBeVisible();
  await expect(page.getByText(/already exists as V001/)).toBeVisible();
  const created = api.find('POST', '/procurement/vendors/');
  expect(created).toHaveLength(1);
  expect(created[0].body).toMatchObject({ name: 'Zed Supplies', code: 'V501' });
});
