/**
 * Payment Register — read-only list of every POSTED outgoing payment
 * (advances + regular). The audit view of what actually hit the GL; the
 * working queue and posting live on the Outgoing Payments page.
 */
import { useMemo, useState } from 'react';
import { BookOpen, Search } from 'lucide-react';
import { formatDate } from '@/utils/date';
import { usePayments } from '../hooks/useAccountingEnhancements';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import { useCurrency } from '../../../context/CurrencyContext';

interface PostedPaymentRow {
    id: number;
    payment_number: string;
    vendor_name?: string;
    is_advance?: boolean;
    advance_type?: string;
    payment_date: string;
    total_amount: string;
    payment_method?: string;
    reference_number?: string;
    bank_account_name?: string;
    payment_voucher_number?: string;
    status: string;
}

const th: React.CSSProperties = {
    padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#64748b',
    fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap',
};
const td: React.CSSProperties = { padding: '11px 14px', color: '#374151' };

export default function PaymentRegisterPage() {
    const { formatCurrency } = useCurrency();
    // Server-side filter to POSTED (the viewset exposes ``status``); the
    // client filter below is a belt-and-suspenders guard.
    const { data, isLoading } = usePayments({ status: 'Posted' });
    const [query, setQuery] = useState('');

    const rows = ((data as PostedPaymentRow[] | undefined) ?? [])
        .filter((p) => p.status === 'Posted');

    const filtered = useMemo(() => {
        const needle = query.trim().toLowerCase();
        if (!needle) return rows;
        return rows.filter((p) =>
            [p.payment_number, p.vendor_name, p.reference_number,
             p.payment_voucher_number, p.bank_account_name]
                .some((v) => (v || '').toLowerCase().includes(needle)),
        );
    }, [rows, query]);

    const total = filtered.reduce((s, p) => s + (parseFloat(p.total_amount) || 0), 0);
    const typeOf = (p: PostedPaymentRow) =>
        p.is_advance ? (p.advance_type || 'Advance') : 'Payment';

    return (
        <AccountingLayout>
            <PageHeader
                title="Payment Register"
                subtitle="All posted outgoing payments — the audit view of what hit the GL"
            />

            <div style={{
                background: '#fff', borderRadius: '16px', border: '1px solid #e2e8f0',
                boxShadow: '0 1px 6px rgba(0,0,0,0.04)', padding: '18px 20px',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <BookOpen size={18} color="#0f766e" />
                        <div>
                            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Posted Payments</h3>
                            <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#64748b' }}>
                                {filtered.length} payment{filtered.length === 1 ? '' : 's'} · total {formatCurrency(String(total))}
                            </p>
                        </div>
                    </div>
                    <div style={{ position: 'relative' }}>
                        <Search size={15} color="#94a3b8" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
                        <input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Filter by #, vendor, reference…"
                            aria-label="Filter posted payments"
                            style={{
                                padding: '8px 12px 8px 32px', border: '1px solid #e2e8f0',
                                borderRadius: '9px', fontSize: '13px', minWidth: '260px', outline: 'none',
                            }}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading posted payments…</div>
                ) : !filtered.length ? (
                    <div style={{ textAlign: 'center', padding: '60px 20px', background: '#f8fafc', borderRadius: '12px', border: '2px dashed #e2e8f0' }}>
                        <BookOpen size={40} color="#cbd5e1" style={{ marginBottom: '12px' }} />
                        <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>
                            {query ? 'No posted payments match your filter.' : 'No posted payments yet.'}
                        </p>
                    </div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc' }}>
                                    {['Payment #', 'Vendor', 'Type', 'Date', 'Amount', 'Method', 'Reference', 'Bank', 'PV', 'Status'].map((h) => (
                                        <th key={h} style={th}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((p) => (
                                    <tr key={p.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{ ...td, fontWeight: 600, color: '#1e293b' }}>{p.payment_number}</td>
                                        <td style={td}>{p.vendor_name || '—'}</td>
                                        <td style={td}>
                                            <span style={{
                                                padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
                                                background: p.is_advance ? '#fef3c7' : '#f1f5f9',
                                                color: p.is_advance ? '#92400e' : '#475569',
                                            }}>{typeOf(p)}</span>
                                        </td>
                                        <td style={td}>{formatDate(p.payment_date)}</td>
                                        <td style={{ ...td, fontWeight: 700, color: '#dc2626', whiteSpace: 'nowrap' }}>{formatCurrency(p.total_amount)}</td>
                                        <td style={td}>{p.payment_method || '—'}</td>
                                        <td style={{ ...td, color: '#64748b', fontFamily: 'monospace', fontSize: '12px' }}>{p.reference_number || '—'}</td>
                                        <td style={td}>{p.bank_account_name || '—'}</td>
                                        <td style={{ ...td, color: '#64748b', fontFamily: 'monospace', fontSize: '12px' }}>{p.payment_voucher_number || '—'}</td>
                                        <td style={td}><StatusBadge status={p.status} /></td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot>
                                <tr style={{ borderTop: '2px solid #e2e8f0', background: '#f8fafc' }}>
                                    <td style={{ ...td, fontWeight: 700 }} colSpan={4}>Total ({filtered.length})</td>
                                    <td style={{ ...td, fontWeight: 800, color: '#1e293b', whiteSpace: 'nowrap' }}>{formatCurrency(String(total))}</td>
                                    <td style={td} colSpan={5} />
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                )}
            </div>
        </AccountingLayout>
    );
}
