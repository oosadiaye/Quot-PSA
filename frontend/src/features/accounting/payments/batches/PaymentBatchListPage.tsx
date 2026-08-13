import { useNavigate } from 'react-router-dom';
import { FileText, Printer, Plus } from 'lucide-react';
import AccountingLayout from '../../AccountingLayout';
import PageHeader from '../../../../components/PageHeader';
import StatusBadge from '../../components/shared/StatusBadge';
import { useCurrency } from '../../../../context/CurrencyContext';
import {
    usePaymentBatches, type PaymentBatch, type PaymentBatchStatus,
} from '../../hooks/usePaymentBatches';

/** DD/MM/YYYY — Nigerian convention, never the US ordering. */
function formatDate(iso: string): string {
    if (!iso) return '—';
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('en-GB');
}

const th: React.CSSProperties = {
    padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#64748b',
    fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap',
};
const td: React.CSSProperties = { padding: '11px 14px', fontSize: '13px', color: '#334155' };

const ghostBtn: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: '5px',
    padding: '5px 10px', borderRadius: '7px', border: '1px solid #e2e8f0',
    background: '#fff', color: '#334155', fontSize: '12px', fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit',
};

export default function PaymentBatchListPage() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const { data: batches = [], isLoading } = usePaymentBatches();

    const draftCount = batches.filter((b) => b.status === 'Draft').length;
    const dispatchedCount = batches.filter((b) => b.status === 'Dispatched').length;
    const totalValue = batches
        .filter((b: PaymentBatch) => b.status !== 'Cancelled')
        .reduce((sum, b) => sum + Number(b.total_amount || 0), 0);

    const stats: { label: string; value: string; hint: string; accent: string }[] = [
        { label: 'Draft', value: String(draftCount), hint: 'Still editable', accent: '#f59e0b' },
        { label: 'Dispatched', value: String(dispatchedCount), hint: 'Sent to bank', accent: '#3b82f6' },
        { label: 'Batches', value: String(batches.length), hint: 'All time', accent: '#10b981' },
        {
            label: 'Total Value', value: formatCurrency(totalValue),
            hint: 'Excluding cancelled', accent: '#8b5cf6',
        },
    ];

    return (
        <AccountingLayout>
            <PageHeader
                title="Payment Batches"
                subtitle="Treasury · Bank Payment/Confirmation Letters"
            />

            {/* Context banner — mirrors the SOD banner on Outgoing Payments. */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '10px',
                background: 'linear-gradient(135deg,#eff6ff,#f0f9ff)',
                border: '1px solid #93c5fd', borderRadius: '12px',
                padding: '12px 16px', marginBottom: '20px',
            }}>
                <FileText size={16} style={{ color: '#1d4ed8', flexShrink: 0 }} />
                <span style={{ fontWeight: 700, color: '#1e3a8a', fontSize: '13px' }}>
                    Bank Instruction
                </span>
                <span style={{ color: '#475569', fontSize: '12px' }}>
                    Groups posted payments drawn on one government account · Signed by
                    AG, Director Treasury &amp; Director Management Accounts
                </span>
            </div>

            {/* Stat cards — same shape/rhythm as the rest of Accounting. */}
            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))',
                gap: '16px', marginBottom: '20px',
            }}>
                {stats.map((s) => (
                    <div key={s.label} style={{
                        background: '#fff', borderRadius: '12px', padding: '18px 20px',
                        borderLeft: `4px solid ${s.accent}`,
                        boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                    }}>
                        <div style={{
                            fontSize: '11px', fontWeight: 700, color: '#94a3b8',
                            textTransform: 'uppercase', letterSpacing: '0.05em',
                        }}>{s.label}</div>
                        <div style={{
                            fontSize: '26px', fontWeight: 800, color: '#0f172a',
                            margin: '6px 0 2px',
                        }}>{s.value}</div>
                        <div style={{ fontSize: '12px', color: '#94a3b8' }}>{s.hint}</div>
                    </div>
                ))}
            </div>

            <div style={{
                background: '#fff', borderRadius: '12px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden',
            }}>
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '18px 20px', flexWrap: 'wrap', gap: '12px',
                }}>
                    <div>
                        <h3 style={{
                            margin: 0, fontSize: '16px', fontWeight: 700, color: '#0f172a',
                        }}>Bank Payment Letters</h3>
                        <p style={{ margin: '3px 0 0', fontSize: '13px', color: '#64748b' }}>
                            Select posted payments on Outgoing Payments to start a batch
                        </p>
                    </div>
                    <button
                        onClick={() => navigate('/accounting/outgoing-payments')}
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: '6px',
                            padding: '9px 16px', borderRadius: '9px', border: 'none',
                            background: 'linear-gradient(135deg,#f59e0b,#ea8c00)',
                            color: '#fff', fontWeight: 700, fontSize: '13px',
                            cursor: 'pointer', fontFamily: 'inherit',
                        }}
                    >
                        <Plus size={15} /> New Batch
                    </button>
                </div>

                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: '#f8fafc' }}>
                                {['Batch #', 'Date', 'Bank', 'Account', 'Lines', 'Total', 'Status', 'Actions'].map(h => (
                                    <th key={h} style={{
                                        ...th,
                                        textAlign: (h === 'Lines' || h === 'Total') ? 'right' : 'left',
                                    }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading && (
                                <tr><td colSpan={8} style={{ ...td, textAlign: 'center', padding: '36px', color: '#94a3b8' }}>
                                    Loading batches…
                                </td></tr>
                            )}
                            {!isLoading && batches.length === 0 && (
                                <tr><td colSpan={8} style={{ ...td, textAlign: 'center', padding: '44px 20px' }}>
                                    <FileText size={30} style={{ color: '#cbd5e1' }} />
                                    <div style={{
                                        marginTop: '10px', fontWeight: 700, color: '#475569', fontSize: '14px',
                                    }}>No payment batches yet</div>
                                    <div style={{ marginTop: '4px', fontSize: '12px', color: '#94a3b8' }}>
                                        Go to Outgoing Payments, tick posted payments, then choose “Add to Batch”.
                                    </div>
                                </td></tr>
                            )}
                            {batches.map((row: PaymentBatch) => (
                                <tr key={row.id} style={{ borderBottom: '1px solid #f1f5f9' }}
                                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                                >
                                    <td style={{ ...td, fontWeight: 700, color: '#0f172a' }}>
                                        {row.batch_number}
                                    </td>
                                    <td style={td}>{formatDate(row.batch_date)}</td>
                                    <td style={td}>{row.addressee_bank_name || '—'}</td>
                                    <td style={{ ...td, fontFamily: 'monospace', color: '#3b82f6' }}>
                                        {row.addressee_account_no || '—'}
                                    </td>
                                    <td style={{ ...td, textAlign: 'right' }}>{row.line_count}</td>
                                    <td style={{
                                        ...td, textAlign: 'right', fontWeight: 700, color: '#dc2626',
                                    }}>
                                        {formatCurrency(Number(row.total_amount || 0))}
                                    </td>
                                    <td style={td}>
                                        <StatusBadge status={row.status as PaymentBatchStatus} />
                                    </td>
                                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                                        <button
                                            style={{ ...ghostBtn, marginRight: '6px' }}
                                            onClick={() => navigate(`/accounting/payment-batches/${row.id}`)}
                                        >
                                            Open
                                        </button>
                                        <button
                                            style={ghostBtn}
                                            onClick={() => navigate(`/accounting/payment-batches/${row.id}/letter`)}
                                        >
                                            <Printer size={13} /> Letter
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </AccountingLayout>
    );
}
