/**
 * Vendor Down Payment — Quot PSE
 * Route: /accounting/advance-requests/new
 *
 * SAP-Fiori-styled request for a vendor down payment (special G/L "A"):
 * an advance to a supplier that is NOT charged to an expense line — it is
 * capitalised as a balance-sheet advance (DR advance / CR cash) and cleared
 * later against the vendor's invoices. Submitting creates a DRAFT Payment
 * Voucher that appears in the PV list for the normal approval → payment flow.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import Sidebar from '../../components/Sidebar';
import SearchableSelect from '../../components/SearchableSelect';
import apiClient from '../../api/client';
import { formatThousandsInput, stripThousands } from '@/utils/number';

interface Vendor {
    id: number;
    code: string;
    name: string;
    tax_id?: string;
}

// ── SAP Fiori design tokens ───────────────────────────────────────────
const FIORI = {
    blue: '#0a6ed1',
    blueDark: '#0854a0',
    bg: '#f5f6f7',
    card: '#ffffff',
    border: '#e5e5e5',
    label: '#6a6d70',
    text: '#32363a',
    green: '#107e3e',
    amber: '#e9730c',
};

const fioriLabel: React.CSSProperties = {
    display: 'block', fontSize: '0.75rem', color: FIORI.label,
    marginBottom: '0.35rem', fontWeight: 400,
};
const fioriInput: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.65rem', fontSize: '0.875rem',
    color: FIORI.text, background: '#fff',
    border: `1px solid #b3b3b3`, borderRadius: '4px', outline: 'none',
};
const fioriReadonly: React.CSSProperties = {
    ...fioriInput, background: '#f2f2f2', color: FIORI.label, borderColor: FIORI.border,
};
const sectionCard: React.CSSProperties = {
    background: FIORI.card, border: `1px solid ${FIORI.border}`,
    borderRadius: '8px', padding: '1.25rem 1.5rem', marginBottom: '1rem',
};
const sectionTitle: React.CSSProperties = {
    margin: '0 0 1rem', fontSize: '1rem', fontWeight: 700, color: FIORI.text,
};

const fmtNGN = (v: number | string): string => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    if (isNaN(n)) return '₦0.00';
    return '₦' + n.toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

export default function AdvanceRequestForm() {
    const navigate = useNavigate();
    const [formError, setFormError] = useState('');
    const [form, setForm] = useState({
        vendor: '', amount: '', due_date: '', reference: '', purpose: '',
    });
    const set = (field: string, value: string) => setForm(p => ({ ...p, [field]: value }));

    const { data: vendors } = useQuery<Vendor[]>({
        queryKey: ['vendors', 'active'],
        queryFn: async () => {
            const { data } = await apiClient.get('/procurement/vendors/', {
                params: { is_active: true, page_size: 2000 },
            });
            return Array.isArray(data) ? data : (data.results ?? []);
        },
        staleTime: 5 * 60 * 1000,
    });

    const vendorOptions = useMemo(() => (vendors || []).map(v => ({
        value: String(v.id),
        label: v.name,
        sublabel: `${v.code}${v.tax_id ? ' · TIN ' + v.tax_id : ''}`,
    })), [vendors]);

    const selectedVendor = useMemo(
        () => (vendors || []).find(v => String(v.id) === form.vendor),
        [vendors, form.vendor],
    );

    const createDownPayment = useMutation({
        mutationFn: async (payload: Record<string, unknown>) => {
            const { data } = await apiClient.post('/accounting/payment-vouchers/create-advance/', payload);
            return data;
        },
    });

    const amtNum = parseFloat(form.amount) || 0;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');
        if (!form.vendor) { setFormError('Select a vendor for the down payment.'); return; }
        if (amtNum <= 0) { setFormError('Enter a valid down payment amount.'); return; }
        try {
            await createDownPayment.mutateAsync({
                vendor: Number(form.vendor),
                amount: form.amount,
                due_date: form.due_date || null,
                reference: form.reference,
                purpose: form.purpose,
            });
            navigate('/accounting/payment-vouchers');
        } catch (err: any) {
            setFormError(err.response?.data?.error || err.message || 'Failed to create the down payment request.');
        }
    };

    const chip = (text: string, bg: string, color: string): React.CSSProperties => ({
        display: 'inline-flex', alignItems: 'center', padding: '0.2rem 0.6rem',
        borderRadius: '999px', fontSize: '0.7rem', fontWeight: 600,
        background: bg, color, letterSpacing: '0.02em',
    });

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', background: FIORI.bg, minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
                {/* Fiori object header */}
                <div style={{ background: '#fff', borderBottom: `1px solid ${FIORI.border}`, padding: '1.1rem 2rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
                        <div>
                            <div style={{ fontSize: '0.72rem', color: FIORI.label, marginBottom: '0.15rem' }}>Vendor Payments</div>
                            <h1 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 700, color: FIORI.text }}>Vendor Down Payment</h1>
                            <div style={{ fontSize: '0.8rem', color: FIORI.label, marginTop: '0.2rem' }}>
                                Special G/L “A” — advance to a supplier, cleared against future invoices
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                            <span style={chip('Draft', 'rgba(233,115,12,0.12)', FIORI.amber)}>Draft</span>
                            <span style={chip('Special G/L: A', 'rgba(10,110,209,0.1)', FIORI.blue)}>Special G/L: A</span>
                        </div>
                    </div>
                </div>

                {/* Form body */}
                <form id="dp-form" onSubmit={handleSubmit} style={{ flex: 1, overflow: 'auto' }}>
                    <div style={{ padding: '1.5rem 2rem', maxWidth: 940 }}>
                        {formError && (
                            <div style={{
                                padding: '0.65rem 0.9rem', borderRadius: '6px', marginBottom: '1rem',
                                background: 'rgba(187,0,0,0.06)', border: '1px solid rgba(187,0,0,0.25)',
                                color: '#bb0000', fontSize: '0.85rem',
                            }}>
                                {formError}
                            </div>
                        )}

                        {/* Vendor */}
                        <section style={sectionCard}>
                            <h3 style={sectionTitle}>Vendor</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                                <div>
                                    <label style={fioriLabel}>Supplier / Vendor <span style={{ color: '#bb0000' }}>*</span></label>
                                    <SearchableSelect
                                        options={vendorOptions}
                                        value={form.vendor}
                                        onChange={(v) => set('vendor', v)}
                                        placeholder="Search vendor by name or code…"
                                        required
                                    />
                                </div>
                                <div>
                                    <label style={fioriLabel}>Vendor Code / TIN</label>
                                    <input style={fioriReadonly} readOnly
                                        value={selectedVendor ? `${selectedVendor.code}${selectedVendor.tax_id ? '  ·  TIN ' + selectedVendor.tax_id : ''}` : ''}
                                        placeholder="—" />
                                </div>
                            </div>
                        </section>

                        {/* Payment details */}
                        <section style={sectionCard}>
                            <h3 style={sectionTitle}>Payment Details</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
                                <div>
                                    <label style={fioriLabel}>Down Payment Amount (NGN) <span style={{ color: '#bb0000' }}>*</span></label>
                                    <input style={{ ...fioriInput, fontWeight: 700, fontSize: '1rem' }}
                                        type="text" inputMode="decimal" required
                                        value={formatThousandsInput(form.amount)}
                                        onChange={e => {
                                            const raw = stripThousands(e.target.value);
                                            if (raw === '' || /^\d*\.?\d{0,2}$/.test(raw)) set('amount', raw);
                                        }}
                                        placeholder="0.00" />
                                    <div style={{ fontSize: '0.72rem', color: FIORI.label, marginTop: '0.25rem' }}>{fmtNGN(amtNum)}</div>
                                </div>
                                <div>
                                    <label style={fioriLabel}>Due Date</label>
                                    <input style={fioriInput} type="date"
                                        value={form.due_date} onChange={e => set('due_date', e.target.value)} />
                                </div>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                                <div>
                                    <label style={fioriLabel}>Special G/L Indicator</label>
                                    <input style={fioriReadonly} readOnly value="A — Down Payment" />
                                </div>
                                <div>
                                    <label style={fioriLabel}>G/L Account (determined)</label>
                                    <input style={fioriReadonly} readOnly value="Supplier advances / prepayment (asset)" />
                                </div>
                            </div>
                            <div style={{
                                marginTop: '0.9rem', fontSize: '0.75rem', color: FIORI.label,
                                background: 'rgba(10,110,209,0.05)', border: `1px solid rgba(10,110,209,0.15)`,
                                borderRadius: '6px', padding: '0.55rem 0.75rem',
                            }}>
                                No expense is posted. The advance is charged to the supplier-advance / prepayment
                                asset account (system-determined) and cleared against the vendor's future invoices.
                            </div>
                        </section>

                        {/* Reference */}
                        <section style={sectionCard}>
                            <h3 style={sectionTitle}>Reference &amp; Text</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '1.25rem' }}>
                                <div>
                                    <label style={fioriLabel}>Reference / Assignment</label>
                                    <input style={fioriInput} value={form.reference}
                                        onChange={e => set('reference', e.target.value)} placeholder="e.g. DP-2026-001" />
                                </div>
                                <div>
                                    <label style={fioriLabel}>Text</label>
                                    <input style={fioriInput} value={form.purpose}
                                        onChange={e => set('purpose', e.target.value)} placeholder="Purpose of the down payment" />
                                </div>
                            </div>
                        </section>
                    </div>
                </form>

                {/* Fiori footer action bar */}
                <div style={{
                    position: 'sticky', bottom: 0, background: '#fff',
                    borderTop: `1px solid ${FIORI.border}`, padding: '0.7rem 2rem',
                    display: 'flex', justifyContent: 'flex-end', gap: '0.6rem',
                    boxShadow: '0 -1px 4px rgba(0,0,0,0.06)',
                }}>
                    <button type="button" onClick={() => navigate(-1)}
                        style={{
                            padding: '0.5rem 1.1rem', fontSize: '0.85rem', fontWeight: 600,
                            background: '#fff', color: FIORI.blue, border: `1px solid ${FIORI.blue}`,
                            borderRadius: '4px', cursor: 'pointer',
                        }}>
                        Cancel
                    </button>
                    <button type="submit" form="dp-form" disabled={createDownPayment.isPending}
                        style={{
                            padding: '0.5rem 1.3rem', fontSize: '0.85rem', fontWeight: 600,
                            background: FIORI.blue, color: '#fff', border: `1px solid ${FIORI.blue}`,
                            borderRadius: '4px', cursor: createDownPayment.isPending ? 'default' : 'pointer',
                            opacity: createDownPayment.isPending ? 0.7 : 1,
                        }}>
                        {createDownPayment.isPending ? 'Creating…' : 'Create Down Payment'}
                    </button>
                </div>
            </main>
        </div>
    );
}
