/**
 * Custom dimensions: a tenant defines a Zone and a Ward under it, the journal form offers them, a line saved with a
 * ward carries it, the server refuses a ward under the wrong zone, and the ward report answers - all through the real
 * screens, with the stored tags as the judge. Each run uses its own codes: the e2e tenant is disposable.
 */
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const stamp = `${Date.now()}`.slice(-7);
const ZONE = { name: `Zone ${stamp}`, code: `zone-${stamp}` };
const WARD = { name: `Ward ${stamp}`, code: `ward-${stamp}` };

test.describe.configure({ mode: 'serial' });

// Each run defines its own Zone and Ward; switch them off afterwards so the tenant's forms do not collect them.
test.afterAll(async () => {
  const api = await apiContext();
  const types = (await (await api.get('/api/v1/dimensions/types/', { params: { page_size: 200 } })).json()).results as Array<{ id: number; code: string }>;
  for (const t of types.filter((x) => [ZONE.code, WARD.code].includes(x.code))) {
    await api.patch(`/api/v1/dimensions/types/${t.id}/`, { data: { is_active: false } });
  }
});

test.describe('Custom dimensions', () => {
  test('an admin defines a Zone, a Ward under it and their values, on the settings screen', async ({ authedPage: page }) => {
    await page.goto('/settings/dimensions');
    await expect(page.getByTestId('dimension-settings')).toBeVisible({ timeout: 30_000 });

    for (const def of [ZONE, WARD]) {
      await page.getByTestId('dim-new').click();
      const dialog = page.getByRole('dialog');
      await dialog.getByTestId('dim-name').fill(def.name);
      await dialog.getByTestId('dim-code').fill(def.code);
      if (def === WARD) {
        await dialog.getByLabel('Sits under (optional)').fill(ZONE.name);
        await page.locator('.ant-select-dropdown:visible').getByText(ZONE.name, { exact: true }).click();
      }
      await dialog.getByRole('button', { name: 'Save' }).click();
      await expect(page.getByTestId(`dim-row-${def.code}`)).toBeVisible({ timeout: 15_000 });
    }

    // Two zones, then a ward under the first.
    await page.getByTestId(`dim-row-${ZONE.code}`).locator('xpath=ancestor::tr').getByRole('button', { name: /expand row/i }).click();
    const zonePanel = page.getByTestId(`dim-values-${ZONE.code}`);
    for (const [code, name] of [['Z1', 'North'], ['Z2', 'South']]) {
      await zonePanel.getByTestId('dim-value-code').fill(code);
      await zonePanel.getByTestId('dim-value-name').fill(name);
      await zonePanel.getByTestId('dim-value-add').click();
      await expect(zonePanel.getByText(name, { exact: true })).toBeVisible({ timeout: 15_000 });
    }
    await page.getByTestId(`dim-row-${WARD.code}`).locator('xpath=ancestor::tr').getByRole('button', { name: /expand row/i }).click();
    const wardPanel = page.getByTestId(`dim-values-${WARD.code}`);
    await wardPanel.getByTestId('dim-value-code').fill('W1');
    await wardPanel.getByTestId('dim-value-name').fill('Ward One');
    await wardPanel.getByLabel(ZONE.name).click();
    await page.locator('.ant-select-dropdown:visible').getByText('Z1 — North').click();
    await wardPanel.getByTestId('dim-value-add').click();
    await expect(wardPanel.getByText('Ward One')).toBeVisible({ timeout: 15_000 });

    const api = await apiContext();
    const types = (await (await api.get('/api/v1/dimensions/types/', { params: { page_size: 200 } })).json()).results as Array<{ code: string; parent_type_code: string | null }>;
    expect(types.find((t) => t.code === WARD.code)?.parent_type_code).toBe(ZONE.code);
  });

  test('the server refuses a ward under the wrong zone and a value on a record it is not switched on for', async () => {
    const api = await apiContext();
    // A ward value under Z2 would be a different ward; tag a throwaway record id (tags only need a record to point at).
    const wardValues = (await (await api.get('/api/v1/dimensions/values/', { params: { page_size: 500 } })).json()).results as Array<{ code: string; dimension_type_code: string }>;
    expect(wardValues.some((v) => v.dimension_type_code === WARD.code && v.code === 'W1')).toBe(true);

    const wrongZone = await api.post('/api/v1/dimensions/tags/set/', {
      data: { record_type: 'journal_line', record_id: 987654321, tags: { [ZONE.code]: 'Z2', [WARD.code]: 'W1' } } });
    expect(wrongZone.status()).toBe(409);
    expect((await wrongZone.json()).error).toMatch(/not in/);

    const notOn = await api.post('/api/v1/dimensions/tags/set/', {
      data: { record_type: 'purchase_order', record_id: 1, tags: { [ZONE.code]: 'Z1' } } });
    expect(notOn.status()).toBe(409);
    expect((await notOn.json()).error).toMatch(/not switched on/);
  });

  test('a journal saved with a zone and ward tags every line, and the ward report lists the ward', async ({ authedPage: page }) => {
    const reference = `DIM-${stamp}`;
    await page.goto('/accounting/new');
    await expect(page.getByTestId('journal-dimension-defaults')).toBeVisible({ timeout: 30_000 });
    await page.getByPlaceholder('e.g. JV-2024-001').fill(reference);
    await page.getByPlaceholder('Purpose of this entry').fill('Ward project cost');
    for (const label of ['MDA', 'Fund', 'Function', 'Program', 'Geo']) {
      await page.getByPlaceholder(new RegExp(`Search ${label}`)).click();
      await page.getByRole('option').first().click();
    }

    // The defaults for every line: zone Z1, then a ward that only offers Z1's wards.
    const defaults = page.getByTestId('journal-dimension-defaults');
    await defaults.getByLabel(ZONE.name).click();
    await page.locator('.ant-select-dropdown:visible').getByText('Z1 — North').click();
    await defaults.getByLabel(WARD.name).click();
    await expect(page.locator('.ant-select-dropdown:visible').getByText('W1 — Ward One')).toBeVisible();
    await page.locator('.ant-select-dropdown:visible').getByText('W1 — Ward One').click();

    const rows = page.locator('tbody tr');
    const lines: Array<[string, 'debit' | 'credit']> = [['31009000', 'debit'], ['19001000', 'credit']];
    for (let i = 0; i < lines.length; i += 1) {
      const row = rows.nth(i);
      await row.getByRole('combobox').first().fill(lines[i][0]);
      await page.getByRole('option', { name: new RegExp(lines[i][0]) }).first().click();
      await row.locator('td').nth(lines[i][1] === 'debit' ? 2 : 3).locator('input').first().fill('1250');
      // A line shows the default it inherits.
      await expect(row.getByTitle(/Ward One/).or(row.getByText('W1 — Ward One'))).toBeVisible();
    }
    await page.getByRole('button', { name: 'Save Draft' }).click();
    await expect(page).toHaveURL(/\/accounting(\?|$|\/?$)/, { timeout: 20_000 });

    const api = await apiContext();
    const found = (await (await api.get('/api/v1/accounting/journals/', { params: { search: reference } })).json()).results as Array<{ id: number }>;
    expect(found.length).toBe(1);
    const journal = await (await api.get(`/api/v1/accounting/journals/${found[0].id}/`)).json();
    expect(journal.lines).toHaveLength(2);
    for (const line of journal.lines as Array<{ id: number }>) {
      const tags = await (await api.get('/api/v1/dimensions/tags/', { params: { record_type: 'journal_line', record_id: line.id } })).json();
      expect(tags).toEqual({ [ZONE.code]: 'Z1', [WARD.code]: 'W1' });
    }

    // The ward report lists the ward; a draft is not yet spend, so its total is nil.
    await page.goto(`/accounting/reports/dimension/${WARD.code}`);
    await expect(page.getByTestId('dim-report-row-W1')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('dim-report-total')).toBeVisible();
  });
});
