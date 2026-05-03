/**
 * Budget Commitment Report — Quot PSE
 * Route: /budget/commitment-report
 *
 * Shows Purchase Order commitments (encumbrances) against appropriations
 * with grand total and per-status breakdown. Used by Internal Audit to
 * reconcile outstanding commitments at period-end.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer, FileText } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

interface CommitmentRow {
    id: number;
    purchase_order: string;
    mda: string;
    mda_code?: string;
    account: string;
    account_code?: string;
    account_name?: string;
    committed_amount: string;
    status: string;
    committed_at: string | null;
    appropriation_balance: string;
}

interface CommitmentResponse {
    items: CommitmentRow[];
    total_committed: string;
    count: number;
}

const STATUS_OPTIONS = ['', 'ACTIVE', 'INVOICED', 'CLOSED', 'CANCELLED'] as const;

const STATUS_COLORS: Record<string, string> = {
    ACTIVE:    '#f59e0b',
    INVOICED:  '#3b82f6',
    CLOSED:    '#16a34a',
    CANCELLED: '#ef4444',
};

const fmtNGN = (v: number | string): string => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (Number.isFinite(n) ? n : 0).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

export default function CommitmentReport() {
    const [statusFilter, setStatusFilter] = useState<string>('');

    const { data, isLoading, error } = useQuery<CommitmentResponse>({
        queryKey: ['budget-commitment-report', statusFilter],
        queryFn: async () => {
            const params: Record<string, string> = {};
            if (statusFilter) params.status = statusFilter;
            const res = await apiClient.get('/budget/commitment-report/', { params });
            return res.data;
        },
        staleTime: 30_000,
        retry: false,
    });

    const rows = data?.items ?? [];

    // Per-status breakdown for the summary strip.
    const byStatus = useMemo(() => {
        const acc: Record<string, { count: number; amount: number }> = {};
        rows.forEach(r => {
            const s = r.status || 'UNKNOWN';
            if (!acc[s]) acc[s] = { count: 0, amount: 0 };
            acc[s].count += 1;
            acc[s].amount += parseFloat(r.committed_amount || '0');
        });
        return acc;
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
                            Budget Commitment Report
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            Purchase Order encumbrances against appropriations (IPSAS 24 disclosure)
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select
                            value={statusFilter}
                            onChange={e => setStatusFilter(e.target.value)}
                            style={{
                                padding: '8px 12px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', fontSize: '14px',
                            }}
                        >
                            {STATUS_OPTIONS.map(s => (
                                <option key={s} value={s}>{s || 'All statuses'}</option>
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
                            endpoint="/budget/commitment-report/"
                            params={{ status: statusFilter || undefined }}
                            filename="commitment-report.xlsx"
                        />
                    </div>
                </div>

                {/* Summary strip */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                    gap: '16px', marginBottom: '24px',
                }}>
                    <div style={{
                        background: '#008751', borderRadius: '12px', padding: '20px', color: '#fff',
                    }}>
                        <div style={{
                            fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
                            opacity: 0.85, letterSpacing: '0.5px',
                        }}>
                            Total Committed
                        </div>
                        <div style={{
                            fontSize: '24px', fontWeight: 800, fontFamily: 'monospace',
                            marginTop: '6px',
                        }}>
                            {fmtNGN(data?.total_committed ?? 0)}
                        </div>
                        <div style={{ fontSize: '12px', marginTop: '4px', opacity: 0.8 }}>
                            {data?.count ?? 0} commitment{(data?.count ?? 0) === 1 ? '' : 's'}
                        </div>
                    </div>

                    {Object.entries(byStatus).map(([st, agg]) => (
                        <div key={st} style={{
                            background: '#fff', borderRadius: '12px', padding: '20px',
                            border: `1px solid ${STATUS_COLORS[st] ?? '#e8ecf1'}33`,
                        }}>
                            <div style={{
                                fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
                                color: STATUS_COLORS[st] ?? '#64748b', letterSpacing: '0.5px',
                            }}>
                                {st}
                            </div>
                            <div style={{
                                fontSize: '20px', fontWeight: 800, fontFamily: 'monospace',
                                color: '#1e293b', marginTop: '6px',
                            }}>
                                {fmtNGN(agg.amount)}
                            </div>
                            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                                {agg.count} PO{agg.count === 1 ? '' : 's'}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Table */}
                <div style={{
                    background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1',
                    overflow: 'hidden',
                }}>
                    {isLoading ? (
                        <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                            Loading commitments...
                        </div>
                    ) : error ? (
                        <ReportError error={error} endpoint="/budget/commitment-report/" />
                    ) : rows.length === 0 ? (
                        <div style={{
                            textAlign: 'center', padding: '60px 20px', color: '#94a3b8',
                        }}>
                            <FileText size={40} style={{ opacity: 0.35, marginBottom: 12 }} />
                            <div style={{ fontSize: 14 }}>
                                No {statusFilter || 'active'} commitments on record.
                            </div>
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                    {['PO Reference', 'MDA', 'Economic Code', 'Date', 'Committed', 'Appro. Balance', 'Status'].map((h, i) => (
                                        <th key={h} style={{
                                            padding: '12px 14px',
                                            textAlign: i >= 4 ? 'right' : 'left',
                                            fontSize: '11px', fontWeight: 700, color: '#64748b',
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                        }}>
                                            {h}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map(row => (
                                    <tr key={row.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{
                                            padding: '10px 14px', fontSize: '13px',
                                            fontFamily: 'monospace', fontWeight: 600,
                                        }}>
                                            {row.purchase_order}
                                        </td>
                                        <td style={{ padding: '10px 14px', fontSize: '13px' }}>{row.mda || '—'}</td>
                                        <td style={{ padding: '10px 14px', fontSize: '13px' }}>
                                            {row.account_code ? (
                                                <>
                                                    <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#4f46e5' }}>
                                                        {row.account_code}
                                                    </span>
                                                    <span style={{ marginLeft: 6, color: '#1e293b' }}>
                                                        — {row.account_name || row.account}
                                                    </span>
                                                </>
                                            ) : (
                                                row.account || '—'
                                            )}
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: '13px', color: '#64748b',
                                        }}>
                                            {row.committed_at ? row.committed_at.split('T')[0] : '—'}
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: '13px',
                                            textAlign: 'right', fontFamily: 'monospace', fontWeight: 600,
                                        }}>
                                            {fmtNGN(row.committed_amount)}
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: '13px',
                                            textAlign: 'right', fontFamily: 'monospace', color: '#64748b',
                                        }}>
                                            {fmtNGN(row.appropriation_balance)}
                                        </td>
                                        <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                                            <span style={{
                                                padding: '4px 10px', borderRadius: '20px',
                                                fontSize: '11px', fontWeight: 600,
                                                background: `${STATUS_COLORS[row.status] ?? '#64748b'}14`,
                                                color: STATUS_COLORS[row.status] ?? '#64748b',
                                                border: `1px solid ${STATUS_COLORS[row.status] ?? '#64748b'}30`,
                                            }}>
                                                {row.status}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                            {data?.total_committed && (
                                <tfoot>
                                    <tr style={{ background: '#f0f4f8', borderTop: '2px solid #1e293b' }}>
                                        <td colSpan={4} style={{
                                            padding: '12px 14px', fontWeight: 800, fontSize: '14px',
                                        }}>
                                            GRAND TOTAL
                                        </td>
                                        <td colSpan={3} style={{
                                            padding: '12px 14px', textAlign: 'right',
                                            fontWeight: 800, fontFamily: 'monospace', fontSize: '14px',
                                        }}>
                                            {fmtNGN(data.total_committed)}
                                        </td>
                                    </tr>
                                </tfoot>
                            )}
                        </table>
                    )}
                </div>

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: '#94a3b8', fontSize: '11px',
                }}>
                    Quot PSE IFMIS — Commitment Register (IPSAS 24 Disclosure)
                </div>
            </main>
        </div>
    );
}
