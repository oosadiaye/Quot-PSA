import { useState } from 'react';
import {
    ArrowUpRight, Play, Trash2, Plus, CheckCircle2, X, AlertTriangle,
    Banknote, TrendingDown, Clock, ShieldCheck, FileCheck2, CreditCard,
    RefreshCw, ChevronRight,
} from 'lucide-react';
import {
    usePayments, useCreatePayment, usePostPayment, useDeletePayment,
    useCreatePaymentAllocation, useVendorInvoices,
} from '../hooks/useAccountingEnhancements';
import {
    useVendors, useDownPaymentRequests, useProcessDownPayment,
    useInvoiceMatchings, useMatchInvoice,
} from '../../procurement/hooks/useProcurement';
import { useBankAccounts } from '../../settings/hooks/useBankAccounts';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import { useCurrency } from '../../../context/CurrencyContext';
import '../styles/glassmorphism.css';

// ─── styles ──────────────────────────────────────────────────────────────────
const inp: React.CSSProperties = {
    width: '100%', padding: '8px 12px', border: '2.5px solid #d1d5db',
    borderRadius: '8px', fontSize: '14px', outline: 'none',
    background: '#fafbfc', color: '#1e293b', boxSizing: 'border-box',
};
const sel: React.CSSProperties = { ...inp, cursor: 'pointer' };

type ActiveTab = 'payments' | 'verification' | 'advances';

const BLANK_PAYMENT = {
    vendor: '', payment_date: new Date().toISOString().slice(0, 10),
    total_amount: '', payment_method: 'Wire', bank_account: '',
    reference_number: '', invoice: '',
};
const BLANK_ADVANCE = {
    vendor: '', payment_date: new Date().toISOString().slice(0, 10),
    total_amount: '', payment_method: 'Wire', bank_account: '',
    reference_number: '', advance_type: 'Vendor Advance' as 'Vendor Advance' | 'Vendor Deposit',
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

// ─── confirm modal ────────────────────────────────────────────────────────────
function ConfirmModal({ title, message, confirmLabel, confirmColor, onConfirm, onCancel }: {
    title: string; message: string; confirmLabel: string;
    confirmColor: string; onConfirm: () => void; onCancel: () => void;
}) {
    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: '14px', padding: '28px 32px', width: 420, boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
                <h3 style={{ margin: '0 0 8px', fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>{title}</h3>
                <p style={{ margin: '0 0 24px', fontSize: '14px', color: '#64748b' }}>{message}</p>
                <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                    <button onClick={onCancel} style={{ padding: '8px 18px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px', color: '#374151' }}>Cancel</button>
                    <button onClick={onConfirm} style={{ padding: '8px 18px', border: 'none', borderRadius: '8px', background: confirmColor, color: '#fff', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>{confirmLabel}</button>
                </div>
            </div>
        </div>
    );
}

// ─── payment form modal ───────────────────────────────────────────────────────
function PaymentFormModal({ vendors, bankAccounts, openInvoices, onSubmit, onClose, isLoading }: {
    vendors: any[]; bankAccounts: any[]; openInvoices: any[];
    onSubmit: (form: typeof BLANK_PAYMENT) => void; onClose: () => void; isLoading: boolean;
}) {
    const [form, setForm] = useState({ ...BLANK_PAYMENT });
    const set = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }));

    const selectedVendorInvoices = openInvoices.filter(
        (inv: any) => !form.vendor || String(inv.vendor) === form.vendor
    );

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: '16px', padding: '32px', width: 520, boxShadow: '0 24px 80px rgba(0,0,0,0.22)', maxHeight: '90vh', overflowY: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: 40, height: 40, borderRadius: '10px', background: 'linear-gradient(135deg,#f59e0b,#d97706)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Banknote size={20} color="#fff" />
                    </div>
                    <div>
                        <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>New Outgoing Payment</h3>
                        <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>Process vendor payment</p>
                    </div>
                    <button onClick={onClose} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}><X size={20} color="#94a3b8" /></button>
                </div>
                <form onSubmit={e => { e.preventDefault(); onSubmit(form); }}>
                    <div style={{ display: 'grid', gap: '14px' }}>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Vendor *</label>
                            <select style={sel} value={form.vendor} onChange={e => set('vendor', e.target.value)} required>
                                <option value="">Select vendor…</option>
                                {vendors?.map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}
                            </select>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Payment Date *</label>
                                <input style={inp} type="date" value={form.payment_date} onChange={e => set('payment_date', e.target.value)} required />
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Amount *</label>
                                <input style={inp} type="number" placeholder="0.00" step="0.01" value={form.total_amount} onChange={e => set('total_amount', e.target.value)} required />
                            </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Method *</label>
                                <select style={sel} value={form.payment_method} onChange={e => set('payment_method', e.target.value)}>
                                    {['Wire', 'Cheque', 'Cash', 'Bank Transfer', 'EFT'].map(m => <option key={m}>{m}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Bank Account</label>
                                <select style={sel} value={form.bank_account} onChange={e => set('bank_account', e.target.value)}>
                                    <option value="">— none —</option>
                                    {bankAccounts?.map((b: any) => <option key={b.id} value={b.id}>{b.name}</option>)}
                                </select>
                            </div>
                        </div>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Reference Number</label>
                            <input style={inp} type="text" placeholder="CHQ-001 / TRF-REF…" value={form.reference_number} onChange={e => set('reference_number', e.target.value)} />
                        </div>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Allocate to Invoice (optional)</label>
                            <select style={sel} value={form.invoice} onChange={e => set('invoice', e.target.value)}>
                                <option value="">— no allocation —</option>
                                {selectedVendorInvoices?.map((inv: any) => (
                                    <option key={inv.id} value={inv.id}>
                                        {inv.invoice_number} · {inv.vendor_name} · Balance: {parseFloat(inv.total_amount) - parseFloat(inv.paid_amount || '0')}
                                    </option>
                                ))}
                            </select>
                            <p style={{ fontSize: '11px', color: '#94a3b8', margin: '4px 0 0' }}>Only approved &amp; matched invoices can be posted.</p>
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', marginTop: '24px', justifyContent: 'flex-end' }}>
                        <button type="button" onClick={onClose} style={{ padding: '9px 20px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
                        <button type="submit" disabled={isLoading} style={{ padding: '9px 20px', border: 'none', borderRadius: '8px', background: 'linear-gradient(135deg,#f59e0b,#d97706)', color: '#fff', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                            {isLoading ? 'Saving…' : 'Save Payment'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ─── advance form modal ───────────────────────────────────────────────────────
function AdvanceFormModal({ vendors, bankAccounts, onSubmit, onClose, isLoading }: {
    vendors: any[]; bankAccounts: any[];
    onSubmit: (form: typeof BLANK_ADVANCE) => void; onClose: () => void; isLoading: boolean;
}) {
    const [form, setForm] = useState({ ...BLANK_ADVANCE });
    const set = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }));

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: '16px', padding: '32px', width: 480, boxShadow: '0 24px 80px rgba(0,0,0,0.22)', maxHeight: '90vh', overflowY: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: 40, height: 40, borderRadius: '10px', background: 'linear-gradient(135deg,#8b5cf6,#6d28d9)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <TrendingDown size={20} color="#fff" />
                    </div>
                    <div>
                        <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>New Vendor Advance</h3>
                        <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>Down payment from purchase order</p>
                    </div>
                    <button onClick={onClose} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}><X size={20} color="#94a3b8" /></button>
                </div>
                <form onSubmit={e => { e.preventDefault(); onSubmit(form); }}>
                    <div style={{ display: 'grid', gap: '14px' }}>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Vendor *</label>
                            <select style={sel} value={form.vendor} onChange={e => set('vendor', e.target.value)} required>
                                <option value="">Select vendor…</option>
                                {vendors?.map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Advance Type</label>
                            <select style={sel} value={form.advance_type} onChange={e => set('advance_type', e.target.value)}>
                                <option value="Vendor Advance">Vendor Advance</option>
                                <option value="Vendor Deposit">Vendor Deposit</option>
                            </select>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Payment Date *</label>
                                <input style={inp} type="date" value={form.payment_date} onChange={e => set('payment_date', e.target.value)} required />
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Amount *</label>
                                <input style={inp} type="number" placeholder="0.00" step="0.01" value={form.total_amount} onChange={e => set('total_amount', e.target.value)} required />
                            </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Method *</label>
                                <select style={sel} value={form.payment_method} onChange={e => set('payment_method', e.target.value)}>
                                    {['Wire', 'Cheque', 'Cash', 'Bank Transfer', 'EFT'].map(m => <option key={m}>{m}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Bank Account</label>
                                <select style={sel} value={form.bank_account} onChange={e => set('bank_account', e.target.value)}>
                                    <option value="">— none —</option>
                                    {bankAccounts?.map((b: any) => <option key={b.id} value={b.id}>{b.name}</option>)}
                                </select>
                            </div>
                        </div>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Reference Number</label>
                            <input style={inp} type="text" placeholder="PO-2024-001…" value={form.reference_number} onChange={e => set('reference_number', e.target.value)} />
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', marginTop: '24px', justifyContent: 'flex-end' }}>
                        <button type="button" onClick={onClose} style={{ padding: '9px 20px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
                        <button type="submit" disabled={isLoading} style={{ padding: '9px 20px', border: 'none', borderRadius: '8px', background: 'linear-gradient(135deg,#8b5cf6,#6d28d9)', color: '#fff', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                            {isLoading ? 'Saving…' : 'Save Advance'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ─── main page ────────────────────────────────────────────────────────────────
export default function OutgoingPaymentsPage() {
    const { formatCurrency } = useCurrency();
    const [activeTab, setActiveTab] = useState<ActiveTab>('payments');
    const [notification, setNotification] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

    // Payment forms
    const [showPaymentForm, setShowPaymentForm] = useState(false);
    const [showAdvanceForm, setShowAdvanceForm] = useState(false);

    // Confirm modals
    const [postConfirm, setPostConfirm] = useState<{ id: number; number: string } | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<{ id: number; number: string } | null>(null);
    const [matchConfirm, setMatchConfirm] = useState<{ id: number; ref: string } | null>(null);
    const [processAdvanceConfirm, setProcessAdvanceConfirm] = useState<{ id: number; ref: string } | null>(null);

    // ─── queries ─────────────────────────────────────────────────────────────
    const { data: payments, isLoading: loadingPayments } = usePayments({ is_advance: false });
    const { data: advances, isLoading: loadingAdvances } = usePayments({ is_advance: true });
    const { data: vendors } = useVendors();
    const { data: bankAccounts } = useBankAccounts({ is_active: true });
    const { data: openInvoices } = useVendorInvoices({ status: 'Approved' });
    const { data: invoiceMatchings, isLoading: loadingMatchings } = useInvoiceMatchings({});
    const { data: downPaymentRequests, isLoading: loadingDPR } = useDownPaymentRequests({ status: 'Approved' });

    // ─── mutations ────────────────────────────────────────────────────────────
    const createPayment = useCreatePayment();
    const createAllocation = useCreatePaymentAllocation();
    const postPayment = usePostPayment();
    const deletePayment = useDeletePayment();
    const matchInvoice = useMatchInvoice();
    const processDownPayment = useProcessDownPayment();

    // ─── helpers ──────────────────────────────────────────────────────────────
    const showSuccess = (msg: string) => { setNotification({ msg, type: 'success' }); setTimeout(() => setNotification(null), 3500); };
    const showError   = (msg: string) => { setNotification({ msg, type: 'error'   }); setTimeout(() => setNotification(null), 4500); };

    // ─── summary metrics ──────────────────────────────────────────────────────
    const todayStr        = new Date().toISOString().slice(0, 10);
    const paidToday       = (payments as any[])?.filter(p => p.payment_date === todayStr)
        .reduce((s, p) => s + parseFloat(p.total_amount || '0'), 0) || 0;
    const pendingPosting  = (payments as any[])?.filter(p => p.status === 'Draft').length || 0;
    const postedCount     = (payments as any[])?.filter(p => p.status === 'Posted').length || 0;
    const advanceBalance  = (advances as any[])?.reduce((s, p) => s + parseFloat(p.advance_remaining || '0'), 0) || 0;
    const matchingsList: any[] = Array.isArray(invoiceMatchings)
        ? invoiceMatchings
        : ((invoiceMatchings as any)?.results ?? []);
    const pendingMatching = matchingsList.filter((m: any) => m.status === 'Pending').length;

    // ─── handlers ─────────────────────────────────────────────────────────────
    const handleSubmitPayment = async (form: typeof BLANK_PAYMENT) => {
        try {
            const payment = await createPayment.mutateAsync({
                vendor: Number(form.vendor) || undefined,
                payment_date: form.payment_date,
                total_amount: form.total_amount,
                payment_method: form.payment_method,
                bank_account: form.bank_account ? Number(form.bank_account) : undefined,
                reference_number: form.reference_number || undefined,
            } as any);
            if (form.invoice) {
                await createAllocation.mutateAsync({
                    payment: payment.id,
                    invoice: Number(form.invoice),
                    amount: form.total_amount,
                });
            }
            setShowPaymentForm(false);
            showSuccess('Payment saved successfully.');
        } catch (err: any) {
            showError(err?.response?.data?.error || err?.response?.data?.detail || 'Failed to save payment.');
        }
    };

    const handleSubmitAdvance = async (form: typeof BLANK_ADVANCE) => {
        try {
            await createPayment.mutateAsync({
                vendor: Number(form.vendor) || undefined,
                payment_date: form.payment_date,
                total_amount: form.total_amount,
                payment_method: form.payment_method,
                bank_account: form.bank_account ? Number(form.bank_account) : undefined,
                reference_number: form.reference_number || undefined,
                is_advance: true,
                advance_type: form.advance_type,
            } as any);
            setShowAdvanceForm(false);
            showSuccess('Vendor advance saved successfully.');
        } catch (err: any) {
            showError(err?.response?.data?.error || 'Failed to save advance.');
        }
    };

    const handlePost = async () => {
        if (!postConfirm) return;
        try {
            await postPayment.mutateAsync(postConfirm.id);
            setPostConfirm(null);
            showSuccess(`Payment ${postConfirm.number} posted to General Ledger.`);
        } catch (err: any) {
            setPostConfirm(null);
            showError(err?.response?.data?.error || 'Failed to post payment.');
        }
    };

    const handleDelete = async () => {
        if (!deleteConfirm) return;
        try {
            await deletePayment.mutateAsync(deleteConfirm.id);
            setDeleteConfirm(null);
            showSuccess(`Payment ${deleteConfirm.number} deleted.`);
        } catch (err: any) {
            setDeleteConfirm(null);
            showError(err?.response?.data?.error || 'Failed to delete payment.');
        }
    };

    const handleMatch = async () => {
        if (!matchConfirm) return;
        try {
            await matchInvoice.mutateAsync({ id: matchConfirm.id });
            setMatchConfirm(null);
            showSuccess(`Invoice matching ${matchConfirm.ref} approved.`);
        } catch (err: any) {
            setMatchConfirm(null);
            showError(err?.response?.data?.error || 'Failed to approve matching.');
        }
    };

    const handleProcessAdvance = async () => {
        if (!processAdvanceConfirm) return;
        try {
            await processDownPayment.mutateAsync(processAdvanceConfirm.id);
            setProcessAdvanceConfirm(null);
            showSuccess(`Down payment request ${processAdvanceConfirm.ref} processed.`);
        } catch (err: any) {
            setProcessAdvanceConfirm(null);
            showError(err?.response?.data?.error || 'Failed to process down payment.');
        }
    };

    // ─── shared card ──────────────────────────────────────────────────────────
    const SummaryCard = ({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent: string }) => (
        <div style={{
            background: '#fff', borderRadius: '14px', padding: '20px 22px',
            border: '1px solid #f1f5f9', boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
            borderLeft: `4px solid ${accent}`,
        }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>{label}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: '#1e293b', letterSpacing: '-0.5px' }}>{value}</div>
            {sub && <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>{sub}</div>}
        </div>
    );

    // ─── payments tab (JSX variable — avoids sub-component remount on parent state changes) ───
    const paymentsTabJSX = (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Vendor Payments</h3>
                    <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#64748b' }}>Process and post outgoing payments to vendors</p>
                </div>
                <button onClick={() => setShowPaymentForm(true)} style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '9px 18px', border: 'none', borderRadius: '9px',
                    background: 'linear-gradient(135deg,#f59e0b,#d97706)', color: '#fff',
                    cursor: 'pointer', fontSize: '13px', fontWeight: 600,
                }}>
                    <Plus size={15} /> New Payment
                </button>
            </div>

            {loadingPayments ? (
                <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading payments…</div>
            ) : !(payments as any[])?.length ? (
                <div style={{ textAlign: 'center', padding: '60px 20px', background: '#f8fafc', borderRadius: '12px', border: '2px dashed #e2e8f0' }}>
                    <Banknote size={40} color="#cbd5e1" style={{ marginBottom: '12px' }} />
                    <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>No payments yet. Click "New Payment" to start.</p>
                </div>
            ) : (
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                        <thead>
                            <tr style={{ background: '#f8fafc' }}>
                                {['Payment #', 'Vendor', 'Date', 'Amount', 'Method', 'Reference', 'Status', 'Actions'].map(h => (
                                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {(payments as any[])?.map((pay: any) => (
                                <tr key={pay.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                    <td style={{ padding: '11px 14px', fontWeight: 600, color: '#1e293b' }}>{pay.payment_number}</td>
                                    <td style={{ padding: '11px 14px', color: '#374151' }}>{pay.vendor_name || '—'}</td>
                                    <td style={{ padding: '11px 14px', color: '#374151' }}>{pay.payment_date}</td>
                                    <td style={{ padding: '11px 14px', fontWeight: 700, color: '#dc2626' }}>{formatCurrency(pay.total_amount)}</td>
                                    <td style={{ padding: '11px 14px', color: '#374151' }}>{pay.payment_method}</td>
                                    <td style={{ padding: '11px 14px', color: '#64748b', fontFamily: 'monospace', fontSize: '12px' }}>{pay.reference_number || '—'}</td>
                                    <td style={{ padding: '11px 14px' }}><StatusBadge status={pay.status} /></td>
                                    <td style={{ padding: '11px 14px' }}>
                                        <div style={{ display: 'flex', gap: '6px' }}>
                                            {pay.status === 'Draft' && (
                                                <>
                                                    <button onClick={() => setPostConfirm({ id: pay.id, number: pay.payment_number })}
                                                        title="Post payment"
                                                        style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#dcfce7', color: '#166534', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: 600 }}>
                                                        <Play size={12} /> Post
                                                    </button>
                                                    <button onClick={() => setDeleteConfirm({ id: pay.id, number: pay.payment_number })}
                                                        title="Delete"
                                                        style={{ padding: '5px 8px', border: 'none', borderRadius: '6px', background: '#fee2e2', color: '#dc2626', cursor: 'pointer' }}>
                                                        <Trash2 size={12} />
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
            )}
        </div>
    );

    // ─── invoice verification tab ─────────────────────────────────────────────
    const matchings = matchingsList;

    const verificationTabJSX = (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Invoice Verification (3-Way Match)</h3>
                    <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#64748b' }}>Review PO → GRN → Invoice matchings before releasing payment</p>
                </div>
            </div>
            <div style={{
                display: 'flex', alignItems: 'flex-start', gap: '10px',
                background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '10px',
                padding: '12px 16px', marginBottom: '20px',
            }}>
                <ShieldCheck size={16} color="#2563eb" style={{ marginTop: '1px', flexShrink: 0 }} />
                <p style={{ margin: 0, fontSize: '13px', color: '#1e40af', lineHeight: 1.5 }}>
                    Payments can only be posted after invoices are matched. Approve pending matchings here to unlock payment posting.
                </p>
            </div>

            {loadingMatchings ? (
                <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading matchings…</div>
            ) : !matchings.length ? (
                <div style={{ textAlign: 'center', padding: '60px 20px', background: '#f8fafc', borderRadius: '12px', border: '2px dashed #e2e8f0' }}>
                    <FileCheck2 size={40} color="#cbd5e1" style={{ marginBottom: '12px' }} />
                    <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>No invoice matchings found. Create them from the Procurement module.</p>
                </div>
            ) : (
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                        <thead>
                            <tr style={{ background: '#f8fafc' }}>
                                {['Invoice Ref', 'PO', 'GRN', 'Invoice Date', 'Amount', 'Variance', 'Status', 'Actions'].map(h => (
                                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {matchings.map((m: any) => (
                                <tr key={m.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                    <td style={{ padding: '11px 14px', fontWeight: 600, color: '#1e293b' }}>{m.invoice_reference}</td>
                                    <td style={{ padding: '11px 14px', color: '#374151' }}>{m.purchase_order_number || m.purchase_order || '—'}</td>
                                    <td style={{ padding: '11px 14px', color: '#374151' }}>{m.grn_number || m.goods_received_note || '—'}</td>
                                    <td style={{ padding: '11px 14px', color: '#374151' }}>{m.invoice_date}</td>
                                    <td style={{ padding: '11px 14px', fontWeight: 700, color: '#1e293b' }}>{formatCurrency(m.invoice_amount)}</td>
                                    <td style={{ padding: '11px 14px' }}>
                                        {m.variance_amount && parseFloat(m.variance_amount) !== 0
                                            ? <span style={{ color: '#d97706', fontWeight: 600 }}>{formatCurrency(m.variance_amount)}</span>
                                            : <span style={{ color: '#16a34a', fontSize: '12px' }}>None</span>}
                                    </td>
                                    <td style={{ padding: '11px 14px' }}><StatusBadge status={m.status} /></td>
                                    <td style={{ padding: '11px 14px' }}>
                                        {m.status === 'Pending' && (
                                            <button onClick={() => setMatchConfirm({ id: m.id, ref: m.invoice_reference })}
                                                style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#dcfce7', color: '#166534', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: 600 }}>
                                                <CheckCircle2 size={12} /> Approve Match
                                            </button>
                                        )}
                                        {m.status === 'Matched' && (
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#16a34a', fontSize: '12px', fontWeight: 600 }}>
                                                <CheckCircle2 size={12} /> Matched
                                            </span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );

    // ─── advances tab ─────────────────────────────────────────────────────────
    const dprList: any[] = Array.isArray(downPaymentRequests)
        ? downPaymentRequests
        : ((downPaymentRequests as any)?.results ?? []);

    const advancesTabJSX = (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Vendor Advances & Downpayments</h3>
                    <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#64748b' }}>Process procurement-approved down payment requests and record vendor advances</p>
                </div>
                <button onClick={() => setShowAdvanceForm(true)} style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '9px 18px', border: 'none', borderRadius: '9px',
                    background: 'linear-gradient(135deg,#8b5cf6,#6d28d9)', color: '#fff',
                    cursor: 'pointer', fontSize: '13px', fontWeight: 600,
                }}>
                    <Plus size={15} /> New Advance
                </button>
            </div>

            {/* Procurement-approved DPRs */}
            <div style={{ marginBottom: '28px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#8b5cf6' }} />
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#374151' }}>Procurement Down Payment Requests (Approved)</span>
                </div>
                {loadingDPR ? (
                    <div style={{ textAlign: 'center', padding: '20px', color: '#94a3b8' }}>Loading…</div>
                ) : !dprList.length ? (
                    <div style={{ padding: '20px', background: '#f8fafc', borderRadius: '10px', border: '1px dashed #e2e8f0', textAlign: 'center' }}>
                        <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>No approved down payment requests from procurement.</p>
                    </div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                            <thead>
                                <tr style={{ background: '#faf5ff' }}>
                                    {['Request #', 'PO', 'Vendor', 'Amount', 'Type', 'Status', 'Actions'].map(h => (
                                        <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#7c3aed', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #ede9fe', whiteSpace: 'nowrap' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {dprList.map((dpr: any) => (
                                    <tr key={dpr.id} style={{ borderBottom: '1px solid #f5f3ff' }}>
                                        <td style={{ padding: '11px 14px', fontWeight: 600, color: '#1e293b' }}>{dpr.request_number || `DPR-${dpr.id}`}</td>
                                        <td style={{ padding: '11px 14px', color: '#374151' }}>{dpr.po_number || dpr.purchase_order || '—'}</td>
                                        <td style={{ padding: '11px 14px', color: '#374151' }}>{dpr.vendor_name || '—'}</td>
                                        <td style={{ padding: '11px 14px', fontWeight: 700, color: '#6d28d9' }}>{formatCurrency(dpr.amount)}</td>
                                        <td style={{ padding: '11px 14px', color: '#374151' }}>{dpr.payment_type || 'Advance'}</td>
                                        <td style={{ padding: '11px 14px' }}><StatusBadge status={dpr.status} /></td>
                                        <td style={{ padding: '11px 14px' }}>
                                            {dpr.status === 'Approved' && (
                                                <button onClick={() => setProcessAdvanceConfirm({ id: dpr.id, ref: dpr.request_number || `DPR-${dpr.id}` })}
                                                    style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#ede9fe', color: '#6d28d9', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: 600 }}>
                                                    <ChevronRight size={12} /> Process
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Manual advances */}
            <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#d97706' }} />
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#374151' }}>Manual Vendor Advances</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px', padding: '10px 14px', marginBottom: '12px' }}>
                    <AlertTriangle size={14} color="#d97706" style={{ marginTop: '1px', flexShrink: 0 }} />
                    <p style={{ margin: 0, fontSize: '12px', color: '#92400e' }}>
                        Manual advances are recorded for reference only. To post an advance to the GL, create a <strong>Down Payment Request</strong> in the Procurement module, get it approved, then use the "Process" button in the section above.
                    </p>
                </div>
                {loadingAdvances ? (
                    <div style={{ textAlign: 'center', padding: '20px', color: '#94a3b8' }}>Loading…</div>
                ) : !(advances as any[])?.length ? (
                    <div style={{ padding: '20px', background: '#f8fafc', borderRadius: '10px', border: '1px dashed #e2e8f0', textAlign: 'center' }}>
                        <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>No manual advances recorded. Use "New Advance" above.</p>
                    </div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                            <thead>
                                <tr style={{ background: '#fffbeb' }}>
                                    {['Payment #', 'Vendor', 'Date', 'Amount', 'Type', 'Remaining', 'Status'].map(h => (
                                        <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#92400e', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #fde68a', whiteSpace: 'nowrap' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {(advances as any[])?.map((adv: any) => (
                                    <tr key={adv.id} style={{ borderBottom: '1px solid #fef9c3' }}>
                                        <td style={{ padding: '11px 14px', fontWeight: 600, color: '#1e293b' }}>{adv.payment_number}</td>
                                        <td style={{ padding: '11px 14px', color: '#374151' }}>{adv.vendor_name || '—'}</td>
                                        <td style={{ padding: '11px 14px', color: '#374151' }}>{adv.payment_date}</td>
                                        <td style={{ padding: '11px 14px', fontWeight: 700, color: '#d97706' }}>{formatCurrency(adv.total_amount)}</td>
                                        <td style={{ padding: '11px 14px', color: '#374151' }}>{adv.advance_type || 'Vendor Advance'}</td>
                                        <td style={{ padding: '11px 14px', fontWeight: 600, color: parseFloat(adv.advance_remaining || '0') > 0 ? '#d97706' : '#16a34a' }}>
                                            {formatCurrency(adv.advance_remaining || '0')}
                                        </td>
                                        <td style={{ padding: '11px 14px' }}><StatusBadge status={adv.status} /></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );

    // ─── render ───────────────────────────────────────────────────────────────
    return (
        <AccountingLayout>
            <PageHeader title="Outgoing Payments" subtitle="Payments Team · AP & Procurement Disbursements" />

            {/* SOD banner */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '10px',
                background: 'linear-gradient(135deg,#fff7ed,#fffbeb)',
                border: '1px solid #fbbf24', borderRadius: '12px',
                padding: '12px 18px', marginBottom: '22px',
            }}>
                <ArrowUpRight size={18} color="#d97706" />
                <div>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#92400e' }}>Payments Team — Disbursements</span>
                    <span style={{ fontSize: '12px', color: '#b45309', marginLeft: '10px' }}>
                        SOD enforced: AP clerks create invoices · Payments team releases funds
                    </span>
                </div>
            </div>

            {/* Summary cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px,1fr))', gap: '14px', marginBottom: '24px' }}>
                <SummaryCard label="Paid Today" value={formatCurrency(paidToday)} sub={`${(payments as any[])?.filter(p => p.payment_date === todayStr).length || 0} payments`} accent="#f59e0b" />
                <SummaryCard label="Pending Posting" value={pendingPosting} sub="Draft payments" accent="#3b82f6" />
                <SummaryCard label="Posted" value={postedCount} sub="This period" accent="#10b981" />
                <SummaryCard label="Advance Balance" value={formatCurrency(advanceBalance)} sub="Outstanding vendor advances" accent="#8b5cf6" />
                <SummaryCard label="Pending Match" value={pendingMatching} sub="Invoices to verify" accent="#ef4444" />
            </div>

            {notification && (
                <InlineAlert msg={notification.msg} type={notification.type} onClose={() => setNotification(null)} />
            )}

            {/* Tabs */}
            <div style={{ background: '#fff', borderRadius: '16px', border: '1px solid #e2e8f0', boxShadow: '0 1px 6px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
                <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                    {([
                        { key: 'payments',     label: 'Payments',             icon: <CreditCard size={14} /> },
                        { key: 'verification', label: 'Invoice Verification',  icon: <FileCheck2 size={14} /> },
                        { key: 'advances',     label: 'Vendor Advances',       icon: <TrendingDown size={14} /> },
                    ] as { key: ActiveTab; label: string; icon: React.ReactNode }[]).map(tab => (
                        <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '13px 20px', border: 'none', cursor: 'pointer',
                            fontSize: '13px', fontWeight: activeTab === tab.key ? 700 : 500,
                            color: activeTab === tab.key ? '#d97706' : '#64748b',
                            background: 'none',
                            borderBottom: activeTab === tab.key ? '2.5px solid #d97706' : '2.5px solid transparent',
                            transition: 'all 0.15s',
                        }}>
                            {tab.icon} {tab.label}
                            {tab.key === 'verification' && pendingMatching > 0 && (
                                <span style={{ background: '#ef4444', color: '#fff', borderRadius: '10px', padding: '1px 6px', fontSize: '10px', fontWeight: 700 }}>{pendingMatching}</span>
                            )}
                        </button>
                    ))}
                </div>
                <div style={{ padding: '24px' }}>
                    {activeTab === 'payments'     && paymentsTabJSX}
                    {activeTab === 'verification' && verificationTabJSX}
                    {activeTab === 'advances'     && advancesTabJSX}
                </div>
            </div>

            {/* Modals */}
            {showPaymentForm && (
                <PaymentFormModal
                    vendors={vendors || []}
                    bankAccounts={bankAccounts || []}
                    openInvoices={openInvoices || []}
                    onSubmit={handleSubmitPayment}
                    onClose={() => setShowPaymentForm(false)}
                    isLoading={createPayment.isPending || createAllocation.isPending}
                />
            )}
            {showAdvanceForm && (
                <AdvanceFormModal
                    vendors={vendors || []}
                    bankAccounts={bankAccounts || []}
                    onSubmit={handleSubmitAdvance}
                    onClose={() => setShowAdvanceForm(false)}
                    isLoading={createPayment.isPending}
                />
            )}
            {postConfirm && (
                <ConfirmModal
                    title="Post Payment"
                    message={`Post payment ${postConfirm.number} to the General Ledger? This action cannot be undone.`}
                    confirmLabel="Post"
                    confirmColor="#16a34a"
                    onConfirm={handlePost}
                    onCancel={() => setPostConfirm(null)}
                />
            )}
            {deleteConfirm && (
                <ConfirmModal
                    title="Delete Payment"
                    message={`Delete payment ${deleteConfirm.number}? This cannot be undone.`}
                    confirmLabel="Delete"
                    confirmColor="#dc2626"
                    onConfirm={handleDelete}
                    onCancel={() => setDeleteConfirm(null)}
                />
            )}
            {matchConfirm && (
                <ConfirmModal
                    title="Approve Invoice Match"
                    message={`Mark invoice ${matchConfirm.ref} as Matched? This will allow payments against this invoice to be posted.`}
                    confirmLabel="Approve Match"
                    confirmColor="#2563eb"
                    onConfirm={handleMatch}
                    onCancel={() => setMatchConfirm(null)}
                />
            )}
            {processAdvanceConfirm && (
                <ConfirmModal
                    title="Process Down Payment"
                    message={`Process down payment request ${processAdvanceConfirm.ref}? This will create an outgoing payment record.`}
                    confirmLabel="Process"
                    confirmColor="#6d28d9"
                    onConfirm={handleProcessAdvance}
                    onCancel={() => setProcessAdvanceConfirm(null)}
                />
            )}
        </AccountingLayout>
    );
}
