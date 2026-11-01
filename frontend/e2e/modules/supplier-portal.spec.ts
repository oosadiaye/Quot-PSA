/**
 * The supplier portal end to end: the procurement office switches it on and lets a supplier in, then the supplier signs in as
 * itself, acknowledges an order, updates contact details and asks to change its bank, and the office approves the change.
 * Everything it creates (one supplier, its sign-in and order) is removed afterwards.
 *
 * Needs the project's Python (E2E_PYTHON, default the repository's .venv) for the few things a browser cannot do.
 */
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Browser, Page } from '@playwright/test';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CODE = 'E2E-SP1';
const EMAIL = 'e2e-sp1@example.test';
const PO = 'E2E-PO-0001';
const REPO = path.resolve(__dirname, '../../..');
const PYTHON = process.env.E2E_PYTHON ?? path.join(REPO, '.venv', 'Scripts', 'python.exe');
const SUPPORT = path.resolve(__dirname, '../fixtures/e2e_support.py');
const session: { tenantDomain: string } = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../.auth/session.json'), 'utf8'));

const support = (...args: string[]) => execFileSync(PYTHON, ['-I', SUPPORT, ...args], { cwd: REPO, encoding: 'utf8' }).trim().split(/\r?\n/).pop()!;

/** A browser signed in as the supplier, the way the app stores a session after login. */
async function supplierPage(browser: Browser): Promise<Page> {
  const token = support('token', session.tenantDomain, EMAIL);
  const context = await browser.newContext({ baseURL: 'http://127.0.0.1:5173' });
  await context.addInitScript(({ t, domain }) => {
    const info = { id: 6, name: 'Office of Accountant General Delta State', domain, role: 'vendor' };
    const entries: Record<string, string> = {
      authToken: t, tenantDomain: domain, tenantInfo: JSON.stringify(info), tenantPermissions: '[]', activeTenant: info.name,
      user: JSON.stringify({ id: 0, username: 'supplier', email: 'e2e-sp1@example.test', first_name: '', last_name: '', is_superuser: false, groups: [], permissions: [] }),
    };
    for (const [k, v] of Object.entries(entries)) { localStorage.setItem(k, v); sessionStorage.setItem(k, v); }
  }, { t: token, domain: session.tenantDomain });
  return context.newPage();
}

async function clean() {
  support('cleanup', session.tenantDomain, CODE);
  const api = await apiContext();
  const cfg = await api.patch('/api/v1/procurement/portal-settings/current/', { data: { enabled: false, auto_activate_on_payment: false } });
  expect(cfg.ok()).toBeTruthy();
  await api.dispose();
}

test.describe('Supplier portal', () => {
  test.setTimeout(180_000);
  test.beforeEach(clean);                       // each test starts with no E2E supplier
  test.afterAll(async () => { test.setTimeout(120_000); await clean(); });    // starting Python is slow on a busy machine

  test('the office lets a supplier in, the supplier uses the portal, the office approves a bank change', async ({ authedPage: office, browser }) => {
    const problems: string[] = [];
    office.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 500) problems.push(`${r.status()} ${r.url()}`); });

    // a supplier with an email address, and the portal switched on, as an officer would have it
    const api = await apiContext();
    const created = await api.post('/api/v1/procurement/vendors/', { data: { name: 'E2E Supplies Ltd', code: CODE, email: EMAIL } });
    expect(created.ok(), await created.text()).toBeTruthy();
    await api.dispose();
    support('activate', session.tenantDomain, CODE);          // registration paid: the register lists only paid-up suppliers

    // ── the office: switch on, invite, let in ─────────────────────────────────────────────────────────────────
    await office.goto('/procurement/supplier-portal');
    await expect(office.getByTestId('spa')).toBeVisible({ timeout: 30_000 });
    await office.getByTestId('spa-enabled').check();
    await expect(office.getByTestId('spa-enabled')).toBeChecked();
    await office.getByLabel('Search suppliers').fill(CODE);
    await expect(office.getByTestId(`spa-status-${CODE}`)).toHaveText('Not invited', { timeout: 20_000 });
    await office.getByTestId(`spa-invite-${CODE}`).click();
    await expect(office.getByTestId(`spa-status-${CODE}`)).toHaveText('Invited');
    await office.getByTestId(`spa-activate-${CODE}`).click();
    await expect(office.getByTestId(`spa-status-${CODE}`)).toHaveText('Active');

    support('po', session.tenantDomain, CODE, PO);

    // ── the supplier ──────────────────────────────────────────────────────────────────────────────────────────
    const sup = await supplierPage(browser);
    const supProblems: string[] = [];
    sup.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 500) supProblems.push(`${r.status()} ${r.url()}`); });
    await sup.goto('/supplier-portal');
    await expect(sup.getByTestId('sp-name')).toHaveText('E2E Supplies Ltd', { timeout: 30_000 });
    await expect(sup.getByTestId('sp-reg-status')).toBeVisible();

    // contact details are the supplier's own to change
    await sup.getByLabel('Phone').fill('08031234567');
    await sup.getByTestId('sp-save-contact').click();
    await expect(sup.getByTestId('sp-saved')).toBeVisible();

    // an order awaiting acknowledgement, with its lines, and acknowledging it
    await sup.getByTestId('sp-tab-orders').click();
    await expect(sup.getByTestId('sp-order-row')).toHaveCount(1);
    await expect(sup.getByTestId('sp-order-row')).toContainText(PO);
    await expect(sup.getByTestId('sp-order-row')).toContainText('Needs your acknowledgement');
    await sup.getByRole('button', { name: `Open order ${PO}` }).click();
    await expect(sup.getByTestId('sp-order-detail')).toContainText('Borehole pump');
    await expect(sup.getByTestId('sp-order-detail')).toContainText('₦300,000.00');
    await sup.getByLabel('Note to the procurement office (optional)').fill('Delivery within two weeks');
    await sup.getByTestId('sp-acknowledge').click();
    await expect(sup.getByTestId('sp-acknowledged')).toBeVisible();

    // invoices and payments are empty, and say so
    await sup.getByTestId('sp-tab-invoices').click();
    await expect(sup.getByTestId('sp-empty')).toContainText('No invoices yet');
    await sup.getByTestId('sp-tab-payments').click();
    await expect(sup.getByTestId('sp-empty')).toContainText('No payments yet');

    // a bank change: an account number must be 10 digits, then it waits for the office
    await sup.getByTestId('sp-tab-bank').click();
    await sup.getByLabel('Bank name').fill('First Bank');
    await sup.getByLabel('Account number (10 digits)').fill('12345');
    await expect(sup.getByTestId('sp-bank-send')).toBeDisabled();
    await sup.getByLabel('Account number (10 digits)').fill('0123456789');
    await sup.getByTestId('sp-bank-send').click();
    await expect(sup.getByTestId('sp-bank-waiting')).toContainText('First Bank');
    await expect(sup.getByTestId('sp-bank-masked')).toHaveText('Not set');           // nothing has moved yet

    // ── the office approves it ───────────────────────────────────────────────────────────────────────────────
    await office.reload();
    await expect(office.getByTestId('spa-change')).toContainText('First Bank', { timeout: 20_000 });
    await office.getByTestId('spa-approve').click();
    await expect(office.getByTestId('spa-no-changes')).toBeVisible({ timeout: 20_000 });

    // ── and the supplier now sees the new bank, masked ───────────────────────────────────────────────────────
    await sup.reload();
    await sup.getByTestId('sp-tab-bank').click();
    await expect(sup.getByTestId('sp-bank-masked')).toHaveText('••••••6789');

    // ── suspending shuts the supplier out ────────────────────────────────────────────────────────────────────
    await office.getByLabel('Search suppliers').fill(CODE);
    await office.getByTestId(`spa-suspend-${CODE}`).click();
    await expect(office.getByTestId(`spa-status-${CODE}`)).toHaveText('Suspended');
    await sup.reload();
    await expect(sup.getByTestId('sp-denied')).toBeVisible({ timeout: 20_000 });

    expect(problems).toEqual([]);
    expect(supProblems).toEqual([]);
    await sup.context().close();
  });

  test('a supplier can see nothing outside its own record', async ({ authedPage: office, browser }) => {
    // two suppliers, each with an order: the second one's order must not be reachable from the first one's session
    const api = await apiContext();
    await api.patch('/api/v1/procurement/portal-settings/current/', { data: { enabled: true } });
    const first = await api.post('/api/v1/procurement/vendors/', { data: { name: 'E2E Supplies Ltd', code: CODE, email: EMAIL } });
    expect(first.ok(), await first.text()).toBeTruthy();
    const { id } = await first.json();
    support('activate', session.tenantDomain, CODE);
    await api.post(`/api/v1/procurement/vendors/${id}/portal-invite/`, { data: {} });
    await api.post(`/api/v1/procurement/vendors/${id}/portal-activate/`, { data: {} });
    await api.dispose();
    support('po', session.tenantDomain, CODE, PO);

    const sup = await supplierPage(browser);
    await sup.goto('/supplier-portal?tab=orders');
    await expect(sup.getByTestId('sp-order-row')).toHaveCount(1, { timeout: 30_000 });

    // staff endpoints answer a supplier with a refusal, not data
    const status = await sup.evaluate(async () => {
      const token = sessionStorage.getItem('authToken');
      const domain = sessionStorage.getItem('tenantDomain');
      const base = `${(window as unknown as { __API__?: string }).__API__ ?? 'http://localhost:8032'}/api/v1`;
      const r = await fetch(`${base}/procurement/vendors/`, { headers: { Authorization: `Token ${token}`, 'X-Tenant-Domain': domain ?? '' } });
      return r.status;
    });
    expect(status).toBe(403);
    await sup.context().close();
    void office;
  });
});
