/**
 * NCoA Functional Segment (COFOG) Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/functional/new      (create)
 * Route: /accounting/ncoa/functional/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, X, GitBranch } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import { useNCoASegments } from '../../hooks/useGovForms';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

const COFOG_DIVISIONS = [
    ['701', '701 - General Public Services'], ['702', '702 - Defence'],
    ['703', '703 - Public Order & Safety'], ['704', '704 - Economic Affairs'],
    ['705', '705 - Environmental Protection'], ['706', '706 - Housing & Community'],
    ['707', '707 - Health'], ['708', '708 - Recreation, Culture & Religion'],
    ['709', '709 - Education'], ['710', '710 - Social Protection'],
];

export default function NCoAFunctionalForm() {
    const { id } = useParams<{ id: string }>();
    const isEdit = !!id;
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: segments } = useNCoASegments();

    const [formError, setFormError] = useState('');
    const [form, setForm] = useState({
        code: '', name: '', division_code: '701', group_code: '0', class_code: '0',
        parent: '', is_active: true, description: '',
    });

    // Fetch existing record when editing
    const { data: existing } = useQuery({
        queryKey: ['ncoa-functional-detail', id],
        queryFn: async () => {
            const res = await apiClient.get(`/accounting/ncoa/functional/${id}/`);
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
                division_code: existing.division_code || '701',
                group_code: existing.group_code || '0',
                class_code: existing.class_code || '0',
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
                ? apiClient.put(`/accounting/ncoa/functional/${id}/`, payload)
                : apiClient.post('/accounting/ncoa/functional/', payload);
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

    const funcList = segments?.functional || [];

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
                        title={isEdit ? 'Edit Functional Segment (COFOG)' : 'Add Functional Segment (COFOG)'}
                        subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'UN Classification of Functions of Government'}
                        icon={<GitBranch size={22} />}
                        actions={
                            <>
                                <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                    <X size={18} /> Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={saveMutation.isPending}>
                                    <Save size={18} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update Function' : 'Create Function'}
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
                        <h3 style={{ marginBottom: '1.5rem' }}>Function Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Code<span className="required-mark"> *</span></label>
                                <input className="input" value={form.code} onChange={set('code')} placeholder="e.g. 70100" maxLength={5} required />
                            </div>
                            <div>
                                <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                <input className="input" value={form.name} onChange={set('name')} placeholder="e.g. General Public Services" required />
                            </div>
                            <div>
                                <label style={labelStyle}>COFOG Division</label>
                                <select className="input" value={form.division_code} onChange={set('division_code')}>
                                    {COFOG_DIVISIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Parent</label>
                                <select className="input" value={form.parent} onChange={set('parent')}>
                                    <option value="">(Top level)</option>
                                    {funcList.map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Group Code</label>
                                <input className="input" value={form.group_code} onChange={set('group_code')} maxLength={1} placeholder="0" />
                            </div>
                            <div>
                                <label style={labelStyle}>Class Code</label>
                                <input className="input" value={form.class_code} onChange={set('class_code')} maxLength={1} placeholder="0" />
                                <p style={helpStyle}>COFOG group and class digits combine with the division to form the full functional code.</p>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', paddingTop: '1.75rem' }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                                    <input type="checkbox" checked={form.is_active} onChange={set('is_active')} />
                                    <span>Active</span>
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
