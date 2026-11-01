/**
 * Importing a register from a CSV, on Budget Preparation: the template download, the checked preview (good rows, bad rows
 * and the reason for each), the import itself, and the lookup of a linked record by name or code. Uses year 2071, far from
 * any real budget, and removes everything it creates.
 */
import * as fs from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';

const YEAR = 2071;
const CEILINGS = '/api/v1/budget-prep/mda-ceilings/';
const SUBMISSIONS = '/api/v1/budget-prep/submissions/';
const LINES = '/api/v1/budget-prep/submission-lines/';
const LINES_MDA = 'E2E Import Lines MDA';
const rowsOf = async (res: { json(): Promise<any> }) => { const b = await res.json(); return (b.results ?? b) as { id: number }[]; };

async function clean() {
  const api = await apiContext();
  for (const row of await rowsOf(await api.get(`${CEILINGS}?fiscal_year=${YEAR}&page_size=200`))) await api.delete(`${CEILINGS}${row.id}/`);
  for (const row of await rowsOf(await api.get(`${SUBMISSIONS}?fiscal_year=${YEAR}&page_size=200`))) await api.delete(`${SUBMISSIONS}${row.id}/`);
  await api.dispose();
}

async function openImport(page: Page, tab: string) {
  await page.goto('/budget-prep');
  await page.getByRole('tab', { name: tab, exact: true }).click();
  await expect(page.getByTestId('reg-count')).not.toHaveText('Loading…', { timeout: 20_000 });
  await page.getByTestId('reg-import').click();
  await expect(page.getByTestId('import-dialog')).toBeVisible();
}

const upload = (page: Page, csv: string) =>
  page.getByTestId('import-file').setInputFiles({ name: 'import.csv', mimeType: 'text/csv', buffer: Buffer.from(csv, 'utf-8') });

test.describe('Import from CSV', () => {
  test.beforeEach(clean);
  test.afterAll(clean);

  test('the template is a real download with the right columns', async ({ authedPage: page }) => {
    await openImport(page, 'MDA Ceilings');
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId('import-template').click()]);
    expect(download.suggestedFilename()).toBe('mda-ceilings-import-template.csv');
    const text = fs.readFileSync((await download.path())!, 'utf-8').replace(/^﻿/, '');
    const [head, example] = text.trim().split(/\r?\n/);
    expect(head).toBe('Fiscal Year *,MDA Name *,Personnel Ceiling,Overhead Ceiling,Capital Ceiling');
    expect(example).toContain('Ministry of Works');
  });

  test('a file is checked row by row, then the good rows are saved', async ({ authedPage: page }) => {
    const problems: string[] = [];
    page.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 500) problems.push(`${r.status()} ${r.url()}`); });
    await openImport(page, 'MDA Ceilings');

    await upload(page, [
      'Fiscal Year *,MDA Name *,Personnel Ceiling,Overhead Ceiling,Capital Ceiling',
      `${YEAR},E2E Import MDA A,"100,000,000",20000000,50000000`,
      `${YEAR},,abc,,`,
      `${YEAR},E2E Import MDA B,30000000,5000000,0`,
    ].join('\r\n'));

    await expect(page.getByTestId('import-summary')).toContainText('2 rows are ready, 1 has a problem');
    const errors = page.getByTestId('import-errors');
    await expect(errors).toContainText('Row 3');
    await expect(errors).toContainText('MDA Name is required.');
    await expect(errors).toContainText('Personnel Ceiling must be a number, not “abc”.');
    await expect(page.getByTestId('import-run')).toHaveText('Import 2 MDA ceilings');

    await page.getByTestId('import-run').click();
    await expect(page.getByTestId('import-done')).toContainText('2 MDA ceilings saved; 1 not saved', { timeout: 30_000 });

    const api = await apiContext();
    const saved = await (await api.get(`${CEILINGS}?fiscal_year=${YEAR}&page_size=50`)).json();
    await api.dispose();
    const names = ((saved.results ?? saved) as { mda_name: string; personnel_ceiling: string }[]).map((r) => `${r.mda_name}:${Number(r.personnel_ceiling)}`).sort();
    expect(names).toEqual(['E2E Import MDA A:100000000', 'E2E Import MDA B:30000000']);

    await page.getByTestId('import-dialog').getByRole('button', { name: 'Close' }).click();
    await page.getByRole('searchbox', { name: /search mda ceilings/i }).fill('E2E Import MDA');
    await expect(page.getByTestId('reg-count')).toContainText('2 records');
    expect(problems).toEqual([]);
  });

  test('a file with a missing required column, or no rows, says so and saves nothing', async ({ authedPage: page }) => {
    await openImport(page, 'MDA Ceilings');
    await upload(page, 'MDA Name\r\nSomewhere');
    await expect(page.getByRole('alert').first()).toContainText('The file has no “Fiscal Year” column.');
    await expect(page.getByTestId('import-run')).toBeDisabled();

    await upload(page, 'Fiscal Year *,MDA Name *\r\n');
    await expect(page.getByRole('alert').first()).toContainText('The file has no rows to import');
  });

  test('a linked record is found by its name or code, and a wrong one is reported', async ({ authedPage: page }) => {
    const api = await apiContext();
    const sub = await api.post(SUBMISSIONS, { data: { fiscal_year: YEAR, mda_name: LINES_MDA } });
    expect(sub.ok(), await sub.text()).toBeTruthy();
    const { id } = await sub.json();
    const accounts = await (await api.get('/api/v1/accounting/accounts/?page_size=1')).json();
    const code = ((accounts.results ?? accounts)[0] as { code: string }).code;
    await api.dispose();

    await openImport(page, 'Submission Lines');
    await upload(page, [
      'Submission *,Line Type *,Economic Code,Description,Proposed Amount',
      `${LINES_MDA},Capital,${code},Borehole rehabilitation,2500000`,
      `No Such Ministry,Overhead,,Stationery,1000`,
      `${LINES_MDA},Overhead,NOT-A-CODE,Stationery,1000`,
    ].join('\r\n'));

    await expect(page.getByTestId('import-summary')).toContainText('1 row is ready, 2 have problems', { timeout: 30_000 });
    await expect(page.getByTestId('import-errors')).toContainText('No submission matches “No Such Ministry”.');
    await expect(page.getByTestId('import-errors')).toContainText('No economic code matches “NOT-A-CODE”.');

    await page.getByTestId('import-run').click();
    await expect(page.getByTestId('import-done')).toContainText('1 submission line saved', { timeout: 30_000 });

    const check = await apiContext();
    const lines = await rowsOf(await check.get(`${LINES}?submission=${id}&page_size=20`));
    await check.dispose();
    expect(lines).toHaveLength(1);
  });
});
