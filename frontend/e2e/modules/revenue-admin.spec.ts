/**
 * Revenue Administration: the lifecycle a revenue officer runs, through the real screens.
 *
 * Each test makes its own taxpayer (a unique TIN), drives the UI where a person would, and checks the outcome through
 * the API, because the point of the actions is what they do to the records, not what the screen says. Everything it
 * creates is removed afterwards. A tenant with the module switched off is expected to show the disabled page.
 */
import type { APIRequestContext, Page } from '@playwright/test';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const BASE = '/api/v1/revenue-admin';
const stamp = () => `${Date.now()}${Math.floor(Math.random() * 1000)}`;

interface Made { taxpayer: number; head: number }

async function firstRevenueHead(api: APIRequestContext): Promise<number> {
  const res = await api.get('/api/v1/accounting/revenue-heads/', { params: { page_size: 1 } });
  expect(res.ok(), `revenue heads: ${res.status()}`).toBeTruthy();
  const body = await res.json();
  const head = (body.results ?? body)[0];
  test.skip(!head, 'the tenant has no revenue head to assess against');
  return head.id as number;
}

async function makeTaxpayer(api: APIRequestContext, label: string): Promise<Made> {
  const created = await api.post(`${BASE}/taxpayers/`, { data: { tin: `E2E-${label}-${stamp()}`, full_name: `E2E ${label}` } });
  expect(created.status(), await created.text()).toBe(201);
  return { taxpayer: (await created.json()).id, head: await firstRevenueHead(api) };
}

async function open(page: Page): Promise<boolean> {
  const modulesKnown = page.waitForResponse((r) => r.url().includes('/tenants/enabled-modules/'), { timeout: 20_000 }).catch(() => null);
  await page.goto('/revenue-admin');
  const register = page.getByRole('tab').first();
  const disabled = page.getByText(/Module Disabled/);
  await expect(register.or(disabled).first()).toBeVisible({ timeout: 30_000 });
  await modulesKnown;
  await page.waitForTimeout(300);
  return (await disabled.count()) === 0;
}

async function cleanup(api: APIRequestContext, made: Made) {
  const notices = await (await api.get(`${BASE}/demand-notices/`, { params: { taxpayer: made.taxpayer } })).json();
  for (const n of notices.results ?? []) await api.delete(`${BASE}/demand-notices/${n.id}/`);
  const assessments = await (await api.get(`${BASE}/assessments/`, { params: { taxpayer: made.taxpayer } })).json();
  for (const a of assessments.results ?? []) await api.delete(`${BASE}/assessments/${a.id}/`);
  const arrears = await (await api.get(`${BASE}/arrears/`)).json();
  for (const r of (arrears.results ?? []).filter((x: { taxpayer: number }) => x.taxpayer === made.taxpayer)) await api.delete(`${BASE}/arrears/${r.id}/`);
  await api.delete(`${BASE}/taxpayers/${made.taxpayer}/`);
}

test.describe('Revenue Administration lifecycle', () => {
  test('an officer issues a draft assessment from the screen and the demand notice and liability appear', async ({ authedPage: page }) => {
    const api = await apiContext();
    const made = await makeTaxpayer(api, 'issue');
    try {
      const drafted = await api.post(`${BASE}/assessments/`, {
        data: { taxpayer: made.taxpayer, revenue_head: made.head, fiscal_year: 2026, assessed_amount: '12500.00', assessment_type: 'self' },
      });
      expect(drafted.status(), await drafted.text()).toBe(201);
      const assessment = (await drafted.json()).id as number;

      if (!(await open(page))) { test.info().annotations.push({ type: 'module', description: 'switched off; disabled page shown' }); return; }
      await page.getByRole('tab', { name: 'Assessments', exact: true }).click();
      const panel = page.getByTestId('ra-assessment');
      const row = panel.locator('li', { hasText: `Assessment ${assessment} ` });
      await expect(row).toBeVisible({ timeout: 20_000 });
      await row.getByTestId('ra-assessment-run').click();
      await expect(row).toHaveCount(0, { timeout: 20_000 });          // it is no longer a draft waiting to be issued

      const notices = await (await api.get(`${BASE}/demand-notices/`, { params: { taxpayer: made.taxpayer } })).json();
      expect(notices.results).toHaveLength(1);
      expect(notices.results[0].notice_number).toMatch(/^DN-/);
      expect(Number(notices.results[0].amount_due)).toBe(12500);
      const after = await (await api.get(`${BASE}/assessments/${assessment}/`)).json();
      expect(after.status).toBe('issued');
    } finally {
      await cleanup(api, made);
    }
  });

  test('issuing the same assessment twice over the API never makes a second notice', async () => {
    const api = await apiContext();
    const made = await makeTaxpayer(api, 'twice');
    try {
      const a = await (await api.post(`${BASE}/assessments/`, {
        data: { taxpayer: made.taxpayer, revenue_head: made.head, fiscal_year: 2026, assessed_amount: '300.00' },
      })).json();
      const first = await api.post(`${BASE}/assessments/${a.id}/issue/`, { data: {} });
      if (first.status() === 403) { test.info().annotations.push({ type: 'module', description: 'switched off' }); return; }
      expect(first.status()).toBe(200);
      expect((await api.post(`${BASE}/assessments/${a.id}/issue/`, { data: {} })).status()).toBe(200);
      const notices = await (await api.get(`${BASE}/demand-notices/`, { params: { taxpayer: made.taxpayer } })).json();
      expect(notices.results).toHaveLength(1);
    } finally {
      await cleanup(api, made);
    }
  });

  test('clearance is refused with a reason while the taxpayer has unsettled arrears, and granted once they do not', async () => {
    const api = await apiContext();
    const made = await makeTaxpayer(api, 'clear');
    try {
      const arrears = await api.post(`${BASE}/arrears/`, {
        data: { taxpayer: made.taxpayer, revenue_head: made.head, fiscal_year: 2024, amount: '75.00' },
      });
      expect(arrears.status(), await arrears.text()).toBe(201);
      const refused = await api.post(`${BASE}/clearance-certificates/issue/`, { data: { taxpayer: made.taxpayer, fiscal_year: 2026 } });
      if (refused.status() === 403) { test.info().annotations.push({ type: 'module', description: 'switched off' }); return; }
      expect(refused.status()).toBe(409);
      expect((await refused.json()).error).toMatch(/arrears/i);

      await api.patch(`${BASE}/arrears/${(await arrears.json()).id}/`, { data: { amount: '0.00', is_settled: true } });
      const granted = await api.post(`${BASE}/clearance-certificates/issue/`, { data: { taxpayer: made.taxpayer, fiscal_year: 2026 } });
      expect(granted.status(), await granted.text()).toBe(201);
      const cert = await granted.json();
      expect(cert.certificate_number).toMatch(/^TCC-/);
      await api.delete(`${BASE}/clearance-certificates/${cert.id}/`);
    } finally {
      await cleanup(api, made);
    }
  });

  test('the ageing action on the Demand Notices tab runs and reports what it did', async ({ authedPage: page }) => {
    if (!(await open(page))) { test.info().annotations.push({ type: 'module', description: 'switched off' }); return; }
    await page.getByRole('tab', { name: 'Demand Notices', exact: true }).click();
    await page.getByTestId('ra-ageing-run').click();
    await expect(page.getByText(/marked overdue/)).toBeVisible({ timeout: 20_000 });
  });
});
