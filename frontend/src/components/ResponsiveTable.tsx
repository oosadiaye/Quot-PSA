/**
 * ResponsiveTable — a single component that renders as:
 *   · a native <table> on desktop/tablet, and
 *   · a list of cards on mobile (xs/sm breakpoints).
 *
 * Callers declare a list of `columns`, marking which ones appear on
 * the mobile card (`mobilePrimary`) and which are hidden behind the
 * expand toggle (`mobileSecondary`).
 *
 * Designed as an *incremental* adoption: existing <table> usages
 * can swap in ResponsiveTable without restructuring their data model.
 *
 * Part of the responsive rollout (docs/RESPONSIVE_PLAN.md, Phase 3).
 */
import { ReactNode, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useIsMobile } from '../design';

export interface Column<Row> {
    /** Column key — any unique string. */
    key: string;
    /** Header label shown in the th cell / mobile label. */
    header: ReactNode;
    /** Optional explicit render. If absent, Row[key] is rendered. */
    render?: (row: Row) => ReactNode;
    /** Appears on the mobile card header (default false). */
    mobilePrimary?: boolean;
    /** Right-align (for amounts / numeric). */
    align?: 'left' | 'right' | 'center';
    /** Fixed/min width on desktop (e.g. '120px'). */
    width?: string;
}

export interface ResponsiveTableProps<Row> {
    data: Row[];
    columns: Column<Row>[];
    keyField: keyof Row;
    /** Row click handler (e.g. open detail drawer). */
    onRowClick?: (row: Row) => void;
    /** Shown when data is an empty array. */
    emptyState?: ReactNode;
    /** Optional aria-label for screen readers. */
    ariaLabel?: string;
    /** Style override for the outer container. */
    style?: React.CSSProperties;
}

function cellValue<Row>(row: Row, col: Column<Row>): ReactNode {
    if (col.render) return col.render(row);
    const raw = (row as any)[col.key];
    if (raw === null || raw === undefined) return '—';
    return String(raw);
}

export function ResponsiveTable<Row>({
    data, columns, keyField, onRowClick, emptyState, ariaLabel, style,
}: ResponsiveTableProps<Row>) {
    const isMobile = useIsMobile();
    const [expandedRows, setExpandedRows] = useState<Set<any>>(new Set());

    if (!data || data.length === 0) {
        return (
            <div style={{
                padding: 32, textAlign: 'center', color: '#64748b', fontSize: 14,
                background: '#f8fafc', borderRadius: 8, border: '1px dashed #cbd5e1',
                ...style,
            }}>
                {emptyState || 'No records found.'}
            </div>
        );
    }

    // ── Mobile: card list ─────────────────────────────────────
    if (isMobile) {
        const primaryCols = columns.filter(c => c.mobilePrimary);
        const secondaryCols = columns.filter(c => !c.mobilePrimary);

        const toggle = (id: any) => {
            setExpandedRows(prev => {
                const next = new Set(prev);
                if (next.has(id)) next.delete(id); else next.add(id);
                return next;
            });
        };

        return (
            <div role="list" aria-label={ariaLabel} style={{ display: 'flex', flexDirection: 'column', gap: 10, ...style }}>
                {data.map(row => {
                    const id = row[keyField];
                    const isExpanded = expandedRows.has(id);
                    return (
                        <div
                            key={String(id)}
                            role="listitem"
                            onClick={() => onRowClick?.(row)}
                            style={{
                                background: '#fff', border: '1px solid rgba(26,35,126,0.10)',
                                borderRadius: 10, padding: '12px 14px',
                                cursor: onRowClick ? 'pointer' : 'default',
                                transition: 'box-shadow 150ms ease',
                            }}
                        >
                            {/* Primary row — first primary col bold, others stacked */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                {primaryCols.map((col, i) => (
                                    <div key={col.key} style={{
                                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                        fontSize: i === 0 ? 15 : 13,
                                        fontWeight: i === 0 ? 700 : 500,
                                        color: i === 0 ? '#0b1320' : '#475569',
                                    }}>
                                        <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                                            {col.header}
                                        </span>
                                        <span style={{ textAlign: 'right' }}>{cellValue(row, col)}</span>
                                    </div>
                                ))}
                            </div>

                            {/* Secondary columns toggle */}
                            {secondaryCols.length > 0 && (
                                <>
                                    <button
                                        type="button"
                                        onClick={e => { e.stopPropagation(); toggle(id); }}
                                        style={{
                                            marginTop: 10, padding: 0, background: 'transparent', border: 'none',
                                            color: '#1a237e', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                                            display: 'flex', alignItems: 'center', gap: 4,
                                        }}
                                    >
                                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                        {isExpanded ? 'Hide details' : `Show ${secondaryCols.length} more`}
                                    </button>

                                    {isExpanded && (
                                        <div style={{
                                            marginTop: 8, paddingTop: 10, borderTop: '1px solid #eef2f7',
                                            display: 'grid', gridTemplateColumns: '1fr', gap: 6,
                                        }}>
                                            {secondaryCols.map(col => (
                                                <div key={col.key} style={{
                                                    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12,
                                                    fontSize: 13, color: '#475569',
                                                }}>
                                                    <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.3px' }}>
                                                        {col.header}
                                                    </span>
                                                    <span style={{ textAlign: 'right', color: '#0b1320', fontWeight: 500 }}>
                                                        {cellValue(row, col)}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    );
                })}
            </div>
        );
    }

    // ── Desktop / tablet: native table with horizontal scroll ──
    return (
        <div className="scroll-x" style={{ width: '100%', ...style }}>
            <table
                aria-label={ariaLabel}
                style={{
                    width: '100%', borderCollapse: 'collapse',
                    fontSize: 14, background: '#fff',
                }}
            >
                <thead>
                    <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                        {columns.map(col => (
                            <th
                                key={col.key}
                                style={{
                                    padding: '10px 12px',
                                    textAlign: col.align || 'left',
                                    fontSize: 11, fontWeight: 700, color: '#64748b',
                                    textTransform: 'uppercase', letterSpacing: '0.5px',
                                    width: col.width,
                                    whiteSpace: 'nowrap',
                                }}
                            >
                                {col.header}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {data.map(row => (
                        <tr
                            key={String(row[keyField])}
                            onClick={() => onRowClick?.(row)}
                            style={{
                                borderBottom: '1px solid #eef2f7',
                                cursor: onRowClick ? 'pointer' : 'default',
                                transition: 'background 120ms ease',
                            }}
                            onMouseEnter={e => { if (onRowClick) e.currentTarget.style.background = '#f8fafc'; }}
                            onMouseLeave={e => { e.currentTarget.style.background = ''; }}
                        >
                            {columns.map(col => (
                                <td
                                    key={col.key}
                                    style={{
                                        padding: '12px 12px',
                                        textAlign: col.align || 'left',
                                        color: '#0b1320',
                                        verticalAlign: 'middle',
                                    }}
                                >
                                    {cellValue(row, col)}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default ResponsiveTable;
