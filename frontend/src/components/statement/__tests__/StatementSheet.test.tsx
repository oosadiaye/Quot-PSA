import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import StatementSheet, { sheetFigure, type SheetRow } from '../StatementSheet';

describe('sheetFigure', () => {
  it('groups thousands, keeps two decimals and brackets a negative', () => {
    expect(sheetFigure(1234567.5)).toBe('1,234,567.50');
    expect(sheetFigure(-1234.5)).toBe('(1,234.50)');
    expect(sheetFigure('0')).toBe('0.00');
  });

  it('leaves nothing blank-looking for a missing figure and does not invent one', () => {
    expect(sheetFigure(null)).toBe('');
    expect(sheetFigure(undefined)).toBe('');
    expect(sheetFigure('')).toBe('');
  });
});

const ROWS: SheetRow[] = [
  { kind: 'section', label: 'Revenue' },
  { kind: 'group', label: 'Tax Revenue' },
  { kind: 'item', code: '11000001', label: 'Personal income tax', values: [1500] },
  { kind: 'item', code: '11000002', label: 'Legacy posting', values: [250], flag: 'Posted to a group account' },
  { kind: 'subtotal', label: 'Total Tax Revenue', values: [1750] },
  { kind: 'total', label: 'TOTAL REVENUE', values: [1750] },
  { kind: 'grand', label: 'SURPLUS / (DEFICIT) FOR THE PERIOD', values: [-400] },
];

describe('StatementSheet', () => {
  it('is a real table with a caption, a heading row and one figure column per year', () => {
    render(<StatementSheet caption="Statement of Financial Performance" valueColumns={['FY 2026', 'FY 2025']} rows={ROWS.map((r) => (r.kind === 'item' || r.kind === 'subtotal' || r.kind === 'total' || r.kind === 'grand' ? { ...r, values: [...r.values, 100] } : r))} />);
    const table = screen.getByRole('table', { name: 'Statement of Financial Performance' });
    const heads = within(table.querySelector('thead') as HTMLElement).getAllByRole('columnheader').map((h) => h.textContent);
    expect(heads).toEqual(['Code', 'Description', 'FY 2026NGN', 'FY 2025NGN']);
  });

  it('shows figures with grouping and brackets for a deficit, and marks it negative', () => {
    render(<StatementSheet caption="S" valueColumns={['FY 2026']} rows={ROWS} />);
    const deficit = screen.getByText('(400.00)');
    expect(deficit.className).toContain('sheet-neg');
    expect(screen.getAllByText('1,750.00').length).toBe(2);                 // the sub-total and the total
  });

  it('puts subtotals, totals and the result in their own styled rows', () => {
    render(<StatementSheet caption="S" valueColumns={['FY 2026']} rows={ROWS} />);
    expect(screen.getByText('Total Tax Revenue').closest('tr')?.className).toBe('sheet-subtotal');
    expect(screen.getByText('TOTAL REVENUE').closest('tr')?.className).toBe('sheet-total');
    expect(screen.getByText(/SURPLUS/).closest('tr')?.className).toBe('sheet-grand');
  });

  it('calls out a line posted to a group account', () => {
    render(<StatementSheet caption="S" valueColumns={['FY 2026']} rows={ROWS} />);
    const row = screen.getByText('Legacy posting').closest('tr')!;
    expect(row.className).toContain('sheet-flagged');
    expect(within(row).getByTitle('Posted to a group account')).toBeTruthy();
  });

  it('drops the code column when no line has a code', () => {
    render(<StatementSheet caption="S" valueColumns={['FY 2026']} rows={[{ kind: 'item', label: 'Cash', values: [10] }]} />);
    expect(screen.queryByRole('columnheader', { name: 'Code' })).toBeNull();
  });

  it('spans section headings across every column', () => {
    render(<StatementSheet caption="S" valueColumns={['FY 2026', 'FY 2025']} rows={ROWS.slice(0, 2)} />);
    expect(screen.getByText('Revenue').closest('th')?.getAttribute('colspan')).toBe('3');
  });
});
