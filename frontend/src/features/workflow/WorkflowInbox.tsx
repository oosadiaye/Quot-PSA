import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import { CheckCircle, XCircle, Clock, FileText, User, DollarSign, ShoppingCart, Wallet, Inbox } from 'lucide-react';
import { useState } from 'react';

const WorkflowInbox = () => {
    const queryClient = useQueryClient();
    const [activeTab, setActiveTab] = useState('pending');
    
    const { data: pendingApprovals, isLoading: loadingPending } = useQuery({
        queryKey: ['approvals', 'pending'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approvals/', { params: { status: 'Pending' } });
            return data;
        }
    });

    const { data: myApprovals, isLoading: loadingMine } = useQuery({
        queryKey: ['approvals', 'my'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approvals/my_pending/');
            return data;
        }
    });

    const approveMutation = useMutation({
        mutationFn: async ({ id, comment }: { id: number; comment: string }) => {
            const { data } = await apiClient.post(`/workflow/approvals/${id}/approve/`, { comment });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approvals'] });
        }
    });

    const rejectMutation = useMutation({
        mutationFn: async ({ id, comment }: { id: number; comment: string }) => {
            const { data } = await apiClient.post(`/workflow/approvals/${id}/reject/`, { comment });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approvals'] });
        }
    });

    const { data: counts } = useQuery({
        queryKey: ['approvals', 'counts'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approvals/pending_count/');
            return data;
        }
    });

    const getIcon = (contentType: string) => {
        if (contentType?.includes('purchase')) return <ShoppingCart size={24} />;
        if (contentType?.includes('journal') || contentType?.includes('invoice')) return <Wallet size={24} />;
        return <FileText size={24} />;
    };

    const approvals = activeTab === 'pending' 
        ? (Array.isArray(pendingApprovals?.results) ? pendingApprovals.results : Array.isArray(pendingApprovals) ? pendingApprovals : [])
        : (Array.isArray(myApprovals?.results) ? myApprovals.results : Array.isArray(myApprovals) ? myApprovals : []);
    const isLoading = activeTab === 'pending' ? loadingPending : loadingMine;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Approval Inbox"
                    subtitle="Review and approve pending documents across all modules."
                    icon={<Inbox size={22} color="white" />}
                />

                <div style={{ display: 'flex', gap: '2rem', marginBottom: '2rem' }}>
                    <div className="card" role="button" tabIndex={0} aria-pressed={activeTab === 'pending'} aria-label="Pending Approvals" style={{ flex: 1, cursor: 'pointer', border: activeTab === 'pending' ? '2px solid var(--color-primary)' : 'none' }} onClick={() => setActiveTab('pending')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setActiveTab('pending'); }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.5rem', background: 'rgba(36, 113, 163, 0.15)' }}>
                                <Clock size={24} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>PENDING APPROVALS</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{counts?.count || 0}</div>
                            </div>
                        </div>
                    </div>
                    <div className="card" role="button" tabIndex={0} aria-pressed={activeTab === 'my'} aria-label="My Approvals" style={{ flex: 1, cursor: 'pointer', border: activeTab === 'my' ? '2px solid var(--color-primary)' : 'none' }} onClick={() => setActiveTab('my')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setActiveTab('my'); }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.5rem', background: 'rgba(34, 197, 94, 0.15)' }}>
                                <CheckCircle size={24} style={{ color: 'var(--color-success)' }} />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>MY APPROVALS</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{Array.isArray(myApprovals?.results) ? myApprovals.results.length : Array.isArray(myApprovals) ? myApprovals.length : 0}</div>
                            </div>
                        </div>
                    </div>
                </div>

                {isLoading ? (
                    <p style={{ color: 'var(--color-text-muted)' }}>Loading tasks...</p>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        {approvals?.length === 0 && (
                            <div className="card flex-center" style={{ height: '150px', color: 'var(--color-text-muted)' }}>
                                <CheckCircle size={32} style={{ marginBottom: '0.5rem', opacity: 0.3 }} />
                                <p>You're all caught up! No pending approvals.</p>
                            </div>
                        )}
                        {approvals?.map((approval: any) => (
                            <div key={approval.id} className="card animate-fade" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '2rem', alignItems: 'center' }}>
                                <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
                                    <div style={{ width: '48px', height: '48px', background: 'rgba(36, 113, 163, 0.15)', color: 'var(--color-primary)', borderRadius: '12px' }} className="flex-center">
                                        {getIcon(approval.content_type_name)}
                                    </div>
                                    <div>
                                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.25rem' }}>
                                            <span style={{ fontWeight: 700, fontSize: 'var(--text-lg)', color: 'var(--color-text)' }}>{approval.title}</span>
                                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{approval.content_type_name}</span>
                                        </div>
                                        <div style={{ display: 'flex', gap: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                                <Clock size={14} /> Step {approval.current_step} of {approval.total_steps}
                                            </span>
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                                <User size={14} /> {approval.requested_by_name}
                                            </span>
                                            {approval.amount && (
                                                <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                                    <DollarSign size={14} /> ${Number(approval.amount).toLocaleString()}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: '0.75rem' }}>
                                    <button
                                        className="btn btn-outline"
                                        style={{ color: 'var(--color-error)', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                                        onClick={() => rejectMutation.mutate({ id: approval.id, comment: 'Rejected from inbox' })}
                                    >
                                        <XCircle size={18} /> Reject
                                    </button>
                                    <button
                                        className="btn btn-primary"
                                        onClick={() => approveMutation.mutate({ id: approval.id, comment: 'Approved from inbox' })}
                                    >
                                        <CheckCircle size={18} /> Approve
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
};

export default WorkflowInbox;
