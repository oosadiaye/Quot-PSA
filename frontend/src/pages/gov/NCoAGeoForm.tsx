/**
 * NCoA Geographic Segment Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/geographic/new      (create)
 * Route: /accounting/ncoa/geographic/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, AlertCircle, MapPin } from 'lucide-react';
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

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader title={isEdit ? 'Edit Geographic Segment' : 'Add Geographic Segment'} subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'Location of government transactions — zones, states, LGAs, wards'} icon={<MapPin size={22} />} />

                {formError && (
                    <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '12px 16px', marginBottom: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
                        <AlertCircle size={16} color="#dc2626" /> <span style={{ color: '#dc2626', fontSize: 13 }}>{formError}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Geographic Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                            <div><label style={lblStyle}>Code *</label><input style={inputStyle} value={form.code} onChange={set('code')} placeholder="e.g. 51000100" maxLength={8} required /></div>
                            <div><label style={lblStyle}>Name *</label><input style={inputStyle} value={form.name} onChange={set('name')} placeholder="e.g. Aniocha North" required /></div>
                            <div><label style={lblStyle}>Parent</label>
                                <select style={selectStyle} value={form.parent} onChange={set('parent')}>
                                    <option value="">(Top level)</option>
                                    {geoList.map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                                </select>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', paddingTop: 24 }}>
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
                        <Save size={16} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update Location' : 'Create Location'}
                    </button>
                </form>
            </main>
        </div>
    );
}
