import './statement-sheet.css';

/**
 * A financial statement laid out like a LibreOffice Calc table: a grid of thin cell borders, a grey heading row, figures
 * right-aligned in tabular numerals with negatives in brackets, shaded sub-total rows and double-underlined totals.
 * Every IPSAS statement uses it, so they read, print and copy into a spreadsheet the same way.
 */
export type SheetRow =
  | { kind: 'section'; label: string }
  | { kind: 'group'; label: string }
  | { kind: 'item'; code?: string; label: string; values: Array<number | string | null | undefined>; flag?: string; indent?: number }
  | { kind: 'subtotal' | 'total' | 'grand'; label: string; values: Array<number | string | null | undefined> }
  | { kind: 'note'; label: string };

interface Props {
  /** Heading above the table (statement title). */
  caption: string;
  /** Names of the figure columns, for example ['FY 2026', 'FY 2025']. */
  valueColumns: string[];
  rows: SheetRow[];
  /** Show a narrow "Code" column. On when any item has a code. */
  codes?: boolean;
  /** What the figures are in, shown in the heading row. */
  unit?: string;
  testId?: string;
}

/** 1,234.50 and (1,234.50) for a negative; a dash for nothing. */
export function sheetFigure(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const text = Math.abs(n).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${text})` : text;
}

const isNegative = (v: number | string | null | undefined) => v !== null && v !== undefined && v !== '' && Number(v) < 0;

export default function StatementSheet({ caption, valueColumns, rows, codes, unit = 'NGN', testId }: Props) {
  const showCodes = codes ?? rows.some((r) => r.kind === 'item' && !!r.code);
  const span = (showCodes ? 2 : 1) + valueColumns.length;

  return (
    <div className="sheet-wrap" data-testid={testId}>
      <table className="sheet" aria-label={caption}>
        <caption className="sheet-caption">{caption}</caption>
        <thead>
          <tr>
            {showCodes && <th scope="col" className="sheet-code">Code</th>}
            <th scope="col" className="sheet-desc">Description</th>
            {valueColumns.map((c) => <th key={c} scope="col" className="sheet-num">{c}<span className="sheet-unit">{unit}</span></th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            if (r.kind === 'section') return <tr key={i} className="sheet-section"><th scope="colgroup" colSpan={span}>{r.label}</th></tr>;
            if (r.kind === 'group') return <tr key={i} className="sheet-group"><th scope="colgroup" colSpan={span}>{r.label}</th></tr>;
            if (r.kind === 'note') return <tr key={i} className="sheet-note"><td colSpan={span}>{r.label}</td></tr>;
            const cls = r.kind === 'item' ? (r.flag ? 'sheet-item sheet-flagged' : 'sheet-item') : `sheet-${r.kind}`;
            return (
              <tr key={i} className={cls}>
                {showCodes && <td className="sheet-code">{r.kind === 'item' ? r.code : ''}</td>}
                <td className="sheet-desc" style={r.kind === 'item' && r.indent ? { paddingLeft: 8 + r.indent * 14 } : undefined}>
                  {r.label}
                  {r.kind === 'item' && r.flag && <span className="sheet-flag" title={r.flag}>group account</span>}
                </td>
                {valueColumns.map((_, c) => (
                  <td key={c} className={`sheet-num${isNegative(r.values[c]) ? ' sheet-neg' : ''}`}>{sheetFigure(r.values[c])}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
