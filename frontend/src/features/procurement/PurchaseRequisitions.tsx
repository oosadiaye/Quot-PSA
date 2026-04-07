import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, CheckCircle, XCircle, ArrowRight, Search, FileText, Send } from 'lucide-react';
import { usePurchaseRequests, useApprovePR, useRejectPR } from './hooks/useProcurement';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from '../accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import PageHeader from '../../components/PageHeader';
import '../accounting/styles/glassmorphism.css';

export default function PurchaseRequisitions() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 20;
    const [confirmAction, setConfirmAction] = useState<{ id: number; action: string } | null>(null);

    const { data: requests, isLoading } = usePurchaseRequests({ status: statusFilter, search: searchTerm || undefined, page: currentPage, page_size: pageSize });
    const approveMutation = useApprovePR();
    const rejectMutation = useRejectPR();

    const requestsList = requests?.results || requests || [];
    const totalCount = requests?.count || (Array.isArray(requests) ? requests.length : 0);
    const totalPages = Math.ceil(totalCount / pageSize);

    const handleConfirmedAction = (id: number, action: string) => {
        if (action === 'approve') approveMutation.mutate(id);
        else if (action === 'reject') rejectMutation.mutate(id);
        setConfirmAction(null);
    };

    const getStatusBadge = (status: string) => {
        const colors: Record<string, string> = {
            'Draft': 'rgba(156, 163, 175, 0.1)',
            'Pending': 'rgba(251, 191, 36, 0.1)',
            'Approved': 'rgba(36, 113, 163, 0.1)',
            'Rejected': 'rgba(239, 68, 68, 0.1)',
        };
        const textColors: Record<string, string> = {
            'Draft': '#9ca3af',
            'Pending': '#fbbf24',
            'Approved': '#2471a3',
            'Rejected': '#ef4444',
        };
        return (
            <span style={{
                display: 'inline-block',
                padding: '0.25rem 0.75rem',
                borderRadius: '9999px',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                background: colors[status] || 'rgba(156, 163, 175, 0.1)',
                color: textColors[status] || '#9ca3af',
            }}>
                {status}
            </span>
        );
    };

    if (isLoading) {
        return (
            <AccountingLayout>
                <LoadingScreen message="Loading purchase requisitions..." />
            </AccountingLayout>
        );
    }

    return (
        <AccountingLayout>
            <PageHeader
                title="Purchase Requisitions"
                subtitle="Manage purchase requisitions and approval workflow"
                icon={<FileText size={22} />}
                actions={
                    <button
                        onClick={() => navigate('/procurement/requisitions/new')}
                        className="glass-button"
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            padding: '0.75rem 1.5rem',
                            background: 'rgba(255,255,255,0.18)',
                            color: 'white',
                            border: '1px solid rgba(255,255,255,0.25)',
                            borderRadius: '8px',
                            cursor: 'pointer',
                            fontWeight: 500,
                        }}
                    >
                        <Plus size={20} />
                        New Requisition
                    </button>
                }
            />

            <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem' }}>
                    <div style={{ position: 'relative' }}>
                        <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} size={20} />
                        <input
                            type="text"
                            placeholder="Search by PR number or description..."
                            value={searchTerm}
                            onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                            style={{
                                width: '100%',
                                paddingLeft: '2.75rem',
                                paddingRight: '1rem',
                                paddingTop: '0.75rem',
                                paddingBottom: '0.75rem',
                                borderRadius: '8px',
                                border: '1px solid var(--color-border)',
                                background: 'var(--color-surface)',
                                color: 'var(--color-text)',
                                fontSize: 'var(--text-sm)',
                            }}
                        />
                    </div>
                    <select
                        value={statusFilter}
                        onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1); }}
                        style={{
                            padding: '0.75rem 1rem',
                            borderRadius: '8px',
                            border: '1px solid var(--color-border)',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                        }}
                    >
                        <option value="">All Status</option>
                        <option value="Draft">Draft</option>
                        <option value="Pending">Pending</option>
                        <option value="Approved">Approved</option>
                        <option value="Rejected">Rejected</option>
                    </select>
                </div>
            </div>

            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>PR Number</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Description</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Priority</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Date</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Est. Total</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Status</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {requestsList.length > 0 ? (
                                requestsList.map((req: any, index: number) => {
                                    const estTotal = req.lines?.reduce((sum: number, l: any) => sum + Number(l.quantity || 0) * Number(l.estimated_unit_price || 0), 0) || 0;
                                    return (
                                        <tr
                                            key={req.id}
                                            style={{
                                                borderBottom: '1px solid var(--color-border)',
                                                animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                            }}
                                        >
                                            <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)', fontWeight: 500 }}>
                                                {req.request_number}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)' }}>
                                                {req.description}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                {req.priority || '\u2014'}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                {new Date(req.requested_date).toLocaleDateString()}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 500, color: 'var(--color-text)' }}>
                                                {formatCurrency(estTotal)}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                                {getStatusBadge(req.status)}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem' }}>
                                                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                    {confirmAction?.id === req.id && (
                                                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                                            <span style={{ fontSize: '0.85rem', color: '#dc2626' }}>Confirm?</span>
                                                            <button onClick={() => handleConfirmedAction(req.id, confirmAction.action)}
                                                                style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer' }}>Yes</button>
                                                            <button onClick={() => setConfirmAction(null)}
                                                                style={{ background: '#e2e8f0', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer' }}>No</button>
                                                        </div>
                                                    )}
                                                    {confirmAction?.id !== req.id && req.status === 'Pending' && (
                                                        <>
                                                            <button
                                                                onClick={() => setConfirmAction({ id: req.id, action: 'approve' })}
                                                                style={{
                                                                    padding: '0.375rem 0.75rem',
                                                                    borderRadius: '6px',
                                                                    border: 'none',
                                                                    background: 'rgba(34, 197, 94, 0.1)',
                                                                    color: '#22c55e',
                                                                    cursor: 'pointer',
                                                                    fontSize: 'var(--text-xs)',
                                                                    fontWeight: 600,
                                                                    display: 'inline-flex',
                                                                    alignItems: 'center',
                                                                    gap: '0.25rem',
                                                                }}
                                                                title="Approve"
                                                            >
                                                                <CheckCircle size={14} />
                                                                Approve
                                                            </button>
                                                            <button
                                                                onClick={() => setConfirmAction({ id: req.id, action: 'reject' })}
                                                                style={{
                                                                    padding: '0.375rem 0.75rem',
                                                                    borderRadius: '6px',
                                                                    border: 'none',
                                                                    background: 'rgba(239, 68, 68, 0.1)',
                                                                    color: '#ef4444',
                                                                    cursor: 'pointer',
                                                                    fontSize: 'var(--text-xs)',
                                                                    fontWeight: 600,
                                                                    display: 'inline-flex',
                                                                    alignItems: 'center',
                                                                    gap: '0.25rem',
                                                                }}
                                                                title="Reject"
                                                            >
                                                                <XCircle size={14} />
                                                                Reject
                                                            </button>
                                                        </>
                                                    )}
                                                    {confirmAction?.id !== req.id && req.status === 'Approved' && (
                                                        <button
                                                            onClick={() => navigate(`/procurement/requisitions/${req.id}/convert`)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                borderRadius: '6px',
                                                                border: 'none',
                                                                background: 'rgba(36, 113, 163, 0.1)',
                                                                color: '#2471a3',
                                                                cursor: 'pointer',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '0.25rem',
                                                            }}
                                                            title="Convert to PO"
                                                        >
                                                            <ArrowRight size={14} />
                                                            Convert to PO
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={() => navigate(`/procurement/requisitions/${req.id}`)}
                                                        style={{
                                                            padding: '0.375rem 0.75rem',
                                                            background: 'transparent',
                                                            color: 'var(--color-text-muted)',
                                                            border: '1px solid var(--color-border)',
                                                            borderRadius: '6px',
                                                            fontSize: 'var(--text-xs)',
                                                            fontWeight: 600,
                                                            cursor: 'pointer',
                                                            display: 'inline-flex',
                                                            alignItems: 'center',
                                                            gap: '0.25rem',
                                                        }}
                                                    >
                                                        <FileText size={14} />
                                                        View
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })
                            ) : (
                                <tr>
                                    <td colSpan={7} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <FileText size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block' }} />
                                        <p>No purchase requisitions found</p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {totalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem', alignItems: 'center' }}>
                    <button className="btn btn-outline" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>Previous</button>
                    <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Page {currentPage} of {totalPages}</span>
                    <button className="btn btn-outline" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>Next</button>
                </div>
            )}
        </AccountingLayout>
    );
}
