/**
 * NCoA Geographic Segment Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/geographic/new      (create)
 * Route: /accounting/ncoa/geographic/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, X, AlertCircle, MapPin } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import { useNCoASegments } from '../../hooks/useGovForms';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

// NCoA hierarchy fields (zone, state, senatorial, LGA, ward) are no longer
// surfaced in this form — they round-trip transparently through the form state
// so an edit doesn't wipe existing values, but users only see / edit the
// essential identity fields (code, name, parent, active, description).

export default function NCoAGeoForm() {
    const { id } = useParams<{ id: string }>();
    const isEdit = !!id;
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: segments } = useNCoASegments();

    const [formError, setFormError] = useState('');
    const [form, setForm] = useState({
        code: '', name: '', zone_code: '1', state_code: '00',
        senatorial_code: '0', lga_code: '00', ward_code: '00',
        parent: '', is_active: true, description: '',
    });

    // Fetch existing record when editing
    const { data: existing } = useQuery({
        queryKey: ['ncoa-geo-detail', id],
        queryFn: async () => {
            const res = await apiClient.get(`/accounting/ncoa/geographic/${id}/`);
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
                zone_code: existing.zone_code || '1',
                state_code: existing.state_code || '00',
                senatorial_code: existing.senatorial_code || '0',
                lga_code: existing.lga_code || '00',
                ward_code: existing.ward_code || '00',
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
                ? apiClient.put(`/accounting/ncoa/geographic/${id}/`, payload)
                : apiClient.post('/accounting/ncoa/geographic/', payload);
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

    const geoList = segments?.geographic || [];

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
                        title={isEdit ? 'Edit Geographic Segment' : 'Add Geographic Segment'}
                        subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'Location of government transactions — zones, states, LGAs, wards'}
                        icon={<MapPin size={22} />}
                        actions={
                            <>
                                <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                    <X size={18} /> Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={saveMutation.isPending}>
                                    <Save size={18} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update Location' : 'Create Location'}
                                </button>
                            </>
                        }
                    />

                    {formError && (
                        <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1rem', display: 'flex', gap: 8, alignItems: 'center' }}>
                            <AlertCircle size={16} /> {formError}
                        </div>
                    )}

                    {/* ── Geographic Details ────────────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Geographic Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Code<span className="required-mark"> *</span></label>
                                <input className="input" value={form.code} onChange={set('code')} placeholder="e.g. 51000100" maxLength={8} required />
                            </div>
                            <div>
                                <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                <input className="input" value={form.name} onChange={set('name')} placeholder="e.g. Aniocha North" required />
                            </div>
                            <div>
                                <label style={labelStyle}>Parent</label>
                                <select className="input" value={form.parent} onChange={set('parent')}>
                                    <option value="">(Top level)</option>
                                    {geoList.map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                                </select>
                                <p style={helpStyle}>Leave empty for a top-level zone or state.</p>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', paddingTop: 24 }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                                    <input type="checkbox" checked={form.is_active} onChange={set('is_active')} /> Active
                                </label>
                            </div>
                        </div>
                        <div style={{ marginTop: '1.5rem' }}>
                            <label style={labelStyle}>Description</label>
                            <textarea className="input" value={form.description} onChange={set('description')} rows={3} placeholder="Optional notes about this location" style={{ width: '100%' }} />
                        </div>
                    </div>
                </form>
            </main>
        </div>
    );
}
