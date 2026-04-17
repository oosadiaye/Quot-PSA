/**
 * Revenue Budget (Target) Create Form — Quot PSE
 * Route: /budget/revenue-budget/new
 *
 * Creates a statistical revenue target — no enforcement.
 * Tracks estimated vs actual IGR/FAAC collections per MDA.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, TrendingUp } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import { useNCoASegments, useFiscalYears } from '../../hooks/useGovForms';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

const selectStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const lblStyle: React.CSSProperties = {
    display: 'block', fontSize: '0.65rem', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.25rem',
    textTransform: 'uppercase' as const, letterSpacing: '0.04em',
};

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

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <div style={{ maxWidth: '900px' }}>
                    <PageHeader title="New Revenue Budget Target" subtitle="Statistical target — no enforcement, for performance tracking only" icon={<TrendingUp size={22} />} />

                    {formError && (
                        <div style={{ padding: '10px 14px', borderRadius: '8px', marginBottom: '14px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                            <AlertCircle size={14} /> {formError}
                        </div>
                    )}

                    <form onSubmit={handleSubmit}>
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '6px' }}><TrendingUp size={14} /> Revenue Target Details</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                                <div>
                                    <label style={lblStyle}>Fiscal Year *</label>
                                    <select style={selectStyle} required value={form.fiscal_year} onChange={e => set('fiscal_year', e.target.value)}>
                                        <option value="">Select year...</option>
                                        {(fiscalYears || []).map((fy: any) => <option key={fy.id} value={fy.id}>{fy.name || fy.year}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={lblStyle}>MDA (Collecting Ministry) *</label>
                                    <select style={selectStyle} required value={form.administrative} onChange={e => set('administrative', e.target.value)}>
                                        <option value="">Select MDA...</option>
                                        {(segments?.administrative || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={lblStyle}>Revenue Account (NCoA Economic) * <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}>type 1 only</span></label>
                                    <select style={selectStyle} required value={form.economic} onChange={e => set('economic', e.target.value)}>
                                        <option value="">Select revenue account...</option>
                                        {revenueAccounts.map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={lblStyle}>Fund Source *</label>
                                    <select style={selectStyle} required value={form.fund} onChange={e => set('fund', e.target.value)}>
                                        <option value="">Select fund...</option>
                                        {(segments?.fund || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                    </select>
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={lblStyle}>Annual Target Amount (NGN) *</label>
                                    <input style={{ ...inputStyle, fontSize: '18px', fontWeight: 700 }} type="number" step="0.01" min="0.01" required value={form.estimated_amount} onChange={e => set('estimated_amount', e.target.value)} placeholder="0.00" />
                                </div>
                            </div>
                        </div>

                        {/* Monthly Spread */}
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>Monthly Target Spread</h3>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12 }}>
                                    <input type="checkbox" checked={useMonthlySpread} onChange={e => setUseMonthlySpread(e.target.checked)} />
                                    Custom monthly targets
                                </label>
                            </div>
                            {useMonthlySpread ? (
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px' }}>
                                    {MONTHS.map((name, i) => (
                                        <div key={i}>
                                            <label style={{ ...lblStyle, fontSize: '10px' }}>{name}</label>
                                            <input style={{ ...inputStyle, fontSize: '12px', padding: '7px 8px' }} type="number" step="0.01" placeholder={equalMonthly}
                                                value={monthly[String(i + 1)] || ''} onChange={e => setMonthly(prev => ({ ...prev, [String(i + 1)]: e.target.value }))} />
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div style={{ color: '#64748b', fontSize: 13 }}>
                                    Annual target will be divided equally: <strong>{'\u20A6'}{Number(equalMonthly).toLocaleString('en-NG', { minimumFractionDigits: 2 })}</strong> per month
                                </div>
                            )}
                        </div>

                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <label style={lblStyle}>Description</label>
                            <textarea style={{ ...inputStyle, minHeight: '50px', fontSize: 13 }} value={form.description} onChange={e => set('description', e.target.value)} placeholder="Revenue target description..." />
                        </div>

                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button type="button" onClick={() => navigate(-1)} className="glass-button" style={{ padding: '10px 20px', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}>
                                Cancel
                            </button>
                            <button type="submit" disabled={createMutation.isPending} style={{
                                padding: '10px 24px', borderRadius: '8px', border: 'none',
                                background: 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)', color: '#fff',
                                fontSize: '13px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
                                opacity: createMutation.isPending ? 0.7 : 1,
                                boxShadow: '0 4px 12px rgba(15, 18, 64, 0.3)',
                            }}>
                                <Save size={14} /> {createMutation.isPending ? 'Saving...' : 'Create Revenue Target'}
                            </button>
                        </div>
                    </form>
                </div>
            </main>
        </div>
    );
}
