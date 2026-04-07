import { useState } from 'react';
import { useTrainingPrograms, useCreateTrainingProgram } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, GraduationCap, Clock, Users } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const TrainingList = () => {
    const { showAlert } = useDialog();
    const { data: programsData, isLoading } = useTrainingPrograms();
    const createProgram = useCreateTrainingProgram();
    
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({ name: '', description: '', duration_hours: '', start_date: '', status: 'Scheduled' });

    const programs = programsData?.results || programsData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = { 'Scheduled': '#2471a3', 'In Progress': '#f59e0b', 'Completed': '#10b981', 'Cancelled': '#ef4444' };
        return colors[status] || '#6b7280';
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createProgram.mutateAsync(formData);
            setShowForm(false);
            setFormData({ name: '', description: '', duration_hours: '', start_date: '', status: 'Scheduled' });
        } catch (err) {
            showAlert('Error creating training program');
        }
    };

    if (isLoading) return <LoadingScreen message="Loading training programs..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Training Programs"
                    subtitle="Manage employee training and development"
                    icon={<GraduationCap size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Program
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>New Training Program</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Name<span className="required-mark"> *</span></label><input type="text" className="input" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Duration (hours)</label><input type="number" className="input" value={formData.duration_hours} onChange={e => setFormData({ ...formData, duration_hours: e.target.value })} /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Start Date</label><input type="date" className="input" value={formData.start_date} onChange={e => setFormData({ ...formData, start_date: e.target.value })} /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Status</label><select className="input" value={formData.status} onChange={e => setFormData({ ...formData, status: e.target.value })}><option value="Scheduled">Scheduled</option><option value="In Progress">In Progress</option><option value="Completed">Completed</option></select></div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Description</label><textarea className="input" value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} rows={2} style={{ width: '100%' }} /></div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">Create Program</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gap: '1rem' }}>
                    {programs.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}><GraduationCap size={48} style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }} /><p>No training programs found</p></div>
                    ) : (
                        programs.map((program: any) => (
                            <div key={program.id} className="card" style={{ padding: '1.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                        <div style={{ width: '48px', height: '48px', borderRadius: '10px', background: 'rgba(139, 92, 246, 0.1)', color: '#8b5cf6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><GraduationCap size={24} /></div>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{program.name}</div>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', display: 'flex', gap: '1rem', marginTop: '0.25rem' }}>
                                                {program.duration_hours && <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Clock size={14} />{program.duration_hours}h</span>}
                                                {program.enrolled_count !== undefined && <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Users size={14} />{program.enrolled_count} enrolled</span>}
                                            </div>
                                        </div>
                                    </div>
                                    <span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(program.status)}15`, color: getStatusColor(program.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>{program.status}</span>
                                </div>
                                {program.description && <p style={{ margin: '1rem 0 0', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{program.description}</p>}
                            </div>
                        ))
                    )}
                </div>
            </main>
        </div>
    );
};

export default TrainingList;
