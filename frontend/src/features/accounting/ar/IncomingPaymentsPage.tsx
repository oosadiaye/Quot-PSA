import { useState } from 'react';
import {
    ArrowDownLeft, Play, Trash2, Plus,
    CheckCircle2, X, AlertTriangle, TrendingUp, Banknote, DollarSign,
} from 'lucide-react';
import {
    useReceipts, useCreateReceipt, usePostReceipt, useDeleteReceipt,
    useCreateReceiptAllocation, useAccountingSettings,
} from '../hooks/useAccountingEnhancements';
import { useCustomerInvoices } from '../hooks/useAccountingEnhancements';
import { useCustomers } from '../hooks/useCustomers';
import { useBankAccounts } from '../../settings/hooks/useBankAccounts';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import { useCurrency } from '../../../context/CurrencyContext';
import { useToast } from '../../../context/ToastContext';
import { parsePostingError } from '../utils/parsePostingError';
import '../styles/glassmorphism.css';

// ─── styles ─────────────────────────────────────────────────────────────────
const inp: React.CSSProperties = {
    width: '100%', padding: '8px 12px', border: '2.5px solid #d1d5db',
    borderRadius: '8px', fontSize: '14px', outline: 'none',
    background: '#fafbfc', color: '#1e293b', boxSizing: 'border-box',
};
const sel: React.CSSProperties = { ...inp, cursor: 'pointer' };

type ActiveTab = 'payments' | 'downpayments';

const BLANK_RECEIPT = {
    customer: '', receipt_date: new Date().toISOString().slice(0, 10),
    total_amount: '', payment_method: 'Wire', bank_account: '', reference_number: '',
    invoice: '',
};
const BLANK_ADVANCE = {
    customer: '', receipt_date: new Date().toISOString().slice(0, 10),
    total_amount: '', payment_method: 'Wire', bank_account: '', reference_number: '',
    advance_type: 'Customer Advance' as 'Customer Advance' | 'Customer Deposit',
};

// ─── inline notification ─────────────────────────────────────────────────────
function InlineAlert({ msg, type, onClose }: { msg: string; type: 'success' | 'error'; onClose: () => void }) {
    return (
        <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            background: type === 'success' ? '#d1fae5' : '#fee2e2',
            border: `1px solid ${type === 'success' ? '#6ee7b7' : '#fca5a5'}`,
            borderRadius: '8px', padding: '12px 16px', marginBottom: '1rem',
            color: type === 'success' ? '#065f46' : '#991b1b',
        }}>
            {type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            <span style={{ fontSize: '14px', fontWeight: 500 }}>{msg}</span>
            <button onClick={onClose} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}>
                <X size={14} />
            </button>
        </div>
    );
}

export default function IncomingPaymentsPage() {
    const { formatCurrency } = useCurrency();
    const [activeTab, setActiveTab] = useState<ActiveTab>('payments');
    const [notification, setNotification] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

    // Payment form
    const [showPaymentForm, setShowPaymentForm] = useState(false);
    const [paymentForm, setPaymentForm] = useState({ ...BLANK_RECEIPT });

    // Downpayment form
    const [showAdvanceForm, setShowAdvanceForm] = useState(false);
    const [advanceForm, setAdvanceForm] = useState({ ...BLANK_ADVANCE });

    // Post / Delete confirm
    const [postConfirm, setPostConfirm] = useState<{ id: number; number: string } | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<{ id: number; number: string } | null>(null);

    // ─── queries ─────────────────────────────────────────────────────────────
    const { data: payments, isLoading: loadingPayments } = useReceipts({ is_advance: false });
    const { data: downpayments, isLoading: loadingDownpayments } = useReceipts({ is_advance: true });
    const { data: customers } = useCustomers();
    const { data: bankAccounts } = useBankAccounts({ is_active: true });
    const { data: openInvoices } = useCustomerInvoices({ status: 'Sent' });
    const { data: accountingSettings } = useAccountingSettings();

    // ─── mutations ────────────────────────────────────────────────────────────
    const createReceipt = useCreateReceipt();
    const createAllocation = useCreateReceiptAllocation();
    const postReceipt = usePostReceipt();
    const deleteReceipt = useDeleteReceipt();

    const { addToast } = useToast();

    // ─── helpers ──────────────────────────────────────────────────────────────
    // Local notification stays for in-context inline alerts; ALSO fire
    // a sticky toast on errors so the operator catches the message even
    // if they've scrolled away. Error toasts use ``duration: 0`` so they
    // remain until manually dismissed — posting errors often need to be
    // read carefully or shared with a colleague before acting.
    const showSuccess = (msg: string) => { setNotification({ msg, type: 'success' }); setTimeout(() => setNotification(null), 3500); };
    const showError   = (msg: string) => {
        setNotification({ msg, type: 'error' }); setTimeout(() => setNotification(null), 4500);
        addToast(msg, 'error', 0);
    };

    // ─── summary metrics ──────────────────────────────────────────────────────
    const todayStr       = new Date().toISOString().slice(0, 10);
    const collectedToday = payments?.filter((r: any) => r.receipt_date === todayStr)
        .reduce((s: number, r: any) => s + parseFloat(r.total_amount || '0'), 0) || 0;
    const pendingPosting = payments?.filter((r: any) => r.status === 'Draft').length || 0;
    const postedCount    = payments?.filter((r: any) => r.status === 'Posted').length || 0;
    const advanceBalance = downpayments?.reduce((s: number, r: any) => s + parseFloat(r.advance_remaining || '0'), 0) || 0;

    // ─── handlers ─────────────────────────────────────────────────────────────
    const handleSubmitPayment = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            const receipt = await createReceipt.mutateAsync({
                customer: Number(paymentForm.customer) || undefined,
                receipt_date: paymentForm.receipt_date,
                total_amount: paymentForm.total_amount,
                payment_method: paymentForm.payment_method,
                bank_account: paymentForm.bank_account ? Number(paymentForm.bank_account) : undefined,
                reference_number: paymentForm.reference_number,
                is_advance: false,
            });
            if (paymentForm.invoice) {
                await createAllocation.mutateAsync({
                    receipt: receipt.id,
                    invoice: Number(paymentForm.invoice),
                    amount: paymentForm.total_amount,
                });
            }
            showSuccess('Payment recorded successfully.');
            setPaymentForm({ ...BLANK_RECEIPT });
            setShowPaymentForm(false);
        } catch (err: any) {
            showError(parsePostingError(err, 'Failed to record payment.'));
        }
    };

    const handleSubmitAdvance = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createReceipt.mutateAsync({
                customer: Number(advanceForm.customer) || undefined,
                receipt_date: advanceForm.receipt_date,
                total_amount: advanceForm.total_amount,
                payment_method: advanceForm.payment_method,
                bank_account: advanceForm.bank_account ? Number(advanceForm.bank_account) : undefined,
                reference_number: advanceForm.reference_number,
                is_advance: true,
                advance_type: advanceForm.advance_type,
            });
            showSuccess('Downpayment recorded successfully.');
            setAdvanceForm({ ...BLANK_ADVANCE });
            setShowAdvanceForm(false);
        } catch (err: any) {
            showError(parsePostingError(err, 'Failed to record downpayment.'));
        }
    };

    const handlePost = async () => {
        if (!postConfirm) return;
        try {
            await postReceipt.mutateAsync(postConfirm.id);
            showSuccess(`${postConfirm.number} posted to GL successfully.`);
        } catch (err: any) {
            showError(parsePostingError(err, 'Failed to post receipt.'));
        }
        setPostConfirm(null);
    };

    const handleDelete = async () => {
        if (!deleteConfirm) return;
        try {
            await deleteReceipt.mutateAsync(deleteConfirm.id);
            showSuccess(`${deleteConfirm.number} deleted.`);
        } catch (err: any) {
            showError(parsePostingError(err, 'Failed to delete receipt.'));
        }
        setDeleteConfirm(null);
    };

    const tabs = [
        { key: 'payments' as ActiveTab,     label: 'Payments',     icon: <ArrowDownLeft size={15} /> },
        { key: 'downpayments' as ActiveTab, label: 'Downpayments', icon: <DollarSign size={15} /> },
    ];

    return (
        <AccountingLayout>
            <div>
                {notification && <InlineAlert msg={notification.msg} type={notification.type} onClose={() => setNotification(null)} />}

                <PageHeader
                    title="Incoming Payments"
                    subtitle="Record and post customer cash receipts and advance downpayments"
                    icon={<ArrowDownLeft size={22} />}
                    actions={
                        activeTab === 'payments' ? (
                            <button className="btn btn-primary" onClick={() => setShowPaymentForm(true)}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <Plus size={16} /> New Payment
                            </button>
                        ) : (
                            <button className="btn btn-outline" onClick={() => setShowAdvanceForm(true)}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px', borderColor: '#7c3aed', color: '#7c3aed' }}>
                                <Plus size={16} /> New Downpayment
                            </button>
                        )
                    }
                />

                {/* SOD Banner */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '12px',
                    background: '#eff6ff', border: '1px solid #bfdbfe',
                    borderRadius: '10px', padding: '12px 18px', marginBottom: '1.5rem',
                    fontSize: '13px', color: '#1d4ed8',
                }}>
                    <Banknote size={16} style={{ flexShrink: 0 }} />
                    <span>
                        <strong>Collections team view.</strong> Record and post customer payments here.
                        Invoice creation and management is handled separately by the AR team.
                    </span>
                </div>

                {/* Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Collected Today</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: '#059669' }}>{formatCurrency(collectedToday)}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Pending Posting</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: '#d97706' }}>{pendingPosting}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Posted</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: '#191e6a' }}>{postedCount}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Advance Balance</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: '#7c3aed' }}>{formatCurrency(advanceBalance)}</p>
                    </div>
                </div>

                {/* Tab Nav */}
                <div style={{ display: 'flex', gap: '4px', background: '#fff', padding: '6px', borderRadius: '10px', marginBottom: '1.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.06)', width: 'fit-content' }}>
                    {tabs.map(t => (
                        <button key={t.key} onClick={() => setActiveTab(t.key)} style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '8px 16px', borderRadius: '8px', border: 'none',
                            background: activeTab === t.key ? '#191e6a' : 'transparent',
                            color: activeTab === t.key ? '#fff' : '#64748b',
                            fontWeight: activeTab === t.key ? 600 : 400,
                            fontSize: '14px', cursor: 'pointer', transition: 'all 0.15s',
                        }}>
                            {t.icon} {t.label}
                        </button>
                    ))}
                </div>

                {/* ── PAYMENTS TAB ── */}
                {activeTab === 'payments' && (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                    {['Receipt #', 'Customer', 'Date', 'Method', 'Amount', 'Allocated To', 'Status', 'Actions'].map(h => (
                                        <th key={h} style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {loadingPayments ? (
                                    <tr><td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>Loading...</td></tr>
                                ) : !payments?.length ? (
                                    <tr><td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <ArrowDownLeft size={48} style={{ margin: '0 auto 1rem', opacity: 0.3, display: 'block' }} />
                                        No payments recorded yet. Click <strong>New Payment</strong> to record one.
                                    </td></tr>
                                ) : payments.map((r: any) => (
                                    <tr key={r.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem 1.5rem', fontWeight: 600, color: 'var(--color-primary)' }}>{r.receipt_number}</td>
                                        <td style={{ padding: '1rem 1.5rem' }}>{r.customer_name ?? '—'}</td>
                                        <td style={{ padding: '1rem 1.5rem' }}>{r.receipt_date}</td>
                                        <td style={{ padding: '1rem 1.5rem' }}>{r.payment_method}</td>
                                        <td style={{ padding: '1rem 1.5rem', fontWeight: 600, fontFamily: 'monospace' }}>
                                            {r.currency_code} {parseFloat(r.total_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', fontSize: '13px', color: 'var(--color-text-muted)' }}>
                                            {r.allocations?.length
                                                ? r.allocations.map((a: any) => a.invoice_number || `INV-${a.invoice}`).join(', ')
                                                : <span style={{ fontStyle: 'italic', opacity: 0.6 }}>Unallocated</span>}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem' }}><StatusBadge status={r.status} /></td>
                                        <td style={{ padding: '0.75rem 1.5rem' }}>
                                            <div style={{ display: 'flex', gap: '8px' }}>
                                                {r.status === 'Draft' && (
                                                    <>
                                                        <button onClick={() => setPostConfirm({ id: r.id, number: r.receipt_number })}
                                                            style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '5px 10px', borderRadius: '6px', border: 'none', background: '#059669', color: '#fff', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}>
                                                            <Play size={12} /> Post
                                                        </button>
                                                        <button onClick={() => setDeleteConfirm({ id: r.id, number: r.receipt_number })}
                                                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '4px' }}>
                                                            <Trash2 size={15} />
                                                        </button>
                                                    </>
                                                )}
                                                {r.status === 'Posted' && (
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#059669', fontWeight: 600 }}>
                                                        <TrendingUp size={13} /> Posted
                                                    </div>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* ── DOWNPAYMENTS TAB ── */}
                {activeTab === 'downpayments' && (
                    <div>
                        {accountingSettings && !accountingSettings.enable_sales_downpayment && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', background: '#fef3c7', border: '1px solid #fcd34d', borderRadius: '10px', padding: '14px 18px', marginBottom: '16px' }}>
                                <AlertTriangle size={18} style={{ color: '#92400e', flexShrink: 0 }} />
                                <span style={{ fontSize: '14px', color: '#92400e' }}>
                                    Sales downpayments are disabled. Enable them in <strong>Accounting → Accounts Receivable → Settings</strong>.
                                </span>
                            </div>
                        )}
                        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                        {['Receipt #', 'Customer', 'Date', 'Type', 'Amount', 'Remaining', 'Status', 'Actions'].map(h => (
                                            <th key={h} style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {loadingDownpayments ? (
                                        <tr><td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>Loading...</td></tr>
                                    ) : !downpayments?.length ? (
                                        <tr><td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <DollarSign size={40} style={{ margin: '0 auto 12px', opacity: 0.3, display: 'block' }} />
                                            No downpayments recorded yet.
                                        </td></tr>
                                    ) : downpayments.map((r: any) => (
                                        <tr key={r.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <td style={{ padding: '1rem 1.5rem', fontWeight: 600, color: '#7c3aed' }}>{r.receipt_number}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>{r.customer_name ?? '—'}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>{r.receipt_date}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>
                                                <span style={{ fontSize: '12px', padding: '2px 8px', borderRadius: '10px', background: 'rgba(124,58,237,0.08)', color: '#7c3aed', fontWeight: 600 }}>
                                                    {r.advance_type || 'Advance'}
                                                </span>
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', fontWeight: 600, fontFamily: 'monospace' }}>
                                                {r.currency_code} {parseFloat(r.total_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', fontFamily: 'monospace', color: parseFloat(r.advance_remaining) > 0 ? '#059669' : '#94a3b8' }}>
                                                {r.currency_code} {parseFloat(r.advance_remaining || '0').toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem' }}><StatusBadge status={r.status} /></td>
                                            <td style={{ padding: '0.75rem 1.5rem' }}>
                                                <div style={{ display: 'flex', gap: '8px' }}>
                                                    {r.status === 'Draft' && (
                                                        <>
                                                            <button onClick={() => setPostConfirm({ id: r.id, number: r.receipt_number })}
                                                                style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '5px 10px', borderRadius: '6px', border: 'none', background: '#7c3aed', color: '#fff', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}>
                                                                <Play size={12} /> Post
                                                            </button>
                                                            <button onClick={() => setDeleteConfirm({ id: r.id, number: r.receipt_number })}
                                                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '4px' }}>
                                                                <Trash2 size={15} />
                                                            </button>
                                                        </>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>

            {/* ── New Payment Modal ── */}
            {showPaymentForm && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '520px', maxHeight: '88vh', overflowY: 'auto' }}>
                        <h2 style={{ margin: '0 0 4px', fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>Record Incoming Payment</h2>
                        <p style={{ margin: '0 0 20px', fontSize: '13px', color: '#64748b' }}>
                            Record a customer payment received. Optionally link it to an open invoice.
                        </p>
                        <form onSubmit={handleSubmitPayment}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Customer *</label>
                                    <select style={sel} required value={paymentForm.customer} onChange={e => setPaymentForm(f => ({ ...f, customer: e.target.value }))}>
                                        <option value="">Select customer...</option>
                                        {customers?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Receipt Date *</label>
                                    <input style={inp} type="date" required value={paymentForm.receipt_date} onChange={e => setPaymentForm(f => ({ ...f, receipt_date: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Amount *</label>
                                    <input style={inp} type="number" step="0.01" min="0.01" required placeholder="0.00"
                                        value={paymentForm.total_amount} onChange={e => setPaymentForm(f => ({ ...f, total_amount: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Payment Method *</label>
                                    <select style={sel} required value={paymentForm.payment_method} onChange={e => setPaymentForm(f => ({ ...f, payment_method: e.target.value }))}>
                                        <option value="Cash">Cash</option>
                                        <option value="Check">Check</option>
                                        <option value="Wire">Wire Transfer</option>
                                        <option value="Credit Card">Credit Card</option>
                                    </select>
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Deposit to Bank Account</label>
                                    <select style={sel} value={paymentForm.bank_account} onChange={e => setPaymentForm(f => ({ ...f, bank_account: e.target.value }))}>
                                        <option value="">Select bank account...</option>
                                        {bankAccounts?.map((b: any) => <option key={b.id} value={b.id}>{b.name} — {b.account_number}</option>)}
                                    </select>
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>
                                        Allocate to Invoice <span style={{ fontWeight: 400, color: '#94a3b8' }}>(optional)</span>
                                    </label>
                                    <select style={sel} value={paymentForm.invoice} onChange={e => setPaymentForm(f => ({ ...f, invoice: e.target.value }))}>
                                        <option value="">— No invoice allocation —</option>
                                        {openInvoices?.map((inv: any) => (
                                            <option key={inv.id} value={inv.id}>
                                                {inv.invoice_number} · {inv.customer_name} · Balance: {inv.currency_code} {parseFloat(inv.balance_due || '0').toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Reference / Cheque #</label>
                                    <input style={inp} placeholder="Optional" value={paymentForm.reference_number}
                                        onChange={e => setPaymentForm(f => ({ ...f, reference_number: e.target.value }))} />
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                                <button type="button" onClick={() => { setShowPaymentForm(false); setPaymentForm({ ...BLANK_RECEIPT }); }}
                                    style={{ padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0', background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer' }}>
                                    Cancel
                                </button>
                                <button type="submit" disabled={createReceipt.isPending || createAllocation.isPending}
                                    style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#059669', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
                                    <ArrowDownLeft size={14} />
                                    {createReceipt.isPending || createAllocation.isPending ? 'Saving...' : 'Record Payment'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── New Downpayment Modal ── */}
            {showAdvanceForm && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '480px', maxHeight: '85vh', overflowY: 'auto' }}>
                        <h2 style={{ margin: '0 0 4px', fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>Record Customer Downpayment</h2>
                        <p style={{ margin: '0 0 20px', fontSize: '13px', color: '#64748b' }}>
                            Record an advance payment before an invoice is issued. Posts to the Customer Advances GL account.
                        </p>
                        <form onSubmit={handleSubmitAdvance}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Customer *</label>
                                    <select style={sel} required value={advanceForm.customer} onChange={e => setAdvanceForm(f => ({ ...f, customer: e.target.value }))}>
                                        <option value="">Select customer...</option>
                                        {customers?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Downpayment Type</label>
                                    <select style={sel} value={advanceForm.advance_type} onChange={e => setAdvanceForm(f => ({ ...f, advance_type: e.target.value as any }))}>
                                        <option value="Customer Advance">Customer Advance</option>
                                        <option value="Customer Deposit">Customer Deposit</option>
                                    </select>
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Date *</label>
                                    <input style={inp} type="date" required value={advanceForm.receipt_date} onChange={e => setAdvanceForm(f => ({ ...f, receipt_date: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Amount *</label>
                                    <input style={inp} type="number" step="0.01" required placeholder="0.00"
                                        value={advanceForm.total_amount} onChange={e => setAdvanceForm(f => ({ ...f, total_amount: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Payment Method *</label>
                                    <select style={sel} required value={advanceForm.payment_method} onChange={e => setAdvanceForm(f => ({ ...f, payment_method: e.target.value }))}>
                                        <option value="Cash">Cash</option>
                                        <option value="Check">Check</option>
                                        <option value="Wire">Wire Transfer</option>
                                        <option value="Credit Card">Credit Card</option>
                                    </select>
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Bank Account</label>
                                    <select style={sel} value={advanceForm.bank_account} onChange={e => setAdvanceForm(f => ({ ...f, bank_account: e.target.value }))}>
                                        <option value="">Select bank account...</option>
                                        {bankAccounts?.map((b: any) => <option key={b.id} value={b.id}>{b.name} — {b.account_number}</option>)}
                                    </select>
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Reference</label>
                                    <input style={inp} placeholder="Optional reference / memo" value={advanceForm.reference_number}
                                        onChange={e => setAdvanceForm(f => ({ ...f, reference_number: e.target.value }))} />
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                                <button type="button" onClick={() => { setShowAdvanceForm(false); setAdvanceForm({ ...BLANK_ADVANCE }); }}
                                    style={{ padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0', background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer' }}>
                                    Cancel
                                </button>
                                <button type="submit" disabled={createReceipt.isPending}
                                    style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#7c3aed', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
                                    <DollarSign size={14} />
                                    {createReceipt.isPending ? 'Saving...' : 'Record Downpayment'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Post Confirm Modal ── */}
            {postConfirm && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '420px' }}>
                        <h2 style={{ margin: '0 0 12px', fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>Post to GL?</h2>
                        <p style={{ margin: '0 0 24px', fontSize: '14px', color: '#64748b', lineHeight: 1.5 }}>
                            This will post <strong>{postConfirm.number}</strong> to the general ledger, creating journal entries and updating account balances. This action cannot be undone.
                        </p>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setPostConfirm(null)} style={{ padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0', background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
                            <button onClick={handlePost} disabled={postReceipt.isPending}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#059669', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
                                <Play size={14} /> {postReceipt.isPending ? 'Posting...' : 'Post to GL'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Delete Confirm Modal ── */}
            {deleteConfirm && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '420px' }}>
                        <h2 style={{ margin: '0 0 12px', fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>Delete Receipt?</h2>
                        <p style={{ margin: '0 0 24px', fontSize: '14px', color: '#64748b' }}>
                            Permanently delete <strong>{deleteConfirm.number}</strong>? This cannot be undone.
                        </p>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setDeleteConfirm(null)} style={{ padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0', background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
                            <button onClick={handleDelete} disabled={deleteReceipt.isPending}
                                style={{ padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#dc2626', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
                                {deleteReceipt.isPending ? 'Deleting...' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
