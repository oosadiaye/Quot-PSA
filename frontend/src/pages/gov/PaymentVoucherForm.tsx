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
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, Receipt, Search, FileText, Building2 } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import SearchableSelect from '../../components/SearchableSelect';
import '../../features/accounting/styles/glassmorphism.css';
import { useCreatePV, useNCoASegments } from '../../hooks/useGovForms';
import apiClient from '../../api/client';

const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const selectStyle = inputStyle;
const lblStyle: React.CSSProperties = {
    display: 'block', fontSize: '0.65rem', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.25rem',
    textTransform: 'uppercase' as const, letterSpacing: '0.04em',
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

    const netAmount = useMemo(() => {
        const gross = parseFloat(form.gross_amount) || 0;
        const wht = parseFloat(form.wht_amount) || 0;
        return Math.max(0, gross - wht);
    }, [form.gross_amount, form.wht_amount]);

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
            gross_amount: form.gross_amount, wht_amount: form.wht_amount || '0',
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

                <form onSubmit={handleSubmit} style={{ maxWidth: 1000 }}>

                    {/* ── 1. MDA (mandatory, first) ────────────────── */}
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <Building2 size={15} /> 1. MDA
                            <span style={{ color: '#ef4444', marginLeft: '0.25rem' }}>*</span>
                        </h3>
                        <p style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', margin: '0 0 0.5rem 0' }}>
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
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem', opacity: form.admin_code ? 1 : 0.55 }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>
                            2. Payment Type & Invoice
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '0.75rem', alignItems: 'end' }}>
                            <div>
                                <label style={lblStyle}>Payment Type</label>
                                <select style={selectStyle} value={form.payment_type} onChange={e => set('payment_type', e.target.value)} disabled={!form.admin_code}>
                                    {PAYMENT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </div>
                            <div ref={dropdownRef} style={{ position: 'relative' }}>
                                <label style={lblStyle}>
                                    Invoice / Document Number <span style={{ color: '#ef4444' }}>*</span>
                                    <span style={{ fontWeight: 400, textTransform: 'none', color: 'var(--color-text-muted)' }}> — filtered by MDA</span>
                                </label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                                    <input
                                        style={{ ...inputStyle, paddingLeft: '2rem' }}
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
                                                        <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)' }}>{inv.invoice_date}</div>
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
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>
                            3. Supplier Details
                            <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', fontSize: '0.7rem', marginLeft: '0.5rem' }}>
                                (optional — auto-filled from invoice, Treasury can amend)
                            </span>
                        </h3>
                        {/* Four fields in a single horizontal row */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0.75rem' }}>
                            <div>
                                <label style={lblStyle}>Supplier Name</label>
                                <input style={inputStyle} value={form.payee_name} onChange={e => set('payee_name', e.target.value)} placeholder="Vendor or employee" />
                            </div>
                            <div>
                                <label style={lblStyle}>Bank</label>
                                <input style={inputStyle} value={form.payee_bank} onChange={e => set('payee_bank', e.target.value)} placeholder="Bank name" />
                            </div>
                            <div>
                                <label style={lblStyle}>Account Number</label>
                                <input style={inputStyle} value={form.payee_account} onChange={e => set('payee_account', e.target.value)} placeholder="NUBAN" />
                            </div>
                            <div>
                                <label style={lblStyle}>Sort Code</label>
                                <input style={inputStyle} value={form.payee_sort_code} onChange={e => set('payee_sort_code', e.target.value)} />
                            </div>
                        </div>
                    </div>

                    {/* ── 4. Amount & Narration ────────────────────── */}
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>
                            4. Amount &amp; Narration
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                            <div>
                                <label style={lblStyle}>Gross Amount (NGN) <span style={{ color: '#ef4444' }}>*</span></label>
                                <input style={{ ...inputStyle, fontSize: 'var(--text-base)', fontWeight: 700 }} type="number" step="0.01" min="0.01" required value={form.gross_amount} onChange={e => set('gross_amount', e.target.value)} placeholder="0.00" />
                            </div>
                            <div>
                                <label style={lblStyle}>WHT Deduction (NGN)</label>
                                <input style={inputStyle} type="number" step="0.01" min="0" value={form.wht_amount} onChange={e => set('wht_amount', e.target.value)} placeholder="0.00" />
                            </div>
                            <div>
                                <label style={lblStyle}>Net Amount</label>
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
                        <div style={{ marginTop: '0.75rem' }}>
                            <label style={lblStyle}>Narration <span style={{ color: '#ef4444' }}>*</span></label>
                            <textarea style={{ ...inputStyle, minHeight: '60px' }} required value={form.narration} onChange={e => set('narration', e.target.value)} placeholder="Description of goods/services..." />
                        </div>
                    </div>

                    {/* ── 5. Source Documents (existing, unchanged) ── */}
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>
                            5. Source Documents
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                            <div><label style={lblStyle}>PO / Contract Ref</label><input style={inputStyle} value={form.source_document} onChange={e => set('source_document', e.target.value)} /></div>
                            <div><label style={lblStyle}>Invoice Number</label><input style={inputStyle} value={form.invoice_number} onChange={e => set('invoice_number', e.target.value)} /></div>
                            <div><label style={lblStyle}>Invoice Date</label><input style={inputStyle} type="date" value={form.invoice_date} onChange={e => set('invoice_date', e.target.value)} /></div>
                        </div>
                        <div style={{ marginTop: '0.75rem' }}>
                            <label style={lblStyle}>Notes</label>
                            <textarea style={{ ...inputStyle, minHeight: '50px' }} value={form.notes} onChange={e => set('notes', e.target.value)} />
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

                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button type="button" onClick={() => navigate(-1)} className="glass-button" style={{ padding: '0.625rem 1.25rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)' }}>Cancel</button>
                        <button type="submit" disabled={createPV.isPending} style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', padding: '0.625rem 1.25rem', borderRadius: '8px', border: 'none', background: 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)', color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: 'var(--text-sm)', boxShadow: '0 4px 12px rgba(15,18,64,0.3)', opacity: createPV.isPending ? 0.7 : 1 }}>
                            <Save size={16} /> {createPV.isPending ? 'Creating…' : 'Raise Payment Request'}
                        </button>
                    </div>
                </form>
            </main>
        </div>
    );
}
