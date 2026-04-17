/**
 * TSA Account Create Form — Quot PSE
 * Route: /accounting/tsa-accounts/new
 *
 * Creates a Treasury Single Account entry with:
 * - Account details (number, name, bank, type)
 * - Linking (MDA segment, fund segment, parent account)
 * - Settings (active status, description)
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, Landmark } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import {
    useCreateTSAAccount, useNCoASegments, useTSAAccounts,
} from '../../hooks/useGovForms';

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

const ACCOUNT_TYPES = [
    ['MAIN_TSA', 'Main TSA'],
    ['CONSOLIDATED', 'Consolidated Revenue Fund'],
    ['SUB_ACCOUNT', 'Sub-Account'],
    ['ZERO_BALANCE', 'Zero-Balance Account'],
    ['HOLDING', 'Holding Account'],
    ['REVENUE', 'Revenue Collection Account'],
];

export default function TSAAccountForm() {
    const navigate = useNavigate();
    const createTSA = useCreateTSAAccount();
    const { data: segments, isLoading: segsLoading } = useNCoASegments();
    const { data: tsaAccounts } = useTSAAccounts();

    const [formError, setFormError] = useState('');
    const [form, setForm] = useState({
        account_number: '', account_name: '', bank: '', sort_code: '',
        account_type: 'SUB_ACCOUNT',
        mda: '', fund_segment: '', parent_account: '',
        is_active: true, description: '',
    });

    const set = (field: string, value: string) => setForm(prev => ({ ...prev, [field]: value }));

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        const payload: Record<string, unknown> = {
            account_number: form.account_number,
            account_name: form.account_name,
            bank: form.bank,
            sort_code: form.sort_code,
            account_type: form.account_type,
            mda: form.mda ? parseInt(form.mda) : null,
            fund_segment: form.fund_segment ? parseInt(form.fund_segment) : null,
            parent_account: form.parent_account ? parseInt(form.parent_account) : null,
            is_active: form.is_active,
            description: form.description,
        };

        try {
            await createTSA.mutateAsync(payload);
            navigate('/accounting/tsa-accounts');
        } catch (err: any) {
            const d = err.response?.data;
            if (d?.detail) setFormError(d.detail);
            else if (d && typeof d === 'object') {
                const msgs = Object.entries(d).map(([k, v]) =>
                    `${k}: ${Array.isArray(v) ? v.join(', ') : v}`
                );
                setFormError(msgs.join(' | '));
            } else {
                setFormError(err.message || 'Failed to create TSA Account');
            }
        }
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <div style={{ maxWidth: '900px' }}>
                    <PageHeader title="New TSA Account" subtitle="Create a Treasury Single Account entry" icon={<Landmark size={22} />} />

                    {formError && (
                        <div style={{
                            padding: '12px 16px', borderRadius: '8px', marginBottom: '16px',
                            background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626',
                            display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px',
                        }}>
                            <AlertCircle size={16} /> {formError}
                        </div>
                    )}

                    <form onSubmit={handleSubmit}>
                        {/* Account Details */}
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Account Details</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                <div>
                                    <label style={lblStyle}>Account Number *</label>
                                    <input style={inputStyle} required value={form.account_number} onChange={e => set('account_number', e.target.value)} placeholder="10-digit NUBAN" />
                                </div>
                                <div>
                                    <label style={lblStyle}>Account Name *</label>
                                    <input style={inputStyle} required value={form.account_name} onChange={e => set('account_name', e.target.value)} placeholder="TSA account name" />
                                </div>
                                <div>
                                    <label style={lblStyle}>Bank *</label>
                                    <input style={inputStyle} required value={form.bank} onChange={e => set('bank', e.target.value)} placeholder="Bank name (e.g. CBN)" />
                                </div>
                                <div>
                                    <label style={lblStyle}>Sort Code</label>
                                    <input style={inputStyle} value={form.sort_code} onChange={e => set('sort_code', e.target.value)} placeholder="Bank sort code" />
                                </div>
                                <div>
                                    <label style={lblStyle}>Account Type *</label>
                                    <select style={selectStyle} required value={form.account_type} onChange={e => set('account_type', e.target.value)}>
                                        {ACCOUNT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                    </select>
                                </div>
                            </div>
                        </div>

                        {/* Linking */}
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Linking</h3>
                            {segsLoading ? <div style={{ color: '#94a3b8' }}>Loading segments...</div> : (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                    <div>
                                        <label style={lblStyle}>MDA (Administrative Segment)</label>
                                        <select style={selectStyle} value={form.mda} onChange={e => set('mda', e.target.value)}>
                                            <option value="">None</option>
                                            {segments?.administrative?.map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={lblStyle}>Fund Segment</label>
                                        <select style={selectStyle} value={form.fund_segment} onChange={e => set('fund_segment', e.target.value)}>
                                            <option value="">None</option>
                                            {segments?.fund?.map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={lblStyle}>Parent TSA Account</label>
                                        <select style={selectStyle} value={form.parent_account} onChange={e => set('parent_account', e.target.value)}>
                                            <option value="">None (top-level)</option>
                                            {(tsaAccounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.account_number} - {a.account_name}</option>)}
                                        </select>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Settings */}
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Settings</h3>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                                <input
                                    type="checkbox"
                                    id="is_active"
                                    checked={form.is_active}
                                    onChange={e => setForm(prev => ({ ...prev, is_active: e.target.checked }))}
                                    style={{ width: '18px', height: '18px', accentColor: 'var(--primary, #191e6a)' }}
                                />
                                <label htmlFor="is_active" style={{ fontSize: '14px', color: '#1e293b', fontWeight: 500 }}>
                                    Account is active
                                </label>
                            </div>
                            <div>
                                <label style={lblStyle}>Description</label>
                                <textarea style={{ ...inputStyle, minHeight: '60px' }} value={form.description} onChange={e => set('description', e.target.value)} placeholder="Account description..." />
                            </div>
                        </div>

                        {/* Submit */}
                        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                            <button type="button" onClick={() => navigate(-1)} className="glass-button" style={{
                                padding: '12px 24px', borderRadius: '8px', border: '1px solid var(--color-border)',
                                background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: '14px', fontWeight: 600, cursor: 'pointer',
                            }}>
                                Cancel
                            </button>
                            <button type="submit" disabled={createTSA.isPending} style={{
                                padding: '12px 24px', borderRadius: '8px', border: 'none',
                                background: 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)', color: '#fff', fontSize: '14px', fontWeight: 600,
                                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
                                opacity: createTSA.isPending ? 0.7 : 1,
                                boxShadow: '0 4px 12px rgba(15, 18, 64, 0.3)',
                            }}>
                                <Save size={16} />
                                {createTSA.isPending ? 'Creating...' : 'Create TSA Account'}
                            </button>
                        </div>
                    </form>
                </div>
            </main>
        </div>
    );
}
