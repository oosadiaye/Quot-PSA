/**
 * NCoA Fund Segment Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/fund/new      (create)
 * Route: /accounting/ncoa/fund/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, AlertCircle, Wallet } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import { useNCoASegments } from '../../hooks/useGovForms';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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

// NCoA fund-hierarchy fields (main_fund_code, sub_fund_code, fund_source_code,
// donor_name) are no longer surfaced in this form. The values still round-trip
// through form state so edits don't wipe existing records, but users only see
// / edit the essential identity fields (code, name, parent, restricted, active,
// description). Backend serializer accepts legacy single-digit codes ('1' → '01')
// and defaults main_fund_code to '01' when omitted.

export default function NCoAFundForm() {
    const { id } = useParams<{ id: string }>();
    const isEdit = !!id;
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: segments } = useNCoASegments();

    const [formError, setFormError] = useState('');
    const [form, setForm] = useState({
        code: '', name: '', main_fund_code: '01', sub_fund_code: '0',
        fund_source_code: '00', donor_name: '',
        parent: '', is_active: true, is_restricted: false, description: '',
    });

    // Fetch existing record when editing
    const { data: existing } = useQuery({
        queryKey: ['ncoa-fund-detail', id],
        queryFn: async () => {
            const res = await apiClient.get(`/accounting/ncoa/fund/${id}/`);
            return res.data;
        },
        enabled: isEdit,
    });

    // Prefill form when existing data loads
    useEffect(() => {
        if (existing) {
            setForm({
                code: existing.code || '',
                name: existing.name || '',
                main_fund_code: existing.main_fund_code || '01',
                sub_fund_code: existing.sub_fund_code || '0',
                fund_source_code: existing.fund_source_code || '00',
                donor_name: existing.donor_name || '',
                parent: existing.parent ? String(existing.parent) : '',
                is_active: existing.is_active ?? true,
                is_restricted: existing.is_restricted ?? false,
                description: existing.description || '',
            });
        }
    }, [existing]);

    const saveMutation = useMutation({
        mutationFn: (data: typeof form) => {
            const payload = { ...data, parent: data.parent || null };
            return isEdit
                ? apiClient.put(`/accounting/ncoa/fund/${id}/`, payload)
                : apiClient.post('/accounting/ncoa/fund/', payload);
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            qc.invalidateQueries({ queryKey: ['ncoa-segments-all'] });
            navigate(-1);
        },
        onError: (err: any) => setFormError(err?.response?.data?.detail || JSON.stringify(err?.response?.data) || 'Failed to save'),
    });

    const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
        setForm(prev => ({ ...prev, [field]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }));

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!form.code || !form.name) { setFormError('Code and name are required'); return; }
        setFormError('');
        saveMutation.mutate(form);
    };

    const fundList = segments?.fund || [];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader title={isEdit ? 'Edit Fund Segment' : 'Add Fund Segment'} subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'Source of government funding'} icon={<Wallet size={22} />} />

                {formError && (
                    <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '12px 16px', marginBottom: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
                        <AlertCircle size={16} color="#dc2626" /> <span style={{ color: '#dc2626', fontSize: 13 }}>{formError}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Fund Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                            <div><label style={lblStyle}>Code *</label><input style={inputStyle} value={form.code} onChange={set('code')} placeholder="e.g. 01000" maxLength={5} required /></div>
                            <div><label style={lblStyle}>Name *</label><input style={inputStyle} value={form.name} onChange={set('name')} placeholder="e.g. FAAC Statutory Allocation" required /></div>
                            <div><label style={lblStyle}>Parent</label>
                                <select style={selectStyle} value={form.parent} onChange={set('parent')}>
                                    <option value="">(Top level)</option>
                                    {fundList.map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                                </select>
                            </div>
                            <div style={{ display: 'flex', gap: 24, alignItems: 'center', paddingTop: 24 }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                                    <input type="checkbox" checked={form.is_restricted} onChange={set('is_restricted')} /> Restricted Fund
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                                    <input type="checkbox" checked={form.is_active} onChange={set('is_active')} /> Active
                                </label>
                            </div>
                        </div>
                        <div style={{ marginTop: 16 }}><label style={lblStyle}>Description</label>
                            <textarea style={{ ...inputStyle, minHeight: 80 }} value={form.description} onChange={set('description')} />
                        </div>
                    </div>
                    <button type="submit" disabled={saveMutation.isPending} style={{
                        display: 'flex', alignItems: 'center', gap: 8, padding: '12px 28px',
                        background: 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, fontSize: 14, cursor: 'pointer',
                        boxShadow: '0 4px 12px rgba(15, 18, 64, 0.3)',
                    }}>
                        <Save size={16} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update Fund' : 'Create Fund'}
                    </button>
                </form>
            </main>
        </div>
    );
}
