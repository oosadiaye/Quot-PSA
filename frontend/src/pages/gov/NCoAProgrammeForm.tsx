/**
 * NCoA Programme Segment Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/programme/new      (create)
 * Route: /accounting/ncoa/programme/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, AlertCircle, Layers } from 'lucide-react';
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

export default function NCoAProgrammeForm() {
    const { id } = useParams<{ id: string }>();
    const isEdit = !!id;
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: segments } = useNCoASegments();

    const [formError, setFormError] = useState('');
    const [form, setForm] = useState({
        code: '', name: '', policy_code: '', programme_code: '', project_code: '',
        objective_code: '', activity_code: '', is_capital: false,
        parent: '', is_active: true, description: '',
    });

    // Fetch existing record when editing
    const { data: existing } = useQuery({
        queryKey: ['ncoa-programme-detail', id],
        queryFn: async () => {
            const res = await apiClient.get(`/accounting/ncoa/programme/${id}/`);
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
                policy_code: existing.policy_code || '',
                programme_code: existing.programme_code || '',
                project_code: existing.project_code || '',
                objective_code: existing.objective_code || '',
                activity_code: existing.activity_code || '',
                is_capital: existing.is_capital ?? false,
                parent: existing.parent ? String(existing.parent) : '',
                is_active: existing.is_active ?? true,
                description: existing.description || '',
            });
        }
    }, [existing]);

    const saveMutation = useMutation({
        mutationFn: (data: typeof form) => {
            const payload = { ...data, parent: data.parent || null };
            return isEdit
                ? apiClient.put(`/accounting/ncoa/programme/${id}/`, payload)
                : apiClient.post('/accounting/ncoa/programme/', payload);
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

    const progList = segments?.programme || [];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader title={isEdit ? 'Edit Programme Segment' : 'Add Programme Segment'} subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'Policy, programme, and capital project classification'} icon={<Layers size={22} />} />

                {formError && (
                    <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '12px 16px', marginBottom: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
                        <AlertCircle size={16} color="#dc2626" /> <span style={{ color: '#dc2626', fontSize: 13 }}>{formError}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Programme Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                            <div><label style={lblStyle}>Code *</label><input style={inputStyle} value={form.code} onChange={set('code')} placeholder="e.g. 01010000000000" maxLength={14} required /></div>
                            <div><label style={lblStyle}>Name *</label><input style={inputStyle} value={form.name} onChange={set('name')} placeholder="e.g. Fiscal Policy Programme" required /></div>
                            <div><label style={lblStyle}>Policy Code</label><input style={inputStyle} value={form.policy_code} onChange={set('policy_code')} placeholder="e.g. 01" maxLength={2} /></div>
                            <div><label style={lblStyle}>Programme Code</label><input style={inputStyle} value={form.programme_code} onChange={set('programme_code')} placeholder="e.g. 01" maxLength={2} /></div>
                            <div><label style={lblStyle}>Project Code</label><input style={inputStyle} value={form.project_code} onChange={set('project_code')} placeholder="e.g. 010001 (capital projects)" maxLength={6} /></div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                                <div><label style={lblStyle}>Objective Code</label><input style={inputStyle} value={form.objective_code} onChange={set('objective_code')} maxLength={2} /></div>
                                <div><label style={lblStyle}>Activity Code</label><input style={inputStyle} value={form.activity_code} onChange={set('activity_code')} maxLength={2} /></div>
                            </div>
                            <div><label style={lblStyle}>Parent</label>
                                <select style={selectStyle} value={form.parent} onChange={set('parent')}>
                                    <option value="">(Top level)</option>
                                    {progList.map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                                </select>
                            </div>
                            <div style={{ display: 'flex', gap: 24, alignItems: 'center', paddingTop: 24 }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                                    <input type="checkbox" checked={form.is_capital} onChange={set('is_capital')} /> Capital Project
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
                        <Save size={16} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update Programme' : 'Create Programme'}
                    </button>
                </form>
            </main>
        </div>
    );
}
