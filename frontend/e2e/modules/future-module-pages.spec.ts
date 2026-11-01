/**
 * The registers and forms shared by the 15 future modules.
 *
 * Every module renders through one register page and one form, driven by its own config. This walks them all, and takes
 * its expectations (tabs, fields, required fields, linked records) from those same configs, so the checks cannot drift
 * from what the app is told to show. It opens forms and checks validation but never submits an empty form, so it creates
 * nothing; the one create / edit / delete round trip cleans up after itself.
 *
 * A module the tenant has switched off is expected to show the "Module Disabled" page, not a broken register.
 */
import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';
import { plainName, singularLabel } from '../../src/features/_base/labels';
import type { EntityConfig, EntityField, ModuleConfig } from '../../src/features/_base/types';
import { moduleConfig as budgetPrep } from '../../src/features/budget-prep/config';
import { moduleConfig as cashPlanning } from '../../src/features/cash-planning/config';
import { moduleConfig as catalogue } from '../../src/features/catalogue/config';
import { moduleConfig as debt } from '../../src/features/debt/config';
import { moduleConfig as disclosure } from '../../src/features/disclosure/config';
import { moduleConfig as egp } from '../../src/features/egp/config';
import { moduleConfig as fleet } from '../../src/features/fleet/config';
import { moduleConfig as integrations } from '../../src/features/integrations/config';
import { moduleConfig as internalAudit } from '../../src/features/internal-audit/config';
import { moduleConfig as legal } from '../../src/features/legal/config';
import { moduleConfig as personnelBudget } from '../../src/features/personnel-budget/config';
import { moduleConfig as results } from '../../src/features/results/config';
import { moduleConfig as revenueAdmin } from '../../src/features/revenue-admin/config';
import { moduleConfig as staffAdvances } from '../../src/features/staff-advances/config';
import { moduleConfig as transparency } from '../../src/features/transparency/config';

const MODULES: ModuleConfig[] = [
  budgetPrep, cashPlanning, catalogue, debt, disclosure, egp, fleet, integrations, internalAudit, legal,
  personnelBudget, results, revenueAdmin, staffAdvances, transparency,
];

const PHONE = { width: 390, height: 844 };
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
/** A field's label as the page prints it: the name, then the visual required marker when there is one. */
const labelled = (label: string) => new RegExp('^' + escapeRe(label) + '\\s*\\*?$');

/** Server errors and uncaught exceptions seen while a test runs: the things a user would experience as "broken". */
function watch(page: Page): string[] {
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`uncaught: ${e.message}`));
  page.on('response', (r) => {
    if (r.url().includes('/api/v1/') && r.status() >= 500) problems.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`);
  });
  return problems;
}

type Outcome = 'register' | 'disabled';

/** Open a module and report whether its register or the "Module Disabled" page appeared. */
async function openModule(page: Page, m: ModuleConfig): Promise<Outcome> {
  // The app first draws the page, then learns which modules are on and may swap it for the disabled page: wait for that answer.
  const modulesKnown = page.waitForResponse((r) => r.url().includes('/tenants/enabled-modules/'), { timeout: 20_000 }).catch(() => null);
  await page.goto(m.basePath);
  // A real tab, not just a tab strip: the module check settles after the shell first appears, and the disabled page must win a tie.
  const register = page.getByRole('tab').first();
  const disabled = page.getByText(/Module Disabled/);
  await expect(register.or(disabled).first()).toBeVisible({ timeout: 30_000 });
  await modulesKnown;
  await page.waitForTimeout(300);                    // let the page swap itself for the disabled one
  return (await disabled.count()) > 0 ? 'disabled' : 'register';
}

const tab = (page: Page, e: EntityConfig) => page.getByRole('tab', { name: e.label, exact: true });
const mustFill = (f: EntityField) => !f.hideInForm && !f.readOnly && !!f.required && f.type !== 'boolean' && f.type !== 'object';
const shown = (e: EntityConfig) => e.fields.filter((f) => !f.hideInForm);

async function openNewForm(page: Page, e: EntityConfig) {
  await tab(page, e).click();
  await expect(page.getByTestId('reg-count')).not.toHaveText('Loading…', { timeout: 20_000 });
  await page.getByRole('button', { name: `New ${singularLabel(e.label, e.singular)}` }).first().click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.locator('.ef-field').first()).toBeVisible({ timeout: 15_000 });
  return dialog;
}

for (const m of MODULES) {
  test.describe(m.label, () => {
    test('register: tabs, header, count and a clear empty or populated state', async ({ authedPage: page }) => {
      const problems = watch(page);
      if ((await openModule(page, m)) === 'disabled') {
        await expect(page.getByText(/Module Disabled/)).toBeVisible();
        test.info().annotations.push({ type: 'module', description: 'switched off for this tenant; disabled page shown' });
        return;
      }
      const tabs = page.getByRole('tab');
      await expect(tabs).toHaveCount(m.entities.length);
      expect(await tabs.allInnerTexts()).toEqual(m.entities.map((e) => e.label));

      for (const e of m.entities) {
        await tab(page, e).click();
        await expect(tab(page, e)).toHaveAttribute('aria-selected', 'true');
        if (e.panel) { await expect(page.getByTestId('mtef-panel')).toBeVisible(); continue; }   // a screen of its own, covered by mtef.spec.ts
        await expect(page.locator('.reg-title')).toHaveText(e.label);
        await expect(page.getByTestId('reg-count')).toHaveText(/^\d[\d,]* records?$/, { timeout: 20_000 });
        if (!e.readOnly) await expect(page.getByRole('button', { name: `New ${singularLabel(e.label, e.singular)}` }).first()).toBeVisible();
        else await expect(page.getByRole('button', { name: `New ${singularLabel(e.label, e.singular)}` })).toHaveCount(0);
        // exactly one of: an explicit empty state, or the table with its pager
        const empty = page.getByTestId('reg-empty');
        if (await empty.count()) await expect(empty).toContainText(/yet|Nothing matches/);
        else await expect(page.getByTestId('reg-range')).toHaveText(/^Showing [\d,]+–[\d,]+ of [\d,]+$/);
      }
      expect(problems).toEqual([]);
    });

    for (const e of m.entities.filter((x) => !x.panel && !x.readOnly)) {
      test(`form: ${e.label} opens well-formed, validates, and cancels`, async ({ authedPage: page }) => {
        const problems = watch(page);
        if ((await openModule(page, m)) === 'disabled') { test.skip(true, 'module switched off for this tenant'); return; }
        const dialog = await openNewForm(page, e);
        const single = singularLabel(e.label, e.singular);

        await expect(dialog).toContainText(`New ${plainName(single)}`);
        await expect(dialog.getByRole('button', { name: `Create ${plainName(single)}` })).toBeVisible();
        await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeVisible();

        // every field a person is meant to fill is reachable by its label (secondary ones sit under "Additional information")
        const more = dialog.getByRole('button', { name: /additional information/i });
        if (await more.count()) await more.click();
        for (const f of shown(e)) {
          if (f.type === 'object') continue;
          await expect(dialog.getByLabel(labelled(f.label)).first(), `field "${f.label}"`).toBeVisible();
        }

        // choice fields offer every option the config declares
        for (const f of shown(e).filter((x) => x.type === 'select' && x.options)) {
          const options = await dialog.getByLabel(labelled(f.label)).first().locator('option').allInnerTexts();
          expect(options, `options of "${f.label}"`).toEqual(['Select…', ...Object.values(f.options!)]);
        }

        // a linked record is a lookup (or, when its target is unknown, an ID box that says so) and opening it does not error
        for (const f of shown(e).filter((x) => x.reference && ['integer', 'number', 'decimal'].includes(x.type))) {
          const field = dialog.locator('.ef-field').filter({ has: page.locator('label', { hasText: new RegExp(`^${escapeRe(f.label)}\\s*\\*?$`) }) });
          const lookup = field.locator('.ef-ref input');
          const fallback = field.getByText('Enter the ID of the linked record.');
          await expect(lookup.or(fallback).first(), `"${f.label}" settles into a lookup or an ID box`).toBeVisible({ timeout: 15_000 });
          if (await lookup.count()) {
            await lookup.first().click();
            await page.waitForTimeout(400);
            await dialog.locator('.ef-section-title').first().click();      // click away; Escape would close the modal itself
            await expect(dialog).toBeVisible();
          }
        }

        // pressing Create on an empty form names every required field and does not save (skipped when nothing is required,
        // because that would create a blank record)
        const required = shown(e).filter(mustFill);
        if (required.length > 0) {
          await dialog.getByRole('button', { name: `Create ${plainName(single)}` }).click();
          await expect(dialog.getByTestId('ef-error')).toContainText(`${required.length} field${required.length === 1 ? ' needs' : 's need'} attention`);
          await expect(dialog.locator('.ef-error')).toHaveCount(required.length);
          await expect(dialog.locator('[aria-invalid="true"]').first()).toBeVisible();
        }

        await dialog.getByRole('button', { name: 'Cancel' }).click();
        await expect(page.getByRole('dialog')).toHaveCount(0);
        expect(problems).toEqual([]);
      });
    }

    test('phone width: no sideways scrolling, the form fills the screen and its actions stay reachable', async ({ authedPage: page }) => {
      await page.setViewportSize(PHONE);
      if ((await openModule(page, m)) === 'disabled') { test.skip(true, 'module switched off for this tenant'); return; }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

      const dialog = await openNewForm(page, m.entities[0]);
      // the modal zooms in, so poll until it has settled; it leaves a small margin, hence the allowance
      await expect.poll(async () => (await dialog.boundingBox())?.width ?? 0, { timeout: 5_000 }).toBeGreaterThan(PHONE.width - 30);
      await expect.poll(async () => (await dialog.boundingBox())?.width ?? 0).toBeLessThanOrEqual(PHONE.width);
      const create = dialog.getByRole('button', { name: /^Create / });
      await expect(create).toBeInViewport();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    });
  });
}

test.describe('create, edit and delete through the redesigned screens', () => {
  const NAME = 'E2E Redesign Check';
  const submissions = budgetPrep.entities.find((e) => e.key === 'budgetSubmission')!;

  test.afterAll(async () => {
    const api = await apiContext();
    const res = await api.get(`/api/v1/budget-prep/submissions/?search=${encodeURIComponent(NAME)}`);
    if (res.ok()) {
      const body = await res.json();
      for (const row of body.results ?? body) await api.delete(`/api/v1/budget-prep/submissions/${row.id}/`);
    }
    await api.dispose();
  });

  test('a record can be created, found, edited and deleted', async ({ authedPage: page }) => {
    const problems = watch(page);
    if ((await openModule(page, budgetPrep)) === 'disabled') { test.skip(true, 'budget_prep switched off for this tenant'); return; }

    // create
    const form = await openNewForm(page, submissions);
    await form.getByLabel(labelled('Fiscal Year')).fill('2031');
    await form.getByLabel(labelled('MDA Name')).fill(NAME);
    await form.getByRole('button', { name: 'Create budget submission' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0, { timeout: 15_000 });

    // find it by search, and see the count honour the search
    await page.getByRole('searchbox', { name: /search budget submissions/i }).fill(NAME);
    const row = page.getByRole('row').filter({ hasText: NAME });
    await expect(row).toHaveCount(1);
    await expect(page.getByTestId('reg-count')).toContainText(`matching “${NAME}”`);
    await expect(row).toContainText('Draft');                                    // the stage is shown by its label, not the raw value

    // edit: the form names the record, and the change is saved
    await row.getByRole('button', { name: 'Edit budget submission' }).click();
    const edit = page.getByRole('dialog');
    await expect(edit.getByTestId('ef-record')).toContainText(NAME);
    await edit.getByLabel(labelled('Notes')).fill('Edited by the end-to-end test');
    await edit.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0, { timeout: 15_000 });

    // delete, with confirmation
    await row.getByRole('button', { name: 'Delete budget submission' }).click();
    await page.getByRole('dialog').filter({ hasText: /Delete this budget submission/ }).getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByTestId('reg-empty')).toContainText('Nothing matches that search', { timeout: 15_000 });
    expect(problems).toEqual([]);
  });
});
