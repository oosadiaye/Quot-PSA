import { useState } from 'react';
import {
    ArrowUpRight, Play, Trash2, Plus, CheckCircle2, X, AlertTriangle, Eye, BookOpen,
    Banknote, TrendingDown, CreditCard,
    ChevronRight,
} from 'lucide-react';
import { useFocusTrap } from '../../../hooks/useFocusTrap';
import {
    usePayments, useCreatePayment, useUpdatePayment, usePostPayment, useDeletePayment,
    useCreatePaymentAllocation, useVendorInvoices,
    useAccountingSettings,
} from '../hooks/useAccountingEnhancements';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import {
    useVendors, useDownPaymentRequests, useProcessDownPayment,
} from '../../procurement/hooks/useProcurement';
import { useClearVendorAdvance } from '../hooks/useVendorAdvances';
import {
    JournalHeaderStrip, JournalLinesTable,
    type JournalDetail,
} from '../components/shared/JournalViewer';
import { useBankAccounts } from '../../settings/hooks/useBankAccounts';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import { useCurrency } from '../../../context/CurrencyContext';
import AmountInput from '../../../components/AmountInput';
import '../styles/glassmorphism.css';

// ─── styles ──────────────────────────────────────────────────────────────────
const inp: React.CSSProperties = {
    width: '100%', padding: '8px 12px', border: '2.5px solid #d1d5db',
    borderRadius: '8px', fontSize: '14px', outline: 'none',
    background: '#fafbfc', color: '#1e293b', boxSizing: 'border-box',
};
const sel: React.CSSProperties = { ...inp, cursor: 'pointer' };

type ActiveTab = 'payments' | 'advances';

// ─── domain row shapes ────────────────────────────────────────────────────
// Minimal interfaces covering only the fields this page reads. Kept
// narrow on purpose — the API surface is broader, but expanding these
// interfaces field-by-field as new accessors are added catches schema
// drift at compile time. Numeric/decimal fields arrive as strings from
// DRF (see DecimalField serialization) so we type them as ``string``.
interface Vendor {
    id: number;
    name: string;
}
interface BankAccount {
    id: number;
    name: string;
}
interface VendorInvoiceRow {
    id: number;
    vendor: number;
    vendor_name: string;
    invoice_number: string;
    total_amount: string;
    paid_amount?: string;
    // Authoritative outstanding from the serializer. Preferred over
    // ``total_amount - paid_amount`` when present.
    balance_due?: string;
}
interface PaymentVoucherRow {
    id: number;
    voucher_number: string;
    payee_name?: string;
    vendor?: number | null;
    invoice_vendor?: number | null;
    net_amount?: string;
    gross_amount?: string;
}
interface PaymentRow {
    id: number;
    payment_number: string;
    payment_date: string;
    vendor: number | null;
    vendor_name?: string;
    total_amount: string;
    payment_method: string;
    bank_account?: number | null;
    reference_number?: string;
    payment_voucher?: number | null;
    status: 'Draft' | 'Posted' | 'Cancelled' | string;
    is_advance?: boolean;
    advance_remaining?: string;
    advance_type?: string;
    // Set by the backend serializer once an advance has been posted:
    // the id of the VendorAdvance Special-GL ledger row that this
    // Payment created. Used by the Clear button to call /clear/
    // without an extra round-trip. Null for non-advance payments or
    // advances that haven't been posted yet.
    linked_vendor_advance_id?: number | null;
    // JournalHeader FK id — set by post_payment / _post_advance_payment
    // once the disbursement journal posts. Drives the View Journal
    // button visibility (only Posted rows with a journal can be viewed).
    journal_entry?: number | null;
}
interface DownPaymentRequestRow {
    id: number;
    request_number?: string;
    po_number?: string;
    purchase_order?: number | null;
    vendor_name?: string;
    amount: string;
    payment_type?: string;
    status: 'Approved' | string;
}

// Axios error shape after the API client transforms backend DRF
// responses. ``response.data`` carries either ``error`` (custom action
// endpoints), ``detail`` (default DRF), or ``non_field_errors``.
// Centralising this helper means every catch handler narrows the
// unknown error the same way.
interface ApiErrorBody {
    error?: string;
    detail?: string;
    non_field_errors?: string[];
}
interface ApiError {
    message?: string;
    response?: { data?: ApiErrorBody };
}
function extractApiErrorMessage(err: unknown, fallback: string): string {
    const e = err as ApiError;
    const body = e?.response?.data;
    if (body?.error) return body.error;
    if (body?.detail) return body.detail;
    if (body?.non_field_errors?.length) return body.non_field_errors.join(' ');
    return e?.message || fallback;
}

// ``Object.freeze`` so the form templates cannot be mutated by any
// caller (even by accident). Spread copies (`{ ...BLANK_PAYMENT }`)
// still work — they create a new mutable object — but a stray
// ``BLANK_PAYMENT.vendor = 'X'`` would now throw in strict mode and
// fail silently in non-strict. The previous unfrozen template
// caused every subsequent form open to inherit any mutation made by
// earlier code paths.
type PaymentForm = {
    vendor: string; payment_date: string; total_amount: string;
    payment_method: string; bank_account: string; reference_number: string;
    invoice: string; payment_voucher: string;
};
type AdvanceForm = {
    vendor: string; payment_date: string; total_amount: string;
    payment_method: string; bank_account: string; reference_number: string;
    advance_type: 'Vendor Advance' | 'Vendor Deposit';
};
const BLANK_PAYMENT: Readonly<PaymentForm> = Object.freeze({
    vendor: '', payment_date: new Date().toISOString().slice(0, 10),
    total_amount: '', payment_method: 'Wire', bank_account: '',
    reference_number: '', invoice: '',
    // Reference to the Payment Voucher that authorises this payment.
    // Required when AccountingSettings.require_pv_before_payment is True;
    // optional otherwise. Selecting a PV auto-fills the Vendor field.
    payment_voucher: '',
});
const BLANK_ADVANCE: Readonly<AdvanceForm> = Object.freeze({
    vendor: '', payment_date: new Date().toISOString().slice(0, 10),
    total_amount: '', payment_method: 'Wire', bank_account: '',
    reference_number: '', advance_type: 'Vendor Advance',
});

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
            <button
                onClick={onClose}
                aria-label="Dismiss notification"
                type="button"
                style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
            >
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
    // useFocusTrap returns a ref that the modal container attaches to;
    // the hook then locks Tab cycling inside the dialog and restores
    // focus to the trigger on close. Escape calls onCancel for free.
    const containerRef = useFocusTrap(true, onCancel);
    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div
                ref={containerRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="confirm-modal-title"
                style={{ background: '#fff', borderRadius: '14px', padding: '28px 32px', width: 420, boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}
            >
                <h3 id="confirm-modal-title" style={{ margin: '0 0 8px', fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>{title}</h3>
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
function PaymentFormModal({
    vendors = [],
    bankAccounts = [],
    openInvoices = [],
    paymentVouchers = [],
    pvRequired = false,
    initialValues,
    onSubmit,
    onClose,
    isLoading,
}: {
    vendors?: Vendor[]; bankAccounts?: BankAccount[]; openInvoices?: VendorInvoiceRow[];
    paymentVouchers?: PaymentVoucherRow[]; pvRequired?: boolean;
    /**
     * Optional pre-fill: merged with ``BLANK_PAYMENT`` so the modal
     * can open with vendor + amount + reference + allocated-invoice
     * already populated when a caller (e.g. an upstream document
     * surface) launches the New Payment flow. The vendor dropdown
     * still resolves the vendor id back to the option in the list,
     * so all auto-fill logic (filtered PVs, vendor invoices)
     * continues to work.
     */
    initialValues?: Partial<typeof BLANK_PAYMENT>;
    onSubmit: (form: typeof BLANK_PAYMENT) => void; onClose: () => void; isLoading: boolean;
}) {
    // ``useState({...})`` evaluates the initial state ONCE on mount, so
    // the initialValues snapshot at open-time is what populates the
    // form — subsequent prop updates won't re-write user input mid-edit.
    const [form, setForm] = useState({ ...BLANK_PAYMENT, ...(initialValues || {}) });
    const set = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }));

    // Outstanding balance for an invoice — prefer the serializer's
    // ``balance_due``; fall back to ``total - paid`` when it's absent.
    const invoiceOutstanding = (inv: VendorInvoiceRow): number => {
        const bd = inv.balance_due != null ? parseFloat(inv.balance_due) : NaN;
        if (Number.isFinite(bd)) return bd;
        return (parseFloat(inv.total_amount) || 0) - (parseFloat(inv.paid_amount || '0') || 0);
    };

    // Only the SELECTED vendor's UNALLOCATED (outstanding) invoices.
    // Previously the filter fell through to *all* invoices when no
    // vendor was chosen (``!form.vendor || …``), so the picker showed
    // unrelated rows before a supplier was even selected. Now it stays
    // empty until a vendor is picked, then lists that vendor's open
    // invoices (balance_due > 0) so the operator allocates only against
    // what's still owed.
    const selectedVendorInvoices = form.vendor
        ? openInvoices.filter(
            (inv) => String(inv.vendor) === form.vendor && invoiceOutstanding(inv) > 0.005,
        )
        : [];
    const outstandingTotal = selectedVendorInvoices.reduce((s, inv) => s + invoiceOutstanding(inv), 0);

    // When a PV is selected we want to auto-populate the Vendor (and, where
    // sensible, the amount and narration). Similarly, selecting a Vendor
    // first narrows the PV dropdown to only that vendor's approved PVs.
    // Both paths converge on the same final state so the user can enter
    // from either direction.
    const filteredPVs = paymentVouchers.filter((pv) => {
        if (!form.vendor) return true;
        // PV's vendor linkage isn't a direct FK — it's captured via the
        // underlying invoice's vendor. We fall back to matching by
        // payee_name as a last resort so PVs raised without an invoice
        // link still surface when the vendor name matches.
        const vendorId = pv.vendor ?? pv.invoice_vendor;
        if (vendorId) return String(vendorId) === String(form.vendor);
        const vendor = vendors.find((v) => String(v.id) === String(form.vendor));
        return Boolean(vendor && pv.payee_name && pv.payee_name.toLowerCase() === vendor.name.toLowerCase());
    });

    const handlePvChange = (pvId: string) => {
        set('payment_voucher', pvId);
        if (!pvId) return;
        const pv = paymentVouchers.find((p) => String(p.id) === pvId);
        if (!pv) return;
        // Resolve the PV's vendor: first via direct FK, then via the
        // payee_name → vendors[] match.
        let vendorId: string | number | null | undefined = pv.vendor ?? pv.invoice_vendor ?? '';
        if (!vendorId && pv.payee_name) {
            const match = vendors.find((v) =>
                v.name && pv.payee_name && v.name.toLowerCase() === pv.payee_name.toLowerCase()
            );
            if (match) vendorId = String(match.id);
        }
        setForm(prev => ({
            ...prev,
            payment_voucher: pvId,
            vendor: vendorId ? String(vendorId) : prev.vendor,
            // Only overwrite amount/reference if the user hasn't edited them
            total_amount: prev.total_amount || pv.net_amount || pv.gross_amount || '',
            reference_number: prev.reference_number || pv.voucher_number || '',
        }));
    };

    const containerRef = useFocusTrap(true, onClose);
    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div
                ref={containerRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="payment-modal-title"
                style={{ background: '#fff', borderRadius: '16px', padding: '32px', width: 620, boxShadow: '0 24px 80px rgba(0,0,0,0.22)', maxHeight: '90vh', overflowY: 'auto' }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: 40, height: 40, borderRadius: '10px', background: 'linear-gradient(135deg,#f59e0b,#d97706)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Banknote size={20} color="#fff" />
                    </div>
                    <div>
                        <h3 id="payment-modal-title" style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>New Outgoing Payment</h3>
                        <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>
                            {pvRequired
                                ? 'Select a Payment Voucher — PV is required by Accounting Settings'
                                : 'Pick a vendor or a Payment Voucher (either works — selecting one auto-fills the other)'}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label="Close payment form"
                        type="button"
                        style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}
                    >
                        <X size={20} color="#94a3b8" />
                    </button>
                </div>
                <form onSubmit={e => { e.preventDefault(); onSubmit(form); }}>
                    <div style={{ display: 'grid', gap: '14px' }}>
                        {/* Vendor + PV in one horizontal row. Either path fills the other. */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
                                    Vendor {!pvRequired && <span style={{ color: '#ef4444' }}>*</span>}
                                </label>
                                <select
                                    style={sel}
                                    value={form.vendor}
                                    onChange={e => set('vendor', e.target.value)}
                                    required={!pvRequired}
                                >
                                    <option value="">Select vendor…</option>
                                    {vendors?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
                                    Payment Voucher {pvRequired && <span style={{ color: '#ef4444' }}>*</span>}
                                    {!pvRequired && <span style={{ fontWeight: 400, color: '#94a3b8', fontSize: '11px' }}> (optional)</span>}
                                </label>
                                <select
                                    style={sel}
                                    value={form.payment_voucher}
                                    onChange={e => handlePvChange(e.target.value)}
                                    required={pvRequired}
                                >
                                    <option value="">{pvRequired ? 'Select PV…' : '— none —'}</option>
                                    {filteredPVs.map((pv) => (
                                        <option key={pv.id} value={pv.id}>
                                            {pv.voucher_number} · {pv.payee_name || 'payee'} · {pv.net_amount ? parseFloat(pv.net_amount).toLocaleString() : '—'}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>
                        {pvRequired && !form.payment_voucher && (
                            <div style={{
                                padding: '8px 12px', borderRadius: '6px',
                                background: '#fef3c7', border: '1px solid #fde68a',
                                color: '#92400e', fontSize: '12px',
                            }}>
                                ⚠ A Payment Voucher is required before an outgoing payment
                                can be posted. If you don't have one yet, raise it on the
                                Payment Vouchers screen first.
                            </div>
                        )}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Payment Date *</label>
                                <input style={inp} type="date" value={form.payment_date} onChange={e => set('payment_date', e.target.value)} required />
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Amount *</label>
                                <AmountInput style={inp} placeholder="0.00" value={form.total_amount} onChange={v => set('total_amount', v)} required />
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
                                    {bankAccounts?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                                </select>
                            </div>
                        </div>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Reference Number</label>
                            <input style={inp} type="text" placeholder="CHQ-001 / TRF-REF…" value={form.reference_number} onChange={e => set('reference_number', e.target.value)} />
                        </div>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Allocate to Invoice (optional)</label>
                            <select style={sel} value={form.invoice} onChange={e => set('invoice', e.target.value)} disabled={!form.vendor}>
                                <option value="">— no allocation —</option>
                                {selectedVendorInvoices.map((inv) => (
                                    <option key={inv.id} value={inv.id}>
                                        {inv.invoice_number} · Outstanding: {invoiceOutstanding(inv).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </option>
                                ))}
                            </select>
                            {/* Vendor-aware helper. Until a supplier is chosen the
                                picker has nothing to allocate against, so we say so
                                instead of silently showing an empty/irrelevant list. */}
                            {!form.vendor ? (
                                <p style={{ fontSize: '11px', color: '#94a3b8', margin: '4px 0 0' }}>Select a vendor to see their open invoices.</p>
                            ) : selectedVendorInvoices.length === 0 ? (
                                <p style={{ fontSize: '11px', color: '#94a3b8', margin: '4px 0 0' }}>No open (unallocated) invoices for this supplier.</p>
                            ) : (
                                <p style={{ fontSize: '11px', color: '#64748b', margin: '4px 0 0' }}>
                                    <strong>{selectedVendorInvoices.length}</strong> open invoice{selectedVendorInvoices.length === 1 ? '' : 's'} ·
                                    total outstanding <strong>{outstandingTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
                                </p>
                            )}
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
    vendors: Vendor[]; bankAccounts: BankAccount[];
    onSubmit: (form: typeof BLANK_ADVANCE) => void; onClose: () => void; isLoading: boolean;
}) {
    const [form, setForm] = useState({ ...BLANK_ADVANCE });
    const set = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }));
    const containerRef = useFocusTrap(true, onClose);

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div
                ref={containerRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="advance-modal-title"
                style={{ background: '#fff', borderRadius: '16px', padding: '32px', width: 480, boxShadow: '0 24px 80px rgba(0,0,0,0.22)', maxHeight: '90vh', overflowY: 'auto' }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: 40, height: 40, borderRadius: '10px', background: 'linear-gradient(135deg,#8b5cf6,#6d28d9)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <TrendingDown size={20} color="#fff" />
                    </div>
                    <div>
                        <h3 id="advance-modal-title" style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>New Vendor Advance</h3>
                        <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>Down payment from purchase order</p>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label="Close advance form"
                        type="button"
                        style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}
                    >
                        <X size={20} color="#94a3b8" />
                    </button>
                </div>
                <form onSubmit={e => { e.preventDefault(); onSubmit(form); }}>
                    <div style={{ display: 'grid', gap: '14px' }}>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Vendor *</label>
                            <select style={sel} value={form.vendor} onChange={e => set('vendor', e.target.value)} required>
                                <option value="">Select vendor…</option>
                                {vendors?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
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
                                <AmountInput style={inp} placeholder="0.00" value={form.total_amount} onChange={v => set('total_amount', v)} required />
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
                                    {bankAccounts?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
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

// ─── summary card (module scope so identity stays stable across renders) ───
interface SummaryCardProps {
    label: string;
    value: string | number;
    sub?: string;
    accent: string;
}

function SummaryCard({ label, value, sub, accent }: SummaryCardProps) {
    return (
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
}

// ─── main page ────────────────────────────────────────────────────────────────
export default function OutgoingPaymentsPage() {
    const { formatCurrency } = useCurrency();
    const [activeTab, setActiveTab] = useState<ActiveTab>('payments');
    const [notification, setNotification] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

    // Payment forms
    const [showPaymentForm, setShowPaymentForm] = useState(false);
    const [showAdvanceForm, setShowAdvanceForm] = useState(false);
    // Prefill carries vendor + amount + reference + allocated-invoice
    // into the New Outgoing Payment modal when an upstream surface
    // launches the flow (e.g. a downstream "raise payment" button on
    // another page). Consumed by ``PaymentFormModal`` via its
    // ``initialValues`` prop; cleared on close so the next standalone
    // "+ New Payment" click opens an empty form again.
    const [paymentPrefill, setPaymentPrefill] = useState<Partial<typeof BLANK_PAYMENT> | null>(null);
    // When the user clicks "Post" on an existing Draft payment row, we
    // open the same prefilled modal — but the submit handler then
    // PATCHes the existing draft (instead of POSTing a new one) and
    // immediately triggers the post-to-GL endpoint. This lets the
    // operator review / pick the bank account before locking the
    // payment in. ``null`` means create-new flow; a number means
    // edit-and-post flow against that Payment row.
    const [editingPaymentId, setEditingPaymentId] = useState<number | null>(null);

    // Confirm modals
    const [postConfirm, setPostConfirm] = useState<{ id: number; number: string } | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<{ id: number; number: string } | null>(null);
    const [processAdvanceConfirm, setProcessAdvanceConfirm] = useState<{ id: number; ref: string } | null>(null);

    // Clear-advance modal. Opens when the operator clicks Clear on a
    // Posted advance row. Carries the linked VendorAdvance id (to call
    // /clear/ against), the vendor (to filter the invoice picker),
    // and the remaining balance (to cap the allocation amount).
    const [clearAdvance, setClearAdvance] = useState<{
        advanceId: number;
        paymentNumber: string;
        vendorId: number | null;
        vendorName: string;
        outstanding: string;
    } | null>(null);

    // View-journal modal. Opens when the operator clicks the Eye icon
    // on a Posted row in either tab. Carries the JournalHeader id to
    // fetch + the source row's display context so the modal title and
    // breadcrumbs match (e.g. "Journal for Payment PAY-0042 — ₦20,000").
    const [viewJournalFor, setViewJournalFor] = useState<{
        journalId: number;
        sourceLabel: string;
        amount: string;
        isAdvance: boolean;
    } | null>(null);

    // ─── queries ─────────────────────────────────────────────────────────────
    const { data: payments, isLoading: loadingPayments } = usePayments({ is_advance: false });
    const { data: advances, isLoading: loadingAdvances } = usePayments({ is_advance: true });
    const { data: vendors } = useVendors();
    const { data: bankAccounts } = useBankAccounts({ is_active: true });
    // Allocation pickers (New Payment + Clear Advance) need every PAYABLE
    // invoice for the vendor — not just status=Approved. ``Posted`` is the
    // primary payable state (AP recognised the moment the invoice posts,
    // still unpaid); ``Partially Paid`` has a residual balance. The
    // client-side ``balance_due > 0`` filter then drops anything settled.
    // page_size is raised because the picker filters client-side by vendor,
    // so the whole payable set must arrive in one page (default was 20).
    const { data: openInvoices } = useVendorInvoices({
        status__in: 'Approved,Posted,Partially Paid',
        page_size: 1000,
    });
    const { data: downPaymentRequests, isLoading: loadingDPR } = useDownPaymentRequests({ status: 'Approved' });

    // Tenant-level setting: whether a PV must back every outgoing payment.
    // Read once and passed down to the PaymentFormModal so it can toggle
    // the PV picker between optional and mandatory without re-fetching.
    const { data: acctSettings } = useAccountingSettings();
    const pvRequired: boolean = Boolean(
        (acctSettings as { require_pv_before_payment?: boolean } | undefined)?.require_pv_before_payment,
    );

    // Approved/draft PVs ready to be paid. Filters on status so finalised
    // and voided vouchers don't pollute the picker. The viewset returns
    // the full detail shape (payee_name, net_amount, voucher_number).
    const { data: paymentVouchers = [] } = useQuery<PaymentVoucherRow[]>({
        queryKey: ['payment-vouchers', { status__in: 'DRAFT,APPROVED' }],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/payment-vouchers/', {
                params: { status__in: 'DRAFT,APPROVED', page_size: 200 },
            });
            return data.results ?? data ?? [];
        },
        staleTime: 60_000,
    });

    // ─── mutations ────────────────────────────────────────────────────────────
    const createPayment = useCreatePayment();
    const updatePayment = useUpdatePayment();
    const createAllocation = useCreatePaymentAllocation();
    const postPayment = usePostPayment();
    const deletePayment = useDeletePayment();
    const processDownPayment = useProcessDownPayment();
    const clearAdvanceMut = useClearVendorAdvance();

    // ─── helpers ──────────────────────────────────────────────────────────────
    const showSuccess = (msg: string) => { setNotification({ msg, type: 'success' }); setTimeout(() => setNotification(null), 3500); };
    const showError   = (msg: string) => { setNotification({ msg, type: 'error'   }); setTimeout(() => setNotification(null), 4500); };

    // ─── summary metrics ──────────────────────────────────────────────────────
    // Cast the React-Query payload arrays once into our typed row shapes
    // so the downstream filters/reducers can use real properties without
    // re-asserting at every site.
    const paymentsList = (payments as PaymentRow[] | undefined) ?? [];
    const advancesList = (advances as PaymentRow[] | undefined) ?? [];
    const todayStr        = new Date().toISOString().slice(0, 10);
    const paidToday       = paymentsList.filter(p => p.payment_date === todayStr)
        .reduce((s, p) => s + parseFloat(p.total_amount || '0'), 0);
    const pendingPosting  = paymentsList.filter(p => p.status === 'Draft').length;
    const postedCount     = paymentsList.filter(p => p.status === 'Posted').length;
    const advanceBalance  = advancesList.reduce((s, p) => s + parseFloat(p.advance_remaining || '0'), 0);

    // ─── handlers ─────────────────────────────────────────────────────────────
    const handleSubmitPayment = async (form: typeof BLANK_PAYMENT) => {
        // Two flows funnel through this handler:
        //
        //  1. CREATE-NEW (editingPaymentId === null): POST a fresh
        //     Payment, optionally allocate to an invoice, leave it in
        //     Draft for a follow-up Post action. This is the standalone
        //     "+ New Payment" path and any upstream prefilled-launch path.
        //
        //  2. EDIT-AND-POST (editingPaymentId is a number): PATCH the
        //     existing Draft with the form's values (most importantly,
        //     the bank account the operator just picked) and then
        //     immediately fire ``post_payment/`` to push it to the GL.
        //     This replaces the old confirm-dialog Post flow with one
        //     that lets the operator confirm/choose the bank before
        //     committing to the ledger.
        try {
            if (editingPaymentId !== null) {
                await updatePayment.mutateAsync({
                    id: editingPaymentId,
                    vendor: Number(form.vendor) || undefined,
                    payment_date: form.payment_date,
                    total_amount: form.total_amount,
                    payment_method: form.payment_method,
                    bank_account: form.bank_account ? Number(form.bank_account) : null,
                    reference_number: form.reference_number || '',
                    payment_voucher: form.payment_voucher ? Number(form.payment_voucher) : null,
                });
                // Allocate to invoice only when the existing payment
                // didn't already have one (avoid duplicate allocations
                // — the API rejects them but we'd waste a request).
                // Optimistically post; if allocation fails the user
                // sees the error and the payment stays in Draft.
                if (form.invoice) {
                    try {
                        await createAllocation.mutateAsync({
                            payment: editingPaymentId,
                            invoice: Number(form.invoice),
                            amount: form.total_amount,
                        });
                    } catch {
                        // Existing allocation — fine, ignore.
                    }
                }
                await postPayment.mutateAsync(editingPaymentId);
                setShowPaymentForm(false);
                setPaymentPrefill(null);
                setEditingPaymentId(null);
                showSuccess('Payment posted to General Ledger.');
                return;
            }

            const payment = await createPayment.mutateAsync({
                vendor: Number(form.vendor) || undefined,
                payment_date: form.payment_date,
                total_amount: form.total_amount,
                payment_method: form.payment_method,
                bank_account: form.bank_account ? Number(form.bank_account) : undefined,
                reference_number: form.reference_number || undefined,
                // PV linkage — sent only when chosen. Backend enforces
                // "required" based on tenant setting, so omitting a PV
                // when it isn't mandatory produces no 400.
                payment_voucher: form.payment_voucher ? Number(form.payment_voucher) : undefined,
            });
            if (form.invoice) {
                await createAllocation.mutateAsync({
                    payment: payment.id,
                    invoice: Number(form.invoice),
                    amount: form.total_amount,
                });
            }
            setShowPaymentForm(false);
            // Clear any upstream prefill so the next click of
            // "+ New Payment" opens an empty form.
            setPaymentPrefill(null);
            showSuccess('Payment saved successfully.');
        } catch (err: unknown) {
            showError(extractApiErrorMessage(err, 'Failed to save payment.'));
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
            });
            setShowAdvanceForm(false);
            showSuccess('Vendor advance saved successfully.');
        } catch (err: unknown) {
            showError(extractApiErrorMessage(err, 'Failed to save advance.'));
        }
    };

    const handlePost = async () => {
        if (!postConfirm) return;
        try {
            await postPayment.mutateAsync(postConfirm.id);
            setPostConfirm(null);
            showSuccess(`Payment ${postConfirm.number} posted to General Ledger.`);
        } catch (err: unknown) {
            setPostConfirm(null);
            showError(extractApiErrorMessage(err, 'Failed to post payment.'));
        }
    };

    const handleDelete = async () => {
        if (!deleteConfirm) return;
        try {
            await deletePayment.mutateAsync(deleteConfirm.id);
            setDeleteConfirm(null);
            showSuccess(`Payment ${deleteConfirm.number} deleted.`);
        } catch (err: unknown) {
            setDeleteConfirm(null);
            showError(extractApiErrorMessage(err, 'Failed to delete payment.'));
        }
    };

    const handleProcessAdvance = async () => {
        if (!processAdvanceConfirm) return;
        try {
            await processDownPayment.mutateAsync(processAdvanceConfirm.id);
            setProcessAdvanceConfirm(null);
            showSuccess(`Down payment request ${processAdvanceConfirm.ref} processed.`);
        } catch (err: unknown) {
            setProcessAdvanceConfirm(null);
            showError(extractApiErrorMessage(err, 'Failed to process down payment.'));
        }
    };

    // SummaryCard is now defined at module scope (above) — defining
    // it inside the render function meant React saw a new component
    // identity on every parent re-render, remounted the card, and
    // destroyed any internal state it held. Module-scope keeps the
    // component identity stable across renders.

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
            ) : !paymentsList.length ? (
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
                            {paymentsList.map((pay) => (
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
                                                    {/* Post — open the New Outgoing Payment
                                                        modal prefilled with this draft's
                                                        values (vendor / amount / method /
                                                        ref / PV / bank) so the operator can
                                                        confirm or change the bank account
                                                        before posting to GL. The submit
                                                        handler detects ``editingPaymentId``
                                                        and runs a PATCH + post_payment/
                                                        sequence instead of POSTing a new
                                                        Payment row. */}
                                                    <button
                                                        onClick={() => {
                                                            setEditingPaymentId(pay.id);
                                                            setPaymentPrefill({
                                                                vendor: pay.vendor ? String(pay.vendor) : '',
                                                                payment_date: pay.payment_date || new Date().toISOString().slice(0, 10),
                                                                total_amount: String(pay.total_amount ?? ''),
                                                                payment_method: pay.payment_method || 'Wire',
                                                                bank_account: pay.bank_account ? String(pay.bank_account) : '',
                                                                reference_number: pay.reference_number || '',
                                                                payment_voucher: pay.payment_voucher ? String(pay.payment_voucher) : '',
                                                            });
                                                            setShowPaymentForm(true);
                                                        }}
                                                        title="Post payment — review bank account first"
                                                        style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#dcfce7', color: '#166534', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: 600 }}>
                                                        <Play size={12} /> Post
                                                    </button>
                                                    <button onClick={() => setDeleteConfirm({ id: pay.id, number: pay.payment_number })}
                                                        title="Delete"
                                                        aria-label={`Delete payment ${pay.payment_number}`}
                                                        type="button"
                                                        style={{ padding: '5px 8px', border: 'none', borderRadius: '6px', background: '#fee2e2', color: '#dc2626', cursor: 'pointer' }}>
                                                        <Trash2 size={12} />
                                                    </button>
                                                </>
                                            )}
                                            {/* View Accounting Entry — visible only when the
                                                payment has been posted AND a journal id is
                                                set. Opens an inline modal showing the
                                                journal header + DR/CR lines so the operator
                                                can audit the posting without leaving the
                                                Outgoing Payments workflow. */}
                                            {pay.status === 'Posted' && pay.journal_entry && (
                                                <button
                                                    onClick={() => setViewJournalFor({
                                                        journalId: pay.journal_entry as number,
                                                        sourceLabel: `Payment ${pay.payment_number}`,
                                                        amount: pay.total_amount,
                                                        isAdvance: false,
                                                    })}
                                                    title="View accounting entry (journal)"
                                                    aria-label={`View journal for ${pay.payment_number}`}
                                                    type="button"
                                                    style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#e0e7ff', color: '#3730a3', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: 600 }}>
                                                    <Eye size={12} /> View
                                                </button>
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

    // ─── advances tab ─────────────────────────────────────────────────────────
    const dprList: DownPaymentRequestRow[] = Array.isArray(downPaymentRequests)
        ? (downPaymentRequests as DownPaymentRequestRow[])
        : ((downPaymentRequests as { results?: DownPaymentRequestRow[] } | undefined)?.results ?? []);

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
                                {dprList.map((dpr) => (
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
                        Manual advances start as <strong>Draft</strong>. Click <strong>Post</strong> on a draft row to confirm the bank account and push the disbursement journal to the GL — same flow as the Payments tab.
                    </p>
                </div>
                {loadingAdvances ? (
                    <div style={{ textAlign: 'center', padding: '20px', color: '#94a3b8' }}>Loading…</div>
                ) : !advancesList.length ? (
                    <div style={{ padding: '20px', background: '#f8fafc', borderRadius: '10px', border: '1px dashed #e2e8f0', textAlign: 'center' }}>
                        <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>No manual advances recorded. Use "New Advance" above.</p>
                    </div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                            <thead>
                                <tr style={{ background: '#fffbeb' }}>
                                    {['Payment #', 'Vendor', 'Date', 'Amount', 'Type', 'Remaining', 'Status', 'Actions'].map(h => (
                                        <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#92400e', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #fde68a', whiteSpace: 'nowrap' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {advancesList.map((adv) => (
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
                                        <td style={{ padding: '11px 14px' }}>
                                            <div style={{ display: 'flex', gap: '6px' }}>
                                                {adv.status === 'Draft' && (
                                                    <>
                                                        {/* Post — opens the Payment modal
                                                            prefilled with this advance's
                                                            values (vendor / amount / method /
                                                            ref / PV / bank) so the operator
                                                            can confirm or change the bank
                                                            account before posting to GL.
                                                            ``editingPaymentId`` flags the
                                                            submit handler to PATCH + post
                                                            instead of POST-create. Backed by
                                                            the same ``postPayment`` mutation
                                                            the Payments tab uses — but the
                                                            backend routes is_advance=true to
                                                            ``VendorAdvanceService.disburse``
                                                            so the journal becomes
                                                            DR Vendor-Advance Recon / CR Cash
                                                            (F-48) instead of the standard
                                                            DR AP / CR Bank (which would need
                                                            allocations the advance doesn't have). */}
                                                        <button
                                                            onClick={() => {
                                                                setEditingPaymentId(adv.id);
                                                                setPaymentPrefill({
                                                                    vendor: adv.vendor ? String(adv.vendor) : '',
                                                                    payment_date: adv.payment_date || new Date().toISOString().slice(0, 10),
                                                                    total_amount: String(adv.total_amount ?? ''),
                                                                    payment_method: adv.payment_method || 'Wire',
                                                                    bank_account: adv.bank_account ? String(adv.bank_account) : '',
                                                                    reference_number: adv.reference_number || '',
                                                                    payment_voucher: adv.payment_voucher ? String(adv.payment_voucher) : '',
                                                                });
                                                                setShowPaymentForm(true);
                                                            }}
                                                            title="Post advance — review bank account first"
                                                            style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#dcfce7', color: '#166534', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: 600 }}>
                                                            <Play size={12} /> Post
                                                        </button>
                                                        <button onClick={() => setDeleteConfirm({ id: adv.id, number: adv.payment_number })}
                                                            title="Delete"
                                                            aria-label={`Delete advance ${adv.payment_number}`}
                                                            type="button"
                                                            style={{ padding: '5px 8px', border: 'none', borderRadius: '6px', background: '#fee2e2', color: '#dc2626', cursor: 'pointer' }}>
                                                            <Trash2 size={12} />
                                                        </button>
                                                    </>
                                                )}
                                                {/* Clear (F-54) — visible on Posted advances
                                                    that still have an outstanding balance
                                                    AND a linked VendorAdvance row (set by
                                                    the backend serializer once the F-48
                                                    disburse journal has posted). Opens the
                                                    Clear-Advance modal where the operator
                                                    picks an invoice to allocate against and
                                                    enters the amount to recover. */}
                                                {adv.status === 'Posted'
                                                    && adv.linked_vendor_advance_id
                                                    && parseFloat(adv.advance_remaining || '0') > 0 && (
                                                    <button
                                                        onClick={() => setClearAdvance({
                                                            advanceId: adv.linked_vendor_advance_id as number,
                                                            paymentNumber: adv.payment_number,
                                                            vendorId: adv.vendor,
                                                            vendorName: adv.vendor_name || '',
                                                            outstanding: adv.advance_remaining || '0',
                                                        })}
                                                        title="Clear / Allocate advance against an invoice (F-54)"
                                                        style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#dbeafe', color: '#1d4ed8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: 600 }}>
                                                        <CheckCircle2 size={12} /> Clear
                                                    </button>
                                                )}
                                                {/* View Accounting Entry — same as the
                                                    Payments tab. For F-48 advance posts the
                                                    journal is:
                                                       DR Vendor-Advance Recon   amount
                                                       CR Cash / Bank                    amount
                                                    so the operator can confirm the disbursement
                                                    journal actually posted against the right
                                                    GLs without leaving the page. */}
                                                {adv.status === 'Posted' && adv.journal_entry && (
                                                    <button
                                                        onClick={() => setViewJournalFor({
                                                            journalId: adv.journal_entry as number,
                                                            sourceLabel: `Advance ${adv.payment_number}`,
                                                            amount: adv.total_amount,
                                                            isAdvance: true,
                                                        })}
                                                        title="View accounting entry (journal)"
                                                        aria-label={`View journal for ${adv.payment_number}`}
                                                        type="button"
                                                        style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#e0e7ff', color: '#3730a3', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: 600 }}>
                                                        <Eye size={12} /> View
                                                    </button>
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
                <SummaryCard label="Paid Today" value={formatCurrency(paidToday)} sub={`${paymentsList.filter(p => p.payment_date === todayStr).length} payments`} accent="#f59e0b" />
                <SummaryCard label="Pending Posting" value={pendingPosting} sub="Draft payments" accent="#3b82f6" />
                <SummaryCard label="Posted" value={postedCount} sub="This period" accent="#10b981" />
                <SummaryCard label="Advance Balance" value={formatCurrency(advanceBalance)} sub="Outstanding vendor advances" accent="#8b5cf6" />
            </div>

            {notification && (
                <InlineAlert msg={notification.msg} type={notification.type} onClose={() => setNotification(null)} />
            )}

            {/* Tabs */}
            <div style={{ background: '#fff', borderRadius: '16px', border: '1px solid #e2e8f0', boxShadow: '0 1px 6px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
                <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                    {([
                        { key: 'payments', label: 'Payments',         icon: <CreditCard size={14} /> },
                        { key: 'advances', label: 'Vendor Advances',  icon: <TrendingDown size={14} /> },
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
                        </button>
                    ))}
                </div>
                <div style={{ padding: '24px' }}>
                    {activeTab === 'payments' && paymentsTabJSX}
                    {activeTab === 'advances' && advancesTabJSX}
                </div>
            </div>

            {/* Modals */}
            {showPaymentForm && (
                <PaymentFormModal
                    vendors={vendors || []}
                    bankAccounts={bankAccounts || []}
                    openInvoices={openInvoices || []}
                    paymentVouchers={paymentVouchers}
                    pvRequired={pvRequired}
                    initialValues={paymentPrefill || undefined}
                    onSubmit={handleSubmitPayment}
                    // Clear prefill alongside closing so the next plain
                    // "+ New Payment" click opens a blank form again.
                    onClose={() => { setShowPaymentForm(false); setPaymentPrefill(null); setEditingPaymentId(null); }}
                    isLoading={createPayment.isPending || createAllocation.isPending || updatePayment.isPending || postPayment.isPending}
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
            {clearAdvance && (
                <ClearAdvanceModal
                    state={clearAdvance}
                    invoices={(openInvoices ?? []) as InvoiceOption[]}
                    formatCurrency={formatCurrency}
                    isLoading={clearAdvanceMut.isPending}
                    onCancel={() => setClearAdvance(null)}
                    onSubmit={async (allocations) => {
                        // Multi-invoice fan-out. Each /clear/ call is
                        // atomic on the backend (row-locked advance + own
                        // contra journal); we run them sequentially so an
                        // earlier failure short-circuits the rest — that
                        // avoids posting a partial set with the operator
                        // unaware which lines landed. ``allSettled`` would
                        // be safer-on-partial but harder to reason about
                        // for accounting integrity, so we serialise.
                        const results: Array<{ ok: boolean; ref: string; amount: string; err?: string }> = [];
                        for (const alloc of allocations) {
                            try {
                                await clearAdvanceMut.mutateAsync({
                                    id: clearAdvance.advanceId,
                                    amount: alloc.amount,
                                    cleared_against_type: 'AP_INVOICE',
                                    cleared_against_id: alloc.invoiceId,
                                    cleared_against_reference: alloc.invoiceRef,
                                });
                                results.push({ ok: true, ref: alloc.invoiceRef, amount: alloc.amount });
                            } catch (err: unknown) {
                                const msg = extractApiErrorMessage(err, 'Failed to clear advance.');
                                results.push({ ok: false, ref: alloc.invoiceRef, amount: alloc.amount, err: msg });
                                break;
                            }
                        }
                        const okCount = results.filter((r) => r.ok).length;
                        const failed = results.find((r) => !r.ok);
                        if (failed) {
                            showError(
                                `Cleared ${okCount} of ${allocations.length} allocations before failure on `
                                + `${failed.ref}: ${failed.err}`,
                            );
                            // Leave the modal open so the operator can see
                            // which lines remain and retry / adjust.
                        } else {
                            setClearAdvance(null);
                            const totalCleared = results.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0);
                            showSuccess(
                                `Cleared ${formatCurrency(totalCleared)} of advance `
                                + `${clearAdvance.paymentNumber} across ${okCount} invoice${okCount === 1 ? '' : 's'}.`,
                            );
                        }
                    }}
                />
            )}
            {viewJournalFor && (
                <JournalViewModal
                    journalId={viewJournalFor.journalId}
                    sourceLabel={viewJournalFor.sourceLabel}
                    amount={viewJournalFor.amount}
                    isAdvance={viewJournalFor.isAdvance}
                    formatCurrency={formatCurrency}
                    onClose={() => setViewJournalFor(null)}
                />
            )}
        </AccountingLayout>
    );
}

// ─── Journal View Modal ──────────────────────────────────────────────
// Modal wrapper. The actual journal rendering (header strip + lines
// table) comes from the canonical shared components — see
// ``features/accounting/components/shared/JournalViewer``. This
// component owns only the modal chrome (overlay, title bar, footer
// with "Open in Journals" deep-link) + the React Query call that
// fetches the journal. Consumer-specific bits like the F-48 ADVANCE
// pill stay here because they're not part of the journal display
// itself — they're context about *what* is being shown.

interface JournalViewModalProps {
    journalId: number;
    sourceLabel: string;
    amount: string;
    isAdvance: boolean;
    formatCurrency: (n: number | string) => string;
    onClose: () => void;
}

function JournalViewModal({
    journalId, sourceLabel, amount, isAdvance, formatCurrency, onClose,
}: JournalViewModalProps) {
    const { data: journal, isLoading, error } = useQuery<JournalDetail>({
        queryKey: ['journal-view', journalId],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/journals/${journalId}/`);
            return data;
        },
        enabled: !!journalId,
    });

    return (
        <div style={modalOverlayStyle}>
            <div style={{ ...modalCardStyle, maxWidth: 880 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 6 }}>
                    <div>
                        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#1e293b' }}>
                            Accounting Entry
                        </h3>
                        <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>
                            <strong>{sourceLabel}</strong> · {formatCurrency(amount)}
                            {isAdvance && (
                                <span style={{ marginLeft: 8, padding: '1px 8px', borderRadius: 999, fontSize: 10, fontWeight: 700, background: '#ede9fe', color: '#6d28d9' }}>
                                    F-48 ADVANCE
                                </span>
                            )}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label="Close"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', padding: 4 }}
                    >
                        <X size={18} />
                    </button>
                </div>

                {isLoading && (
                    <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
                        Loading journal…
                    </div>
                )}

                {error && (
                    <div style={{ padding: 16, marginTop: 8, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, color: '#991b1b', fontSize: 13 }}>
                        Failed to load journal #{journalId}. {(error as Error)?.message ?? 'Please try again.'}
                    </div>
                )}

                {journal && (
                    <>
                        <div style={{ marginTop: 12 }}>
                            <JournalHeaderStrip journal={journal} formatCurrency={formatCurrency} />
                        </div>
                        <div style={{ marginTop: 14 }}>
                            <JournalLinesTable
                                lines={journal.lines}
                                formatCurrency={formatCurrency}
                                emptyMessage="This journal has no lines."
                            />
                        </div>

                        {/* Footer — Close + Open in Journals (canonical full-page viewer) */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 16 }}>
                            <a
                                href={`/accounting/journals/${journalId}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#1e4d8c', fontWeight: 600, fontSize: 12, textDecoration: 'none' }}
                            >
                                <BookOpen size={14} /> Open in Journals
                            </a>
                            <button
                                onClick={onClose}
                                style={{ padding: '8px 16px', border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', color: '#475569', cursor: 'pointer', fontWeight: 600, fontSize: 13 }}
                            >
                                Close
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

// ─── Clear Advance Modal (F-54) ──────────────────────────────────────
// Operator allocates a posted advance against an open vendor invoice.
// Posts the contra journal: DR Real-AP / CR Vendor-Advance Recon.
// Filters the invoice picker to invoices for the same vendor so the
// operator can't accidentally cross-allocate to another vendor's
// payable. The amount input is capped at the outstanding balance.

interface InvoiceOption {
    id: number;
    invoice_number?: string;
    vendor?: number | null;
    total_amount?: string | number;
    balance_due?: string | number;
    status?: string;
}

// One allocation line inside the Clear modal. The operator can add
// many of these — each becomes one /clear/ POST when the form submits.
interface AllocationLine {
    rowKey: string;        // local-only React list key; not sent to backend
    invoiceId: number | '';
    amount: string;
}

interface SubmittedAllocation {
    invoiceId: number;
    invoiceRef: string;
    amount: string;
}

interface ClearAdvanceModalProps {
    state: {
        advanceId: number;
        paymentNumber: string;
        vendorId: number | null;
        vendorName: string;
        outstanding: string;
    };
    invoices: InvoiceOption[];
    formatCurrency: (n: number | string) => string;
    isLoading: boolean;
    onCancel: () => void;
    onSubmit: (allocations: SubmittedAllocation[]) => void | Promise<void>;
}

function ClearAdvanceModal({
    state, invoices, formatCurrency, isLoading, onCancel, onSubmit,
}: ClearAdvanceModalProps) {
    const outstandingNum = parseFloat(state.outstanding) || 0;
    // Same-vendor AND still-unallocated (outstanding balance > 0). An
    // invoice already fully paid/cleared has nothing left to allocate
    // the advance against, so it's excluded from the picker.
    const invoiceBalance = (inv: InvoiceOption): number =>
        parseFloat(String(inv.balance_due ?? inv.total_amount ?? '0')) || 0;
    const vendorInvoices = invoices.filter((inv) =>
        (state.vendorId == null || inv.vendor === state.vendorId)
        && invoiceBalance(inv) > 0.005,
    );

    // Seed with one empty allocation row. The operator can Add more
    // and Remove individual rows. Default amount is the full
    // outstanding so the most common single-invoice case is one click.
    const [rows, setRows] = useState<AllocationLine[]>([
        { rowKey: 'r0', invoiceId: '', amount: state.outstanding },
    ]);

    const updateRow = (key: string, patch: Partial<AllocationLine>) => {
        setRows((prev) => prev.map((r) => (r.rowKey === key ? { ...r, ...patch } : r)));
    };
    const addRow = () => {
        setRows((prev) => [
            ...prev,
            { rowKey: `r${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, invoiceId: '', amount: '' },
        ]);
    };
    const removeRow = (key: string) => {
        setRows((prev) => (prev.length === 1 ? prev : prev.filter((r) => r.rowKey !== key)));
    };

    // Per-invoice usage map — used to show the "balance left on this
    // invoice if the rest of the form submits" hint without forcing the
    // operator to compute it in their head. Also catches the case where
    // two rows pick the same invoice and over-allocate it.
    const allocByInvoice: Record<number, number> = {};
    rows.forEach((r) => {
        if (r.invoiceId !== '') {
            const n = parseFloat(r.amount) || 0;
            allocByInvoice[r.invoiceId] = (allocByInvoice[r.invoiceId] || 0) + n;
        }
    });

    const totalAllocated = rows.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0);
    const advanceRemaining = outstandingNum - totalAllocated;
    const overAllocated = advanceRemaining < -0.005;     // tolerate fp noise

    // Per-row validity. A row is valid when it has an invoice picked,
    // the amount is positive, the amount is ≤ the invoice's balance
    // (minus this row's own contribution so the check doesn't double-
    // subtract), AND the cumulative sum across all rows fits in the
    // advance.
    const rowProblems = rows.map((r) => {
        if (r.invoiceId === '') return 'no-invoice';
        const inv = vendorInvoices.find((i) => i.id === r.invoiceId);
        if (!inv) return 'invoice-missing';
        const bal = parseFloat(String(inv.balance_due ?? inv.total_amount ?? '0')) || 0;
        const n = parseFloat(r.amount) || 0;
        if (n <= 0) return 'zero';
        // The cumulative allocation to THIS invoice across all rows
        // must not exceed its balance.
        if ((allocByInvoice[r.invoiceId] || 0) > bal + 0.005) return 'over-invoice';
        return null;
    });

    const submitDisabled = isLoading
        || overAllocated
        || totalAllocated <= 0
        || rowProblems.some((p) => p !== null);

    const handleSubmit = () => {
        const payload: SubmittedAllocation[] = rows
            .filter((r) => r.invoiceId !== '' && (parseFloat(r.amount) || 0) > 0)
            .map((r) => {
                const inv = vendorInvoices.find((i) => i.id === r.invoiceId);
                return {
                    invoiceId: r.invoiceId as number,
                    invoiceRef: inv?.invoice_number ?? `INV-${inv?.id ?? r.invoiceId}`,
                    amount: r.amount,
                };
            });
        if (payload.length === 0) return;
        onSubmit(payload);
    };

    return (
        <div style={modalOverlayStyle}>
            <div style={{ ...modalCardStyle, maxWidth: 760 }}>
                <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#1e293b' }}>
                    Clear Advance (F-54)
                </h3>
                <p style={{ margin: '6px 0 16px', fontSize: 13, color: '#64748b' }}>
                    Allocate advance <strong>{state.paymentNumber}</strong> for <strong>{state.vendorName}</strong> across one or more outstanding invoices.
                    Each allocation posts its own contra journal: <strong>DR Accounts Payable / CR Vendor Advance Recon</strong>.
                </p>

                {/* Running-balance summary card. Tints amber if there's
                    still a residual after the planned allocations, red
                    if the planned set over-allocates the advance. */}
                <div style={{
                    background: overAllocated ? '#fef2f2' : advanceRemaining > 0.005 ? '#fffbeb' : '#f0fdf4',
                    border: `1px solid ${overAllocated ? '#fecaca' : advanceRemaining > 0.005 ? '#fde68a' : '#bbf7d0'}`,
                    borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 13,
                    display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap',
                }}>
                    <div><strong>Outstanding on advance:</strong> {formatCurrency(outstandingNum)}</div>
                    <div><strong>Total allocated:</strong> {formatCurrency(totalAllocated)}</div>
                    <div style={{ color: overAllocated ? '#991b1b' : advanceRemaining > 0.005 ? '#92400e' : '#166534', fontWeight: 700 }}>
                        {overAllocated
                            ? `Over by ${formatCurrency(Math.abs(advanceRemaining))}`
                            : `Remaining after submit: ${formatCurrency(Math.max(0, advanceRemaining))}`}
                    </div>
                </div>

                {vendorInvoices.length === 0 && (
                    <div style={{ marginBottom: 14, padding: '10px 14px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, fontSize: 12, color: '#92400e' }}>
                        No open invoices found for this vendor. Post the vendor's invoice first, then return to clear the advance.
                    </div>
                )}

                {/* Allocation rows */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
                    {rows.map((r, idx) => {
                        const inv = vendorInvoices.find((i) => i.id === r.invoiceId);
                        const bal = inv ? parseFloat(String(inv.balance_due ?? inv.total_amount ?? '0')) || 0 : 0;
                        const usedOnThisInvoice = inv ? (allocByInvoice[inv.id] || 0) : 0;
                        const balanceLeftAfter = bal - usedOnThisInvoice;
                        const problem = rowProblems[idx];
                        return (
                            <div key={r.rowKey} style={{
                                display: 'grid', gridTemplateColumns: '1fr 180px 36px', gap: 8,
                                alignItems: 'start',
                                padding: '8px 10px', background: '#f8fafc',
                                border: `1px solid ${problem ? '#fecaca' : '#e2e8f0'}`,
                                borderRadius: 8,
                            }}>
                                <div>
                                    <select
                                        value={r.invoiceId === '' ? '' : String(r.invoiceId)}
                                        onChange={(e) => updateRow(r.rowKey, {
                                            invoiceId: e.target.value === '' ? '' : Number(e.target.value),
                                        })}
                                        style={{ width: '100%', padding: '7px 10px', border: '1.5px solid #cbd5e1', borderRadius: 6, fontSize: 12, background: '#fff' }}
                                    >
                                        <option value="">— Select invoice —</option>
                                        {vendorInvoices.map((opt) => {
                                            const optBal = parseFloat(String(opt.balance_due ?? opt.total_amount ?? '0')) || 0;
                                            return (
                                                <option key={opt.id} value={opt.id}>
                                                    {opt.invoice_number ?? `#${opt.id}`} — balance {formatCurrency(optBal)}
                                                </option>
                                            );
                                        })}
                                    </select>
                                    {inv && (
                                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                                            Balance after this allocation: <strong>{formatCurrency(balanceLeftAfter)}</strong>
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <input
                                        type="number"
                                        min="0"
                                        step="0.01"
                                        placeholder="Amount"
                                        value={r.amount}
                                        onChange={(e) => updateRow(r.rowKey, { amount: e.target.value })}
                                        style={{ width: '100%', padding: '7px 10px', border: '1.5px solid #cbd5e1', borderRadius: 6, fontSize: 12, textAlign: 'right', fontFamily: 'monospace' }}
                                    />
                                    {problem === 'over-invoice' && (
                                        <div style={{ fontSize: 10, color: '#dc2626', marginTop: 4, fontWeight: 600 }}>
                                            Exceeds invoice balance
                                        </div>
                                    )}
                                </div>
                                <button
                                    onClick={() => removeRow(r.rowKey)}
                                    disabled={rows.length === 1}
                                    title={rows.length === 1 ? 'Need at least one allocation' : 'Remove this allocation'}
                                    style={{
                                        padding: '7px 8px', border: 'none', borderRadius: 6,
                                        background: rows.length === 1 ? '#f1f5f9' : '#fee2e2',
                                        color: rows.length === 1 ? '#cbd5e1' : '#dc2626',
                                        cursor: rows.length === 1 ? 'not-allowed' : 'pointer',
                                        height: 'fit-content',
                                    }}
                                >
                                    <Trash2 size={13} />
                                </button>
                            </div>
                        );
                    })}
                </div>

                <button
                    onClick={addRow}
                    disabled={vendorInvoices.length === 0}
                    style={{
                        padding: '7px 14px', border: '1px dashed #94a3b8', borderRadius: 6,
                        background: '#fff', color: '#475569', cursor: vendorInvoices.length === 0 ? 'not-allowed' : 'pointer',
                        fontSize: 12, fontWeight: 600, marginBottom: 16,
                        display: 'inline-flex', alignItems: 'center', gap: 6,
                        opacity: vendorInvoices.length === 0 ? 0.5 : 1,
                    }}
                >
                    <Plus size={13} /> Add another allocation
                </button>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                    <button
                        onClick={onCancel}
                        disabled={isLoading}
                        style={{ padding: '9px 16px', border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', color: '#475569', cursor: 'pointer', fontWeight: 600, fontSize: 13 }}
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={submitDisabled}
                        style={{ padding: '9px 18px', border: 'none', borderRadius: 8, background: '#1d4ed8', color: '#fff', cursor: submitDisabled ? 'not-allowed' : 'pointer', fontWeight: 700, fontSize: 13, opacity: submitDisabled ? 0.5 : 1 }}
                    >
                        {isLoading ? 'Clearing…' : `Post ${rows.filter((r) => r.invoiceId !== '').length} Clearance${rows.filter((r) => r.invoiceId !== '').length === 1 ? '' : 's'}`}
                    </button>
                </div>
            </div>
        </div>
    );
}

const modalOverlayStyle: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.45)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000, padding: 20,
};

const modalCardStyle: React.CSSProperties = {
    background: '#fff', borderRadius: 14, padding: '22px 24px',
    width: '100%', boxShadow: '0 20px 50px -12px rgba(0,0,0,0.25)',
};
