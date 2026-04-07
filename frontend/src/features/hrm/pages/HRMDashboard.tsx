import { Users, Building2, Calendar, Clock, UserCheck, UserX, TrendingUp } from 'lucide-react';
import { useHRMDashboard, usePendingLeaveCount, useAttendanceToday } from '../hooks/useHrm';
import LoadingScreen from '../../../components/common/LoadingScreen';
import PageHeader from '../../../components/PageHeader';
import Sidebar from '../../../components/Sidebar';

const HRMDashboard = () => {
    const { data: dashboard, isLoading } = useHRMDashboard();
    const { data: pendingLeave } = usePendingLeaveCount();
    const { data: attendance } = useAttendanceToday();

    if (isLoading) {
        return <LoadingScreen message="Loading HR dashboard..." />;
    }

    const presentCount = attendance?.summary?.find((s: any) => s.status === 'Present')?.count || 0;
    const absentCount = attendance?.summary?.find((s: any) => s.status === 'Absent')?.count || 0;
    const lateCount = attendance?.summary?.find((s: any) => s.status === 'Late')?.count || 0;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <div style={{
                flex: 1,
                marginLeft: '260px',
                padding: '2rem',
                background: 'var(--color-background)'
            }}>
                <PageHeader
                    title="Human Resources"
                    subtitle="Employee management, attendance, and leave tracking."
                    icon={<Users size={22} color="white" />}
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.25rem', marginBottom: '2rem' }}>
                    <div className="card">
                        <Users size={24} style={{ color: 'var(--color-primary)', marginBottom: '0.75rem' }} />
                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                            TOTAL EMPLOYEES
                        </div>
                        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {dashboard?.total_employees || 0}
                        </div>
                    </div>

                    <div className="card">
                        <UserCheck size={24} style={{ color: 'var(--color-success)', marginBottom: '0.75rem' }} />
                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                            ACTIVE EMPLOYEES
                        </div>
                        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {dashboard?.active_employees || 0}
                        </div>
                    </div>

                    <div className="card">
                        <Calendar size={24} style={{ color: 'var(--color-warning)', marginBottom: '0.75rem' }} />
                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                            ON LEAVE
                        </div>
                        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {dashboard?.on_leave || 0}
                        </div>
                    </div>

                    <div className="card">
                        <Clock size={24} style={{ color: 'var(--color-info)', marginBottom: '0.75rem' }} />
                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                            PENDING LEAVES
                        </div>
                        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {pendingLeave?.count || 0}
                        </div>
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
                    <div className="card">
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)' }}>
                            Employees by Department
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {dashboard?.by_department?.map((dept: any) => (
                                <div key={dept.department__id || dept.department__name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <Building2 size={16} style={{ color: 'var(--color-text-muted)' }} />
                                        <span style={{ color: 'var(--color-text)' }}>{dept.department__name || 'Unknown'}</span>
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <div style={{
                                            width: '100px',
                                            height: '8px',
                                            background: 'var(--color-border)',
                                            borderRadius: '4px',
                                            overflow: 'hidden'
                                        }}>
                                            <div style={{
                                                width: `${((dept.count / (dashboard?.total_employees || 1)) * 100)}%`,
                                                height: '100%',
                                                background: 'var(--color-primary)',
                                                borderRadius: '4px'
                                            }} />
                                        </div>
                                        <span style={{ fontWeight: 600, color: 'var(--color-text)', minWidth: '30px', textAlign: 'right' }}>
                                            {dept.count}
                                        </span>
                                    </div>
                                </div>
                            ))}
                            {(!dashboard?.by_department || dashboard.by_department.length === 0) && (
                                <p style={{ color: 'var(--color-text-muted)', textAlign: 'center', padding: '1rem' }}>
                                    No department data available
                                </p>
                            )}
                        </div>
                    </div>

                    <div className="card">
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)' }}>
                            Today's Attendance
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--color-success)' }} />
                                    <span style={{ color: 'var(--color-text)' }}>Present</span>
                                </div>
                                <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{presentCount}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--color-error)' }} />
                                    <span style={{ color: 'var(--color-text)' }}>Absent</span>
                                </div>
                                <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{absentCount}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--color-warning)' }} />
                                    <span style={{ color: 'var(--color-text)' }}>Late</span>
                                </div>
                                <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{lateCount}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {dashboard?.by_status && dashboard.by_status.length > 0 && (
                    <div className="card" style={{ marginTop: '1.5rem' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)' }}>
                            Employees by Status
                        </h3>
                        <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
                            {dashboard.by_status.map((status: any) => (
                                <div key={status.status} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <span style={{ color: 'var(--color-text)' }}>{status.status}:</span>
                                    <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{status.count}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default HRMDashboard;
