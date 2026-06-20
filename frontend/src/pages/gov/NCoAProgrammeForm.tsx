/**
 * NCoA Programme Segment Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/programme/new      (create)
 * Route: /accounting/ncoa/programme/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, X, Layers } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import { useNCoASegments } from '../../hooks/useGovForms';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

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
                        title={isEdit ? 'Edit Programme Segment' : 'Add Programme Segment'}
                        subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'Policy, programme, and capital project classification'}
                        icon={<Layers size={22} />}
                        actions={
                            <>
                                <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                    <X size={18} /> Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={saveMutation.isPending}>
                                    <Save size={18} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update Programme' : 'Create Programme'}
                                </button>
                            </>
                        }
                    />

                    {formError && (
                        <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1rem' }}>
                            {formError}
                        </div>
                    )}

                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Programme Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Code<span className="required-mark"> *</span></label>
                                <input className="input" value={form.code} onChange={set('code')} placeholder="e.g. 01010000000000" maxLength={14} required />
                            </div>
                            <div>
                                <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                <input className="input" value={form.name} onChange={set('name')} placeholder="e.g. Fiscal Policy Programme" required />
                            </div>
                            <div>
                                <label style={labelStyle}>Policy Code</label>
                                <input className="input" value={form.policy_code} onChange={set('policy_code')} placeholder="e.g. 01" maxLength={2} />
                            </div>
                            <div>
                                <label style={labelStyle}>Programme Code</label>
                                <input className="input" value={form.programme_code} onChange={set('programme_code')} placeholder="e.g. 01" maxLength={2} />
                            </div>
                            <div>
                                <label style={labelStyle}>Project Code</label>
                                <input className="input" value={form.project_code} onChange={set('project_code')} placeholder="e.g. 010001 (capital projects)" maxLength={6} />
                                <p style={helpStyle}>Used for capital projects.</p>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                                <div>
                                    <label style={labelStyle}>Objective Code</label>
                                    <input className="input" value={form.objective_code} onChange={set('objective_code')} maxLength={2} />
                                </div>
                                <div>
                                    <label style={labelStyle}>Activity Code</label>
                                    <input className="input" value={form.activity_code} onChange={set('activity_code')} maxLength={2} />
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Parent</label>
                                <select className="input" value={form.parent} onChange={set('parent')}>
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
                        <div style={{ marginTop: '1.5rem' }}>
                            <label style={labelStyle}>Description</label>
                            <textarea className="input" value={form.description} onChange={set('description')} rows={3} style={{ width: '100%' }} />
                        </div>
                    </div>
                </form>
            </main>
        </div>
    );
}
