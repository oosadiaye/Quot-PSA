import { useState } from 'react';
import { usePayrollRuns, useCreatePayrollRun } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, DollarSign, Calendar, Users } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const PayrollList = () => {
    const { showAlert } = useDialog();
    const { data: payrollRunsData, isLoading } = usePayrollRuns();
    const createPayrollRun = useCreatePayrollRun();
    
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({ period_start: '', period_end: '', status: 'Draft' });

    const payrollRuns = payrollRunsData?.results || payrollRunsData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = {
            'Draft': '#6b7280', 'In Progress': '#f59e0b',
            'Approved': '#2471a3', 'Paid': '#10b981', 'Cancelled': '#ef4444',
        };
        return colors[status] || '#6b7280';
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createPayrollRun.mutateAsync(formData);
            setShowForm(false);
            setFormData({ period_start: '', period_end: '', status: 'Draft' });
        } catch (err) {
            showAlert('Error creating payroll run');
        }
    };

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount || 0);
    };

    if (isLoading) return <LoadingScreen message="Loading payroll runs..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Payroll Runs"
                    subtitle="Manage employee payroll processing"
                    icon={<DollarSign size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Payroll Run
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>New Payroll Run</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Period Start<span className="required-mark"> *</span></label><input type="date" className="input" value={formData.period_start} onChange={e => setFormData({ ...formData, period_start: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Period End<span className="required-mark"> *</span></label><input type="date" className="input" value={formData.period_end} onChange={e => setFormData({ ...formData, period_end: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Status</label><select className="input" value={formData.status} onChange={e => setFormData({ ...formData, status: e.target.value })}><option value="Draft">Draft</option></select></div>
                            </div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">Create Run</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gap: '1rem' }}>
                    {payrollRuns.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}><DollarSign size={48} style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }} /><p>No payroll runs found</p></div>
                    ) : (
                        payrollRuns.map((run: any) => (
                            <div key={run.id} className="card" style={{ padding: '1.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                        <div style={{ width: '48px', height: '48px', borderRadius: '10px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><DollarSign size={24} /></div>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>Payroll #{run.id}</div>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                                <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Calendar size={14} />{run.period_start} - {run.period_end}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Total Amount</div>
                                            <div style={{ fontWeight: 600, fontSize: 'var(--text-lg)' }}>{formatCurrency(run.total_amount)}</div>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Employees</div>
                                            <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Users size={16} />{run.employee_count || 0}</div>
                                        </div>
                                        <span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(run.status)}15`, color: getStatusColor(run.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>{run.status}</span>
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

export default PayrollList;
