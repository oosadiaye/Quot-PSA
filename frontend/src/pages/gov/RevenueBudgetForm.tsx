/**
 * Revenue Budget (Target) Create Form — Quot PSE
 * Route: /budget/revenue-budget/new
 *
 * Creates a statistical revenue target — no enforcement.
 * Tracks estimated vs actual IGR/FAAC collections per MDA.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, X, TrendingUp } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import { useNCoASegments, useFiscalYears } from '../../hooks/useGovForms';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

export default function RevenueBudgetForm() {
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: segments } = useNCoASegments();
    const { data: fiscalYears } = useFiscalYears();

    const [formError, setFormError] = useState('');
    const [useMonthlySpread, setUseMonthlySpread] = useState(false);
    const [form, setForm] = useState({
        fiscal_year: '', administrative: '', economic: '', fund: '',
        estimated_amount: '', description: '', notes: '',
    });
    const [monthly, setMonthly] = useState<Record<string, string>>({});

    const createMutation = useMutation({
        mutationFn: (data: Record<string, unknown>) => apiClient.post('/budget/revenue-budgets/', data),
        onSuccess: () => { qc.invalidateQueries({ queryKey: ['generic-list'] }); navigate('/budget/revenue-budget'); },
        onError: (err: any) => setFormError(err?.response?.data?.detail || JSON.stringify(err?.response?.data) || 'Failed to create'),
    });

    const set = (field: string, value: string) => setForm(prev => ({ ...prev, [field]: value }));

    // Filter economic segments to revenue type only (account_type_code = '1')
    const revenueAccounts = (segments?.economic || []).filter((s: any) => s.account_type_code === '1' || s.code?.startsWith('1'));

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');
        if (!form.fiscal_year || !form.administrative || !form.economic || !form.fund || !form.estimated_amount) {
            setFormError('All required fields must be filled');
            return;
        }

        const spread = useMonthlySpread
            ? Object.fromEntries(Object.entries(monthly).filter(([, v]) => v).map(([k, v]) => [k, parseFloat(v)]))
            : null;

        createMutation.mutate({
            fiscal_year: parseInt(form.fiscal_year),
            administrative: parseInt(form.administrative),
            economic: parseInt(form.economic),
            fund: parseInt(form.fund),
            estimated_amount: form.estimated_amount,
            monthly_spread: spread,
            status: 'ACTIVE',
            description: form.description,
            notes: form.notes,
        });
    };

    const annualAmount = parseFloat(form.estimated_amount) || 0;
    const equalMonthly = annualAmount > 0 ? (annualAmount / 12).toFixed(2) : '0.00';

    const labelStyle: React.CSSProperties = {
        display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
        fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
    };
    const helpStyle: React.CSSProperties = {
        fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px',
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <form onSubmit={handleSubmit}>
                    <PageHeader
                        title="New Revenue Budget Target"
                        subtitle="Statistical target — no enforcement, for performance tracking only"
                        icon={<TrendingUp size={22} />}
                        actions={
                            <>
                                <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                    <X size={18} /> Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
                                    <Save size={18} /> {createMutation.isPending ? 'Saving...' : 'Create Revenue Target'}
                                </button>
                            </>
                        }
                    />

                    {formError && (
                        <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1rem' }}>
                            {formError}
                        </div>
                    )}

                    {/* ── Revenue Target Details ───────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Revenue Target Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Fiscal Year<span className="required-mark"> *</span></label>
                                <select className="input" required value={form.fiscal_year} onChange={e => set('fiscal_year', e.target.value)}>
                                    <option value="">Select year...</option>
                                    {(fiscalYears || []).map((fy: any) => <option key={fy.id} value={fy.id}>{fy.name || fy.year}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>MDA (Collecting Ministry)<span className="required-mark"> *</span></label>
                                <select className="input" required value={form.administrative} onChange={e => set('administrative', e.target.value)}>
                                    <option value="">Select MDA...</option>
                                    {(segments?.administrative || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Revenue Account (NCoA Economic)<span className="required-mark"> *</span></label>
                                <select className="input" required value={form.economic} onChange={e => set('economic', e.target.value)}>
                                    <option value="">Select revenue account...</option>
                                    {revenueAccounts.map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                </select>
                                <p style={helpStyle}>Type 1 (revenue) accounts only.</p>
                            </div>
                            <div>
                                <label style={labelStyle}>Fund Source<span className="required-mark"> *</span></label>
                                <select className="input" required value={form.fund} onChange={e => set('fund', e.target.value)}>
                                    <option value="">Select fund...</option>
                                    {(segments?.fund || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                </select>
                            </div>
                            <div style={{ gridColumn: '1 / -1' }}>
                                <label style={labelStyle}>Annual Target Amount (NGN)<span className="required-mark"> *</span></label>
                                <input className="input" style={{ fontSize: '18px', fontWeight: 700 }} type="number" step="0.01" min="0.01" required value={form.estimated_amount} onChange={e => set('estimated_amount', e.target.value)} placeholder="0.00" />
                            </div>
                        </div>
                    </div>

                    {/* ── Monthly Target Spread ────────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                            <h3 style={{ margin: 0 }}>Monthly Target Spread</h3>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12 }}>
                                <input type="checkbox" checked={useMonthlySpread} onChange={e => setUseMonthlySpread(e.target.checked)} />
                                Custom monthly targets
                            </label>
                        </div>
                        {useMonthlySpread ? (
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem' }}>
                                {MONTHS.map((name, i) => (
                                    <div key={i}>
                                        <label style={labelStyle}>{name}</label>
                                        <input className="input" type="number" step="0.01" placeholder={equalMonthly}
                                            value={monthly[String(i + 1)] || ''} onChange={e => setMonthly(prev => ({ ...prev, [String(i + 1)]: e.target.value }))} />
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div style={{ color: 'var(--color-text-muted)', fontSize: 13 }}>
                                Annual target will be divided equally: <strong>{'₦'}{Number(equalMonthly).toLocaleString('en-NG', { minimumFractionDigits: 2 })}</strong> per month
                            </div>
                        )}
                    </div>

                    {/* ── Description ──────────────────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Description</h3>
                        <div>
                            <label style={labelStyle}>Description</label>
                            <textarea className="input" style={{ width: '100%', minHeight: '50px' }} value={form.description} onChange={e => set('description', e.target.value)} placeholder="Revenue target description..." />
                        </div>
                    </div>
                </form>
            </main>
        </div>
    );
}
