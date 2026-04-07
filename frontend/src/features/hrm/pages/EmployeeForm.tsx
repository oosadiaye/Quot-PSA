import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    useEmployee, useCreateEmployee, useUpdateEmployee, useDeleteEmployee,
    useDepartments, usePositions, useEmployees,
} from '../hooks/useHrm';
import apiClient from '../../../api/client';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Save, Trash2, X, UserCheck } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const labelStyle: React.CSSProperties = {
    display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
    fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem', border: '2.5px solid var(--color-border)',
    borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)',
    fontSize: 'var(--text-sm)',
};

const EmployeeForm = () => {
    const { showAlert, showConfirm } = useDialog();
    const navigate = useNavigate();
    const { id } = useParams();
    const isEdit = Boolean(id);
    const employeeId = isEdit && id ? Number(id) : 0;

    const { data: employee, isLoading: empLoading } = useEmployee(employeeId);
    const { data: departmentsData } = useDepartments();
    const { data: positionsData } = usePositions();
    const { data: employeesData } = useEmployees({});
    const { data: usersData } = useQuery({
        queryKey: ['tenant-users-list'],
        queryFn: async () => {
            const res = await apiClient.get('/core/tenant-users/');
            return res.data;
        },
    });

    const createEmployee = useCreateEmployee();
    const updateEmployee = useUpdateEmployee();
    const deleteEmployee = useDeleteEmployee();

    const departments = departmentsData?.results || departmentsData || [];
    const positions = positionsData?.results || positionsData || [];
    const employees = employeesData?.results || employeesData || [];
    const users = Array.isArray(usersData) ? usersData : (usersData?.results || []);

    const [formData, setFormData] = useState({
        user: '',
        employee_type: 'Permanent',
        department: '',
        position: '',
        supervisor: '',
        hire_date: '',
        confirmation_date: '',
        contract_start_date: '',
        contract_end_date: '',
        termination_date: '',
        status: 'Active',
        base_salary: '',
        hourly_rate: '',
        bank_name: '',
        bank_account: '',
        bank_routing: '',
        emergency_contact_name: '',
        emergency_contact_phone: '',
        emergency_contact_relation: '',
    });

    useEffect(() => {
        if (isEdit && employee) {
            setFormData({
                user: employee.user || '',
                employee_type: employee.employee_type || 'Permanent',
                department: employee.department || '',
                position: employee.position || '',
                supervisor: employee.supervisor || '',
                hire_date: employee.hire_date || '',
                confirmation_date: employee.confirmation_date || '',
                contract_start_date: employee.contract_start_date || '',
                contract_end_date: employee.contract_end_date || '',
                termination_date: employee.termination_date || '',
                status: employee.status || 'Active',
                base_salary: employee.base_salary || '',
                hourly_rate: employee.hourly_rate || '',
                bank_name: employee.bank_name || '',
                bank_account: employee.bank_account || '',
                bank_routing: employee.bank_routing || '',
                emergency_contact_name: employee.emergency_contact_name || '',
                emergency_contact_phone: employee.emergency_contact_phone || '',
                emergency_contact_relation: employee.emergency_contact_relation || '',
            });
        }
    }, [isEdit, employee]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const payload: any = {
            user: Number(formData.user),
            employee_type: formData.employee_type,
            department: Number(formData.department),
            position: Number(formData.position),
            hire_date: formData.hire_date,
            status: formData.status,
        };
        if (formData.supervisor) payload.supervisor = Number(formData.supervisor);
        if (formData.confirmation_date) payload.confirmation_date = formData.confirmation_date;
        if (formData.contract_start_date) payload.contract_start_date = formData.contract_start_date;
        if (formData.contract_end_date) payload.contract_end_date = formData.contract_end_date;
        if (formData.termination_date) payload.termination_date = formData.termination_date;
        if (formData.base_salary) payload.base_salary = formData.base_salary;
        if (formData.hourly_rate) payload.hourly_rate = formData.hourly_rate;
        if (formData.bank_name) payload.bank_name = formData.bank_name;
        if (formData.bank_account) payload.bank_account = formData.bank_account;
        if (formData.bank_routing) payload.bank_routing = formData.bank_routing;
        if (formData.emergency_contact_name) payload.emergency_contact_name = formData.emergency_contact_name;
        if (formData.emergency_contact_phone) payload.emergency_contact_phone = formData.emergency_contact_phone;
        if (formData.emergency_contact_relation) payload.emergency_contact_relation = formData.emergency_contact_relation;

        try {
            if (isEdit) {
                await updateEmployee.mutateAsync({ id: employeeId, data: payload });
            } else {
                await createEmployee.mutateAsync(payload);
            }
            navigate('/hrm/employees');
        } catch (err: any) {
            const data = err.response?.data;
            if (data) {
                const msgs = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('\n');
                showAlert(msgs);
            } else {
                showAlert('Error saving employee');
            }
        }
    };

    const handleDelete = async () => {
        if (await showConfirm('Are you sure you want to delete this employee record?')) {
            try {
                await deleteEmployee.mutateAsync(employeeId);
                navigate('/hrm/employees');
            } catch {
                showAlert('Error deleting employee');
            }
        }
    };

    const set = (field: string, value: string) => setFormData(prev => ({ ...prev, [field]: value }));

    if (isEdit && empLoading) return <LoadingScreen message="Loading employee..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title={isEdit ? 'Edit Employee' : 'New Employee'}
                    subtitle={isEdit ? `Editing ${employee?.employee_number || ''}` : 'Create a new employee record'}
                    icon={<UserCheck size={22} color="white" />}
                />

                <form onSubmit={handleSubmit}>
                    {/* Basic Information */}
                    <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.25rem', fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)' }}>Basic Information</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                            <div>
                                <label style={labelStyle}>User Account *</label>
                                <select value={formData.user} onChange={e => set('user', e.target.value)} style={inputStyle} required>
                                    <option value="">Select User</option>
                                    {users.map((u: any) => (
                                        <option key={u.id} value={u.id}>
                                            {u.first_name || u.last_name ? `${u.first_name} ${u.last_name}`.trim() : u.username} ({u.username})
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Department *</label>
                                <select value={formData.department} onChange={e => set('department', e.target.value)} style={inputStyle} required>
                                    <option value="">Select Department</option>
                                    {departments.map((d: any) => (
                                        <option key={d.id} value={d.id}>{d.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Position *</label>
                                <select value={formData.position} onChange={e => set('position', e.target.value)} style={inputStyle} required>
                                    <option value="">Select Position</option>
                                    {positions.map((p: any) => (
                                        <option key={p.id} value={p.id}>{p.title}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Employee Type *</label>
                                <select value={formData.employee_type} onChange={e => set('employee_type', e.target.value)} style={inputStyle} required>
                                    <option value="Permanent">Permanent</option>
                                    <option value="Contract">Contract</option>
                                    <option value="Intern">Intern</option>
                                    <option value="Part-time">Part-time</option>
                                    <option value="Freelance">Freelance</option>
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Status *</label>
                                <select value={formData.status} onChange={e => set('status', e.target.value)} style={inputStyle} required>
                                    <option value="Active">Active</option>
                                    <option value="Probation">Probation</option>
                                    <option value="On Leave">On Leave</option>
                                    <option value="Terminated">Terminated</option>
                                    <option value="Retired">Retired</option>
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Supervisor</label>
                                <select value={formData.supervisor} onChange={e => set('supervisor', e.target.value)} style={inputStyle}>
                                    <option value="">None</option>
                                    {employees.filter((emp: any) => emp.id !== employeeId).map((emp: any) => (
                                        <option key={emp.id} value={emp.id}>
                                            {emp.first_name} {emp.last_name} ({emp.employee_number})
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </div>

                    {/* Dates */}
                    <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.25rem', fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)' }}>Employment Dates</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                            <div>
                                <label style={labelStyle}>Hire Date *</label>
                                <input type="date" value={formData.hire_date} onChange={e => set('hire_date', e.target.value)} style={inputStyle} required />
                            </div>
                            <div>
                                <label style={labelStyle}>Confirmation Date</label>
                                <input type="date" value={formData.confirmation_date} onChange={e => set('confirmation_date', e.target.value)} style={inputStyle} />
                            </div>
                            <div>
                                <label style={labelStyle}>Termination Date</label>
                                <input type="date" value={formData.termination_date} onChange={e => set('termination_date', e.target.value)} style={inputStyle} />
                            </div>
                            <div>
                                <label style={labelStyle}>Contract Start Date</label>
                                <input type="date" value={formData.contract_start_date} onChange={e => set('contract_start_date', e.target.value)} style={inputStyle} />
                            </div>
                            <div>
                                <label style={labelStyle}>Contract End Date</label>
                                <input type="date" value={formData.contract_end_date} onChange={e => set('contract_end_date', e.target.value)} style={inputStyle} />
                            </div>
                        </div>
                    </div>

                    {/* Compensation */}
                    <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.25rem', fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)' }}>Compensation & Banking</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                            <div>
                                <label style={labelStyle}>Base Salary</label>
                                <input type="number" step="0.01" value={formData.base_salary} onChange={e => set('base_salary', e.target.value)} style={inputStyle} placeholder="0.00" />
                            </div>
                            <div>
                                <label style={labelStyle}>Hourly Rate</label>
                                <input type="number" step="0.01" value={formData.hourly_rate} onChange={e => set('hourly_rate', e.target.value)} style={inputStyle} placeholder="0.00" />
                            </div>
                            <div />
                            <div>
                                <label style={labelStyle}>Bank Name</label>
                                <input type="text" value={formData.bank_name} onChange={e => set('bank_name', e.target.value)} style={inputStyle} />
                            </div>
                            <div>
                                <label style={labelStyle}>Bank Account Number</label>
                                <input type="text" value={formData.bank_account} onChange={e => set('bank_account', e.target.value)} style={inputStyle} />
                            </div>
                            <div>
                                <label style={labelStyle}>Bank Routing Number</label>
                                <input type="text" value={formData.bank_routing} onChange={e => set('bank_routing', e.target.value)} style={inputStyle} />
                            </div>
                        </div>
                    </div>

                    {/* Emergency Contact */}
                    <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.25rem', fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)' }}>Emergency Contact</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                            <div>
                                <label style={labelStyle}>Contact Name</label>
                                <input type="text" value={formData.emergency_contact_name} onChange={e => set('emergency_contact_name', e.target.value)} style={inputStyle} />
                            </div>
                            <div>
                                <label style={labelStyle}>Contact Phone</label>
                                <input type="text" value={formData.emergency_contact_phone} onChange={e => set('emergency_contact_phone', e.target.value)} style={inputStyle} />
                            </div>
                            <div>
                                <label style={labelStyle}>Relationship</label>
                                <input type="text" value={formData.emergency_contact_relation} onChange={e => set('emergency_contact_relation', e.target.value)} style={inputStyle} placeholder="e.g. Spouse, Parent" />
                            </div>
                        </div>
                    </div>

                    {/* Actions */}
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <div>
                            {isEdit && (
                                <button type="button" className="btn btn-outline" onClick={handleDelete}
                                    style={{ color: 'var(--color-error)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <Trash2 size={16} /> Delete Employee
                                </button>
                            )}
                        </div>
                        <div style={{ display: 'flex', gap: '1rem' }}>
                            <button type="button" className="btn btn-outline" onClick={() => navigate('/hrm/employees')}
                                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <X size={16} /> Cancel
                            </button>
                            <button type="submit" className="btn btn-primary"
                                disabled={createEmployee.isPending || updateEmployee.isPending}
                                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <Save size={16} /> {isEdit ? 'Update' : 'Create'} Employee
                            </button>
                        </div>
                    </div>
                </form>
            </main>
        </div>
    );
};

export default EmployeeForm;
