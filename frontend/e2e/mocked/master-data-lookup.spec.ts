import { test, expect } from '@playwright/test';
import { bootMock, duplicateCheck, dupMatch, emptyList } from './mockApi';

/**
 * Master-data duplicate lookup — UI behaviour, API mocked.
 * (Backend matching rules are covered by accounting/tests/test_duplicate_lookup.py.)
 */

// NCoA-style create forms: route segment, duplicate-check entity, list endpoint they save to.
const NCOA_FORMS = [
  { name: 'MDA (administrative)', route: 'administrative', entity: 'admin_segment', save: '/accounting/ncoa/administrative/', code: '010100000000' },
  { name: 'Fund',        route: 'fund',        entity: 'ncoa_fund',        save: '/accounting/ncoa/fund/',        code: '01000' },
  { name: 'Functional',  route: 'functional',  entity: 'ncoa_functional',  save: '/accounting/ncoa/functional/',  code: '70100' },
  { name: 'Programme',   route: 'programme',   entity: 'ncoa_programme',   save: '/accounting/ncoa/programme/',   code: '01010000000000' },
  { name: 'Geographic',  route: 'geographic',  entity: 'ncoa_geographic',  save: '/accounting/ncoa/geographic/',  code: '51000100' },
];

for (const f of NCOA_FORMS) {
  test.describe(`${f.name} create form`, () => {
    const existing = dupMatch({ id: 7, code: '99999', name: 'Ministry of Finance', level: 'likely' });

    test('shows an inline hint while typing, and a prompt on save', async ({ page }) => {
      const api = await bootMock(page, [duplicateCheck(f.entity, [existing])]);
      await page.goto(`/accounting/ncoa/${f.route}/new`);

      await page.locator('input[required]').first().fill(f.code);
      await page.locator('input[required]').nth(1).fill('Ministry of Finances');

      // As-you-type hint (debounced) — no click needed.
      const hint = page.getByRole('status').filter({ hasText: 'already exists' });
      await expect(hint).toBeVisible();
      await expect(hint).toContainText('Ministry of Finance');
      await expect(hint).toContainText('Likely duplicate');

      // The (debounced) lookup is eventually sent with everything typed.
      await expect.poll(() =>
        api.find('POST', '/core/duplicate-check/').some(
          (c) => c.body.entity === f.entity && c.body.values?.code === f.code && c.body.values?.name === 'Ministry of Finances',
        ),
      ).toBe(true);

      // Saving is held until the operator decides.
      await page.locator('button[type="submit"]').first().click();
      const dialog = page.getByRole('alertdialog');
      await expect(dialog).toBeVisible();
      await expect(dialog).toContainText('Ministry of Finance');
      expect(api.find('POST', f.save)).toHaveLength(0);
    });

    test('"Use this one" opens the existing record instead of creating', async ({ page }) => {
      const api = await bootMock(page, [duplicateCheck(f.entity, [existing])]);
      await page.goto(`/accounting/ncoa/${f.route}/new`);
      await page.locator('input[required]').first().fill(f.code);
      await page.locator('input[required]').nth(1).fill('Ministry of Finances');
      await page.locator('button[type="submit"]').first().click();

      await page.getByRole('alertdialog').getByRole('button', { name: 'Use this one' }).click();
      await expect(page).toHaveURL(new RegExp(`/accounting/ncoa/${f.route}/7/edit$`));
      expect(api.find('POST', f.save)).toHaveLength(0);
    });

    test('"Create anyway" saves the new record', async ({ page }) => {
      const api = await bootMock(page, [duplicateCheck(f.entity, [existing])]);
      await page.goto(`/accounting/ncoa/${f.route}/new`);
      await page.locator('input[required]').first().fill(f.code);
      await page.locator('input[required]').nth(1).fill('Ministry of Finances');
      await page.locator('button[type="submit"]').first().click();

      await page.getByRole('alertdialog').getByRole('button', { name: 'Create anyway' }).click();
      await expect.poll(() => api.find('POST', f.save).length).toBe(1);
      expect(api.find('POST', f.save)[0].body).toMatchObject({ code: f.code, name: 'Ministry of Finances' });
    });

    test('saves straight away when nothing matches', async ({ page }) => {
      const api = await bootMock(page, [duplicateCheck(f.entity, [])]);
      await page.goto(`/accounting/ncoa/${f.route}/new`);
      await page.locator('input[required]').first().fill(f.code);
      await page.locator('input[required]').nth(1).fill('Brand New Thing');
      await expect(page.getByRole('status').filter({ hasText: 'already exists' })).toHaveCount(0);
      await page.locator('button[type="submit"]').first().click();
      await expect.poll(() => api.find('POST', f.save).length).toBe(1);
      await expect(page.getByRole('alertdialog')).toHaveCount(0);
    });

    test('a failing lookup never blocks the save', async ({ page }) => {
      const api = await bootMock(page, [
        (c) => (c.path === '/core/duplicate-check/' ? { status: 500, body: { detail: 'boom' } } : undefined),
      ]);
      await page.goto(`/accounting/ncoa/${f.route}/new`);
      await page.locator('input[required]').first().fill(f.code);
      await page.locator('input[required]').nth(1).fill('Whatever');
      await page.locator('button[type="submit"]').first().click();
      await expect.poll(() => api.find('POST', f.save).length).toBe(1);
    });
  });
}

test('an exact code collision hides "Create anyway" (the server would reject it)', async ({ page }) => {
  await bootMock(page, [
    duplicateCheck('ncoa_fund', [dupMatch({ id: 3, code: '01000', name: 'FAAC Statutory Allocation', level: 'exact', reasons: ['Same code'] })]),
  ]);
  await page.goto('/accounting/ncoa/fund/new');
  await page.locator('input[required]').first().fill('01000');
  await page.locator('input[required]').nth(1).fill('Something');
  await page.locator('button[type="submit"]').first().click();
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('already exists');
  await expect(dialog.getByRole('button', { name: 'Create anyway' })).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: 'Go back' })).toBeVisible();
});

test('editing an existing record does not prompt', async ({ page }) => {
  const api = await bootMock(page, [
    duplicateCheck('ncoa_fund', [dupMatch()]),
    (c) => (c.method === 'GET' && c.path === '/accounting/ncoa/fund/5/' ? { body: { id: 5, code: '01000', name: 'FAAC', is_active: true } } : undefined),
  ]);
  await page.goto('/accounting/ncoa/fund/5/edit');
  await page.locator('button[type="submit"]').first().click();
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
  await expect.poll(() => api.calls.filter((c) => c.method === 'PUT').length).toBe(1);
  void emptyList;
});
