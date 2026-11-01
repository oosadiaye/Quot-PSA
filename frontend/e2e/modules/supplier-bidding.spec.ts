/**
 * Bidding end to end: a supplier asks to be a registered bidder, the office registers it, the supplier seals and then replaces a
 * bid, the office sees who bid but not what, and after the closing date opens the bids in front of witnesses. Everything it creates
 * is removed afterwards and the e-procurement module is put back as it was.
 */
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Browser, Page } from '@playwright/test';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CODE = 'E2E-SP4';
const EMAIL = 'e2e-sp4@example.test';
const REF = 'E2E-T-0001';
const REPO = path.resolve(__dirname, '../../..');
const PYTHON = process.env.E2E_PYTHON ?? path.join(REPO, '.venv', 'Scripts', 'python.exe');
const SUPPORT = path.resolve(__dirname, '../fixtures/e2e_support.py');
const session: { tenantDomain: string } = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../.auth/session.json'), 'utf8'));
const support = (...args: string[]) => execFileSync(PYTHON, ['-I', SUPPORT, ...args], { cwd: REPO, encoding: 'utf8' }).trim().split(/\r?\n/).pop()!;

async function supplierPage(browser: Browser): Promise<Page> {
  const token = support('token', session.tenantDomain, EMAIL);
  const context = await browser.newContext({ baseURL: 'http://127.0.0.1:5173' });
  await context.addInitScript(({ t, domain }) => {
    const info = { id: 6, name: 'Office of Accountant General Delta State', domain, role: 'vendor' };
    const entries: Record<string, string> = {
      authToken: t, tenantDomain: domain, tenantInfo: JSON.stringify(info), tenantPermissions: '[]', activeTenant: info.name,
      user: JSON.stringify({ id: 0, username: 'supplier', email: 'e2e-sp4@example.test', first_name: '', last_name: '', is_superuser: false, groups: [], permissions: [] }),
    };
    for (const [k, v] of Object.entries(entries)) { localStorage.setItem(k, v); sessionStorage.setItem(k, v); }
  }, { t: token, domain: session.tenantDomain });
  return context.newPage();
}

test.describe('Supplier bidding', () => {
  test.setTimeout(420_000);
  test.beforeEach(() => { support('cleanup', session.tenantDomain, CODE); });
  test.afterAll(async () => { test.setTimeout(120_000); support('cleanup', session.tenantDomain, CODE); });

  test('register, bid, replace, see it sealed, open after closing', async ({ authedPage: office, browser }) => {
    const was = support('module', session.tenantDomain, 'egp', 'on');
    try {
      const api = await apiContext();
      await api.patch('/api/v1/procurement/portal-settings/current/', { data: { enabled: true } });
      const v = await api.post('/api/v1/procurement/vendors/', { data: { name: 'E2E Bidder Ltd', code: CODE, email: EMAIL } });
      expect(v.ok(), await v.text()).toBeTruthy();
      const vendor = (await v.json()).id;
      support('activate', session.tenantDomain, CODE);
      await api.post(`/api/v1/procurement/vendors/${vendor}/portal-invite/`, { data: {} });
      await api.post(`/api/v1/procurement/vendors/${vendor}/portal-activate/`, { data: {} });
      support('tender', session.tenantDomain, REF, '5');

      const sup = await supplierPage(browser);
      // the server remembers a module's state for up to a minute, so wait for the tab to appear
      await expect(async () => {
        await sup.goto('/supplier-portal?tab=tenders');
        await expect(sup.getByTestId('sp-tab-tenders')).toBeVisible({ timeout: 5_000 });
      }).toPass({ timeout: 120_000, intervals: [5_000] });

      // not yet a registered bidder: the tender is shown but bidding is closed to this supplier
      await expect(sup.getByTestId(`sp-tender-${REF}`)).toContainText('E2E borehole drilling');
      await expect(sup.getByTestId(`sp-bid-open-${REF}`)).toBeDisabled();
      await sup.getByLabel('What you supply (separate with commas)').fill('civil works, drilling');
      await sup.getByTestId('sp-register-bidder').click();
      await expect(sup.getByTestId('sp-not-eligible')).toContainText('waiting for the procurement office');

      // the office registers it
      const regs = await (await api.get('/api/v1/egp/bidder-registrations/?page_size=100')).json();
      const reg = ((regs.results ?? regs) as { id: number; vendor: number }[]).find((r) => r.vendor === vendor)!;
      expect((await api.patch(`/api/v1/egp/bidder-registrations/${reg.id}/`, { data: { status: 'registered' } })).ok()).toBeTruthy();

      // the supplier seals a bid, then replaces it
      await sup.reload();
      await expect(sup.getByTestId('sp-eligible')).toBeVisible({ timeout: 20_000 });
      await sup.getByTestId(`sp-bid-open-${REF}`).click();
      await sup.getByLabel('Your price (₦)').fill('1250000');
      await sup.getByLabel('Completion time (days)').fill('45');
      await sup.getByLabel('Technical approach (optional)').fill('Own rig and crew');
      await sup.getByTestId('sp-bid-send').click();
      await expect(sup.getByTestId('sp-my-bid-status')).toHaveText('Your bid is sealed');
      const firstReceipt = await sup.getByTestId('sp-receipt').innerText();
      await sup.getByTestId(`sp-bid-open-${REF}`).click();
      await sup.getByLabel('Your price (₦)').fill('1100000');
      await sup.getByLabel('Completion time (days)').fill('40');
      await sup.getByTestId('sp-bid-send').click();
      await expect(async () => { expect(await sup.getByTestId('sp-receipt').innerText()).not.toBe(firstReceipt); }).toPass({ timeout: 15_000 });

      // the office sees who bid, and not what
      await office.goto('/egp');
      await expect(office.getByTestId('bo-panel')).toBeVisible({ timeout: 30_000 });
      await office.getByTestId(`bo-toggle-${REF}`).click();
      const row = office.getByTestId('bo-bid');
      await expect(row).toContainText('E2E Bidder Ltd');
      await expect(row).toContainText('Sealed');
      await expect(row).not.toContainText('1,100,000');
      await expect(office.getByTestId('bo-wait')).toBeVisible();                      // cannot be opened while the tender is open

      // time passes: the closing date is yesterday, and the bids are opened in front of witnesses
      support('closes', session.tenantDomain, REF, '-1');
      await office.reload();
      await office.getByTestId(`bo-toggle-${REF}`).click();
      await office.getByTestId('bo-open').waitFor();
      await expect(office.getByTestId('bo-open')).toBeDisabled();                     // no witnesses listed yet
      await office.getByTestId('bo-attendance').fill('A. Obi\nB. Eze');
      await office.getByTestId('bo-open').click();
      await expect(office.getByTestId('bo-opened')).toBeVisible({ timeout: 20_000 });
      await expect(office.getByTestId('bo-bid')).toContainText('₦1,100,000.00');
      await expect(office.getByTestId('bo-bid')).toContainText('opened');

      // the supplier no longer sees the tender among those open for bids
      await sup.reload();
      await expect(sup.getByTestId('sp-empty')).toContainText('No tenders are open');
      await sup.context().close();
      await api.dispose();
    } finally {
      if (was !== 'on') support('module', session.tenantDomain, 'egp', 'off');
    }
  });
});
