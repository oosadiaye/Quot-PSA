import { useComplianceRecords } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Shield, CheckCircle, AlertTriangle, Calendar } from 'lucide-react';

const ComplianceList = () => {
    const { data: complianceData, isLoading } = useComplianceRecords();

    const records = complianceData?.results || complianceData || [];

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = { 'Compliant': '#10b981', 'Pending': '#f59e0b', 'Non-Compliant': '#ef4444', 'Expired': '#6b7280' };
        return colors[status] || '#6b7280';
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'Compliant': return <CheckCircle size={16} />;
            case 'Non-Compliant': return <AlertTriangle size={16} />;
            default: return <Calendar size={16} />;
        }
    };

    if (isLoading) return <LoadingScreen message="Loading compliance records..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Compliance"
                    subtitle="Track regulatory compliance and certifications"
                    icon={<Shield size={22} color="white" />}
                />

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Type</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Employee</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Issue Date</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Expiry Date</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {records.length === 0 ? (
                                <tr><td colSpan={5} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}><Shield size={32} style={{ marginBottom: '0.5rem' }} /><p>No compliance records found</p></td></tr>
                            ) : (
                                records.map((record: any) => (
                                    <tr key={record.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Shield size={16} />{record.compliance_type || record.type}</div>
                                        </td>
                                        <td style={{ padding: '1rem' }}>{record.employee_name || `Employee #${record.employee_id || record.employee}`}</td>
                                        <td style={{ padding: '1rem' }}>{record.issue_date || record.issued_date || '-'}</td>
                                        <td style={{ padding: '1rem' }}>{record.expiry_date || record.expiration_date || '-'}</td>
                                        <td style={{ padding: '1rem' }}>
                                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.25rem 0.5rem', borderRadius: '4px', background: `${getStatusColor(record.status)}15`, color: getStatusColor(record.status), fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                {getStatusIcon(record.status)} {record.status}
                                            </span>
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

export default ComplianceList;
