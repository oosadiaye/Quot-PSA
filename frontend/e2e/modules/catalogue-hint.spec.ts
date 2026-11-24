/**
 * The catalogue's slot on a purchase order line: with the module on and a supplier price in force, the line shows it, flags a
 * higher typed price, and offers to use it. Cleans up the supplier, item, catalogue and module state it touched.
 */
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CODE = 'E2E-SP3';
const SKU = 'E2E-HINT';
const REPO = path.resolve(__dirname, '../../..');
const PYTHON = process.env.E2E_PYTHON ?? path.join(REPO, '.venv', 'Scripts', 'python.exe');
const SUPPORT = path.resolve(__dirname, '../fixtures/e2e_support.py');
const session: { tenantDomain: string } = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../.auth/session.json'), 'utf8'));
const support = (...args: string[]) => execFileSync(PYTHON, ['-I', SUPPORT, ...args], { cwd: REPO, encoding: 'utf8' }).trim().split(/\r?\n/).pop()!;

test.describe('Catalogue price on an order line', () => {
  test.setTimeout(300_000);
  test.beforeEach(() => { support('cleanup', session.tenantDomain, CODE); });
  test.afterAll(async () => { test.setTimeout(120_000); support('cleanup', session.tenantDomain, CODE); });

  test('shows the supplier\u2019s catalogue price, flags a higher one, and uses it on request', async ({ authedPage: page }) => {
    const was = support('module', session.tenantDomain, 'catalogue', 'on');
    try {
      const api = await apiContext();
      const v = await api.post('/api/v1/procurement/vendors/', { data: { name: 'E2E Hint Supplies Ltd', code: CODE, email: 'e2e-sp3@example.test' } });
      expect(v.ok(), await v.text()).toBeTruthy();
      const vendor = (await v.json()).id;
      support('activate', session.tenantDomain, CODE);
      const itemId = Number(support('item', session.tenantDomain, SKU, 'E2E Hint Cement'));

      // the supplier has a price in force, entered the way an officer would: a catalogue and a line in it
      await expect(async () => {
        const c = await api.post('/api/v1/catalogue/supplier-catalogues/', { data: { name: 'E2E hint catalogue', supplier: vendor, status: 'active' } });
        expect(c.ok(), await c.text()).toBeTruthy();
        const cat = (await c.json()).id;
        const l = await api.post('/api/v1/catalogue/items/', { data: { catalogue: cat, item: itemId, unit_price: '4500.00' } });
        expect(l.ok(), await l.text()).toBeTruthy();
      }).toPass({ timeout: 120_000, intervals: [5_000] });                       // the server remembers a module's state for up to a minute
      await api.dispose();

      await page.goto('/procurement/orders/new');
      await page.locator('select').filter({ has: page.locator('option', { hasText: 'Select Vendor' }) }).selectOption({ label: 'E2E Hint Supplies Ltd' });
      await page.locator('select').filter({ has: page.locator('option', { hasText: 'E2E-HINT - E2E Hint Cement' }) }).first().selectOption({ label: 'E2E-HINT - E2E Hint Cement' });

      const hint = page.getByTestId('catalogue-hint');
      await expect(hint).toContainText('Catalogue price', { timeout: 60_000 });
      await expect(hint).toContainText('4,500.00');
      const price = page.locator('input[type="number"][step="0.01"]').first();
      await price.fill('5000');
      await expect(hint).toContainText('above it');
      await page.getByTestId('catalogue-use').click();
      await expect(price).toHaveValue('4500.00');
      await expect(page.getByTestId('catalogue-use')).toHaveCount(0);              // already at the catalogue price
    } finally {
      if (was !== 'on') support('module', session.tenantDomain, 'catalogue', 'off');
    }
  });
});
