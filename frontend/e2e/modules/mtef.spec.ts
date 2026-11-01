/**
 * The Medium Term Expenditure Framework screen on Budget Preparation.
 *
 * Drives the real screen end to end for the years 2061-2063 (far from any real budget): enter a balanced budget year through
 * the form, roll it forward, break the financing, see the fiscal rules react, approve with a recorded reason, reopen, and
 * change a rule limit. Everything it creates is removed afterwards, and the rule limits are put back.
 */
import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const BASE = 2061;
const YEARS = [BASE, BASE + 1, BASE + 2];
const BN = 1_000_000_000;
const API = '/api/v1/budget-prep/mtef-projections/';
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const labelled = (label: string) => new RegExp('^' + escapeRe(label) + '\\s*\\*?$');

/** A balanced year: recurrent revenue 700bn, spending 540bn recurrent + 260bn capital against 800bn of revenue. */
const BALANCED: Record<string, number> = {
  'Statutory allocation (FAAC)': 400, 'VAT allocation': 100, 'Internally generated revenue': 150, 'Other recurrent revenue': 50,
  'Grants and aid': 50, 'Capital receipts': 50,
  'Debt service': 40, 'Personnel cost': 300, Overheads: 100, 'Other recurrent': 100, 'Capital expenditure': 260,
};

async function removeTestYears() {
  const api = await apiContext();
  const res = await api.get(`${API}?page_size=200`);
  if (res.ok()) {
    const body = await res.json();
    for (const row of (body.results ?? body) as { id: number; fiscal_year: number; status: string }[]) {
      if (!YEARS.includes(row.fiscal_year)) continue;
      if (row.status === 'approved') await api.post(`${API}${row.id}/reopen/`, { data: { reason: 'end-to-end clean-up' } });
      await api.delete(`${API}${row.id}/`);
    }
  }
  await api.dispose();
}

async function openFramework(page: Page) {
  await page.goto('/budget-prep');
  await page.getByRole('tab', { name: /MTEF/ }).click();
  await expect(page.getByTestId('mtef-panel')).toBeVisible({ timeout: 30_000 });
  await page.getByTestId('mtef-base-year').fill(String(BASE));
  await expect(page.getByTestId(`mtef-year-${BASE + 2}`)).toBeVisible();
}

test.describe('MTEF framework', () => {
  test.beforeAll(removeTestYears);
  test.afterAll(removeTestYears);

  test('enter, roll forward, break, approve, reopen', async ({ authedPage: page }) => {
    const problems: string[] = [];
    page.on('pageerror', (e) => problems.push(e.message));
    page.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 500) problems.push(`${r.status()} ${r.url()}`); });

    await openFramework(page);

    // nothing entered yet: each year offers to be added
    for (const y of YEARS) await expect(page.getByTestId(`mtef-add-${y}`)).toBeVisible();

    // enter the budget year through the form, named for what it is
    await page.getByTestId(`mtef-add-${BASE}`).click();
    const form = page.getByRole('dialog');
    await expect(form.getByText('New MTEF year')).toBeVisible();
    await expect(form.getByLabel(labelled('Fiscal Year'))).toHaveValue(String(BASE));
    for (const [label, bn] of Object.entries(BALANCED)) await form.getByLabel(labelled(label)).fill(String(bn * BN));
    await form.getByLabel(labelled('GDP (GSDP for a state)')).fill(String(2000 * BN));
    await form.getByLabel(labelled('Public debt at start of year')).fill(String(100 * BN));
    await form.getByRole('button', { name: 'Create MTEF year' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0, { timeout: 15_000 });

    // the framework shows it balanced and every core rule met
    await expect(page.getByTestId(`mtef-status-${BASE}`)).toContainText('Draft');
    await expect(page.getByTestId(`mtef-gap-${BASE}`)).not.toHaveText('–');
    await expect(page.getByTestId(`mtef-rule-fully-financed-${BASE}`)).toContainText('Met');
    await expect(page.getByTestId(`mtef-rule-golden-rule-${BASE}`)).toContainText('Met');
    await expect(page.getByTestId(`mtef-rule-deficit-to-gdp-${BASE}`)).toContainText('Met');   // no deficit
    await expect(page.getByTestId(`mtef-rule-debt-stock-${BASE}`)).toContainText('Met');       // 100bn of 2 000bn

    // roll forward creates the two outer years
    await page.getByTestId('mtef-roll').click();
    for (const y of YEARS.slice(1)) await expect(page.getByTestId(`mtef-status-${y}`)).toBeVisible({ timeout: 15_000 });

    // overspend on capital with no financing: the rule breaks and the year is flagged
    await page.getByTestId(`mtef-edit-${BASE}`).click();
    const edit = page.getByRole('dialog');
    await edit.getByLabel(labelled('Capital expenditure')).fill(String(360 * BN));
    await edit.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByTestId(`mtef-rule-fully-financed-${BASE}`)).toContainText('Broken');
    await expect(page.getByTestId(`mtef-rule-deficit-to-gdp-${BASE}`)).toContainText('Broken');  // 100bn of 2 000bn is 5%, over the 3% limit
    await expect(page.getByTestId('mtef-attention')).toBeVisible();
    await expect(page.getByTestId('mtef-allgood')).toHaveCount(0);

    // approval needs a recorded reason while a rule is broken
    await page.getByTestId(`mtef-approve-${BASE}`).click();
    await expect(page.getByTestId('mtef-decision')).toBeVisible();
    await expect(page.getByTestId('mtef-decision-confirm')).toBeDisabled();
    await page.getByTestId('mtef-reason').fill('Deficit to be financed by a bond approved by the Assembly');
    await page.getByTestId('mtef-decision-confirm').click();
    await expect(page.getByTestId(`mtef-status-${BASE}`)).toContainText('Approved', { timeout: 15_000 });

    // an approved year is locked until it is reopened with a reason
    await expect(page.getByTestId(`mtef-edit-${BASE}`)).toBeDisabled();
    await page.getByTestId(`mtef-reopen-${BASE}`).click();
    await expect(page.getByTestId('mtef-decision-confirm')).toBeDisabled();
    await page.getByTestId('mtef-reason').fill('Financing plan changed');
    await page.getByTestId('mtef-decision-confirm').click();
    await expect(page.getByTestId(`mtef-status-${BASE}`)).not.toContainText('Approved', { timeout: 15_000 });
    await expect(page.getByTestId(`mtef-edit-${BASE}`)).toBeEnabled();

    expect(problems).toEqual([]);
  });

  test('a rule limit is the government’s to set, and is held to', async ({ authedPage: page }) => {
    const api = await apiContext();
    await api.post(API, { data: { fiscal_year: BASE, inflation_assumption: '15', exchange_rate_assumption: '1500', gdp_assumption: String(2000 * BN), ...Object.fromEntries(
      [['rev_statutory', 400], ['rev_vat', 100], ['rev_igr', 150], ['rev_other', 50], ['rev_grants', 50], ['rev_capital_receipts', 50],
        ['exp_debt_service', 40], ['exp_personnel', 300], ['exp_overhead', 100], ['exp_other_recurrent', 100], ['exp_capital', 260]]
        .map(([k, v]) => [k, String(Number(v) * BN)])) } });
    await api.dispose();

    await openFramework(page);
    const debtRule = page.getByTestId(`mtef-rule-debt-service-${BASE}`);
    await expect(debtRule).toContainText('Met');

    await page.getByText('Fiscal rules and their limits').click();
    await expect(page.getByTestId('mtef-policy')).toBeVisible();
    const limit = page.getByTestId('policy-max_debt_service_pct');
    const original = await limit.inputValue();
    try {
      await limit.fill('1');
      await page.getByTestId('policy-save').click();
      await expect(debtRule).toContainText('Broken', { timeout: 15_000 });
    } finally {
      await limit.fill(original);
      await page.getByTestId('policy-save').click();
    }
    await expect(debtRule).toContainText('Met', { timeout: 15_000 });

    // a fall in the oil price is run against the framework without saving anything
    await page.getByTestId('mtef-oil').fill('-30');
    await page.getByTestId('mtef-scenario-run').click();
    await expect(page.getByTestId('mtef-scenario-result')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId(`mtef-shock-change-${BASE}`)).not.toHaveText(/^₦0\.00$/);
    await expect(page.getByTestId(`mtef-shock-verdict-${BASE}`)).toBeVisible();
  });

  test('fits a phone screen without sideways page scroll', async ({ authedPage: page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openFramework(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
