/**
 * Budget Execution Report — Quot PSE
 * Route: /budget/execution-report
 *
 * Shows active appropriations with the full budget lifecycle:
 * Approved → Committed (PO encumbrances) → Expended (paid invoices) → Available.
 *
 * Includes totals, execution-rate bars, and colour-coded variance.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer, TrendingUp } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import { useFiscalYears } from '../../../hooks/useGovForms';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

interface ExecutionRow {
    id: number;
    mda: string;
    account: string;
    fund: string;
    approved: string;
    committed: string;
    expended: string;
    available: string;
    execution_pct: number | string;
}

const fmtNGN = (v: number | string): string => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (Number.isFinite(n) ? n : 0).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

const pct = (v: number | string): number => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return Number.isFinite(n) ? n : 0;
};

/** Traffic-light colour for execution percentage. */
const pctColor = (p: number): string => {
    if (p >= 90) return '#dc2626'; // Over-executed / exhausted — red
    if (p >= 75) return '#f59e0b'; // High utilisation — amber
    if (p >= 40) return '#16a34a'; // On track — green
    return '#3b82f6';              // Under-utilised — blue
};

export default function ExecutionReport() {
    const { data: fiscalYears } = useFiscalYears();
    const [fyId, setFyId] = useState<string>('');

    const { data: rows, isLoading, error } = useQuery<ExecutionRow[]>({
        queryKey: ['budget-execution-report', fyId],
        queryFn: async () => {
            const params: Record<string, string> = {};
            if (fyId) params.fiscal_year = fyId;
            const res = await apiClient.get('/budget/execution-report/', { params });
            return Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        },
        staleTime: 30_000,
        retry: false,
    });

    const totals = useMemo(() => {
        const list = rows ?? [];
        const sum = (key: keyof ExecutionRow) =>
            list.reduce((acc, r) => acc + parseFloat(String(r[key]) || '0'), 0);
        const approved = sum('approved');
        const committed = sum('committed');
        const expended = sum('expended');
        const available = sum('available');
        const overall = approved > 0 ? (expended / approved) * 100 : 0;
        return { approved, committed, expended, available, overall, count: list.length };
    }, [rows]);

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: '24px',
                }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>
                            Budget Execution Report
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            Appropriation lifecycle — Approved → Committed → Expended → Available
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select
                            value={fyId}
                            onChange={e => setFyId(e.target.value)}
                            style={{
                                padding: '8px 12px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', fontSize: '14px',
                            }}
                        >
                            <option value="">All fiscal years</option>
                            {(fiscalYears ?? []).map((fy: { id: number; year?: number }) => (
                                <option key={fy.id} value={fy.id}>FY {fy.year ?? fy.id}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => window.print()}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '8px 16px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', background: '#fff',
                                cursor: 'pointer', fontSize: '14px',
                            }}
                        >
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/budget/execution-report/"
                            params={{ fiscal_year: fyId || undefined }}
                            filename={`execution-report-${fyId || 'all'}.xlsx`}
                        />
                    </div>
                </div>

                {/* Summary cards */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '16px', marginBottom: '24px',
                }}>
                    <div style={{
                        background: '#1e4d8c', borderRadius: '12px', padding: '20px', color: '#fff',
                    }}>
                        <div style={{
                            fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
                            opacity: 0.85, letterSpacing: '0.5px',
                        }}>
                            Approved
                        </div>
                        <div style={{
                            fontSize: '22px', fontWeight: 800, fontFamily: 'monospace',
                            marginTop: '6px',
                        }}>
                            {fmtNGN(totals.approved)}
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.8, marginTop: '4px' }}>
                            {totals.count} appropriation{totals.count === 1 ? '' : 's'}
                        </div>
                    </div>

                    <SummaryCard label="Committed" amount={totals.committed} accent="#f59e0b" />
                    <SummaryCard label="Expended"  amount={totals.expended}  accent="#16a34a" />
                    <SummaryCard label="Available" amount={totals.available} accent="#3b82f6" />

                    <div style={{
                        background: '#fff', borderRadius: '12px', padding: '20px',
                        border: `2px solid ${pctColor(totals.overall)}`,
                    }}>
                        <div style={{
                            fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
                            color: pctColor(totals.overall), letterSpacing: '0.5px',
                            display: 'flex', alignItems: 'center', gap: 6,
                        }}>
                            <TrendingUp size={14} /> Overall Execution
                        </div>
                        <div style={{
                            fontSize: '24px', fontWeight: 800, fontFamily: 'monospace',
                            color: pctColor(totals.overall), marginTop: '6px',
                        }}>
                            {totals.overall.toFixed(1)}%
                        </div>
                    </div>
                </div>

                {/* Table */}
                <div style={{
                    background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1',
                    overflow: 'hidden',
                }}>
                    {isLoading ? (
                        <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                            Loading execution data...
                        </div>
                    ) : error ? (
                        <ReportError error={error} endpoint="/budget/execution-report/" />
                    ) : !rows || rows.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#94a3b8' }}>
                            No active appropriations to display.
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                    {['MDA', 'Economic Code', 'Fund', 'Approved', 'Committed', 'Expended', 'Available', 'Execution'].map((h, i) => (
                                        <th key={h} style={{
                                            padding: '12px 14px',
                                            textAlign: i >= 3 ? 'right' : 'left',
                                            fontSize: '11px', fontWeight: 700, color: '#64748b',
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                        }}>
                                            {h}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map(row => {
                                    const p = pct(row.execution_pct);
                                    const c = pctColor(p);
                                    return (
                                        <tr key={row.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                            <td style={{ padding: '10px 14px', fontSize: '13px' }}>{row.mda}</td>
                                            <td style={{ padding: '10px 14px', fontSize: '13px' }}>{row.account}</td>
                                            <td style={{
                                                padding: '10px 14px', fontSize: '13px', color: '#64748b',
                                            }}>
                                                {row.fund}
                                            </td>
                                            <td style={{
                                                padding: '10px 14px', fontSize: '13px',
                                                textAlign: 'right', fontFamily: 'monospace', fontWeight: 600,
                                            }}>
                                                {fmtNGN(row.approved)}
                                            </td>
                                            <td style={{
                                                padding: '10px 14px', fontSize: '13px',
                                                textAlign: 'right', fontFamily: 'monospace', color: '#f59e0b',
                                            }}>
                                                {fmtNGN(row.committed)}
                                            </td>
                                            <td style={{
                                                padding: '10px 14px', fontSize: '13px',
                                                textAlign: 'right', fontFamily: 'monospace', color: '#16a34a',
                                            }}>
                                                {fmtNGN(row.expended)}
                                            </td>
                                            <td style={{
                                                padding: '10px 14px', fontSize: '13px',
                                                textAlign: 'right', fontFamily: 'monospace',
                                                color: parseFloat(row.available) < 0 ? '#dc2626' : '#1e293b',
                                                fontWeight: 600,
                                            }}>
                                                {fmtNGN(row.available)}
                                            </td>
                                            <td style={{
                                                padding: '10px 14px', minWidth: 140,
                                            }}>
                                                <div style={{
                                                    display: 'flex', alignItems: 'center', gap: 8,
                                                }}>
                                                    <div style={{
                                                        flex: 1, height: 6, borderRadius: 3,
                                                        background: '#eef2f7', overflow: 'hidden',
                                                    }}>
                                                        <div style={{
                                                            width: `${Math.min(100, Math.max(0, p))}%`,
                                                            height: '100%', background: c,
                                                            transition: 'width 150ms',
                                                        }} />
                                                    </div>
                                                    <span style={{
                                                        fontSize: 12, fontWeight: 700, color: c,
                                                        fontFamily: 'monospace', minWidth: 46,
                                                        textAlign: 'right',
                                                    }}>
                                                        {p.toFixed(1)}%
                                                    </span>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                            <tfoot>
                                <tr style={{ background: '#f0f4f8', borderTop: '2px solid #1e293b' }}>
                                    <td colSpan={3} style={{
                                        padding: '12px 14px', fontWeight: 800, fontSize: '14px',
                                    }}>
                                        TOTAL
                                    </td>
                                    <td style={{
                                        padding: '12px 14px', textAlign: 'right',
                                        fontWeight: 800, fontFamily: 'monospace',
                                    }}>
                                        {fmtNGN(totals.approved)}
                                    </td>
                                    <td style={{
                                        padding: '12px 14px', textAlign: 'right',
                                        fontWeight: 800, fontFamily: 'monospace', color: '#f59e0b',
                                    }}>
                                        {fmtNGN(totals.committed)}
                                    </td>
                                    <td style={{
                                        padding: '12px 14px', textAlign: 'right',
                                        fontWeight: 800, fontFamily: 'monospace', color: '#16a34a',
                                    }}>
                                        {fmtNGN(totals.expended)}
                                    </td>
                                    <td style={{
                                        padding: '12px 14px', textAlign: 'right',
                                        fontWeight: 800, fontFamily: 'monospace',
                                    }}>
                                        {fmtNGN(totals.available)}
                                    </td>
                                    <td style={{
                                        padding: '12px 14px', textAlign: 'right',
                                        fontWeight: 800, fontFamily: 'monospace',
                                        color: pctColor(totals.overall),
                                    }}>
                                        {totals.overall.toFixed(1)}%
                                    </td>
                                </tr>
                            </tfoot>
                        </table>
                    )}
                </div>

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: '#94a3b8', fontSize: '11px',
                }}>
                    Quot PSE IFMIS — Budget Execution (IPSAS 24 Disclosure)
                </div>
            </main>
        </div>
    );
}

interface SummaryCardProps {
    label: string;
    amount: number;
    accent: string;
}

function SummaryCard({ label, amount, accent }: SummaryCardProps) {
    return (
        <div style={{
            background: '#fff', borderRadius: '12px', padding: '20px',
            border: `1px solid ${accent}33`,
        }}>
            <div style={{
                fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
                color: accent, letterSpacing: '0.5px',
            }}>
                {label}
            </div>
            <div style={{
                fontSize: '22px', fontWeight: 800, fontFamily: 'monospace',
                color: '#1e293b', marginTop: '6px',
            }}>
                {fmtNGN(amount)}
            </div>
        </div>
    );
}
