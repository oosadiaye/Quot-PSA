import { useState } from 'react';
import { useCandidates, useJobPosts, useCreateCandidate, useUpdateCandidate } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Edit, User, Mail, Phone, FileText } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const CandidateList = () => {
    const { showAlert } = useDialog();
    const { data: candidatesData, isLoading } = useCandidates();
    const { data: jobPostsData } = useJobPosts();
    const createCandidate = useCreateCandidate();
    const updateCandidate = useUpdateCandidate();
    
    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState({ first_name: '', last_name: '', email: '', phone: '', job_post: '', status: 'Applied', resume: '' });

    const candidates = candidatesData?.results || candidatesData || [];
    const jobPosts = jobPostsData?.results || jobPostsData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = { 'Applied': '#2471a3', 'Screening': '#f59e0b', 'Interview': '#8b5cf6', 'Rejected': '#ef4444', 'Hired': '#10b981' };
        return colors[status] || '#6b7280';
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            if (editingId) {
                await updateCandidate.mutateAsync({ id: editingId, data: formData });
            } else {
                await createCandidate.mutateAsync(formData);
            }
            setShowForm(false);
            setEditingId(null);
            setFormData({ first_name: '', last_name: '', email: '', phone: '', job_post: '', status: 'Applied', resume: '' });
        } catch (err) {
            showAlert('Error saving candidate');
        }
    };

    const handleEdit = (candidate: any) => {
        setFormData({ first_name: candidate.first_name, last_name: candidate.last_name, email: candidate.email, phone: candidate.phone || '', job_post: candidate.job_post_id || candidate.job_post || '', status: candidate.status, resume: candidate.resume || '' });
        setEditingId(candidate.id);
        setShowForm(true);
    };

    const getJobTitle = (id: number) => {
        const job = jobPosts.find((j: any) => j.id === id);
        return job ? job.title : `Job #${id}`;
    };

    if (isLoading) return <LoadingScreen message="Loading candidates..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Candidates"
                    subtitle="Track job applicants and candidates"
                    icon={<User size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditingId(null); setFormData({ first_name: '', last_name: '', email: '', phone: '', job_post: '', status: 'Applied', resume: '' }); }}>
                            <Plus size={18} /> Add Candidate
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>{editingId ? 'Edit Candidate' : 'New Candidate'}</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>First Name<span className="required-mark"> *</span></label><input type="text" className="input" value={formData.first_name} onChange={e => setFormData({ ...formData, first_name: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Last Name<span className="required-mark"> *</span></label><input type="text" className="input" value={formData.last_name} onChange={e => setFormData({ ...formData, last_name: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Email<span className="required-mark"> *</span></label><input type="email" className="input" value={formData.email} onChange={e => setFormData({ ...formData, email: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Phone</label><input type="tel" className="input" value={formData.phone} onChange={e => setFormData({ ...formData, phone: e.target.value })} /></div>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Job Post</label><select className="input" value={formData.job_post} onChange={e => setFormData({ ...formData, job_post: e.target.value })}><option value="">Select Job</option>{jobPosts.map((j: any) => <option key={j.id} value={j.id}>{j.title}</option>)}</select></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Status</label><select className="input" value={formData.status} onChange={e => setFormData({ ...formData, status: e.target.value })}><option value="Applied">Applied</option><option value="Screening">Screening</option><option value="Interview">Interview</option><option value="Rejected">Rejected</option><option value="Hired">Hired</option></select></div>
                            </div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">{editingId ? 'Update' : 'Add Candidate'}</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gap: '1rem' }}>
                    {candidates.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}><User size={48} style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }} /><p>No candidates found</p></div>
                    ) : (
                        candidates.map((candidate: any) => (
                            <div key={candidate.id} className="card" style={{ padding: '1.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                                    <div style={{ display: 'flex', gap: '1rem' }}>
                                        <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'var(--color-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><User size={24} /></div>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{candidate.first_name} {candidate.last_name}</div>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '0.25rem' }}>
                                                <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Mail size={14} />{candidate.email}</span>
                                                {candidate.phone && <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Phone size={14} />{candidate.phone}</span>}
                                            </div>
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                        <span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(candidate.status)}15`, color: getStatusColor(candidate.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>{candidate.status}</span>
                                        <button className="btn btn-outline" onClick={() => handleEdit(candidate)}><Edit size={16} /></button>
                                    </div>
                                </div>
                                {(candidate.job_post || candidate.job_post_id) && (
                                    <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><FileText size={14} />Applied for: {getJobTitle(candidate.job_post_id || candidate.job_post)}</div>
                                )}
                            </div>
                        ))
                    )}
                </div>
            </main>
        </div>
    );
};

export default CandidateList;
