import { useState, useCallback } from 'react';
import { Plus, Search, ClipboardCheck } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useQualityChecklists, useCreateQualityChecklist } from '../hooks/useQuality';
import QualityLayout from '../QualityLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useFocusTrap } from '../../../hooks/useFocusTrap';

export default function Checklists() {
    const [searchTerm, setSearchTerm] = useState('');
    const [typeFilter, setTypeFilter] = useState('');
    const [showModal, setShowModal] = useState(false);
    const closeModal = useCallback(() => setShowModal(false), []);
    const modalRef = useFocusTrap(showModal, closeModal);

    const { data: checklists, isLoading } = useQualityChecklists({ checklist_type: typeFilter });
    const createChecklist = useCreateQualityChecklist();

    const checklistsList = checklists?.results || checklists || [];

    const filteredChecklists = Array.isArray(checklistsList) ? checklistsList.filter((c: any) =>
        c.name?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const [formData, setFormData] = useState({ name: '', description: '', checklist_type: '' });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createChecklist.mutate(formData, { onSuccess: () => { setShowModal(false); setFormData({ name: '', description: '', checklist_type: '' }); } });
    };

    if (isLoading) return <LoadingScreen message="Loading checklists..." />;

    return (
        <QualityLayout>
            <div style={{ padding: '1.5rem' }}>
                <PageHeader
                    title="Quality Checklists"
                    subtitle="Manage quality inspection checklists"
                    icon={<ClipboardCheck size={22} color="white" />}
                    backButton={false}
                    actions={
                        <button onClick={() => setShowModal(true)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.625rem 1.25rem', background: 'var(--color-primary)', color: 'white', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' }}>
                            <Plus size={18} /> New Checklist
                        </button>
                    }
                />

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input type="text" placeholder="Search checklists..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} style={{ width: '100%', padding: '0.625rem 0.75rem 0.625rem 2.5rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} />
                    </div>
                    <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={{ padding: '0.625rem 1rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)', minWidth: '150px' }}>
                        <option value="">All Types</option>
                        <option value="Incoming">Incoming</option>
                        <option value="In-Process">In-Process</option>
                        <option value="Final">Final</option>
                    </select>
                </div>

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Name</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Type</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredChecklists.length === 0 ? (
                                <tr><td colSpan={3} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}><ClipboardCheck size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} /><p>No checklists found</p></td></tr>
                            ) : (
                                filteredChecklists.map((checklist: any) => (
                                    <tr key={checklist.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{checklist.name}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{checklist.checklist_type || '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <span style={{ display: 'inline-block', padding: '0.25rem 0.75rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 600, background: checklist.is_active ? 'rgba(34, 197, 94, 0.1)' : 'rgba(156, 163, 175, 0.1)', color: checklist.is_active ? '#22c55e' : '#9ca3af' }}>
                                                {checklist.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {showModal && (
                    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={closeModal} role="presentation">
                        <div ref={modalRef} role="dialog" aria-modal="true" aria-label="Create Checklist" style={{ background: 'var(--color-surface)', borderRadius: '12px', padding: '1.5rem', maxWidth: '400px', width: '100%' }} onClick={e => e.stopPropagation()}>
                            <h3 style={{ margin: '0 0 1rem 0' }}>Create Checklist</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Name<span className="required-mark"> *</span></label>
                                    <input type="text" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} />
                                </div>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Type</label>
                                    <input type="text" value={formData.checklist_type} onChange={e => setFormData({ ...formData, checklist_type: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} />
                                </div>
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Description</label>
                                    <textarea rows={2} value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)', resize: 'vertical' }} />
                                </div>
                                <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                                    <button type="button" onClick={() => setShowModal(false)} style={{ padding: '0.625rem 1.25rem', background: 'transparent', border: '1px solid var(--color-border)', borderRadius: '8px', color: 'var(--color-text)', cursor: 'pointer' }}>Cancel</button>
                                    <button type="submit" style={{ padding: '0.625rem 1.25rem', background: 'var(--color-primary)', border: 'none', borderRadius: '8px', color: 'white', fontWeight: 600, cursor: 'pointer' }}>Create</button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </div>
        </QualityLayout>
    );
}
