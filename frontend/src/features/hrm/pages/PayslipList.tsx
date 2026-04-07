import { usePayslips } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { FileText, Download, User, Calendar } from 'lucide-react';

const PayslipList = () => {
    const { data: payslipsData, isLoading } = usePayslips();

    const payslips = payslipsData?.results || payslipsData || [];

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount || 0);
    };

    if (isLoading) return <LoadingScreen message="Loading payslips..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Payslips"
                    subtitle="View and download employee payslips"
                    icon={<FileText size={22} color="white" />}
                />

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Employee</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Period</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Basic Salary</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Deductions</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Net Pay</th>
                                <th style={{ padding: '1rem', width: '80px' }}></th>
                            </tr>
                        </thead>
                        <tbody>
                            {payslips.length === 0 ? (
                                <tr><td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No payslips found</td></tr>
                            ) : (
                                payslips.map((payslip: any) => (
                                    <tr key={payslip.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><User size={16} />{payslip.employee_name || `Employee #${payslip.employee_id || payslip.employee}`}</div>
                                        </td>
                                        <td style={{ padding: '1rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Calendar size={14} />{payslip.period_start} - {payslip.period_end}</div></td>
                                        <td style={{ padding: '1rem' }}>{formatCurrency(payslip.basic_salary)}</td>
                                        <td style={{ padding: '1rem', color: '#ef4444' }}>-{formatCurrency(payslip.deductions)}</td>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{formatCurrency(payslip.net_pay)}</td>
                                        <td style={{ padding: '1rem' }}>
                                            <button className="btn btn-outline"><Download size={16} /></button>
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

export default PayslipList;
