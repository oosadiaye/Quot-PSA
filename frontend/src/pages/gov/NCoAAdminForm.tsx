/**
 * NCoA Administrative Segment (MDA) Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/administrative/new      (create)
 * Route: /accounting/ncoa/administrative/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, AlertCircle, Building2 } from 'lucide-react';
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

const LEVELS = [
    ['SECTOR', 'Sector (grouping header — not an MDA itself)'],
    ['ORGANIZATION', 'Organization (Ministry / Department / Agency)'],
    ['SUB_ORG', 'Sub-Organization (unit inside an MDA)'],
    ['SUB_SUB_ORG', 'Sub-Sub-Organization'],
    ['UNIT', 'Unit (smallest level)'],
];
const SECTORS = [
    ['01', '01 - Administrative Sector (Governor, Finance, AG, etc.)'],
    ['02', '02 - Economic Sector (Agriculture, Works, Commerce, etc.)'],
    ['03', '03 - Law & Justice Sector (Justice, Judiciary)'],
    ['04', '04 - Regional Sector (Information, Communications)'],
    ['05', '05 - Social Sector (Education, Health, Youth, etc.)'],
];
const MDA_TYPES = [
    ['', '(None — for Sector headers)'],
    ['MINISTRY', 'Ministry — headed by Commissioner/Minister'],
    ['DEPARTMENT', 'Department — headed by Director'],
    ['AGENCY', 'Agency — semi-autonomous body (e.g. SIEC, BPP)'],
    ['UNIT', 'Unit — small unit within a department'],
];

const EMPTY_FORM = {
    code: '', name: '', short_name: '', level: 'ORGANIZATION',
    sector_code: '01', mda_type: 'MINISTRY', parent: '',
    is_active: true, is_mda: true, description: '',
};

export default function NCoAAdminForm() {
    const { id } = useParams<{ id: string }>();
    const isEdit = !!id;
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: segments } = useNCoASegments();

    const [formError, setFormError] = useState('');
    const [form, setForm] = useState(EMPTY_FORM);

    // Fetch existing record when editing
    const { data: existing } = useQuery({
        queryKey: ['ncoa-admin-detail', id],
        queryFn: async () => {
            const res = await apiClient.get(`/accounting/ncoa/administrative/${id}/`);
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
                short_name: existing.short_name || '',
                level: existing.level || 'ORGANIZATION',
                sector_code: existing.sector_code || '01',
                mda_type: existing.mda_type || '',
                parent: existing.parent ? String(existing.parent) : '',
                is_active: existing.is_active ?? true,
                is_mda: existing.is_mda ?? true,
                description: existing.description || '',
            });
        }
    }, [existing]);

    const saveMutation = useMutation({
        mutationFn: (data: typeof form) => {
            const payload = { ...data, parent: data.parent || null };
            return isEdit
                ? apiClient.put(`/accounting/ncoa/administrative/${id}/`, payload)
                : apiClient.post('/accounting/ncoa/administrative/', payload);
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            qc.invalidateQueries({ queryKey: ['ncoa-segments-all'] });
            navigate(-1);
        },
        onError: (err: any) => setFormError(
            err?.response?.data?.detail || JSON.stringify(err?.response?.data) || 'Failed to save'
        ),
    });

    const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
        setForm(prev => ({ ...prev, [field]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }));

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!form.code || !form.name) { setFormError('Code and name are required'); return; }
        setFormError('');
        saveMutation.mutate(form);
    };

    const adminList = segments?.administrative || [];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader title={isEdit ? 'Edit Administrative Segment (MDA)' : 'Add Administrative Segment (MDA)'} subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'Create a new Ministry, Department, or Agency entry'} icon={<Building2 size={22} />} />

                {formError && (
                    <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '12px 16px', marginBottom: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
                        <AlertCircle size={16} color="#dc2626" /> <span style={{ color: '#dc2626', fontSize: 13 }}>{formError}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>MDA Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                            <div><label style={lblStyle}>Code * <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}>(12-digit NCoA)</span></label><input style={inputStyle} value={form.code} onChange={set('code')} placeholder="e.g. 010100000000" maxLength={12} required /></div>
                            <div><label style={lblStyle}>Name *</label><input style={inputStyle} value={form.name} onChange={set('name')} placeholder="e.g. Ministry of Finance" required /></div>
                            <div><label style={lblStyle}>Short Name</label><input style={inputStyle} value={form.short_name} onChange={set('short_name')} placeholder="e.g. MoF" maxLength={50} /></div>
                            <div><label style={lblStyle}>Level <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}>(where in hierarchy)</span></label>
                                <select style={selectStyle} value={form.level} onChange={set('level')}>
                                    {LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </div>
                            <div><label style={lblStyle}>Sector <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}>(groups MDAs by function)</span></label>
                                <select style={selectStyle} value={form.sector_code} onChange={set('sector_code')}>
                                    {SECTORS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </div>
                            <div><label style={lblStyle}>MDA Type <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}>(what kind of body)</span></label>
                                <select style={selectStyle} value={form.mda_type} onChange={set('mda_type')}>
                                    {MDA_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </div>
                            <div><label style={lblStyle}>Parent</label>
                                <select style={selectStyle} value={form.parent} onChange={set('parent')}>
                                    <option value="">(Top level)</option>
                                    {adminList.map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                                </select>
                            </div>
                            <div style={{ display: 'flex', gap: 24, alignItems: 'center', paddingTop: 24 }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                                    <input type="checkbox" checked={form.is_mda} onChange={set('is_mda')} /> Is MDA
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
                        background: 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)', color: '#fff', border: 'none', borderRadius: 8,
                        fontWeight: 600, fontSize: 14, cursor: 'pointer',
                        boxShadow: '0 4px 12px rgba(15, 18, 64, 0.3)',
                    }}>
                        <Save size={16} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update MDA' : 'Create MDA'}
                    </button>
                </form>
            </main>
        </div>
    );
}
