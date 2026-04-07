import { useState } from 'react';
import { usePerformanceCycles, usePerformanceReviews, useCreatePerformanceReview, useEmployees } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Star, User, Calendar, TrendingUp } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const PerformanceList = () => {
    const { showAlert } = useDialog();
    const { data: cyclesData, isLoading: cyclesLoading } = usePerformanceCycles();
    const { data: reviewsData } = usePerformanceReviews();
    const { data: employeesData } = useEmployees({});
    const createReview = useCreatePerformanceReview();

    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({ employee: '', cycle: '', rating: 3, comments: '' });

    const cycles = cyclesData?.results || cyclesData || [];
    const employees = employeesData?.results || employeesData || [];
    const reviews = reviewsData?.results || reviewsData || [];

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createReview.mutateAsync(formData);
            setShowForm(false);
            setFormData({ employee: '', cycle: '', rating: 3, comments: '' });
        } catch (err) {
            showAlert('Error creating review');
        }
    };

    const getRatingColor = (rating: number) => {
        if (rating >= 4) return '#10b981';
        if (rating >= 3) return '#f59e0b';
        return '#ef4444';
    };

    if (cyclesLoading) return <LoadingScreen message="Loading performance data..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Performance"
                    subtitle="Manage performance reviews and cycles"
                    icon={<TrendingUp size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Review
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>New Performance Review</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Employee<span className="required-mark"> *</span></label><select className="input" value={formData.employee} onChange={e => setFormData({ ...formData, employee: e.target.value })} required><option value="">Select Employee</option>{employees.map((e: any) => <option key={e.id} value={e.id}>{e.first_name} {e.last_name}</option>)}</select></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Cycle<span className="required-mark"> *</span></label><select className="input" value={formData.cycle} onChange={e => setFormData({ ...formData, cycle: e.target.value })} required><option value="">Select Cycle</option>{cycles.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Rating (1-5)</label><input type="number" className="input" min="1" max="5" value={formData.rating} onChange={e => setFormData({ ...formData, rating: parseInt(e.target.value) })} /></div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Comments</label><textarea className="input" value={formData.comments} onChange={e => setFormData({ ...formData, comments: e.target.value })} rows={2} style={{ width: '100%' }} /></div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">Submit Review</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div style={{ marginBottom: '2rem' }}>
                    <h3 style={{ marginBottom: '1rem' }}>Performance Cycles</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
                        {cycles.length === 0 ? (
                            <div className="card" style={{ textAlign: 'center', padding: '2rem', gridColumn: '1 / -1' }}><Calendar size={32} style={{ color: 'var(--color-text-muted)', marginBottom: '0.5rem' }} /><p>No cycles found</p></div>
                        ) : (
                            cycles.map((cycle: any) => (
                                <div key={cycle.id} className="card" style={{ padding: '1.25rem' }}>
                                    <div style={{ fontWeight: 600 }}>{cycle.name}</div>
                                    <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{cycle.start_date} - {cycle.end_date}</div>
                                    <div style={{ marginTop: '0.75rem', fontSize: 'var(--text-sm)' }}>Status: <span style={{ color: cycle.is_active ? '#10b981' : '#6b7280' }}>{cycle.is_active ? 'Active' : 'Completed'}</span></div>
                                </div>
                            ))
                        )}
                    </div>
                </div>

                <div>
                    <h3 style={{ marginBottom: '1rem' }}>Performance Reviews</h3>
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Employee</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Cycle</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Rating</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {reviews.length === 0 ? (
                                    <tr><td colSpan={4} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No reviews found</td></tr>
                                ) : (
                                    reviews.map((review: any) => (
                                        <tr key={review.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><User size={16} />{review.employee_name || `Employee #${review.employee}`}</div></td>
                                            <td style={{ padding: '1rem' }}>{review.cycle_name || review.cycle}</td>
                                            <td style={{ padding: '1rem' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                                    {[1, 2, 3, 4, 5].map((star) => (
                                                        <Star key={star} size={14} fill={star <= review.rating ? getRatingColor(review.rating) : 'transparent'} color={getRatingColor(review.rating)} />
                                                    ))}
                                                </div>
                                            </td>
                                            <td style={{ padding: '1rem' }}>{review.review_date || review.created_at?.split('T')[0]}</td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default PerformanceList;
