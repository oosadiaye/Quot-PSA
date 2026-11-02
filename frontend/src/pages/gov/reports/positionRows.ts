import { sheetFigure, type SheetRow } from '../../../components/statement/StatementSheet';

export interface Line { code?: string; name: string; amount: number; direct_amount?: number; is_header?: boolean }
export interface Section { items?: Line[]; total?: number }
interface Family { current?: Section; non_current?: Section; unclassified?: Section; total?: number }
interface Net { items?: Line[]; total?: number }

/** The statement as the endpoint returns it, for the year asked for, with the comparison year's under ``comparative``. */
export interface Position {
  assets?: Family;
  liabilities?: Family;
  net_assets?: Net;
  balance_check?: { assets?: number; liabilities_plus_net_assets?: number; is_balanced?: boolean };
  comparative?: Omit<Position, 'comparative' | 'balance_check'> | null;
}

export const GROUP_NOTE = 'Posted directly to a group account. Included so the statement adds up; move these postings to a leaf account.';

const key = (i: Line) => i.code ?? i.name;
const postedToHeader = (i: Line | undefined) => !!i && !!i.is_header && Number(i.direct_amount || 0) !== 0;
const amount = (i: Line | undefined) => (i ? (postedToHeader(i) ? Number(i.direct_amount) : Number(i.amount)) : 0);

/** The figures of one row: this year, and (when comparing) the other year and the change from the other year to this one. */
export const figures = (now: number, then: number, comparing: boolean): number[] => (comparing ? [now, then, now - then] : [now]);

/**
 * A header's ``amount`` is the roll-up of its children, which are listed individually, so showing both would read as double
 * counting and header rows stay hidden. The exception is ``direct_amount``: a balance posted to the header itself, represented
 * by no child line. It is counted in the section total, so it is shown (flagged) to keep the visible lines adding up.
 * With two years, a line appears if it is there in either, and the year that lacks it counts as nil.
 */
export function lines(now: Line[] | undefined, then: Line[] | undefined, comparing: boolean): SheetRow[] {
  const visible = (i: Line) => !i.is_header || Number(i.direct_amount || 0) !== 0;
  const a = (now ?? []).filter(visible);
  const b = (then ?? []).filter(visible);
  const order = [...a.map(key), ...b.map(key).filter((k) => !a.some((x) => key(x) === k))];
  return order.map((k): SheetRow => {
    const x = a.find((i) => key(i) === k);
    const y = b.find((i) => key(i) === k);
    const named = (x ?? y)!;
    return {
      kind: 'item', code: named.code, label: named.name, values: figures(amount(x), amount(y), comparing),
      flag: postedToHeader(x) || postedToHeader(y) ? GROUP_NOTE : undefined,
    };
  });
}

const total = (now: { total?: number } | undefined, then: { total?: number } | undefined, comparing: boolean) =>
  figures(now?.total ?? 0, then?.total ?? 0, comparing);

/** Accounts in the family but outside the statement's named sub-families: shown only when there is something, so a well-coded chart has no extra heading. */
function unclassified(now: Section | undefined, then: Section | undefined, label: string, comparing: boolean): SheetRow[] {
  const nonZero = (sec: Section | undefined) => (sec?.items ?? []).filter((i) => Number(i.amount) !== 0);
  if (nonZero(now).length === 0 && nonZero(then).length === 0) return [];
  return [
    { kind: 'group', label },
    { kind: 'note', label: 'Not yet assigned to a statement heading; give these codes a sub-family so they report in the right place.' },
    ...lines(nonZero(now), nonZero(then), comparing),
    { kind: 'subtotal', label: `Total ${label}`, values: total(now, then, comparing) },
  ];
}

/** Every row of the Statement of Financial Position, for one year or for two with the change between them. */
export function buildPositionRows(data: Position, comparing: boolean): SheetRow[] {
  const c = comparing ? data.comparative ?? undefined : undefined;
  const cmpLiabAndNet = c ? Number(c.liabilities?.total ?? 0) + Number(c.net_assets?.total ?? 0) : 0;
  const balanced = !!data.balance_check?.is_balanced;
  return [
    { kind: 'section', label: 'Assets' },
    { kind: 'group', label: 'Current Assets' }, ...lines(data.assets?.current?.items, c?.assets?.current?.items, comparing),
    { kind: 'subtotal', label: 'Total Current Assets', values: total(data.assets?.current, c?.assets?.current, comparing) },
    { kind: 'group', label: 'Non-Current Assets' }, ...lines(data.assets?.non_current?.items, c?.assets?.non_current?.items, comparing),
    { kind: 'subtotal', label: 'Total Non-Current Assets', values: total(data.assets?.non_current, c?.assets?.non_current, comparing) },
    ...unclassified(data.assets?.unclassified, c?.assets?.unclassified, 'Unclassified Assets', comparing),
    { kind: 'total', label: 'TOTAL ASSETS', values: total(data.assets, c?.assets, comparing) },
    { kind: 'section', label: 'Liabilities' },
    { kind: 'group', label: 'Current Liabilities' }, ...lines(data.liabilities?.current?.items, c?.liabilities?.current?.items, comparing),
    { kind: 'subtotal', label: 'Total Current Liabilities', values: total(data.liabilities?.current, c?.liabilities?.current, comparing) },
    { kind: 'group', label: 'Non-Current Liabilities' }, ...lines(data.liabilities?.non_current?.items, c?.liabilities?.non_current?.items, comparing),
    { kind: 'subtotal', label: 'Total Non-Current Liabilities', values: total(data.liabilities?.non_current, c?.liabilities?.non_current, comparing) },
    ...unclassified(data.liabilities?.unclassified, c?.liabilities?.unclassified, 'Unclassified Liabilities', comparing),
    { kind: 'total', label: 'TOTAL LIABILITIES', values: total(data.liabilities, c?.liabilities, comparing) },
    { kind: 'section', label: 'Net Assets / Equity' }, ...lines(data.net_assets?.items, c?.net_assets?.items, comparing),
    { kind: 'total', label: 'TOTAL NET ASSETS', values: total(data.net_assets, c?.net_assets, comparing) },
    { kind: 'grand', label: 'TOTAL LIABILITIES AND NET ASSETS', values: figures(Number(data.balance_check?.liabilities_plus_net_assets ?? 0), cmpLiabAndNet, comparing) },
    {
      kind: 'note',
      label: balanced
        ? 'The statement balances: total assets equal total liabilities and net assets.'
        : `NOT BALANCED: total assets ${sheetFigure(data.balance_check?.assets)} against liabilities and net assets ${sheetFigure(data.balance_check?.liabilities_plus_net_assets)}.`,
    },
  ];
}

export function positionColumns(fy: number, compareYear: number | null): string[] {
  return compareYear === null ? [`FY ${fy}`] : [`FY ${fy}`, `FY ${compareYear}`, `Change (FY ${fy} less FY ${compareYear})`];
}
