import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, CheckCircle, Search, Package, FileText, XCircle, Trash2 } from 'lucide-react';
import { useGRNs, usePostGRN, useCancelGRN, useBulkCancelGRN } from './hooks/useProcurement';
import AccountingLayout from '../accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import '../accounting/styles/glassmorphism.css';

export default function GoodsReceivedNotes() {
    const navigate = useNavigate();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [selectedIds, setSelectedIds] = useState<number[]>([]);
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 20;
    const [confirmAction, setConfirmAction] = useState<{ id: number; action: string } | null>(null);

    const { data: grns, isLoading } = useGRNs({ status: statusFilter, search: searchTerm || undefined, page: currentPage, page_size: pageSize });
    const postMutation = usePostGRN();
    const cancelMutation = useCancelGRN();
    const bulkCancelMutation = useBulkCancelGRN();

    const grnsList = grns?.results || grns || [];
    const totalCount = grns?.count || (Array.isArray(grns) ? grns.length : 0);
    const totalPages = Math.ceil(totalCount / pageSize);

    const cancellableGRNs = Array.isArray(grnsList) ? grnsList.filter((grn: any) => grn.status !== 'Cancelled') : [];

    const handleConfirmedAction = (id: number, action: string) => {
        if (action === 'post') {
            postMutation.mutate(id);
        } else if (action === 'cancel') {
            cancelMutation.mutate(id, {
                onSuccess: () => setSelectedIds(prev => prev.filter(i => i !== id)),
            });
        }
        setConfirmAction(null);
    };

    const [confirmBulk, setConfirmBulk] = useState(false);

    const handleBulkCancel = () => {
        if (selectedIds.length === 0) return;
        bulkCancelMutation.mutate(selectedIds, {
            onSuccess: () => { setSelectedIds([]); setConfirmBulk(false); },
        });
    };

    const toggleSelect = (id: number) => {
        setSelectedIds(prev =>
            prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
        );
    };

    const toggleSelectAll = () => {
        if (selectedIds.length === cancellableGRNs.length) {
            setSelectedIds([]);
        } else {
            setSelectedIds(cancellableGRNs.map((g: any) => g.id));
        }
    };

    const getStatusBadge = (status: string) => {
        const colors: any = {
            'Draft': 'rgba(156, 163, 175, 0.1)',
            'Received': 'rgba(36, 113, 163, 0.1)',
            'Posted': 'rgba(34, 197, 94, 0.1)',
            'Cancelled': 'rgba(239, 68, 68, 0.1)',
        };
        const textColors: any = {
            'Draft': '#9ca3af',
            'Received': '#2471a3',
            'Posted': '#22c55e',
            'Cancelled': '#ef4444',
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

    if (isLoading) return <LoadingScreen message="Loading GRNs..." />;

    return (
        <AccountingLayout>
            <div style={{ padding: '1.5rem' }}>
                <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Goods Received Notes
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                            Track incoming goods from vendors
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                        {selectedIds.length > 0 && !confirmBulk && (
                            <button
                                onClick={() => setConfirmBulk(true)}
                                disabled={bulkCancelMutation.isPending}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    padding: '0.625rem 1.25rem',
                                    background: 'rgba(239, 68, 68, 0.1)',
                                    color: '#ef4444',
                                    border: '1px solid rgba(239, 68, 68, 0.3)',
                                    borderRadius: '8px',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    fontSize: 'var(--text-sm)',
                                }}
                            >
                                <Trash2 size={18} />
                                {bulkCancelMutation.isPending ? 'Cancelling...' : `Cancel Selected (${selectedIds.length})`}
                            </button>
                        )}
                        {confirmBulk && selectedIds.length > 0 && (
                            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                <span style={{ fontSize: '0.85rem', color: '#dc2626' }}>Cancel {selectedIds.length} GRN(s)?</span>
                                <button onClick={handleBulkCancel}
                                    style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '4px', padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>Yes</button>
                                <button onClick={() => setConfirmBulk(false)}
                                    style={{ background: '#e2e8f0', border: 'none', borderRadius: '4px', padding: '4px 12px', cursor: 'pointer' }}>No</button>
                            </div>
                        )}
                        <button
                            onClick={() => navigate('/procurement/grn/new')}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                padding: '0.625rem 1.25rem',
                                background: 'var(--color-primary)',
                                color: 'white',
                                border: 'none',
                                borderRadius: '8px',
                                fontWeight: 600,
                                cursor: 'pointer',
                            }}
                        >
                            <Plus size={18} />
                            New GRN
                        </button>
                    </div>
                </div>

                <div style={{
                    display: 'flex',
                    gap: '1rem',
                    marginBottom: '1.5rem',
                    flexWrap: 'wrap',
                }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search GRNs..."
                            value={searchTerm}
                            onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                            style={{
                                width: '100%',
                                padding: '0.625rem 0.75rem 0.625rem 2.5rem',
                                border: '1px solid var(--color-border)',
                                borderRadius: '8px',
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
                            padding: '0.625rem 1rem',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                            minWidth: '150px',
                        }}
                    >
                        <option value="">All Status</option>
                        <option value="Draft">Draft</option>
                        <option value="Received">Received</option>
                        <option value="Posted">Posted</option>
                        <option value="Cancelled">Cancelled</option>
                    </select>
                </div>

                <div style={{
                    background: 'var(--color-surface)',
                    borderRadius: '12px',
                    border: '1px solid var(--color-border)',
                    overflow: 'hidden',
                }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', width: '40px' }}>
                                    <input
                                        type="checkbox"
                                        checked={cancellableGRNs.length > 0 && selectedIds.length === cancellableGRNs.length}
                                        onChange={toggleSelectAll}
                                        style={{ cursor: 'pointer' }}
                                    />
                                </th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>GRN Number</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>PO Number</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Received Date</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Received By</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {grnsList.length === 0 ? (
                                <tr>
                                    <td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Package size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No GRNs found</p>
                                    </td>
                                </tr>
                            ) : (
                                grnsList.map((grn: any) => (
                                    <tr key={grn.id} style={{
                                        borderBottom: '1px solid var(--color-border)',
                                        background: selectedIds.includes(grn.id) ? 'rgba(36, 113, 163, 0.05)' : 'transparent',
                                    }}>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            {grn.status !== 'Cancelled' ? (
                                                <input
                                                    type="checkbox"
                                                    checked={selectedIds.includes(grn.id)}
                                                    onChange={() => toggleSelect(grn.id)}
                                                    style={{ cursor: 'pointer' }}
                                                />
                                            ) : null}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{grn.grn_number}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{grn.po_number}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{new Date(grn.received_date).toLocaleDateString()}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{grn.received_by}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{getStatusBadge(grn.status)}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            {confirmAction?.id === grn.id && (
                                                <div style={{ display: 'inline-flex', gap: '0.5rem', alignItems: 'center', marginRight: '0.5rem' }}>
                                                    <span style={{ fontSize: '0.85rem', color: '#dc2626' }}>Confirm?</span>
                                                    <button onClick={() => handleConfirmedAction(grn.id, confirmAction.action)}
                                                        style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer' }}>Yes</button>
                                                    <button onClick={() => setConfirmAction(null)}
                                                        style={{ background: '#e2e8f0', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer' }}>No</button>
                                                </div>
                                            )}
                                            {confirmAction?.id !== grn.id && ['Draft', 'Received', 'On Hold'].includes(grn.status) && (
                                                <button
                                                    onClick={() => setConfirmAction({ id: grn.id, action: 'post' })}
                                                    style={{
                                                        padding: '0.375rem 0.75rem',
                                                        background: 'rgba(34, 197, 94, 0.1)',
                                                        color: '#22c55e',
                                                        border: 'none',
                                                        borderRadius: '6px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 600,
                                                        cursor: 'pointer',
                                                        display: 'inline-flex',
                                                        alignItems: 'center',
                                                        gap: '0.25rem',
                                                    }}
                                                >
                                                    <CheckCircle size={14} />
                                                    Post
                                                </button>
                                            )}
                                            {confirmAction?.id !== grn.id && grn.status !== 'Cancelled' && (
                                                <button
                                                    onClick={() => setConfirmAction({ id: grn.id, action: 'cancel' })}
                                                    disabled={cancelMutation.isPending}
                                                    style={{
                                                        padding: '0.375rem 0.75rem',
                                                        background: 'rgba(239, 68, 68, 0.1)',
                                                        color: '#ef4444',
                                                        border: 'none',
                                                        borderRadius: '6px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 600,
                                                        cursor: 'pointer',
                                                        display: 'inline-flex',
                                                        alignItems: 'center',
                                                        gap: '0.25rem',
                                                        marginLeft: '0.5rem',
                                                    }}
                                                >
                                                    <XCircle size={14} />
                                                    Cancel
                                                </button>
                                            )}
                                            <button
                                                onClick={() => navigate(`/procurement/grn/${grn.id}`)}
                                                style={{
                                                    padding: '0.375rem 0.75rem',
                                                    background: 'transparent',
                                                    color: 'var(--color-text-muted)',
                                                    border: '1px solid var(--color-border)',
                                                    borderRadius: '6px',
                                                    fontSize: 'var(--text-xs)',
                                                    fontWeight: 600,
                                                    cursor: 'pointer',
                                                    marginLeft: '0.5rem',
                                                }}
                                            >
                                                <FileText size={14} />
                                                View
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
                {totalPages > 1 && (
                    <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem', alignItems: 'center' }}>
                        <button className="btn btn-outline" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>Previous</button>
                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Page {currentPage} of {totalPages}</span>
                        <button className="btn btn-outline" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>Next</button>
                    </div>
                )}
            </div>
        </AccountingLayout>
    );
}
