/**
 * Advance Request Form — Quot PSE
 * Route: /accounting/advance-requests/new
 *
 * Requests a payment advance (mobilisation, imprest, staff, travel, …).
 * The operator picks a budget line (appropriation) plus payee / amount /
 * purpose; on submit the backend materialises a DRAFT Payment Voucher
 * (NCoA + TSA resolved server-side) that appears in the PV list for the
 * normal approval → payment workflow.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, HandCoins, X, Building2 } from 'lucide-react';
import { useQuery, useMutation } from '@tanstack/react-query';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import SearchableSelect from '../../components/SearchableSelect';
import apiClient from '../../api/client';
import { formatThousandsInput, stripThousands } from '@/utils/number';

interface Appropriation {
    id: number;
    budget_code?: string;
    administrative_code: string; administrative_name: string;
    economic_code: string; economic_name: string;
    fund_code: string; fund_name: string;
    status: string;
}

const ADVANCE_TYPES: string[] = [
    'Mobilization Advance',
    'Operational / Imprest Advance',
    'Staff Advance',
    'Travel Advance',
    'Other Advance',
];

const fmtNGN = (v: number | string): string => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    if (isNaN(n)) return '₦0.00';
    return '₦' + n.toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const labelStyle: React.CSSProperties = {
    display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
    fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
};

export default function AdvanceRequestForm() {
    const navigate = useNavigate();
    const [formError, setFormError] = useState('');
    const [form, setForm] = useState({
        appropriation: '', advance_type: ADVANCE_TYPES[0],
        payee_name: '', payee_bank: '', payee_account: '',
        amount: '', purpose: '',
    });
    const set = (field: string, value: string) => setForm(p => ({ ...p, [field]: value }));

    const { data: appropriations } = useQuery<Appropriation[]>({
        queryKey: ['appropriations', 'active'],
        queryFn: async () => {
            const { data } = await apiClient.get('/budget/appropriations/', {
                params: { status: 'ACTIVE', page_size: 2000 },
            });
            return Array.isArray(data) ? data : (data.results ?? []);
        },
        staleTime: 5 * 60 * 1000,
    });

    // Each budget line carries its six NCoA segments; label by economic
    // line, sublabel by MDA + fund so the operator can search either.
    const appropriationOptions = useMemo(() => (appropriations || []).map(a => ({
        value: String(a.id),
        label: `${a.economic_code} — ${a.economic_name}`,
        sublabel: `${a.administrative_name} · Fund ${a.fund_name}`,
    })), [appropriations]);

    const createAdvance = useMutation({
        mutationFn: async (payload: Record<string, unknown>) => {
            const { data } = await apiClient.post('/accounting/payment-vouchers/create-advance/', payload);
            return data;
        },
    });

    const amtNum = parseFloat(form.amount) || 0;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');
        if (!form.appropriation) { setFormError('Select a budget line for the advance.'); return; }
        if (amtNum <= 0) { setFormError('Enter a valid advance amount.'); return; }
        if (!form.payee_name.trim()) { setFormError('Enter the payee / beneficiary name.'); return; }
        if (!form.purpose.trim()) { setFormError('Enter the purpose of the advance.'); return; }
        try {
            await createAdvance.mutateAsync({
                appropriation: Number(form.appropriation),
                advance_type: form.advance_type,
                payee_name: form.payee_name,
                payee_bank: form.payee_bank,
                payee_account: form.payee_account,
                amount: form.amount,
                purpose: form.purpose,
            });
            // The draft PV now lives in the PV list.
            navigate('/accounting/payment-vouchers');
        } catch (err: any) {
            setFormError(err.response?.data?.error || err.message || 'Failed to create the advance request.');
        }
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Advance Request"
                    subtitle="Request a payment advance — creates a draft Payment Voucher for approval"
                    icon={<HandCoins size={22} />}
                    actions={
                        <>
                            <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                <X size={18} /> Cancel
                            </button>
                            <button type="submit" form="advance-form" className="btn btn-primary" disabled={createAdvance.isPending}>
                                <Save size={18} /> {createAdvance.isPending ? 'Submitting…' : 'Submit Advance Request'}
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

                <form id="advance-form" onSubmit={handleSubmit} style={{ maxWidth: 900 }}>
                    {/* Budget line + type */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <Building2 size={18} /> Budget Line &amp; Type
                        </h3>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1rem' }}>
                            The budget line supplies the NCoA classification the advance is charged to.
                        </p>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: '1.5rem', alignItems: 'start' }}>
                            <div>
                                <label style={labelStyle}>Budget Line (Appropriation)<span className="required-mark"> *</span></label>
                                <SearchableSelect
                                    options={appropriationOptions}
                                    value={form.appropriation}
                                    onChange={(v) => set('appropriation', v)}
                                    placeholder="Search budget line by code, MDA or fund…"
                                    required
                                />
                            </div>
                            <div>
                                <label style={labelStyle}>Advance Type<span className="required-mark"> *</span></label>
                                <select className="input" value={form.advance_type} onChange={e => set('advance_type', e.target.value)}>
                                    {ADVANCE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                            </div>
                        </div>
                    </div>

                    {/* Beneficiary */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Beneficiary</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Payee / Beneficiary Name<span className="required-mark"> *</span></label>
                                <input className="input" value={form.payee_name} onChange={e => set('payee_name', e.target.value)} placeholder="Vendor, contractor or staff" />
                            </div>
                            <div>
                                <label style={labelStyle}>Bank</label>
                                <input className="input" value={form.payee_bank} onChange={e => set('payee_bank', e.target.value)} placeholder="Bank name" />
                            </div>
                            <div>
                                <label style={labelStyle}>Account Number</label>
                                <input className="input" value={form.payee_account} onChange={e => set('payee_account', e.target.value)} placeholder="NUBAN" />
                            </div>
                        </div>
                    </div>

                    {/* Amount + purpose */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Amount &amp; Purpose</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Advance Amount (NGN)<span className="required-mark"> *</span></label>
                                <input className="input" style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}
                                    type="text" inputMode="decimal" required
                                    value={formatThousandsInput(form.amount)}
                                    onChange={e => {
                                        const raw = stripThousands(e.target.value);
                                        if (raw === '' || /^\d*\.?\d{0,2}$/.test(raw)) set('amount', raw);
                                    }}
                                    placeholder="0.00" />
                                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                                    {fmtNGN(amtNum)}
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Purpose / Justification<span className="required-mark"> *</span></label>
                                <textarea className="input" style={{ width: '100%', minHeight: '80px' }} required
                                    value={form.purpose}
                                    onChange={e => set('purpose', e.target.value)}
                                    placeholder="What is the advance for?" />
                            </div>
                        </div>
                    </div>

                    <div style={{
                        padding: '0.625rem 0.875rem', borderRadius: '6px',
                        background: 'rgba(25,30,106,0.04)', border: '1px solid rgba(25,30,106,0.1)',
                        fontSize: '0.7rem', color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: '0.75rem',
                    }}>
                        <strong>What happens next:</strong> submitting creates a <strong>draft Payment Voucher</strong> in the
                        Payment Vouchers list. Treasury reviews, approves and schedules it for payment from there.
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button type="button" onClick={() => navigate(-1)} className="btn btn-outline">
                            <X size={18} /> Cancel
                        </button>
                        <button type="submit" className="btn btn-primary" disabled={createAdvance.isPending}>
                            <Save size={18} /> {createAdvance.isPending ? 'Submitting…' : 'Submit Advance Request'}
                        </button>
                    </div>
                </form>
            </main>
        </div>
    );
}
