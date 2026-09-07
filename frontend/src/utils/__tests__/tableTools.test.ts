/**
 * tableTools — column classification and totals.
 *
 * These cover the logic that actually shipped a defect: the Journal list
 * totalled its Document No column to -2,348.00 because JV-000118 parsed
 * as -118. A reference column presented as money is the kind of figure
 * that quietly undermines every other figure on the screen, so the
 * classifier gets tests even though the rest of the module is DOM glue.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { initTableTools } from '../tableTools';

/** Build a real table so the module under test sees what a page renders. */
function makeTable(headers: string[], rows: string[][]): HTMLTableElement {
  const table = document.createElement('table');
  const thead = table.createTHead();
  const hr = thead.insertRow();
  headers.forEach((h) => {
    const th = document.createElement('th');
    th.textContent = h;
    hr.appendChild(th);
  });
  const tbody = table.createTBody();
  rows.forEach((cells) => {
    const tr = tbody.insertRow();
    cells.forEach((c) => { tr.insertCell().textContent = c; });
  });
  document.body.appendChild(table);
  return table;
}

/** The enhancer runs off a MutationObserver; give it a tick to attach. */
const settle = () => new Promise((r) => setTimeout(r, 200));

/** Locate a column by its header text rather than by position.
 *
 *  Positional indices were how these tests first broke: adding the
 *  row-number gutter shifted every column by one and three assertions
 *  started reading the wrong cell. A test that names the column it means
 *  survives any decoration added to the left of it. */
function colIndex(table: HTMLTableElement, header: string): number {
  const rows = Array.from(table.tHead!.rows);
  const fieldRow = rows.find((r) => !r.hasAttribute('data-tools-letters'))!;
  return Array.from(fieldRow.cells).findIndex(
    (c) => (c.textContent || '').trim() === header,
  );
}

/** Visible values of a named column, in the order they now appear. */
function columnValues(table: HTMLTableElement, header: string): (string | null)[] {
  const i = colIndex(table, header);
  return Array.from(table.tBodies[0].rows)
    .filter((r) => !r.hasAttribute('data-tools-row'))
    .map((r) => r.cells[i]?.textContent ?? null);
}

/** Click a named column header. */
function sortBy(table: HTMLTableElement, header: string) {
  const fieldRow = Array.from(table.tHead!.rows)
    .find((r) => !r.hasAttribute('data-tools-letters'))!;
  (fieldRow.cells[colIndex(table, header)] as HTMLElement).click();
}

function totalsFor(table: HTMLTableElement): Record<string, string> {
  const foot = table.querySelector('tfoot[data-tools-foot]');
  if (!foot) return {};
  const headers = Array.from(table.tHead!.rows[0].cells).map((c) => c.textContent || '');
  const cells = Array.from((foot as HTMLTableSectionElement).rows[0].cells);
  const out: Record<string, string> = {};
  headers.forEach((h, i) => {
    const text = cells[i]?.textContent?.trim();
    if (text && !text.startsWith('Σ')) out[h] = text;
  });
  return out;
}

describe('tableTools', () => {
  beforeEach(() => {
    document.body.replaceChildren();
    initTableTools();
  });
  afterEach(() => document.body.replaceChildren());

  describe('what counts as a figure', () => {
    it('does not total a document reference column', async () => {
      // The shipped bug: JV-000118 -> -118, summed to -2,348.00.
      const t = makeTable(
        ['Document No', 'Total Debit'],
        [
          ['JV-000118', '1,089,440.86'],
          ['JV-000126', '324,905.57'],
          ['JV-000117', '4,547,726.78'],
        ],
      );
      await settle();
      const totals = totalsFor(t);
      expect(totals['Document No']).toBeUndefined();
      expect(totals['Total Debit']).toBe('5,962,073.21');
    });

    it('does not total an all-digit account code', async () => {
      // An NCoA code parses as a perfectly good number. What separates it
      // from money is the absence of a decimal or thousands separator.
      const t = makeTable(
        ['Code', 'Balance'],
        [
          ['10000000', '0.00'],
          ['11000000', '1,204.40'],
          ['11100100', '86,442.05'],
        ],
      );
      await settle();
      const totals = totalsFor(t);
      expect(totals['Code']).toBeUndefined();
      expect(totals['Balance']).toBe('87,646.45');
    });

    it('does not total a date column', async () => {
      const t = makeTable(
        ['Date', 'Amount'],
        [
          ['01/12/2026', '4,770,750.44'],
          ['02/12/2026', '537,115.85'],
          ['03/12/2026', '400,920.19'],
        ],
      );
      await settle();
      const totals = totalsFor(t);
      expect(totals['Date']).toBeUndefined();
      expect(totals['Amount']).toBe('5,708,786.48');
    });

    it('reads parentheses as negative, per accounting convention', async () => {
      const t = makeTable(
        ['Account', 'Balance'],
        [
          ['Revenue', '1,000.00'],
          ['Travel', '(400.00)'],
          ['Stationery', '(100.00)'],
        ],
      );
      await settle();
      expect(totalsFor(t)['Balance']).toBe('500.00');
    });

    it('ignores the currency symbol and the Dr/Cr suffix', async () => {
      const t = makeTable(
        ['Account', 'Net'],
        [
          ['PAYE', '₦1,500.50 Cr'],
          ['Salaries', '₦2,499.50 Dr'],
        ],
      );
      await settle();
      expect(totalsFor(t)['Net']).toBe('4,000.00');
    });

    it('treats an em dash as no value rather than zero', async () => {
      const t = makeTable(
        ['Account', 'Balance'],
        [['A', '100.00'], ['B', '—'], ['C', '50.00']],
      );
      await settle();
      expect(totalsFor(t)['Balance']).toBe('150.00');
    });
  });

  describe('deference', () => {
    it('leaves a page-authored tfoot alone', async () => {
      // Trial Balance computes its own totals and knows which columns
      // should be summed; we do not.
      const t = makeTable(
        ['Account', 'Debit'],
        [['A', '100.00'], ['B', '50.00']],
      );
      const foot = t.createTFoot();
      const row = foot.insertRow();
      row.insertCell().textContent = 'Page total';
      row.insertCell().textContent = '150.00';
      await settle();
      expect(t.querySelector('tfoot[data-tools-foot]')).toBeNull();
      expect(t.tFoot!.textContent).toContain('Page total');
    });

    it('skips a table whose page owns sorting', async () => {
      const wrap = document.createElement('div');
      wrap.setAttribute('data-no-sort', '');
      document.body.appendChild(wrap);
      const t = makeTable(['Account', 'Amount'], [['A', '1.00'], ['B', '2.00']]);
      wrap.appendChild(t);
      await settle();
      // Ordering is the page's, but the filter and totals still apply.
      expect(t.querySelectorAll('thead th.tt-sortable').length).toBe(0);
      expect(t.querySelector('caption[data-tools-bar]')).not.toBeNull();
      expect(totalsFor(t)['Amount']).toBe('3.00');
    });

    it('skips an opted-out statutory document', async () => {
      const t = makeTable(['Vendor', 'Amount'], [['A', '1.00'], ['B', '2.00']]);
      t.setAttribute('data-plain-table', '');
      await settle();
      expect(t.hasAttribute('data-tools-ready')).toBe(false);
      expect(t.querySelector('caption[data-tools-bar]')).toBeNull();
    });

    it('skips an empty-state table', async () => {
      // "No employees found" is one row; a filter and a Σ 1 rows footer
      // on it reads as a bug.
      const t = makeTable(['Name', 'Grade'], [['No employees found', '']]);
      await settle();
      expect(t.hasAttribute('data-tools-ready')).toBe(false);
    });
  });

  describe('sorting', () => {
    it('orders figures by value, not as strings', async () => {
      const t = makeTable(
        ['Receipt', 'Amount'],
        [
          ['R-1', '4,770,750.44'],
          ['R-2', '537,115.85'],
          ['R-3', '1,169,161.80'],
        ],
      );
      await settle();
      sortBy(t, 'Amount');
      // A lexical sort would give 1,169… 4,770… 537,115 — plausible and wrong.
      expect(columnValues(t, 'Amount'))
        .toEqual(['537,115.85', '1,169,161.80', '4,770,750.44']);
    });

    it('still orders a bare integer column numerically', async () => {
      // Not summable, but must not sort as text: 10 belongs after 9.
      const t = makeTable(
        ['MDA', '# Lines'],
        [['A', '10'], ['B', '9'], ['C', '100']],
      );
      await settle();
      sortBy(t, '# Lines');
      expect(columnValues(t, '# Lines')).toEqual(['9', '10', '100']);
    });

    it('sorts DD/MM/YYYY chronologically', async () => {
      const t = makeTable(
        ['Ref', 'Date'],
        [['A', '01/12/2026'], ['B', '03/01/2026'], ['C', '15/06/2026']],
      );
      await settle();
      sortBy(t, 'Date');
      expect(columnValues(t, 'Date'))
        .toEqual(['03/01/2026', '15/06/2026', '01/12/2026']);
    });
  });

  describe('filtering', () => {
    it('recomputes the total over the visible rows only', async () => {
      const t = makeTable(
        ['Head', 'Amount'],
        [
          ['FAAC VAT Distribution', '4,000.00'],
          ['Capital Gains Tax', '500.00'],
          ['FAAC Statutory Allocation', '3,000.00'],
        ],
      );
      await settle();
      const input = t.querySelector('.tt-filter') as HTMLInputElement;
      input.value = 'FAAC';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      expect(totalsFor(t)['Amount']).toBe('7,000.00');
      expect(t.querySelector('.tt-count')!.textContent).toBe('2 of 3 rows');
    });
  });
});
