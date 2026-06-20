/**
 * NCoA Administrative Segment (MDA) Create/Edit Form — Quot PSE
 * Route: /accounting/ncoa/administrative/new      (create)
 * Route: /accounting/ncoa/administrative/:id/edit  (edit)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, X, Building2 } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import { useNCoASegments } from '../../hooks/useGovForms';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

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

    const labelStyle: React.CSSProperties = { display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' };
    const helpStyle: React.CSSProperties = { fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' };

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
                <form onSubmit={handleSubmit}>
                    <PageHeader
                        title={isEdit ? 'Edit Administrative Segment (MDA)' : 'Add Administrative Segment (MDA)'}
                        subtitle={isEdit ? `Editing: ${form.name || '...'}` : 'Create a new Ministry, Department, or Agency entry'}
                        icon={<Building2 size={22} />}
                        actions={
                            <>
                                <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                    <X size={18} /> Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={saveMutation.isPending}>
                                    <Save size={18} /> {saveMutation.isPending ? 'Saving...' : isEdit ? 'Update MDA' : 'Create MDA'}
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
                        <h3 style={{ marginBottom: '1.5rem' }}>MDA Details</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Code<span className="required-mark"> *</span></label>
                                <input className="input" value={form.code} onChange={set('code')} placeholder="e.g. 010100000000" maxLength={12} required />
                                <p style={helpStyle}>12-digit NCoA</p>
                            </div>
                            <div>
                                <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                <input className="input" value={form.name} onChange={set('name')} placeholder="e.g. Ministry of Finance" required />
                            </div>
                            <div>
                                <label style={labelStyle}>Short Name</label>
                                <input className="input" value={form.short_name} onChange={set('short_name')} placeholder="e.g. MoF" maxLength={50} />
                            </div>
                            <div>
                                <label style={labelStyle}>Level</label>
                                <select className="input" value={form.level} onChange={set('level')}>
                                    {LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                                <p style={helpStyle}>Where in hierarchy</p>
                            </div>
                            <div>
                                <label style={labelStyle}>Sector</label>
                                <select className="input" value={form.sector_code} onChange={set('sector_code')}>
                                    {SECTORS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                                <p style={helpStyle}>Groups MDAs by function</p>
                            </div>
                            <div>
                                <label style={labelStyle}>MDA Type</label>
                                <select className="input" value={form.mda_type} onChange={set('mda_type')}>
                                    {MDA_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                                <p style={helpStyle}>What kind of body</p>
                            </div>
                            <div>
                                <label style={labelStyle}>Parent</label>
                                <select className="input" value={form.parent} onChange={set('parent')}>
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
