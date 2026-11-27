/**
 * Advances & Travel: the approval and money steps, through the real screens, with the records as the judge.
 *
 * Posted advances are immutable ledger history, so these tests do not try to delete what they post: each run uses a
 * unique destination and the e2e tenant is disposable. A test that needs the seeded employee or the staff-advance
 * accounts skips, with the reason, when the tenant has none, because then there is nothing true to assert.
 */
import type { APIRequestContext } from '@playwright/test';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const BASE = '/api/v1/staff-advances';
const unique = (label: string) => `${label}-${Date.now()}${Math.floor(Math.random() * 1000)}`;

async function employeeId(api: APIRequestContext): Promise<number> {
  const res = await api.get('/api/v1/hrm/employees/', { params: { page_size: 1 } });
  const body = res.ok() ? await res.json() : {};
  const first = (body.results ?? [])[0];
  test.skip(!first, 'the tenant has no employee to give an advance to (run seed_e2e_tenant)');
  return first.id as number;
}

async function reconConfigured(api: APIRequestContext): Promise<boolean> {
  const res = await api.get('/api/v1/accounting/accounts/', { params: { page_size: 200 } });
  const body = res.ok() ? await res.json() : {};
  return ((body.results ?? []) as Array<{ reconciliation_type?: string }>).some((a) => a.reconciliation_type === 'staff_advance');
}

async function newRequest(api: APIRequestContext, employee: number, destination: string, cost = '300.00') {
  const res = await api.post(`${BASE}/travel-requests/`, { data: { employee, destination, estimated_cost: cost, days: 2 } });
  expect(res.status(), await res.text()).toBe(201);
  return (await res.json()).id as number;
}

test.describe('Advances & Travel', () => {
  test('an officer takes a travel request from draft to an advance paid, on the screen', async ({ authedPage: page }) => {
    const api = await apiContext();
    test.skip(!(await reconConfigured(api)), 'no staff-advance reconciliation account is configured in this tenant');
    const destination = unique('Asaba');
    const id = await newRequest(api, await employeeId(api), destination);

    await page.goto('/staff-advances');
    const disabled = page.getByText(/Module Disabled/);
    const tab = page.getByRole('tab', { name: 'Travel Requests', exact: true });
    await expect(tab.or(disabled).first()).toBeVisible({ timeout: 30_000 });
    if (await disabled.count()) { test.info().annotations.push({ type: 'module', description: 'switched off' }); return; }
    await tab.click();

    const row = page.getByTestId('aa-travelRequest').locator('li', { hasText: destination });
    await expect(row).toBeVisible({ timeout: 20_000 });
    await row.getByTestId('aa-submit').click();
    await expect(row.getByText('submitted')).toBeVisible({ timeout: 20_000 });
    await row.getByTestId('aa-approve').click();
    await expect(row.getByText('approved')).toBeVisible({ timeout: 20_000 });
    await row.getByTestId('aa-advance').click();
    await expect(row).toHaveCount(0, { timeout: 20_000 });                 // advanced: no further step waiting here

    const request = await (await api.get(`${BASE}/travel-requests/${id}/`)).json();
    expect(request.status).toBe('advanced');
    const advances = await (await api.get(`${BASE}/staff-advances/`, { params: { employee: request.employee, purpose: 'travel' } })).json();
    const paid = (advances.results as Array<{ reference: string; journal: number | null; amount: string }>).find((a) => a.reference === `TRAVEL-${String(id).padStart(5, '0')}`);
    expect(paid, 'the staff advance raised for the trip').toBeTruthy();
    expect(paid!.journal, 'it was posted to the ledger').not.toBeNull();
    expect(Number(paid!.amount)).toBe(300);
  });

  test('a rejection needs a reason, and the request cannot then be approved', async ({ authedPage: page }) => {
    const api = await apiContext();
    const destination = unique('Sapele');
    const id = await newRequest(api, await employeeId(api), destination, '80.00');
    await api.post(`${BASE}/travel-requests/${id}/submit/`, { data: {} });

    await page.goto('/staff-advances');
    const disabled = page.getByText(/Module Disabled/);
    const tab = page.getByRole('tab', { name: 'Travel Requests', exact: true });
    await expect(tab.or(disabled).first()).toBeVisible({ timeout: 30_000 });
    if (await disabled.count()) { test.info().annotations.push({ type: 'module', description: 'switched off' }); return; }
    await tab.click();

    const row = page.getByTestId('aa-travelRequest').locator('li', { hasText: destination });
    await expect(row.getByTestId('aa-reject')).toBeDisabled();             // no reason yet
    await row.getByLabel(/Reason for rejecting/).fill('Out of budget this quarter');
    await row.getByTestId('aa-reject').click();
    await expect(row).toHaveCount(0, { timeout: 20_000 });

    expect((await (await api.get(`${BASE}/travel-requests/${id}/`)).json()).status).toBe('rejected');
    expect((await api.post(`${BASE}/travel-requests/${id}/approve/`, { data: {} })).status()).toBe(409);
  });

  test('the ledger refuses a second disbursement, an over-recovery and a retirement that does not clear the advance', async () => {
    const api = await apiContext();
    test.skip(!(await reconConfigured(api)), 'no staff-advance reconciliation account is configured in this tenant');
    const requestId = await newRequest(api, await employeeId(api), unique('Warri'), '500.00');
    for (const step of ['submit', 'approve']) {
      const r = await api.post(`${BASE}/travel-requests/${requestId}/${step}/`, { data: {} });
      if (r.status() === 403) { test.info().annotations.push({ type: 'module', description: 'switched off' }); return; }
      expect(r.status()).toBe(200);
    }
    const paid = await api.post(`${BASE}/travel-requests/${requestId}/advance/`, { data: {} });
    expect(paid.status(), await paid.text()).toBe(201);
    const travelAdvance = (await paid.json()) as { id: number; staff_advance: number };

    const again = await api.post(`${BASE}/staff-advances/${travelAdvance.staff_advance}/disburse/`, { data: {} });
    expect(again.status()).toBe(409);                                       // already disbursed: never twice
    const over = await api.post(`${BASE}/staff-advances/${travelAdvance.staff_advance}/recover/`, { data: { amount: '999.00' } });
    expect(over.status()).toBe(409);
    expect((await over.json()).error).toMatch(/outstanding/);

    const short = await api.post(`${BASE}/travel-retirements/`, { data: { travel_advance: travelAdvance.id, amount: '400.00', balance_returned: '50.00' } });
    expect(short.status(), await short.text()).toBe(201);
    const refused = await api.post(`${BASE}/travel-retirements/${(await short.json()).id}/post/`, { data: {} });
    expect(refused.status()).toBe(409);
    expect((await refused.json()).error).toMatch(/whole advance/);
    expect((await (await api.get(`${BASE}/staff-advances/${travelAdvance.staff_advance}/`)).json()).status).toBe('OUTSTANDING');
  });
});
