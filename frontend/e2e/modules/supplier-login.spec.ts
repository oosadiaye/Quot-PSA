/**
 * A supplier's own way in: the emailed link to choose a password, then the real login screen, landing in the supplier
 * portal and nowhere else, then signing out. (supplier-portal.spec.ts injects a session instead, to test the portal itself.)
 */
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';
import { apiContext } from '../fixtures/api';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CODE = 'E2E-SP2';
const EMAIL = 'e2e-sp2@example.test';
const PASSWORD = 'Supplier-Test-2026!';
const REPO = path.resolve(__dirname, '../../..');
const PYTHON = process.env.E2E_PYTHON ?? path.join(REPO, '.venv', 'Scripts', 'python.exe');
const SUPPORT = path.resolve(__dirname, '../fixtures/e2e_support.py');
const session: { tenantDomain: string } = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../.auth/session.json'), 'utf8'));
const support = (...args: string[]) => execFileSync(PYTHON, ['-I', SUPPORT, ...args], { cwd: REPO, encoding: 'utf8' }).trim().split(/\r?\n/).pop()!;

test.use({ storageState: { cookies: [], origins: [] } });       // nobody is signed in

test.describe('Supplier login', () => {
  test.setTimeout(240_000);
  test.beforeEach(() => { support('cleanup', session.tenantDomain, CODE); });
  test.afterAll(async () => { test.setTimeout(120_000); support('cleanup', session.tenantDomain, CODE); });

  test('a supplier chooses a password from the emailed link, signs in, lands in the portal, and signs out', async ({ page }) => {
    const api = await apiContext();
    await api.patch('/api/v1/procurement/portal-settings/current/', { data: { enabled: true } });
    const v = await api.post('/api/v1/procurement/vendors/', { data: { name: 'E2E Login Supplies Ltd', code: CODE, email: EMAIL } });
    expect(v.ok(), await v.text()).toBeTruthy();
    const { id } = await v.json();
    support('activate', session.tenantDomain, CODE);
    expect((await api.post(`/api/v1/procurement/vendors/${id}/portal-invite/`, { data: {} })).ok()).toBeTruthy();
    expect((await api.post(`/api/v1/procurement/vendors/${id}/portal-activate/`, { data: {} })).ok()).toBeTruthy();
    await api.dispose();

    // the emailed link: choose a password
    const [uid, token] = support('reset-link', session.tenantDomain, EMAIL).split(' ');
    await page.goto(`/reset-password?uid=${uid}&token=${token}`);
    await page.getByLabel(/^New Password/).fill(PASSWORD);
    await page.getByLabel(/^Confirm New Password/).fill(PASSWORD);
    await page.getByRole('button', { name: /reset|set|save|change/i }).first().click();
    await expect(page.getByText(/successfully|has been reset|now sign in|log in/i).first()).toBeVisible({ timeout: 20_000 });

    // the real login screen
    await page.goto('/login');
    await page.getByLabel(/^Username or Email/).fill(EMAIL);
    await page.getByLabel(/^Password/).fill(PASSWORD);
    await page.getByRole('button', { name: /sign in|log in/i }).first().click();
    await expect(page).toHaveURL(/\/supplier-portal/, { timeout: 40_000 });
    await expect(page.getByTestId('sp-name')).toHaveText('E2E Login Supplies Ltd', { timeout: 30_000 });

    // a supplier who goes looking elsewhere in the app finds nothing there
    const refused = await page.evaluate(async () => {
      const base = 'http://localhost:8032/api/v1';
      const r = await fetch(`${base}/procurement/vendors/`, {
        headers: { Authorization: `Token ${sessionStorage.getItem('authToken') ?? localStorage.getItem('authToken')}`, 'X-Tenant-Domain': sessionStorage.getItem('tenantDomain') ?? localStorage.getItem('tenantDomain') ?? '' },
      });
      return r.status;
    });
    expect(refused).toBe(403);

    // signing out ends the session
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });
    await page.goto('/supplier-portal');
    await expect(page).toHaveURL(/\/login/);
  });
});
