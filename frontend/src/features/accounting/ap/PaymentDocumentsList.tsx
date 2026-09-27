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

// Just the line fields the list needs to derive the account being paid.
interface PdRowLine {
    account_code?: string;
    account_name?: string;
    vendor_name?: string;
    debit: string;
    credit: string;
}

interface PaymentDocumentRow {
    id: number | string;
    document_number: string;
    document_date?: string;
    reference_number?: string;
    bank_account_name?: string;
    net_amount?: string | number;
    status: string;
    lines?: PdRowLine[];
}

const STATUS_COLORS: Record<string, string> = {
    Posted: 'var(--success, #16a34a)',
    Draft: 'var(--warning, #d97706)',
    Void: 'var(--error, #dc2626)',
};

/**
 * Derive the "account paid" label from a document's lines: the debit account(s)
 * being settled. Uses the first debit line (debit > 0), showing its account name
 * (falling back to code) and, when tagged, the vendor it settles. Extra debit
 * lines are summarised as " +N". Returns "—" when there are no debit lines.
 */
function deriveAccountPaid(lines?: PdRowLine[]): string {
    const debitLines = (lines ?? []).filter((l) => (parseFloat(l.debit) || 0) > 0);
    if (debitLines.length === 0) return '—';
    const primary = debitLines[0];
    const name = primary.account_name || primary.account_code || '—';
    const withVendor = primary.vendor_name ? `${name} → ${primary.vendor_name}` : name;
    return debitLines.length > 1 ? `${withVendor} +${debitLines.length - 1}` : withVendor;
}

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
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Reference</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Date</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Bank Account</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Account Paid</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', textAlign: 'right' }}>Net Amount</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Status</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', textAlign: 'right' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr><td colSpan={8} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>Loading…</td></tr>
                            ) : docs.length === 0 ? (
                                <tr><td colSpan={8} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>No payment documents yet.</td></tr>
                            ) : (
                                docs.map((d: PaymentDocumentRow) => {
                                    const accountPaid = deriveAccountPaid(d.lines);
                                    return (
                                        <tr key={d.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                            <td style={{ padding: '1rem', fontWeight: 600 }}>
                                                <Link
                                                    to={`/accounting/payment-documents/${d.id}`}
                                                    style={{ color: 'var(--primary)', textDecoration: 'none' }}
                                                    title={d.status === 'Draft' ? 'Open to edit or Post & Pay' : 'View payment document'}
                                                >
                                                    {d.document_number}
                                                </Link>
                                            </td>
                                            <td style={{ padding: '1rem' }}>{d.reference_number || '—'}</td>
                                            <td style={{ padding: '1rem' }}>{formatDate(d.document_date)}</td>
                                            <td style={{ padding: '1rem' }}>{d.bank_account_name ?? '—'}</td>
                                            <td style={{ padding: '1rem', maxWidth: 240 }}>
                                                <span
                                                    title={accountPaid !== '—' ? accountPaid : undefined}
                                                    style={{ display: 'block', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                                >
                                                    {accountPaid}
                                                </span>
                                            </td>
                                            <td style={{ padding: '1rem', textAlign: 'right' }}>{formatCurrency(Number(d.net_amount ?? 0))}</td>
                                            <td style={{ padding: '1rem', fontWeight: 600, color: STATUS_COLORS[d.status] ?? 'var(--text)' }}>{d.status}</td>
                                            <td style={{ padding: '1rem', textAlign: 'right' }}>
                                                <Link
                                                    to={`/accounting/payment-documents/${d.id}`}
                                                    className="btn btn-outline"
                                                    style={{ fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}
                                                >
                                                    Details
                                                </Link>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </AccountingLayout>
    );
}
