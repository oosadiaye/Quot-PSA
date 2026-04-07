import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useEmployees, useDepartments, usePositions, useCreateEmployee } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Search, Edit, UserCheck, UserX, Users } from 'lucide-react';

const EmployeeList = () => {
    const navigate = useNavigate();
    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [departmentFilter, setDepartmentFilter] = useState('');
    
    const { data: employeesData, isLoading } = useEmployees({ search, status: statusFilter, department: departmentFilter });
    const { data: departmentsData } = useDepartments();
    const createEmployee = useCreateEmployee();

    const employees = employeesData?.results || employeesData || [];
    const departments = departmentsData?.results || departmentsData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = {
            'Active': '#10b981', 'Probation': '#f59e0b', 'On Leave': '#2471a3',
            'Terminated': '#ef4444', 'Retired': '#6b7280',
        };
        return colors[status] || '#6b7280';
    };

    if (isLoading) return <LoadingScreen message="Loading employees..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Employee Directory"
                    subtitle="Manage employee records and information"
                    icon={<Users size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => navigate('/hrm/employees/new')}>
                            <Plus size={18} /> Add Employee
                        </button>
                    }
                />

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
                    <div style={{ position: 'relative', flex: 1 }}>
                        <Search size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input type="text" placeholder="Search employees..." value={search} onChange={e => setSearch(e.target.value)} style={{ width: '100%', padding: '0.75rem 1rem 0.75rem 2.75rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)' }} />
                    </div>
                    <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ padding: '0.75rem 1rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)' }}>
                        <option value="">All Status</option>
                        <option value="Active">Active</option>
                        <option value="Probation">Probation</option>
                        <option value="On Leave">On Leave</option>
                        <option value="Terminated">Terminated</option>
                    </select>
                    <select value={departmentFilter} onChange={e => setDepartmentFilter(e.target.value)} style={{ padding: '0.75rem 1rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)' }}>
                        <option value="">All Departments</option>
                        {departments.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                </div>

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Employee</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Department</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Position</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Type</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '1rem', width: '80px' }}></th>
                            </tr>
                        </thead>
                        <tbody>
                            {employees.length === 0 ? (
                                <tr><td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No employees found</td></tr>
                            ) : (
                                employees.map((emp: any) => (
                                    <tr key={emp.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}>
                                            <div style={{ fontWeight: 600 }}>{emp.first_name} {emp.last_name}</div>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{emp.employee_number}</div>
                                        </td>
                                        <td style={{ padding: '1rem' }}>{emp.department_name || '-'}</td>
                                        <td style={{ padding: '1rem' }}>{emp.position_title || '-'}</td>
                                        <td style={{ padding: '1rem' }}>{emp.employee_type}</td>
                                        <td style={{ padding: '1rem' }}>
                                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(emp.status)}15`, color: getStatusColor(emp.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                {emp.status === 'Active' ? <UserCheck size={12} /> : <UserX size={12} />} {emp.status}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem' }}>
                                            <button className="btn btn-outline" onClick={() => navigate(`/hrm/employees/${emp.id}`)}><Edit size={16} /></button>
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

export default EmployeeList;
