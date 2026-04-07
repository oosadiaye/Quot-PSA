import { useState } from 'react';
import { useAttendances, useEmployees, useCreateAttendance } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Clock, User, CheckCircle } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const AttendanceList = () => {
    const { showAlert } = useDialog();
    const { data: attendancesData, isLoading } = useAttendances();
    const { data: employeesData } = useEmployees();
    const createAttendance = useCreateAttendance();
    
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({ employee: '', date: '', check_in: '', check_out: '', status: 'Present' });

    const attendances = attendancesData?.results || attendancesData || [];
    const employees = employeesData?.results || employeesData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = {
            'Present': '#10b981', 'Absent': '#ef4444', 'Late': '#f59e0b', 'On Leave': '#2471a3',
        };
        return colors[status] || '#6b7280';
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createAttendance.mutateAsync(formData);
            setShowForm(false);
            setFormData({ employee: '', date: '', check_in: '', check_out: '', status: 'Present' });
        } catch (err) {
            showAlert('Error creating attendance');
        }
    };

    const getEmployeeName = (id: number) => {
        const emp = employees.find((e: any) => e.id === id);
        return emp ? `${emp.first_name} ${emp.last_name}` : `Employee #${id}`;
    };

    if (isLoading) return <LoadingScreen message="Loading attendance records..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Attendance"
                    subtitle="Track employee attendance records"
                    icon={<Clock size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> Record Attendance
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>New Attendance Record</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Employee<span className="required-mark"> *</span></label><select className="input" value={formData.employee} onChange={e => setFormData({ ...formData, employee: e.target.value })} required><option value="">Select Employee</option>{employees.map((e: any) => <option key={e.id} value={e.id}>{e.first_name} {e.last_name}</option>)}</select></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Date<span className="required-mark"> *</span></label><input type="date" className="input" value={formData.date} onChange={e => setFormData({ ...formData, date: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Check In</label><input type="time" className="input" value={formData.check_in} onChange={e => setFormData({ ...formData, check_in: e.target.value })} /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Check Out</label><input type="time" className="input" value={formData.check_out} onChange={e => setFormData({ ...formData, check_out: e.target.value })} /></div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Status<span className="required-mark"> *</span></label><select className="input" value={formData.status} onChange={e => setFormData({ ...formData, status: e.target.value })}><option value="Present">Present</option><option value="Absent">Absent</option><option value="Late">Late</option><option value="On Leave">On Leave</option></select></div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">Save Record</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Employee</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Date</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Check In</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Check Out</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {attendances.length === 0 ? (
                                <tr><td colSpan={5} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No attendance records found</td></tr>
                            ) : (
                                attendances.map((att: any) => (
                                    <tr key={att.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><User size={16} />{getEmployeeName(att.employee_id || att.employee)}</div></td>
                                        <td style={{ padding: '1rem' }}>{att.date}</td>
                                        <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Clock size={14} />{att.check_in || '-'}</div></td>
                                        <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Clock size={14} />{att.check_out || '-'}</div></td>
                                        <td style={{ padding: '1rem' }}><span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(att.status)}15`, color: getStatusColor(att.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>{att.status}</span></td>
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

export default AttendanceList;
