/**
 * Payment Voucher Create Form — Quot PSE
 * Route: /accounting/payment-vouchers/new
 *
 * Simplified flow per user requirements:
 *   1. MDA is the first (mandatory) field at the top
 *   2. Payment type + Invoice search next
 *   3. Supplier fields display horizontally (optional at create time;
 *      Treasury fills in later)
 *   4. Payment amount + narration
 *   5. Source documents (PO / Invoice # / Date / Notes)
 *
 * Removed sections:
 *   - "Treasury & Budget" card (TSA + explicit Appropriation pick). The
 *     MDA + invoice combo uniquely determines the budget line, so the
 *     appropriation is resolved automatically at post time.
 *   - Full NCoA Classification grid — still captured but derived from
 *     the selected invoice (no manual segment picking required).
 *
 * On submit, the PV becomes a payment request that the Treasury team
 * posts from the Outgoing Payments page.
 */
import { useState, useMemo, useEffect, useRef } from 'react';
import { formatDate } from '@/utils/date';
import { formatThousandsInput, stripThousands } from '@/utils/number';
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, Receipt, Search, FileText, Building2, X } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import SearchableSelect from '../../components/SearchableSelect';
import { useCreatePV, useNCoASegments } from '../../hooks/useGovForms';
import apiClient from '../../api/client';
import {
    DeductionLinesEditor,
    serializeDeductions,
    type DeductionRow,
} from './DeductionLinesEditor';

// Compact field style retained for the computed Total/Net display boxes,
// which need a tighter footprint than the canonical full-size `.input` class.
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};

const PAYMENT_TYPES: [string, string][] = [
    ['VENDOR', 'Vendor / Contractor Payment'],
    ['SALARY', 'Salary Payment'],
    ['ALLOWANCE', 'Allowance / Honorarium'],
    ['PENSION', 'Pension Remittance'],
    ['STATUTORY', 'Statutory Deduction Remittance'],
    ['REFUND', 'Revenue Refund'],
    ['TRANSFER', 'Inter-Account Transfer'],
    ['PETTY_CASH', 'Petty Cash Replenishment'],
    ['SUBVENTION', 'Subvention / Transfer'],
    ['DEBT', 'Debt Service Payment'],
];

const fmtNGN = (v: number | string): string => {
    const num = typeof v === 'string' ? parseFloat(v) : v;
    if (isNaN(num)) return '\u20A60.00';
    return '\u20A6' + num.toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

interface PayableInvoice {
    id: number;
    invoice_number: string;
    reference: string;
    vendor_name: string;
    vendor_bank: string;
    vendor_account: string;
    vendor_sort_code: string;
    invoice_date: string;
    total_amount: string;
    balance_due: string;
    description: string;
    account_code: string;
    mda_code: string;
    fund_code: string;
    function_code: string;
    program_code: string;
    geo_code: string;
    purchase_order: string;
}

export default function PaymentVoucherForm() {
    const navigate = useNavigate();
    const createPV = useCreatePV();
    const { data: segments } = useNCoASegments();

    const labelStyle: React.CSSProperties = { display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' };
    const helpStyle: React.CSSProperties = { fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' };

    const [formError, setFormError] = useState('');
    const [invoiceSearch, setInvoiceSearch] = useState('');
    const [invoiceResults, setInvoiceResults] = useState<PayableInvoice[]>([]);
    const [selectedInvoice, setSelectedInvoice] = useState<PayableInvoice | null>(null);
    const [showDropdown, setShowDropdown] = useState(false);
    const [searchLoading, setSearchLoading] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    const [form, setForm] = useState({
        payment_type: 'VENDOR',
        payee_name: '', payee_account: '', payee_bank: '', payee_sort_code: '',
        gross_amount: '', wht_amount: '0',
        narration: '', source_document: '', invoice_number: '', invoice_date: '',
        notes: '',
        // MDA stored separately; all other NCoA segments ride along from the
        // selected invoice and are resolved server-side at submit time.
        admin_code: '',
        // Captured silently from the selected invoice — not shown in the UI,
        // but still sent in the payload so the backend can resolve the
        // appropriation without a separate picker.
        economic_code: '', functional_code: '',
        programme_code: '', fund_code: '', geo_code: '',
    });

    const set = (field: string, value: string) =>
        setForm(prev => ({ ...prev, [field]: value }));

    // ── Deduction lines ───────────────────────────────────────────────
    // Each row posts one CR line to its setting's GL account at payment
    // time. Net paid to vendor = gross − Σ amount. The grid + all its
    // logic live in the shared DeductionLinesEditor.
    const [deductions, setDeductions] = useState<DeductionRow[]>([]);
    const grossNum = parseFloat(form.gross_amount) || 0;

    const totalDeductions = useMemo(
        () => deductions.reduce((s, d) => s + (parseFloat(d.amount) || 0), 0),
        [deductions],
    );
    const netAmount = useMemo(
        () => Math.max(0, grossNum - totalDeductions),
        [grossNum, totalDeductions],
    );

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) setShowDropdown(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Search invoices — filtered by the MDA first (so the user only ever
    // picks a payable that matches their chosen MDA). Mirrors the
    // user's requirement that MDA drives downstream selection.
    useEffect(() => {
        if (!form.admin_code) {
            setInvoiceResults([]);
            return;
        }
        const timer = setTimeout(async () => {
            setSearchLoading(true);
            try {
                const params: Record<string, string> = { mda_code: form.admin_code };
                if (invoiceSearch.trim()) params.search = invoiceSearch;
                const res = await apiClient.get('/accounting/vendor-invoices/payable/', { params });
                setInvoiceResults(res.data);
            } catch { /* ignore */ }
            setSearchLoading(false);
        }, 300);
        return () => clearTimeout(timer);
    }, [invoiceSearch, showDropdown, form.admin_code]);

    const handleSelectInvoice = (inv: PayableInvoice) => {
        setSelectedInvoice(inv);
        setInvoiceSearch(inv.invoice_number);
        setShowDropdown(false);
        setForm(prev => ({
            ...prev,
            payee_name: inv.vendor_name,
            payee_bank: inv.vendor_bank,
            payee_account: inv.vendor_account,
            payee_sort_code: inv.vendor_sort_code,
            gross_amount: inv.balance_due,
            invoice_number: inv.invoice_number,
            invoice_date: inv.invoice_date,
            source_document: inv.purchase_order,
            narration: inv.description || `Payment for ${inv.invoice_number} — ${inv.vendor_name}`,
            // NCoA segments carried in from the invoice — silent, resolved at submit.
            // admin_code stays as the user-selected MDA (top of form); we
            // prefer the invoice's MDA only if the user hasn't picked one yet.
            admin_code: prev.admin_code || inv.mda_code,
            economic_code: inv.account_code,
            functional_code: inv.function_code,
            programme_code: inv.program_code,
            fund_code: inv.fund_code,
            geo_code: inv.geo_code,
        }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!form.admin_code) {
            setFormError('MDA is required — please pick an MDA at the top of the form.');
            return;
        }
        if (!selectedInvoice) {
            setFormError(
                'Please select a payable invoice — the PV draws its budget line ' +
                'and payee details from the invoice.'
            );
            return;
        }

        // Resolve NCoA code from the six segments carried in from the invoice.
        let ncoaCodeId: number | null = null;
        if (form.admin_code && form.economic_code && form.functional_code &&
            form.programme_code && form.fund_code && form.geo_code) {
            try {
                const { data } = await apiClient.post('/accounting/ncoa/codes/resolve/', {
                    admin_code: form.admin_code, economic_code: form.economic_code,
                    functional_code: form.functional_code, programme_code: form.programme_code,
                    fund_code: form.fund_code, geo_code: form.geo_code,
                });
                ncoaCodeId = data.id;
            } catch (err: any) {
                setFormError(err.response?.data?.error || 'Failed to resolve NCoA code from the selected invoice.');
                return;
            }
        } else {
            setFormError(
                "The selected invoice doesn't have all six NCoA segments populated. " +
                'Ask the originator to complete the invoice coding before raising a PV.'
            );
            return;
        }

        const payload: Record<string, unknown> = {
            payment_type: form.payment_type, ncoa_code: ncoaCodeId,
            payee_name: form.payee_name, payee_account: form.payee_account,
            payee_bank: form.payee_bank, payee_sort_code: form.payee_sort_code,
            gross_amount: form.gross_amount,
            // wht_amount kept at 0 on the header when deduction lines are used;
            // the backend reads the sum of WHT-typed deduction rows.
            wht_amount: deductions.length > 0 ? '0' : (form.wht_amount || '0'),
            deductions: serializeDeductions(deductions),
            narration: form.narration,
            source_document: form.source_document,
            invoice_number: form.invoice_number,
            invoice_date: form.invoice_date || null,
            notes: form.notes,
        };

        try {
            await createPV.mutateAsync(payload);
            navigate('/accounting/payment-vouchers');
        } catch (err: any) {
            const d = err.response?.data;
            if (d?.detail) setFormError(d.detail);
            else if (d && typeof d === 'object') {
                const msgs = Object.entries(d).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(msgs.join(' | '));
            } else setFormError(err.message || 'Failed to create Payment Voucher');
        }
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="New Payment Voucher"
                    subtitle="Raise a payment request — Treasury will post the final payment from the Outgoing Payments screen"
                    icon={<Receipt size={22} />}
                    actions={
                        <>
                            <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                <X size={18} /> Cancel
                            </button>
                            <button type="submit" form="pv-form" className="btn btn-primary" disabled={createPV.isPending}>
                                <Save size={18} /> {createPV.isPending ? 'Creating…' : 'Raise Payment Request'}
                            </button>
                        </>
                    }
                />

                {formError && (
                    <div style={{
                        padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                        color: '#ef4444', fontSize: 'var(--text-sm)',
                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                    }}>
                        <AlertCircle size={15} /> {formError}
                    </div>
                )}

                <form id="pv-form" onSubmit={handleSubmit} style={{ maxWidth: 1000 }}>

                    {/* ── 1. MDA (mandatory, first) ────────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <Building2 size={18} /> MDA
                            <span className="required-mark"> *</span>
                        </h3>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1rem' }}>
                            Determines the budget line. Invoices below are filtered to
                            this MDA so you pay only against its approved spend.
                        </p>
                        <SearchableSelect
                            options={(segments?.administrative || []).map((s: any) => ({
                                value: s.code, label: `${s.code} - ${s.name}`, sublabel: s.mda_type || s.level,
                            }))}
                            value={form.admin_code}
                            onChange={(v) => {
                                set('admin_code', v);
                                // Clear selected invoice when MDA changes — the old
                                // selection is now irrelevant to the new scope.
                                setSelectedInvoice(null);
                                setInvoiceSearch('');
                            }}
                            placeholder="Type MDA name or code..."
                            required
                        />
                    </div>

                    {/* ── 2. Payment Type + Invoice Search ─────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem', opacity: form.admin_code ? 1 : 0.55 }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>
                            Payment Type &amp; Invoice
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '1.5rem', alignItems: 'end' }}>
                            <div>
                                <label style={labelStyle}>Payment Type</label>
                                <select className="input" value={form.payment_type} onChange={e => set('payment_type', e.target.value)} disabled={!form.admin_code}>
                                    {PAYMENT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </div>
                            <div ref={dropdownRef} style={{ position: 'relative' }}>
                                <label style={labelStyle}>
                                    Invoice / Document Number<span className="required-mark"> *</span>
                                    <span style={{ fontWeight: 400, textTransform: 'none', color: 'var(--color-text-muted)' }}> — filtered by MDA</span>
                                </label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)', zIndex: 1 }} />
                                    <input
                                        className="input"
                                        style={{ paddingLeft: '2rem' }}
                                        disabled={!form.admin_code}
                                        value={invoiceSearch}
                                        onChange={e => { setInvoiceSearch(e.target.value); setSelectedInvoice(null); }}
                                        onFocus={() => setShowDropdown(true)}
                                        placeholder={form.admin_code ? 'Type invoice number or vendor name…' : 'Pick an MDA first'}
                                    />
                                </div>
                                {showDropdown && form.admin_code && (
                                    <div style={{
                                        position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                                        marginTop: 4, background: 'var(--color-surface, #fff)',
                                        border: '2px solid var(--color-border)', borderRadius: '8px',
                                        boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                                        maxHeight: 300, overflowY: 'auto',
                                    }}>
                                        {searchLoading ? (
                                            <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>Searching…</div>
                                        ) : invoiceResults.length === 0 ? (
                                            <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>No payable invoices for this MDA</div>
                                        ) : (
                                            invoiceResults.map(inv => (
                                                <button key={inv.id} type="button" onClick={() => handleSelectInvoice(inv)} style={{
                                                    width: '100%', padding: '0.625rem 0.75rem', border: 'none',
                                                    background: selectedInvoice?.id === inv.id ? 'rgba(25,30,106,0.06)' : 'transparent',
                                                    cursor: 'pointer', textAlign: 'left',
                                                    borderBottom: '1px solid var(--color-border)',
                                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                                }}>
                                                    <div>
                                                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                            {inv.invoice_number}
                                                            {inv.purchase_order && <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}> (PO: {inv.purchase_order})</span>}
                                                        </div>
                                                        <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>
                                                            {inv.vendor_name} — {inv.description?.substring(0, 50) || 'No description'}
                                                        </div>
                                                    </div>
                                                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                                                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--primary, #191e6a)' }}>{fmtNGN(inv.balance_due)}</div>
                                                        <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)' }}>{formatDate(inv.invoice_date)}</div>
                                                    </div>
                                                </button>
                                            ))
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                        {selectedInvoice && (
                            <div style={{
                                marginTop: '0.75rem', padding: '0.625rem 0.75rem', borderRadius: '6px',
                                background: 'rgba(22,101,52,0.06)', border: '1px solid rgba(22,101,52,0.15)',
                                fontSize: 'var(--text-xs)', color: '#166534',
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                            }}>
                                <FileText size={14} />
                                Linked to invoice <strong>{selectedInvoice.invoice_number}</strong> — {selectedInvoice.vendor_name} — Balance: <strong>{fmtNGN(selectedInvoice.balance_due)}</strong>
                                {selectedInvoice.fund_code && <span>— Fund: {selectedInvoice.fund_code}</span>}
                                {selectedInvoice.account_code && <span>— Econ: {selectedInvoice.account_code}</span>}
                            </div>
                        )}
                    </div>

                    {/* ── 3. Supplier Details (HORIZONTAL, optional) ─ */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>
                            Supplier Details
                            <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginLeft: '0.5rem' }}>
                                (optional — auto-filled from invoice, Treasury can amend)
                            </span>
                        </h3>
                        {/* Four fields in a single horizontal row */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Supplier Name</label>
                                <input className="input" value={form.payee_name} onChange={e => set('payee_name', e.target.value)} placeholder="Vendor or employee" />
                            </div>
                            <div>
                                <label style={labelStyle}>Bank</label>
                                <input className="input" value={form.payee_bank} onChange={e => set('payee_bank', e.target.value)} placeholder="Bank name" />
                            </div>
                            <div>
                                <label style={labelStyle}>Account Number</label>
                                <input className="input" value={form.payee_account} onChange={e => set('payee_account', e.target.value)} placeholder="NUBAN" />
                            </div>
                            <div>
                                <label style={labelStyle}>Sort Code</label>
                                <input className="input" value={form.payee_sort_code} onChange={e => set('payee_sort_code', e.target.value)} />
                            </div>
                        </div>
                    </div>

                    {/* ── 4. Amount & Deductions ───────────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>
                            Amount &amp; Deductions
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem', marginBottom: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Gross Amount (NGN)<span className="required-mark"> *</span></label>
                                <input className="input" style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}
                                    type="text" inputMode="decimal" required
                                    value={formatThousandsInput(form.gross_amount)}
                                    onChange={e => {
                                        const raw = stripThousands(e.target.value);
                                        if (raw === '' || /^\d*\.?\d{0,2}$/.test(raw)) set('gross_amount', raw);
                                    }}
                                    placeholder="0.00" />
                            </div>
                            <div>
                                <label style={labelStyle}>Total Deductions</label>
                                <div style={{
                                    ...inputStyle,
                                    background: 'rgba(234,179,8,0.06)',
                                    fontWeight: 700,
                                    color: '#ca8a04',
                                    display: 'flex', alignItems: 'center',
                                }}>
                                    {fmtNGN(totalDeductions)}
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Net Paid to Vendor</label>
                                <div style={{
                                    ...inputStyle,
                                    background: 'rgba(25,30,106,0.04)',
                                    fontWeight: 700, fontSize: 'var(--text-base)',
                                    color: 'var(--primary, #191e6a)',
                                    display: 'flex', alignItems: 'center',
                                }}>
                                    {fmtNGN(netAmount)}
                                </div>
                            </div>
                        </div>

                        {/* Deduction lines — shared editor (create + draft edit) */}
                        <DeductionLinesEditor
                            gross={grossNum}
                            deductions={deductions}
                            setDeductions={setDeductions}
                        />

                        <div style={{ marginTop: '1.5rem' }}>
                            <label style={labelStyle}>Narration<span className="required-mark"> *</span></label>
                            <textarea className="input" style={{ width: '100%', minHeight: '60px' }} required
                                value={form.narration}
                                onChange={e => set('narration', e.target.value)}
                                placeholder="Description of goods/services..." />
                        </div>
                    </div>

                    {/* ── 5. Source Documents (existing, unchanged) ── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>
                            Source Documents
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem' }}>
                            <div><label style={labelStyle}>PO / Contract Ref</label><input className="input" value={form.source_document} onChange={e => set('source_document', e.target.value)} /></div>
                            <div><label style={labelStyle}>Invoice Number</label><input className="input" value={form.invoice_number} onChange={e => set('invoice_number', e.target.value)} /></div>
                            <div><label style={labelStyle}>Invoice Date</label><input className="input" type="date" value={form.invoice_date} onChange={e => set('invoice_date', e.target.value)} /></div>
                        </div>
                        <div style={{ marginTop: '1.5rem' }}>
                            <label style={labelStyle}>Notes</label>
                            <textarea className="input" style={{ width: '100%', minHeight: '50px' }} value={form.notes} onChange={e => set('notes', e.target.value)} />
                        </div>
                    </div>

                    {/* Info banner — clarifies where the budget line comes from */}
                    <div style={{
                        padding: '0.625rem 0.875rem', borderRadius: '6px',
                        background: 'rgba(25,30,106,0.04)', border: '1px solid rgba(25,30,106,0.1)',
                        fontSize: '0.7rem', color: 'var(--color-text-muted)', lineHeight: 1.6,
                        marginBottom: '0.75rem',
                    }}>
                        <strong>How this PV books:</strong> MDA (above) + the selected invoice's
                        economic code + fund determine the budget line automatically. Treasury
                        will post the final cash payment from the Outgoing Payments screen.
                    </div>

                    {/* Footer actions mirror the header buttons for long-form scrolling */}
                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button type="button" onClick={() => navigate(-1)} className="btn btn-outline">
                            <X size={18} /> Cancel
                        </button>
                        <button type="submit" className="btn btn-primary" disabled={createPV.isPending}>
                            <Save size={18} /> {createPV.isPending ? 'Creating…' : 'Raise Payment Request'}
                        </button>
                    </div>
                </form>
            </main>
        </div>
    );
}
