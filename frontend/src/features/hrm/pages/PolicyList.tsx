import { useState } from 'react';
import { usePolicies, useCreatePolicy } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, FileText, Shield } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const PolicyList = () => {
    const { showAlert } = useDialog();
    const { data: policiesData, isLoading } = usePolicies();
    const createPolicy = useCreatePolicy();
    
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({ title: '', content: '', category: 'General', is_active: true });

    const policies = policiesData?.results || policiesData || [];

    const getCategoryColor = (category: string) => {
        const colors: Record<string, string> = { 'General': '#2471a3', 'Leave': '#10b981', 'Attendance': '#f59e0b', 'Safety': '#ef4444', 'HR': '#8b5cf6' };
        return colors[category] || '#6b7280';
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createPolicy.mutateAsync(formData);
            setShowForm(false);
            setFormData({ title: '', content: '', category: 'General', is_active: true });
        } catch (err) {
            showAlert('Error creating policy');
        }
    };

    if (isLoading) return <LoadingScreen message="Loading policies..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Policies"
                    subtitle="Manage company policies and documents"
                    icon={<FileText size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Policy
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>New Policy</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Title<span className="required-mark"> *</span></label><input type="text" className="input" value={formData.title} onChange={e => setFormData({ ...formData, title: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Category</label><select className="input" value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })}><option value="General">General</option><option value="Leave">Leave</option><option value="Attendance">Attendance</option><option value="Safety">Safety</option><option value="HR">HR</option></select></div>
                                <div style={{ display: 'flex', alignItems: 'center', marginTop: '1.5rem' }}><label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={formData.is_active} onChange={e => setFormData({ ...formData, is_active: e.target.checked })} /> Active</label></div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Content</label><textarea className="input" value={formData.content} onChange={e => setFormData({ ...formData, content: e.target.value })} rows={4} style={{ width: '100%' }} /></div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">Create Policy</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gap: '1rem' }}>
                    {policies.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}><FileText size={48} style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }} /><p>No policies found</p></div>
                    ) : (
                        policies.map((policy: any) => (
                            <div key={policy.id} className="card" style={{ padding: '1.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                        <div style={{ width: '48px', height: '48px', borderRadius: '10px', background: 'rgba(36, 113, 163, 0.1)', color: '#2471a3', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><FileText size={24} /></div>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{policy.title}</div>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{policy.category}</div>
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                        <span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getCategoryColor(policy.category)}15`, color: getCategoryColor(policy.category), fontSize: 'var(--text-xs)', fontWeight: 600 }}>{policy.category}</span>
                                        <span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: policy.is_active ? 'rgba(16, 185, 129, 0.1)' : 'rgba(107, 114, 128, 0.1)', color: policy.is_active ? '#10b981' : '#6b7280', fontSize: 'var(--text-xs)', fontWeight: 600 }}>{policy.is_active ? 'Active' : 'Inactive'}</span>
                                    </div>
                                </div>
                                {policy.content && <p style={{ margin: '1rem 0 0', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{policy.content.substring(0, 150)}...</p>}
                            </div>
                        ))
                    )}
                </div>
            </main>
        </div>
    );
};

export default PolicyList;
