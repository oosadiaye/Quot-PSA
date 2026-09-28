/**
 * Supplementary Budget — Quot PSE
 * Route: /budget/supplementary
 *
 * The register of supplementary appropriations: additional funding voted
 * after the original Appropriation Act, which — unlike a virement — adds
 * to the envelope rather than moving within it, and so needs legislative
 * sign-off (Submitted → Approved by Legislature → Active).
 *
 * Supplementary is an appropriation_type, so this is the appropriations
 * list scoped to that type. "New Supplementary Budget" opens the
 * appropriation form preset to SUPPLEMENTARY, where the same duplicate
 * guard that blocks a second ORIGINAL line for a code permits topping it
 * up here.
 */
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Layers, Plus } from 'lucide-react';
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
    DRAFT: { color: 'var(--color-text-muted)', bg: 'var(--color-surface-hover)' },
    SUBMITTED: { color: '#1e40af', bg: '#dbeafe' },
    APPROVED: { color: '#6b21a8', bg: '#f3e8ff' },
    ENACTED: { color: '#166534', bg: '#dcfce7' },
    ACTIVE: { color: '#166534', bg: '#dcfce7' },
    CLOSED: { color: '#dc2626', bg: '#fef2f2' },
};

interface Line {
    id: number;
    budget_code: string;
    administrative_code: string;
    administrative_name: string;
    economic_code: string;
    economic_name: string;
    fund_code: string;
    fund_name: string;
    fiscal_year_label: string;
    amount_approved: string;
    status: string;
    law_reference: string;
    enactment_date: string | null;
}

const thStyle: React.CSSProperties = {
    padding: '0.6rem 0.75rem', textAlign: 'left', fontSize: '0.68rem',
    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.03em',
    color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)', whiteSpace: 'nowrap',
};
const tdStyle: React.CSSProperties = {
    padding: '0.55rem 0.75rem', borderBottom: '1px solid var(--color-border-light)',
    color: 'var(--color-text)', fontSize: '0.82rem',
};

const SupplementaryBudgetList = () => {
    const navigate = useNavigate();

    const { data: rows = [], isLoading, isError, error } = useQuery<Line[]>({
        queryKey: ['supplementary-appropriations'],
        queryFn: async () => {
            const { data } = await apiClient.get('/budget/appropriations/', {
                params: {
                    appropriation_type: 'SUPPLEMENTARY',
                    page_size: 1000,
                    ordering: '-created_at',
                },
            });
            return Array.isArray(data) ? data : data?.results ?? [];
        },
    });

    const totalSupplementary = useMemo(
        () => rows.reduce((s, r) => s + Number(r.amount_approved || 0), 0),
        [rows],
    );

    return (
        <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--color-surface-hover)' }}>
            <Sidebar />
            {/* Sidebar is position:fixed at 260px — offset the content so it
                sits beside the nav, matching every other page. */}
            <main style={{ flex: 1, minWidth: 0, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Supplementary Budget"
                    subtitle="Additional appropriations voted after the original Appropriation Act"
                    icon={<Layers size={22} />}
                    actions={
                        <button
                            type="button"
                            onClick={() => navigate('/budget/appropriations/new?type=SUPPLEMENTARY')}
                            style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                padding: '0.5rem 1rem', background: '#4f46e5', color: '#fff',
                                border: 'none', borderRadius: '8px', fontSize: '0.85rem',
                                fontWeight: 600, cursor: 'pointer',
                            }}
                        >
                            <Plus size={16} /> New Supplementary Budget
                        </button>
                    }
                />

                <div style={{ marginTop: '1.5rem' }}>
                    <div style={{
                        background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '10px',
                        overflow: 'hidden', boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
                    }}>
                        <div style={{
                            padding: '0.9rem 1.1rem', borderBottom: '1px solid var(--color-border)',
                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                            fontSize: '0.85rem', fontWeight: 600, color: 'var(--color-text)',
                        }}>
                            <Layers size={16} style={{ color: '#4f46e5' }} />
                            Supplementary appropriations
                            <span style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', fontWeight: 400 }}>
                                {isLoading ? 'loading…' : `${rows.length} ${rows.length === 1 ? 'line' : 'lines'}`}
                            </span>
                        </div>

                        {isError ? (
                            <div style={{ color: '#b91c1c', fontSize: '0.82rem', padding: '1rem' }}>
                                Could not load supplementary appropriations: {String((error as any)?.message || 'unknown error')}
                            </div>
                        ) : isLoading ? (
                            <div style={{ color: 'var(--color-text-subtle)', fontSize: '0.82rem', padding: '1.5rem', textAlign: 'center' }}>Loading…</div>
                        ) : rows.length === 0 ? (
                            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', padding: '2.5rem 1.5rem', textAlign: 'center', lineHeight: 1.6 }}>
                                <Layers size={22} style={{ color: '#cbd5e1' }} />
                                <div style={{ marginTop: '0.5rem' }}>No supplementary budgets have been raised yet.</div>
                                <button
                                    type="button"
                                    onClick={() => navigate('/budget/appropriations/new?type=SUPPLEMENTARY')}
                                    style={{
                                        marginTop: '0.9rem', padding: '0.45rem 0.9rem', background: 'var(--color-surface)',
                                        color: '#4f46e5', border: '1px solid #c7d2fe', borderRadius: '8px',
                                        fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
                                    }}
                                >
                                    Raise the first supplementary budget
                                </button>
                            </div>
                        ) : (
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1000px' }}>
                                    <thead>
                                        <tr>
                                            <th style={thStyle}>Budget Code</th>
                                            <th style={thStyle}>MDA</th>
                                            <th style={thStyle}>Economic</th>
                                            <th style={thStyle}>Fund</th>
                                            <th style={thStyle}>FY</th>
                                            <th style={{ ...thStyle, textAlign: 'right' }}>Amount</th>
                                            <th style={thStyle}>Status</th>
                                            <th style={thStyle}>Law Reference</th>
                                            <th style={thStyle}>Enacted</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rows.map((r) => {
                                            const sc = STATUS_CONFIG[r.status] || STATUS_CONFIG.DRAFT;
                                            return (
                                                <tr
                                                    key={r.id}
                                                    onClick={() => navigate(`/budget/appropriations/${r.id}`)}
                                                    style={{ cursor: 'pointer' }}
                                                >
                                                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600 }}>
                                                        {r.budget_code || '—'}
                                                    </td>
                                                    <td style={tdStyle} title={r.administrative_name}>
                                                        {r.administrative_name || r.administrative_code}
                                                    </td>
                                                    <td style={tdStyle}>
                                                        <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{r.economic_code}</span>
                                                        <div style={{ fontSize: '0.68rem', color: 'var(--color-text-subtle)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.economic_name}</div>
                                                    </td>
                                                    <td style={{ ...tdStyle, fontFamily: 'monospace' }}>{r.fund_code}</td>
                                                    <td style={tdStyle}>{r.fiscal_year_label}</td>
                                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                                                        {fmtNGN(r.amount_approved)}
                                                    </td>
                                                    <td style={tdStyle}>
                                                        <span style={{
                                                            padding: '0.15rem 0.5rem', borderRadius: '8px', fontSize: '0.68rem',
                                                            fontWeight: 600, background: sc.bg, color: sc.color, whiteSpace: 'nowrap',
                                                        }}>
                                                            {r.status}
                                                        </span>
                                                    </td>
                                                    <td style={{ ...tdStyle, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--color-text-muted)' }} title={r.law_reference || ''}>
                                                        {r.law_reference || '—'}
                                                    </td>
                                                    <td style={tdStyle}>{fmtDate(r.enactment_date)}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                    <tfoot>
                                        <tr style={{ borderTop: '2px solid var(--color-border)', background: 'var(--color-surface-hover)' }}>
                                            <td colSpan={5} style={{ ...tdStyle, fontWeight: 700, textAlign: 'right' }}>Total supplementary:</td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#4f46e5' }}>{fmtNGN(totalSupplementary)}</td>
                                            <td colSpan={3} style={tdStyle}></td>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
};

export default SupplementaryBudgetList;
