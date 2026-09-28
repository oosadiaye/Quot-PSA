import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ClipboardList, Plus } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '@/utils/date';
import AccountingLayout from '../AccountingLayout';
import { usePaymentProposals, type PaymentProposalRow } from '../hooks/usePaymentProposals';

/**
 * Payment Proposal register — a unified list of Payment Vouchers and Payment
 * Documents. Everything routes through here for approval before it becomes an
 * Outgoing Payment. Status tabs filter by the unified proposal status; each row
 * opens its source's own detail page.
 */

const TABS = ['Proposed', 'Approved', 'Paid', 'Void'] as const;
type Tab = (typeof TABS)[number];

const STATUS_COLORS: Record<string, string> = {
    Proposed: 'var(--warning, #d97706)',
    Approved: 'var(--primary)',
    Paid: 'var(--success, #16a34a)',
    Void: 'var(--error, #dc2626)',
};

const SOURCE_LABEL: Record<string, string> = { pv: 'Voucher', pd: 'Document' };

export default function PaymentProposalsPage() {
    const [tab, setTab] = useState<Tab>('Proposed');
    const { data: rows = [], isLoading } = usePaymentProposals(tab);
    const { formatCurrency } = useCurrency();

    return (
        <AccountingLayout>
            <PageHeader
                title="Payment Proposals"
                subtitle="Payment Vouchers and Payment Documents awaiting approval and disbursement. Approve a proposal to raise its Outgoing Payment."
                icon={<ClipboardList size={22} />}
                actions={
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <Link to="/accounting/payment-vouchers/new" className="btn btn-outline">
                            <Plus size={18} /> New Voucher
                        </Link>
                        <Link to="/accounting/payment-documents/new" className="btn btn-primary">
                            <Plus size={18} /> New Document
                        </Link>
                    </div>
                }
            />

            {/* Status filter — pill buttons; the active one fills with that
                status's own colour (amber Proposed / primary Approved / green
                Paid / red Void) so the current filter reads at a glance. */}
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                {TABS.map((t) => {
                    const active = tab === t;
                    const accent = STATUS_COLORS[t];
                    return (
                        <button
                            key={t}
                            type="button"
                            aria-pressed={active}
                            onClick={() => setTab(t)}
                            style={{
                                padding: '0.5rem 1.15rem',
                                borderRadius: 999,
                                fontSize: '0.875rem',
                                fontWeight: active ? 700 : 600,
                                cursor: 'pointer',
                                background: active ? accent : 'var(--surface-hover, rgba(148,163,184,0.14))',
                                color: active ? '#fff' : 'var(--text, var(--text-muted))',
                                border: `1px solid ${active ? accent : 'var(--border, rgba(148,163,184,0.35))'}`,
                                boxShadow: active ? '0 1px 3px rgba(0,0,0,0.18)' : 'none',
                                transition: 'background 120ms, color 120ms, border-color 120ms',
                            }}
                        >
                            {t}
                        </button>
                    );
                })}
            </div>

            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
                        <thead>
                            <tr style={{ background: 'var(--background)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Number</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Type</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Date</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Payee / Description</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', textAlign: 'right' }}>Amount</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Status</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', textAlign: 'right' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr><td colSpan={7} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>Loading…</td></tr>
                            ) : rows.length === 0 ? (
                                <tr><td colSpan={7} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>No {tab.toLowerCase()} proposals.</td></tr>
                            ) : (
                                rows.map((r: PaymentProposalRow) => (
                                    <tr key={`${r.source}-${r.id}`} style={{ borderBottom: '1px solid var(--border)' }}>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>
                                            <Link to={r.detail_path} style={{ color: 'var(--primary)', textDecoration: 'none' }}>
                                                {r.number}
                                            </Link>
                                        </td>
                                        <td style={{ padding: '1rem' }}>{SOURCE_LABEL[r.source] ?? r.source}</td>
                                        <td style={{ padding: '1rem' }}>{formatDate(r.date ?? undefined)}</td>
                                        <td style={{ padding: '1rem', maxWidth: 280 }}>
                                            <span style={{ display: 'block', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {r.payee_or_description || '—'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem', textAlign: 'right' }}>{formatCurrency(Number(r.amount ?? 0))}</td>
                                        <td style={{ padding: '1rem', fontWeight: 600, color: STATUS_COLORS[r.unified_status] ?? 'var(--text)' }} title={r.native_status}>
                                            {r.unified_status}
                                        </td>
                                        <td style={{ padding: '1rem', textAlign: 'right' }}>
                                            <Link to={r.detail_path} className="btn btn-outline" style={{ fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}>
                                                Details
                                            </Link>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </AccountingLayout>
    );
}
