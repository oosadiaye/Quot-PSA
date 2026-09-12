/**
 * Budget code — capture, import and lookup.
 *
 * The optional per-line reference is only useful if it survives the
 * whole round trip: typed or imported, stored, served, and findable
 * again. These drive the parts a unit test cannot reach — the form
 * actually rendering the column, and the search box actually narrowing
 * the page.
 *
 * Data is created through the API and removed in afterAll, so the suite
 * does not depend on rows someone left behind and does not leave any of
 * its own.
 */
import type { APIRequestContext } from '@playwright/test';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const CODE_SERIES = 'E2E-BL-2026';
const CODE_A = `${CODE_SERIES}-0101`;
const CODE_B = `${CODE_SERIES}-0288`;

/** Rows created here, removed in afterAll. */
const created: number[] = [];

/** Token- and tenant-aware request context, shared by the suite. */
let api: APIRequestContext;

/** Build the CSV the importer accepts, one row per line. */
function importCsv(rows: string[][]): string {
  const header = [
    'fiscal_year', 'mda_code', 'economic_code', 'fund_code',
    'functional_code', 'programme_code', 'amount_approved',
    'description', 'budget_code',
  ].join(',');
  return [header, ...rows.map((r) => r.join(','))].join('\n') + '\n';
}

test.describe('Budget code', () => {
  test.beforeAll(async () => {
    api = await apiContext();
  });

  test('the appropriation form offers a Budget Code per line', async ({ authedPage }) => {
    await authedPage.goto('/budget/appropriations/new');

    const header = authedPage.locator('th', { hasText: 'Budget Code' });
    await expect(header).toBeVisible({ timeout: 15_000 });
    // The caption is what tells an operator it is safe to leave blank.
    await expect(header).toContainText(/optional/i);

    const input = authedPage.locator('input[placeholder="BL-2026-0142"]').first();
    await expect(input).toBeVisible();

    // Rendering is not wiring: prove the value reaches component state.
    await input.fill('BL-2026-0999');
    await expect(input).toHaveValue('BL-2026-0999');
  });

  test('a line table row has as many cells as the header has columns', async ({ authedPage }) => {
    // Adding a column and forgetting a colSpan misaligns every figure
    // underneath it, which reads as corrupt data rather than a layout bug.
    await authedPage.goto('/budget/appropriations/new');
    await expect(authedPage.locator('th', { hasText: 'Budget Code' })).toBeVisible({ timeout: 15_000 });

    const counts = await authedPage.evaluate(() => {
      const table = [...document.querySelectorAll('table')].find((t) =>
        [...(t.tHead?.rows[0]?.cells ?? [])].some((c) => /Economic Code/i.test(c.textContent || '')),
      );
      if (!table) return null;
      return {
        headers: table.tHead!.rows[0].cells.length,
        bodyCells: table.tBodies[0]?.rows[0]?.cells.length ?? -1,
      };
    });

    expect(counts).not.toBeNull();
    expect(counts!.bodyCells).toBe(counts!.headers);
  });

  test('imported codes are stored and searchable', async ({ authedPage }) => {
    // ── Arrange: import three lines, two sharing one code ───────────
    const mda = process.env.E2E_BUDGET_MDA_CODE ?? '010000000000';
    const fund = process.env.E2E_BUDGET_FUND_CODE ?? '01200';
    const func = process.env.E2E_BUDGET_FUNCTIONAL_CODE ?? '70100';
    const prog = process.env.E2E_BUDGET_PROGRAMME_CODE ?? '01010000000000';
    const fy = process.env.E2E_BUDGET_FY ?? '2026';

    const csv = importCsv([
      [fy, mda, '22100300', fund, func, prog, '4500000.00', 'E2E materials', CODE_A],
      [fy, mda, '22100200', fund, func, prog, '2750000.00', 'E2E utilities', CODE_A],
      [fy, mda, '22000000', fund, func, prog, '900000.00', 'E2E ops', CODE_B],
    ]);

    const importRes = await api.post('/api/v1/budget/appropriations/bulk-import/', {
      multipart: {
        file: { name: 'e2e.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) },
      },
    });
    expect(importRes.ok(), await importRes.text()).toBeTruthy();
    const importJson = await importRes.json();
    expect(importJson.errors).toEqual([]);

    // ── Assert: the API can find them by code ──────────────────────
    const listRes = await api.get(
      `/api/v1/budget/appropriations/?budget_code__icontains=${encodeURIComponent(CODE_SERIES)}&page_size=100`,
    );
    expect(listRes.ok()).toBeTruthy();
    const listJson = await listRes.json();
    const rows: Array<{ id: number; budget_code: string }> = listJson.results ?? listJson;
    for (const r of rows) created.push(r.id);

    expect(rows.length).toBeGreaterThanOrEqual(3);
    // Two lines share one code on purpose — the field is not a key.
    expect(rows.filter((r) => r.budget_code === CODE_A).length).toBeGreaterThanOrEqual(2);

    // ── Assert: the UI search narrows to those lines ───────────────
    await authedPage.goto('/budget/appropriations');
    const search = authedPage.getByTestId('budget-code-search');
    await expect(search).toBeVisible({ timeout: 15_000 });

    await search.fill(CODE_SERIES);
    const results = authedPage.getByTestId('budget-code-results');
    await expect(results).toBeVisible({ timeout: 15_000 });
    await expect(results.locator('tbody tr')).toHaveCount(rows.length, { timeout: 15_000 });
    await expect(results).toContainText(CODE_A);
    await expect(results).toContainText(CODE_B);

    // Narrowing to one code must drop the other.
    await search.fill(CODE_B);
    await expect(results.locator('tbody tr')).toHaveCount(1, { timeout: 15_000 });
    await expect(results).toContainText(CODE_B);
    await expect(results).not.toContainText(CODE_A);

    // A code nobody used says so rather than showing everything.
    await search.fill('E2E-NO-SUCH-CODE');
    await expect(results).toContainText(/No budget line carries a code matching/i, {
      timeout: 15_000,
    });

    // Clearing restores the MDA rollup.
    await search.fill('');
    await expect(authedPage.getByTestId('budget-code-results')).toBeHidden({ timeout: 15_000 });
    await expect(authedPage.locator('text=Budget by MDA').first()).toBeVisible();
  });

  test('re-importing a pre-existing CSV does not wipe stored codes', async () => {
    // The template invites editing a saved CSV and re-uploading it to
    // adjust amounts. A file exported before budget_code existed has no
    // such column, and must leave stored codes alone — "column absent"
    // is not "cell blank".
    test.skip(created.length === 0, 'depends on the import test having run');

    const mda = process.env.E2E_BUDGET_MDA_CODE ?? '010000000000';
    const fund = process.env.E2E_BUDGET_FUND_CODE ?? '01200';
    const func = process.env.E2E_BUDGET_FUNCTIONAL_CODE ?? '70100';
    const prog = process.env.E2E_BUDGET_PROGRAMME_CODE ?? '01010000000000';
    const fy = process.env.E2E_BUDGET_FY ?? '2026';

    const legacyHeader = [
      'fiscal_year', 'mda_code', 'economic_code', 'fund_code',
      'functional_code', 'programme_code', 'amount_approved', 'description',
    ].join(',');
    const legacyCsv =
      `${legacyHeader}\n${fy},${mda},22000000,${fund},${func},${prog},1000000.00,E2E ops amended\n`;

    const res = await api.post('/api/v1/budget/appropriations/bulk-import/', {
      multipart: {
        file: { name: 'legacy.csv', mimeType: 'text/csv', buffer: Buffer.from(legacyCsv) },
      },
    });
    expect(res.ok(), await res.text()).toBeTruthy();
    const json = await res.json();
    expect(json.errors).toEqual([]);
    // Same segment tuple, so this updates rather than creates.
    expect(json.updated).toBeGreaterThanOrEqual(1);

    const check = await api.get(
      `/api/v1/budget/appropriations/?budget_code=${encodeURIComponent(CODE_B)}&page_size=10`,
    );
    const rows = (await check.json()).results ?? [];
    expect(rows.length).toBe(1);
    // The amount moved; the code survived.
    expect(Number(rows[0].amount_approved)).toBe(1000000);
    expect(rows[0].budget_code).toBe(CODE_B);
  });

  test.afterAll(async () => {
    // Remove only what this suite created. bulk-delete carries a
    // DRAFT-only gate, so it physically cannot take out an approved
    // appropriation even if an id were wrong.
    const ids = [...new Set(created)];
    if (ids.length) {
      await api.post('/api/v1/budget/appropriations/bulk-delete/', {
        data: { ids },
      }).catch(() => undefined);
    }
    await api.dispose().catch(() => undefined);
  });
});
