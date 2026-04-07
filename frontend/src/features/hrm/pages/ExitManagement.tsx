import { useState } from 'react';
import { useExitRequests, useCreateExitRequest, useEmployees } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, User, Calendar, FileText } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const ExitManagement = () => {
    const { showAlert } = useDialog();
    const { data: exitRequestsData, isLoading } = useExitRequests();
    const { data: employeesData } = useEmployees({});
    const createExitRequest = useCreateExitRequest();
    const employees = employeesData?.results || employeesData || [];
    
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({ employee: '', exit_date: '', reason: '', type: 'Resignation' });

    const exitRequests = exitRequestsData?.results || exitRequestsData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = { 'Pending': '#f59e0b', 'Approved': '#10b981', 'Rejected': '#ef4444', 'Processed': '#2471a3' };
        return colors[status] || '#6b7280';
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createExitRequest.mutateAsync(formData);
            setShowForm(false);
            setFormData({ employee: '', exit_date: '', reason: '', type: 'Resignation' });
        } catch (err) {
            showAlert('Error creating exit request');
        }
    };

    if (isLoading) return <LoadingScreen message="Loading exit requests..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Exit Management"
                    subtitle="Manage employee exit requests and processes"
                    icon={<User size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Exit Request
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>New Exit Request</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Employee<span className="required-mark"> *</span></label><select className="input" value={formData.employee} onChange={e => setFormData({ ...formData, employee: e.target.value })} required><option value="">Select Employee</option>{employees.map((e: any) => <option key={e.id} value={e.id}>{e.first_name} {e.last_name} ({e.employee_number})</option>)}</select></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Exit Date<span className="required-mark"> *</span></label><input type="date" className="input" value={formData.exit_date} onChange={e => setFormData({ ...formData, exit_date: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Type</label><select className="input" value={formData.type} onChange={e => setFormData({ ...formData, type: e.target.value })}><option value="Resignation">Resignation</option><option value="Termination">Termination</option><option value="Retirement">Retirement</option></select></div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Reason</label><textarea className="input" value={formData.reason} onChange={e => setFormData({ ...formData, reason: e.target.value })} rows={2} style={{ width: '100%' }} /></div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">Submit Request</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Employee</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Type</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Exit Date</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Reason</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {exitRequests.length === 0 ? (
                                <tr><td colSpan={5} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}><User size={32} style={{ marginBottom: '0.5rem' }} /><p>No exit requests found</p></td></tr>
                            ) : (
                                exitRequests.map((request: any) => (
                                    <tr key={request.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><User size={16} />{request.employee_name || `Employee #${request.employee}`}</div></td>
                                        <td style={{ padding: '1rem' }}>{request.exit_type || request.type}</td>
                                        <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Calendar size={14} />{request.exit_date || '-'}</div></td>
                                        <td style={{ padding: '1rem', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{request.reason || '-'}</td>
                                        <td style={{ padding: '1rem' }}><span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(request.status)}15`, color: getStatusColor(request.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>{request.status}</span></td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </main>
        </div>
    );
};

export default ExitManagement;
