import { describe, expect, it } from 'vitest';
import { buildPositionRows, positionColumns, type Position } from '../positionRows';

const cash = (amount: number) => ({ code: '31100100', name: 'Cash in TSA', amount });
const land = (amount: number) => ({ code: '32100100', name: 'Land', amount });

const THIS_YEAR: Position = {
  assets: { current: { items: [cash(4000)], total: 4000 }, non_current: { items: [land(9000)], total: 9000 }, total: 13000 },
  liabilities: { current: { items: [], total: 0 }, non_current: { items: [], total: 0 }, total: 0 },
  net_assets: { items: [{ code: '43100100', name: 'Accumulated fund', amount: 13000 }], total: 13000 },
  balance_check: { assets: 13000, liabilities_plus_net_assets: 13000, is_balanced: true },
  comparative: {
    assets: { current: { items: [cash(2500)], total: 2500 }, non_current: { items: [land(8000), { code: '32100200', name: 'Buildings', amount: 500 }], total: 8500 }, total: 11000 },
    liabilities: { current: { items: [], total: 0 }, non_current: { items: [], total: 0 }, total: 0 },
    net_assets: { items: [{ code: '43100100', name: 'Accumulated fund', amount: 11000 }], total: 11000 },
  },
};

const row = (rows: ReturnType<typeof buildPositionRows>, label: string) => rows.find((r) => 'label' in r && r.label === label)!;

describe('the statement for one year', () => {
  it('has one figure per line and no comparison', () => {
    const rows = buildPositionRows(THIS_YEAR, false);
    expect(row(rows, 'Cash in TSA')).toMatchObject({ values: [4000] });
    expect(row(rows, 'TOTAL ASSETS')).toMatchObject({ values: [13000] });
    expect(positionColumns(2026, null)).toEqual(['FY 2026']);
  });
});

describe('the statement against another year', () => {
  it('shows this year, the other year and the change between them', () => {
    const rows = buildPositionRows(THIS_YEAR, true);
    expect(row(rows, 'Cash in TSA')).toMatchObject({ values: [4000, 2500, 1500] });
    expect(row(rows, 'Land')).toMatchObject({ values: [9000, 8000, 1000] });
    expect(row(rows, 'TOTAL ASSETS')).toMatchObject({ values: [13000, 11000, 2000] });
    expect(row(rows, 'TOTAL NET ASSETS')).toMatchObject({ values: [13000, 11000, 2000] });
  });

  it('keeps a line that exists in only one of the years, counting the other as nil', () => {
    const rows = buildPositionRows(THIS_YEAR, true);
    expect(row(rows, 'Buildings')).toMatchObject({ values: [0, 500, -500] });
  });

  it('adds up the right-hand side for both years', () => {
    const rows = buildPositionRows(THIS_YEAR, true);
    expect(row(rows, 'TOTAL LIABILITIES AND NET ASSETS')).toMatchObject({ values: [13000, 11000, 2000] });
  });

  it('names the columns after the years and the direction of the change', () => {
    expect(positionColumns(2026, 2022)).toEqual(['FY 2026', 'FY 2022', 'Change (FY 2026 less FY 2022)']);
  });

  it('treats a missing comparison as nil rather than failing', () => {
    const rows = buildPositionRows({ ...THIS_YEAR, comparative: null }, true);
    expect(row(rows, 'Cash in TSA')).toMatchObject({ values: [4000, 0, 4000] });
  });

  it('can set an earlier year against a later one, the change then being negative', () => {
    const early: Position = { ...THIS_YEAR, assets: { ...THIS_YEAR.assets, current: { items: [cash(1000)], total: 1000 } }, comparative: { assets: { current: { items: [cash(4000)], total: 4000 } } } };
    expect(row(buildPositionRows(early, true), 'Cash in TSA')).toMatchObject({ values: [1000, 4000, -3000] });
  });
});

describe('group-account postings', () => {
  const posted = { code: '31000000', name: 'Current Assets', amount: 5000, direct_amount: 200, is_header: true };

  it('hides a header whose balance is only the roll-up of its children', () => {
    const data: Position = { assets: { current: { items: [{ ...posted, direct_amount: 0 }, cash(10)], total: 10 } } };
    expect(buildPositionRows(data, false).some((r) => 'label' in r && r.label === 'Current Assets' && r.kind === 'item')).toBe(false);
  });

  it('shows a header that has money posted straight to it, flagged, at that direct amount', () => {
    const data: Position = { assets: { current: { items: [posted], total: 200 } } };
    const r = buildPositionRows(data, false).find((x) => x.kind === 'item')!;
    expect(r).toMatchObject({ values: [200] });
    expect('flag' in r && r.flag).toBeTruthy();
  });
});
