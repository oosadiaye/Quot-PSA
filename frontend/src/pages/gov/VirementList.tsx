/**
 * Virements — Quot PSE
 * Route: /budget/virements
 *
 * The register of budget transfers done: every virement between two
 * appropriation lines, newest first, with its reference, the lines it
 * moved money between, the amount, and where it is in the workflow
 * (Draft → Submitted → Applied, or Rejected).
 *
 * This is the landing page for the menu item; "New Virement" opens the
 * form. A virement changes appropriation balances, so the list is the
 * audit surface — you should be able to see what has been moved before
 * moving more.
 */
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeftRight, Plus, ArrowRight } from 'lucide-react';
import apiClient from '../../api/client';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';

const fmtNGN = (v: number | string | undefined | null): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v || 0);
    if (isNaN(num)) return '₦0.00';
    return '₦' + num.toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

// Dates are shown DD/MM/YYYY — Nigerian convention.
const fmtDate = (v: string | null | undefined): string => {
    if (!v) return '—';
    const d = new Date(v);
    return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB');
};

const STATUS_CONFIG: Record<string, { color: string; bg: string }> = {
    DRAFT: { color: '#64748b', bg: '#f1f5f9' },
    SUBMITTED: { color: '#1e40af', bg: '#dbeafe' },
    APPLIED: { color: '#166534', bg: '#dcfce7' },
    APPROVED: { color: '#166534', bg: '#dcfce7' },
    REJECTED: { color: '#dc2626', bg: '#fef2f2' },
};

interface Virement {
    id: number;
    reference_number: string;
    from_label: string;
    to_label: string;
    amount: string;
    fiscal_year: number | null;
    status: string;
    status_display: string;
    reason: string;
    submitted_at: string | null;
    applied_at: string | null;
    created_at: string | null;
}

const thStyle: React.CSSProperties = {
    padding: '0.6rem 0.75rem', textAlign: 'left', fontSize: '0.68rem',
    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.03em',
    color: '#64748b', borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap',
};
const tdStyle: React.CSSProperties = {
    padding: '0.55rem 0.75rem', borderBottom: '1px solid #f1f5f9',
    color: '#1e293b', fontSize: '0.82rem',
};

const VirementList = () => {
    const navigate = useNavigate();

    const { data: rows = [], isLoading, isError, error } = useQuery<Virement[]>({
        queryKey: ['virements'],
        queryFn: async () => {
            const { data } = await apiClient.get('/budget/virements/', {
                params: { page_size: 500, ordering: '-created_at' },
            });
            return Array.isArray(data) ? data : data?.results ?? [];
        },
    });

    const totalMoved = useMemo(
        () => rows
            .filter((r) => r.status === 'APPLIED' || r.status === 'APPROVED')
            .reduce((s, r) => s + Number(r.amount || 0), 0),
        [rows],
    );

    return (
        <div style={{ display: 'flex', minHeight: '100vh', background: '#f8fafc' }}>
            <Sidebar />
            <main style={{ flex: 1, overflow: 'auto' }}>
                <PageHeader
                    title="Virements"
                    subtitle="Budget transfers between appropriation lines"
                    icon={<ArrowLeftRight size={22} />}
                    actions={
                        <button
                            type="button"
                            onClick={() => navigate('/budget/virements/new')}
                            style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                padding: '0.5rem 1rem', background: '#4f46e5', color: '#fff',
                                border: 'none', borderRadius: '8px', fontSize: '0.85rem',
                                fontWeight: 600, cursor: 'pointer',
                            }}
                        >
                            <Plus size={16} /> New Virement
                        </button>
                    }
                />

                <div style={{ padding: '1.25rem 1.5rem' }}>
                    <div style={{
                        background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px',
                        overflow: 'hidden', boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
                    }}>
                        <div style={{
                            padding: '0.9rem 1.1rem', borderBottom: '1px solid #e2e8f0',
                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                            fontSize: '0.85rem', fontWeight: 600, color: '#0f172a',
                        }}>
                            <ArrowLeftRight size={16} style={{ color: '#4f46e5' }} />
                            Virements done
                            <span style={{ fontSize: '0.72rem', color: '#64748b', fontWeight: 400 }}>
                                {isLoading ? 'loading…' : `${rows.length} ${rows.length === 1 ? 'record' : 'records'}`}
                            </span>
                        </div>

                        {isError ? (
                            <div style={{ color: '#b91c1c', fontSize: '0.82rem', padding: '1rem' }}>
                                Could not load virements: {String((error as any)?.message || 'unknown error')}
                            </div>
                        ) : isLoading ? (
                            <div style={{ color: '#94a3b8', fontSize: '0.82rem', padding: '1.5rem', textAlign: 'center' }}>Loading…</div>
                        ) : rows.length === 0 ? (
                            <div style={{ color: '#64748b', fontSize: '0.85rem', padding: '2.5rem 1.5rem', textAlign: 'center', lineHeight: 1.6 }}>
                                <ArrowLeftRight size={22} style={{ color: '#cbd5e1' }} />
                                <div style={{ marginTop: '0.5rem' }}>No virements have been done yet.</div>
                                <button
                                    type="button"
                                    onClick={() => navigate('/budget/virements/new')}
                                    style={{
                                        marginTop: '0.9rem', padding: '0.45rem 0.9rem', background: '#fff',
                                        color: '#4f46e5', border: '1px solid #c7d2fe', borderRadius: '8px',
                                        fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
                                    }}
                                >
                                    Create the first virement
                                </button>
                            </div>
                        ) : (
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '900px' }}>
                                    <thead>
                                        <tr>
                                            <th style={thStyle}>Reference</th>
                                            <th style={thStyle}>From → To</th>
                                            <th style={{ ...thStyle, textAlign: 'right' }}>Amount</th>
                                            <th style={thStyle}>FY</th>
                                            <th style={thStyle}>Status</th>
                                            <th style={thStyle}>Submitted</th>
                                            <th style={thStyle}>Applied</th>
                                            <th style={thStyle}>Reason</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rows.map((r) => {
                                            const sc = STATUS_CONFIG[r.status] || STATUS_CONFIG.DRAFT;
                                            return (
                                                <tr key={r.id}>
                                                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600 }}>
                                                        {r.reference_number || '—'}
                                                    </td>
                                                    <td style={tdStyle}>
                                                        <span style={{ fontFamily: 'monospace' }}>{r.from_label}</span>
                                                        <ArrowRight size={12} style={{ margin: '0 0.35rem', color: '#94a3b8', verticalAlign: 'middle' }} />
                                                        <span style={{ fontFamily: 'monospace' }}>{r.to_label}</span>
                                                    </td>
                                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                                                        {fmtNGN(r.amount)}
                                                    </td>
                                                    <td style={tdStyle}>{r.fiscal_year ?? '—'}</td>
                                                    <td style={tdStyle}>
                                                        <span style={{
                                                            padding: '0.15rem 0.5rem', borderRadius: '8px', fontSize: '0.68rem',
                                                            fontWeight: 600, background: sc.bg, color: sc.color, whiteSpace: 'nowrap',
                                                        }}>
                                                            {r.status_display || r.status}
                                                        </span>
                                                    </td>
                                                    <td style={tdStyle}>{fmtDate(r.submitted_at)}</td>
                                                    <td style={tdStyle}>{fmtDate(r.applied_at)}</td>
                                                    <td style={{ ...tdStyle, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#64748b' }} title={r.reason || ''}>
                                                        {r.reason || '—'}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>

                    {rows.length > 0 && (
                        <div style={{ marginTop: '0.75rem', fontSize: '0.78rem', color: '#64748b' }}>
                            Total moved (applied virements): <strong style={{ color: '#166534' }}>{fmtNGN(totalMoved)}</strong>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
};

export default VirementList;
