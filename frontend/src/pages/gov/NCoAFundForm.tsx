/**
 * NCoA Fund Segment Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/fund/new      (create)
 * Route: /accounting/ncoa/fund/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, X, Wallet } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import { useNCoASegments } from '../../hooks/useGovForms';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

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

    const labelStyle: React.CSSProperties = { display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' };
    const helpStyle: React.CSSProperties = { fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <form onSubmit={handleSubmit}>
                    <PageHeader
                        title={isEdit ? 'Edit Fund Segment' : 'Add Fund Segment'}
                        subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'Source of government funding'}
                        icon={<Wallet size={22} />}
                        actions={
                            <>
                                <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                    <X size={18} /> Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={saveMutation.isPending}>
                                    <Save size={18} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update Fund' : 'Create Fund'}
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
                        <h3 style={{ marginBottom: '1.5rem' }}>Fund Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Code<span className="required-mark"> *</span></label>
                                <input className="input" value={form.code} onChange={set('code')} placeholder="e.g. 01000" maxLength={5} required />
                            </div>
                            <div>
                                <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                <input className="input" value={form.name} onChange={set('name')} placeholder="e.g. FAAC Statutory Allocation" required />
                            </div>
                            <div>
                                <label style={labelStyle}>Parent</label>
                                <select className="input" value={form.parent} onChange={set('parent')}>
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
                        <div style={{ marginTop: '1.5rem' }}>
                            <label style={labelStyle}>Description</label>
                            <textarea className="input" value={form.description} onChange={set('description')} style={{ width: '100%', minHeight: 80 }} />
                            <p style={helpStyle}>Optional notes describing this fund segment.</p>
                        </div>
                    </div>
                </form>
            </main>
        </div>
    );
}
