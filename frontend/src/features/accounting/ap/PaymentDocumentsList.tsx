import { Link } from 'react-router-dom';
import { FileText, Plus } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '@/utils/date';
import AccountingLayout from '../AccountingLayout';
import { usePaymentDocuments } from '../hooks/usePaymentDocuments';

/**
 * Payment Documents register — the list of multi-line outgoing payments,
 * adjacent to Outgoing Payments. Each row links back to its status; the
 * header links to the New Payment Document form.
 */

interface PaymentDocumentRow {
    id: number | string;
    document_number: string;
    document_date?: string;
    bank_account_name?: string;
    net_amount?: string | number;
    status: string;
}

const STATUS_COLORS: Record<string, string> = {
    Posted: 'var(--success, #16a34a)',
    Draft: 'var(--warning, #d97706)',
    Void: 'var(--error, #dc2626)',
};

export default function PaymentDocumentsList() {
    const { data: docs = [], isLoading } = usePaymentDocuments({});
    const { formatCurrency } = useCurrency();

    return (
        <AccountingLayout>
            <PageHeader
                title="Payment Documents"
                subtitle="Multi-line outgoing payments. Each posts one balanced journal and settles the bank."
                icon={<FileText size={22} />}
                actions={
                    <Link to="/accounting/payment-documents/new" className="btn btn-primary">
                        <Plus size={18} /> New Payment Document
                    </Link>
                }
            />

            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
                        <thead>
                            <tr style={{ background: 'var(--background)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Document #</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Date</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Bank Account</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', textAlign: 'right' }}>Net Amount</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr><td colSpan={5} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>Loading…</td></tr>
                            ) : docs.length === 0 ? (
                                <tr><td colSpan={5} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>No payment documents yet.</td></tr>
                            ) : (
                                docs.map((d: PaymentDocumentRow) => (
                                    <tr key={d.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{d.document_number}</td>
                                        <td style={{ padding: '1rem' }}>{formatDate(d.document_date)}</td>
                                        <td style={{ padding: '1rem' }}>{d.bank_account_name ?? '—'}</td>
                                        <td style={{ padding: '1rem', textAlign: 'right' }}>{formatCurrency(Number(d.net_amount ?? 0))}</td>
                                        <td style={{ padding: '1rem', fontWeight: 600, color: STATUS_COLORS[d.status] ?? 'var(--text)' }}>{d.status}</td>
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
