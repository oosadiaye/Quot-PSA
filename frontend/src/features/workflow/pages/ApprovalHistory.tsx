import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { History, CheckCircle, XCircle, Clock, FileText } from 'lucide-react';

const ApprovalHistory = () => {
    const { data: approvals, isLoading } = useQuery({
        queryKey: ['approval-history'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approvals/', {
                params: { status: 'Approved,Rejected' }
            });
            return data;
        }
    });

    const { data: logs } = useQuery({
        queryKey: ['approval-logs'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approval-logs/');
            return data;
        }
    });

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'Approved': return <CheckCircle size={16} style={{ color: 'var(--color-success)' }} />;
            case 'Rejected': return <XCircle size={16} style={{ color: 'var(--color-error)' }} />;
            default: return <Clock size={16} style={{ color: 'var(--color-warning)' }} />;
        }
    };

    const approvalsList = Array.isArray(approvals?.results) ? approvals.results : Array.isArray(approvals) ? approvals : [];
    const logsList = Array.isArray(logs?.results) ? logs.results : Array.isArray(logs) ? logs : [];

    const stats = {
        total: approvalsList.length || 0,
        approved: approvalsList.filter((a: any) => a.status === 'Approved').length || 0,
        rejected: approvalsList.filter((a: any) => a.status === 'Rejected').length || 0,
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Approval History"
                    subtitle="View history of all approval requests."
                    icon={<History size={22} color="white" />}
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem', marginBottom: '2rem' }}>
                    <div className="card">
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>TOTAL</div>
                        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{stats.total}</div>
                    </div>
                    <div className="card">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <CheckCircle size={20} style={{ color: 'var(--color-success)' }} />
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>APPROVED</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{stats.approved}</div>
                            </div>
                        </div>
                    </div>
                    <div className="card">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <XCircle size={20} style={{ color: 'var(--color-error)' }} />
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>REJECTED</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{stats.rejected}</div>
                            </div>
                        </div>
                    </div>
                </div>

                <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: '1rem' }}>Recent Approvals</h2>
                <div className="card">
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>TITLE</th>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>TYPE</th>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>REQUESTED BY</th>
                                <th style={{ textAlign: 'right', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>AMOUNT</th>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>STATUS</th>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>DATE</th>
                            </tr>
                        </thead>
                        <tbody>
                            {approvals?.results?.map((approval: any) => (
                                <tr key={approval.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)' }}>{approval.title}</td>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)', textTransform: 'capitalize' }}>{approval.content_type_name}</td>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)' }}>{approval.requested_by_name}</td>
                                    <td style={{ padding: '1rem', textAlign: 'right', fontSize: 'var(--text-sm)' }}>${Number(approval.amount || 0).toLocaleString()}</td>
                                    <td style={{ padding: '1rem' }}>
                                        <span style={{
                                            display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                            padding: '0.25rem 0.5rem', borderRadius: '1rem', fontSize: 'var(--text-xs)',
                                            background: approval.status === 'Approved' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                                            color: approval.status === 'Approved' ? 'var(--color-success)' : 'var(--color-error)'
                                        }}>
                                            {getStatusIcon(approval.status)}
                                            {approval.status}
                                        </span>
                                    </td>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                        {new Date(approval.created_at).toLocaleDateString()}
                                    </td>
                                </tr>
                            ))}
                            {(!approvals?.results || approvals.results.length === 0) && (
                                <tr>
                                    <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        No approval history found.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                <h2 style={{ fontSize: 'var(--text-lg)', margin: '2rem 0 1rem' }}>Activity Log</h2>
                <div className="card">
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>ACTION</th>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>USER</th>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>COMMENT</th>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>DATE</th>
                            </tr>
                        </thead>
                        <tbody>
                            {logs?.results?.slice(0, 20).map((log: any) => (
                                <tr key={log.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <td style={{ padding: '1rem' }}>
                                        <span style={{
                                            padding: '0.2rem 0.5rem', borderRadius: '0.25rem', fontSize: 'var(--text-xs)',
                                            background: log.action === 'Approve' ? 'rgba(34, 197, 94, 0.15)' : log.action === 'Reject' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(36, 113, 163, 0.15)',
                                            color: log.action === 'Approve' ? 'var(--color-success)' : log.action === 'Reject' ? 'var(--color-error)' : 'var(--color-primary)'
                                        }}>
                                            {log.action}
                                        </span>
                                    </td>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)' }}>{log.user_name || 'System'}</td>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{log.comment || '-'}</td>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                        {new Date(log.created_at).toLocaleString()}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </main>
        </div>
    );
};

export default ApprovalHistory;
