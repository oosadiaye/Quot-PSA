import { useState } from 'react';
import { useJobPosts, useCreateJobPost } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Briefcase, Users, Clock } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const JobPostList = () => {
    const { showAlert } = useDialog();
    const { data: jobPostsData, isLoading } = useJobPosts();
    const createJobPost = useCreateJobPost();
    
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({ title: '', department: '', description: '', requirements: '', job_type: 'Full-time', status: 'Open' });

    const jobPosts = jobPostsData?.results || jobPostsData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = { 'Open': '#10b981', 'Closed': '#ef4444', 'Draft': '#6b7280' };
        return colors[status] || '#6b7280';
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createJobPost.mutateAsync(formData);
            setShowForm(false);
            setFormData({ title: '', department: '', description: '', requirements: '', job_type: 'Full-time', status: 'Open' });
        } catch (err) {
            showAlert('Error creating job post');
        }
    };

    if (isLoading) return <LoadingScreen message="Loading job posts..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Job Postings"
                    subtitle="Manage open positions and job listings"
                    icon={<Briefcase size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Job Post
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>New Job Posting</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Title<span className="required-mark"> *</span></label><input type="text" className="input" value={formData.title} onChange={e => setFormData({ ...formData, title: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Department</label><input type="text" className="input" value={formData.department} onChange={e => setFormData({ ...formData, department: e.target.value })} /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Job Type</label><select className="input" value={formData.job_type} onChange={e => setFormData({ ...formData, job_type: e.target.value })}><option value="Full-time">Full-time</option><option value="Part-time">Part-time</option><option value="Contract">Contract</option><option value="Internship">Internship</option></select></div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Description</label><textarea className="input" value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} rows={3} style={{ width: '100%' }} /></div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Requirements</label><textarea className="input" value={formData.requirements} onChange={e => setFormData({ ...formData, requirements: e.target.value })} rows={2} style={{ width: '100%' }} /></div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">Create Post</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gap: '1rem' }}>
                    {jobPosts.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}><Briefcase size={48} style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }} /><p>No job postings found</p></div>
                    ) : (
                        jobPosts.map((post: any) => (
                            <div key={post.id} className="card" style={{ padding: '1.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                                            <h3 style={{ margin: 0 }}>{post.title}</h3>
                                            <span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(post.status)}15`, color: getStatusColor(post.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>{post.status}</span>
                                        </div>
                                        <div style={{ display: 'flex', gap: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Briefcase size={14} />{post.department || 'No Department'}</span>
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Users size={14} />{post.applicants_count || 0} Applicants</span>
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Clock size={14} />{post.job_type}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </main>
        </div>
    );
};

export default JobPostList;
