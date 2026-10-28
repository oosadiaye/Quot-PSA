import { test, expect, type Page } from '@playwright/test';
import { bootMock, type Handler } from './mockApi';

/**
 * GL-coding check on a posting form: when a line's memo doesn't fit its GL
 * account the operator is warned, can adopt a suggested existing account,
 * post anyway, or go back. (Suggestion ranking is covered by pytest.)
 */

const ACCOUNTS = [
  { id: 1, code: '22101001', name: 'Motor Vehicle Fuel', account_type: 'Expense' },
  { id: 2, code: '22109999', name: 'Bank Charges', account_type: 'Expense' },
  { id: 3, code: '10101001', name: 'Cash at Bank', account_type: 'Asset' },
];
const FUEL = { id: 1, code: '22101001', name: 'Motor Vehicle Fuel', account_type: 'Expense', score: 1, source: 'name' };

interface GlLine { name: string; code: string; description: string }

const page_ = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results });

/** Chart of accounts + the five mandatory journal dimensions (one option each). */
const accountsHandler: Handler = (c) => {
  if (c.method !== 'GET') return undefined;
  if (c.path === '/accounting/accounts/') return { body: page_(ACCOUNTS) };
  const dim: Record<string, string> = {
    '/accounting/mdas/': 'MDA', '/accounting/funds/': 'Fund', '/accounting/functions/': 'Function',
    '/accounting/programs/': 'Program', '/accounting/geos/': 'Geo',
  };
  return dim[c.path] ? { body: page_([{ id: 1, code: '01', name: `Test ${dim[c.path]}`, is_active: true }]) } : undefined;
};

/** Server stand-in: a "fuel" memo coded to Bank Charges is suspect and Motor Vehicle Fuel is suggested. */
const glCheck: Handler = (c) => {
  if (c.method !== 'POST' || c.path !== '/accounting/gl-coding-check/') return undefined;
  const results = (c.body.lines as GlLine[]).map((l) => {
    const bad = /fuel/i.test(l.description) && l.code === '22109999';
    return {
      ...l, verdict: bad ? 'suspect' : 'ok', score: bad ? 0 : 1, ai_used: false,
      reason: bad ? 'Description doesn’t look like it belongs to "Bank Charges".' : '',
      suggestions: bad ? [FUEL] : [],
    };
  });
  return { body: { results, ai_used: false } };
};

/** The GL-account combobox of journal line `nth` (the placeholder disappears once a value is chosen). */
const accountBox = (page: Page, nth: number) => page.locator('tbody tr').nth(nth).getByRole('combobox').first();

async function pickAccount(page: Page, nth: number, search: string) {
  const box = accountBox(page, nth);
  await box.click();
  await box.fill(search);
  // The code is unique, so the list narrows to one option and Enter selects it
  // (more robust than clicking a menu that may be positioned off-screen).
  await expect(page.getByRole('option', { name: new RegExp(search) })).toHaveCount(1);
  await box.press('Enter');
}

/** A balanced two-line journal whose second line (Bank Charges) carries a fuel memo. */
async function fillJournal(page: Page) {
  await page.goto('/accounting/new');
  await page.getByPlaceholder('e.g. JV-2024-001').fill('JV-E2E-1');
  await page.getByPlaceholder('Purpose of this entry').fill('Fuel purchase');
  for (const dim of ['MDA', 'Fund', 'Function', 'Program', 'Geo']) {
    const box = page.getByPlaceholder(`Search ${dim}…`);
    await box.click();
    await box.press('Enter');
  }
  await pickAccount(page, 0, '22101001');
  await pickAccount(page, 1, '22109999');
  const amounts = page.locator('input[inputmode="decimal"]');
  await amounts.nth(0).fill('5000');   // line 1 debit
  await amounts.nth(3).fill('5000');   // line 2 credit
  const memos = page.getByPlaceholder('Line memo');
  await memos.nth(0).fill('Generator service');
  await memos.nth(1).fill('Fuel for vehicles');
}
const save = (page: Page) => page.getByRole('button', { name: /Save Draft/ }).click();

test.describe('Journal form — GL coding check', () => {
  test('warns, and "Use this account" recodes the line without posting', async ({ page }) => {
    const api = await bootMock(page, [accountsHandler, glCheck, (c) => (c.method === 'POST' && c.path === '/accounting/journals/' ? { body: { id: 99 } } : undefined)]);
    await fillJournal(page);
    await save(page);

    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('Check the GL account');
    await expect(dialog).toContainText('Fuel for vehicles');
    await expect(dialog).toContainText('22101001 · Motor Vehicle Fuel');
    expect(api.find('POST', '/accounting/journals/')).toHaveLength(0);

    await dialog.getByRole('button', { name: 'Use this account' }).click();
    // Adopting the only flagged line closes the warning WITHOUT posting …
    await expect(dialog).toHaveCount(0);
    expect(api.find('POST', '/accounting/journals/')).toHaveLength(0);
    // … and the line now shows the adopted account.
    await expect(accountBox(page, 1)).toHaveValue(/Motor Vehicle Fuel/);

    // Saving again passes the check and posts the recoded line.
    await save(page);
    await expect.poll(() => api.find('POST', '/accounting/journals/').length).toBe(1);
    const lines = api.find('POST', '/accounting/journals/')[0].body.lines as Array<{ account: unknown }>;
    expect(lines.map((l) => String(l.account))).toEqual(['1', '1']);
  });

  test('"Post anyway" posts the original coding', async ({ page }) => {
    const api = await bootMock(page, [accountsHandler, glCheck, (c) => (c.method === 'POST' && c.path === '/accounting/journals/' ? { body: { id: 99 } } : undefined)]);
    await fillJournal(page);
    await save(page);
    await page.getByRole('alertdialog').getByRole('button', { name: 'Post anyway' }).click();
    await expect.poll(() => api.find('POST', '/accounting/journals/').length).toBe(1);
    const lines = api.find('POST', '/accounting/journals/')[0].body.lines as Array<{ account: unknown }>;
    expect(lines.map((l) => String(l.account))).toEqual(['1', '2']);
  });

  test('"Go back & fix" posts nothing', async ({ page }) => {
    const api = await bootMock(page, [accountsHandler, glCheck]);
    await fillJournal(page);
    await save(page);
    await page.getByRole('alertdialog').getByRole('button', { name: /Go back/ }).click();
    await expect(page.getByRole('alertdialog')).toHaveCount(0);
    expect(api.find('POST', '/accounting/journals/')).toHaveLength(0);
  });

  test('a well-coded journal posts with no warning', async ({ page }) => {
    const api = await bootMock(page, [accountsHandler, glCheck, (c) => (c.method === 'POST' && c.path === '/accounting/journals/' ? { body: { id: 99 } } : undefined)]);
    await fillJournal(page);
    await page.getByPlaceholder('Line memo').nth(1).fill('Quarterly bank fees');
    await save(page);
    await expect.poll(() => api.find('POST', '/accounting/journals/').length).toBe(1);
    await expect(page.getByRole('alertdialog')).toHaveCount(0);
  });

  test('a failing check never blocks the post', async ({ page }) => {
    const api = await bootMock(page, [
      accountsHandler,
      (c) => (c.path === '/accounting/gl-coding-check/' ? { status: 500, body: {} } : undefined),
      (c) => (c.method === 'POST' && c.path === '/accounting/journals/' ? { body: { id: 99 } } : undefined),
    ]);
    await fillJournal(page);
    await save(page);
    await expect.poll(() => api.find('POST', '/accounting/journals/').length).toBe(1);
  });
});

test.describe('Recurring journal form — GL coding check', () => {
  test('"Use this account" recodes the line, then the template saves', async ({ page }) => {
    const api = await bootMock(page, [
      accountsHandler, glCheck,
      (c) => (c.method === 'POST' && c.path === '/accounting/recurring-journals/' ? { body: { id: 5 } } : undefined),
    ]);
    await page.goto('/accounting/recurring-journals/new');
    await page.locator('form input[required]').first().fill('Monthly fuel');          // template name
    await page.locator('form input[type="date"][required]').first().fill('2026-11-01'); // start date

    const lineAccount = (n: number) => page.locator('tbody tr').nth(n).locator('select');
    await lineAccount(0).selectOption('1');   // Motor Vehicle Fuel
    await lineAccount(1).selectOption('2');   // Bank Charges  (mis-coded)
    await page.getByPlaceholder('Line description').nth(0).fill('Generator service');
    await page.getByPlaceholder('Line description').nth(1).fill('Fuel for vehicles');
    const nums = page.locator('tbody input[type="number"]');
    await nums.nth(0).fill('5000');   // line 1 debit
    await nums.nth(3).fill('5000');   // line 2 credit

    await page.getByRole('button', { name: /Create Template/ }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('22101001 · Motor Vehicle Fuel');
    expect(api.find('POST', '/accounting/recurring-journals/')).toHaveLength(0);

    await dialog.getByRole('button', { name: 'Use this account' }).click();
    await expect(dialog).toHaveCount(0);
    await expect(lineAccount(1)).toHaveValue('1');
    expect(api.find('POST', '/accounting/recurring-journals/')).toHaveLength(0);

    await page.getByRole('button', { name: /Create Template/ }).click();
    await expect.poll(() => api.find('POST', '/accounting/recurring-journals/').length).toBe(1);
    const lines = api.find('POST', '/accounting/recurring-journals/')[0].body.lines as Array<{ account: unknown }>;
    expect(lines.map((l) => String(l.account))).toEqual(['1', '1']);
  });
});
