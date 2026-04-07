import { useState } from 'react';
import { useLeaveRequests, useLeaveTypes, useEmployees, useApproveLeave, useRejectLeave, useCreateLeaveRequest } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Check, X, Calendar, User } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const LeaveManagement = () => {
    const { showAlert, showPrompt } = useDialog();
    const { data: leaveRequestsData, isLoading } = useLeaveRequests();
    const { data: leaveTypesData } = useLeaveTypes();
    const { data: employeesData } = useEmployees();
    const approveLeave = useApproveLeave();
    const rejectLeave = useRejectLeave();
    const createLeaveRequest = useCreateLeaveRequest();
    
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({ employee: '', leave_type: '', start_date: '', end_date: '', reason: '' });

    const leaveRequests = leaveRequestsData?.results || leaveRequestsData || [];
    const leaveTypes = leaveTypesData?.results || leaveTypesData || [];
    const employees = employeesData?.results || employeesData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = {
            'Pending': '#f59e0b', 'Approved': '#10b981', 'Rejected': '#ef4444',
        };
        return colors[status] || '#6b7280';
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createLeaveRequest.mutateAsync(formData);
            setShowForm(false);
            setFormData({ employee: '', leave_type: '', start_date: '', end_date: '', reason: '' });
        } catch (err) {
            showAlert('Error creating leave request');
        }
    };

    const handleApprove = async (id: number) => {
        try { await approveLeave.mutateAsync(id); } catch (err) { showAlert('Error approving request'); }
    };

    const handleReject = async (id: number) => {
        const comment = await showPrompt('Rejection reason:');
        if (comment) {
            try { await rejectLeave.mutateAsync({ id, comment }); } catch (err) { showAlert('Error rejecting request'); }
        }
    };

    const getEmployeeName = (id: number) => {
        const emp = employees.find((e: any) => e.id === id);
        return emp ? `${emp.first_name} ${emp.last_name}` : `Employee #${id}`;
    };

    if (isLoading) return <LoadingScreen message="Loading leave requests..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Leave Management"
                    subtitle="Review and manage employee leave requests"
                    icon={<Calendar size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Request
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>New Leave Request</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Employee<span className="required-mark"> *</span></label><select className="input" value={formData.employee} onChange={e => setFormData({ ...formData, employee: e.target.value })} required><option value="">Select Employee</option>{employees.map((e: any) => <option key={e.id} value={e.id}>{e.first_name} {e.last_name}</option>)}</select></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Leave Type<span className="required-mark"> *</span></label><select className="input" value={formData.leave_type} onChange={e => setFormData({ ...formData, leave_type: e.target.value })} required><option value="">Select Type</option>{leaveTypes.map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Start Date<span className="required-mark"> *</span></label><input type="date" className="input" value={formData.start_date} onChange={e => setFormData({ ...formData, start_date: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>End Date<span className="required-mark"> *</span></label><input type="date" className="input" value={formData.end_date} onChange={e => setFormData({ ...formData, end_date: e.target.value })} required /></div>
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
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Leave Type</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Dates</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '1rem', width: '120px' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {leaveRequests.length === 0 ? (
                                <tr><td colSpan={5} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No leave requests found</td></tr>
                            ) : (
                                leaveRequests.map((req: any) => (
                                    <tr key={req.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><User size={16} />{getEmployeeName(req.employee_id || req.employee)}</div></td>
                                        <td style={{ padding: '1rem' }}>{req.leave_type_name || req.leave_type}</td>
                                        <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Calendar size={14} />{req.start_date} - {req.end_date}</div></td>
                                        <td style={{ padding: '1rem' }}><span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(req.status)}15`, color: getStatusColor(req.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>{req.status}</span></td>
                                        <td style={{ padding: '1rem' }}>
                                            {req.status === 'Pending' && (
                                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                                    <button className="btn btn-outline" onClick={() => handleApprove(req.id)} style={{ color: '#10b981' }}><Check size={16} /></button>
                                                    <button className="btn btn-outline" onClick={() => handleReject(req.id)} style={{ color: '#ef4444' }}><X size={16} /></button>
                                                </div>
                                            )}
                                        </td>
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

export default LeaveManagement;
