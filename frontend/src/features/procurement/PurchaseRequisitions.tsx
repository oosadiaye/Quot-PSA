import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, CheckCircle, XCircle, ArrowRight, Search, FileText, Send, Pencil, Trash2, CheckSquare } from 'lucide-react';
import { usePurchaseRequests, useApprovePR, useRejectPR, useBulkApprovePR, useBulkDeletePR } from './hooks/useProcurement';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from '../accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import PageHeader from '../../components/PageHeader';
import '../accounting/styles/glassmorphism.css';

interface BulkResult {
    type: 'approve' | 'delete';
    approved?: { id: number; number: string }[];
    deleted?: { id: number; number: string }[];
    skipped?: { id: number; number: string; reason: string }[];
    errors?: { id: number; number: string; reason: string }[];
}

export default function PurchaseRequisitions() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 20;
    const [confirmAction, setConfirmAction] = useState<{ id: number; action: string } | null>(null);

    // Bulk selection state
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [bulkConfirm, setBulkConfirm] = useState<'delete' | null>(null);
    const [bulkResult, setBulkResult] = useState<BulkResult | null>(null);

    const { data: requests, isLoading } = usePurchaseRequests({ status: statusFilter, search: searchTerm || undefined, page: currentPage, page_size: pageSize });
    const approveMutation = useApprovePR();
    const rejectMutation = useRejectPR();
    const bulkApproveMutation = useBulkApprovePR();
    const bulkDeleteMutation = useBulkDeletePR();

    const requestsList: any[] = requests?.results || requests || [];
    const totalCount = requests?.count || (Array.isArray(requests) ? requests.length : 0);
    const totalPages = Math.ceil(totalCount / pageSize);

    // Derived selection info
    const allVisibleIds = requestsList.map((r: any) => r.id as number);
    const allSelected = allVisibleIds.length > 0 && allVisibleIds.every(id => selectedIds.has(id));
    const someSelected = selectedIds.size > 0;
    const selectedList = requestsList.filter((r: any) => selectedIds.has(r.id));
    const canBulkApprove = selectedList.some((r: any) => r.status === 'Pending' || r.status === 'Draft');
    const canBulkDelete = selectedList.some((r: any) => r.status === 'Draft' || r.status === 'Rejected');
    const canEdit = selectedIds.size === 1 && selectedList[0]?.status === 'Draft';

    const toggleRow = (id: number) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    const toggleAll = () => {
        if (allSelected) {
            setSelectedIds(prev => {
                const next = new Set(prev);
                allVisibleIds.forEach(id => next.delete(id));
                return next;
            });
        } else {
            setSelectedIds(prev => new Set([...prev, ...allVisibleIds]));
        }
    };

    const clearSelection = () => setSelectedIds(new Set());

    const handleConfirmedAction = (id: number, action: string) => {
        if (action === 'approve') approveMutation.mutate(id);
        else if (action === 'reject') rejectMutation.mutate(id);
        setConfirmAction(null);
    };

    const handleBulkApprove = async () => {
        const ids = selectedList.filter((r: any) => r.status === 'Pending' || r.status === 'Draft').map((r: any) => r.id);
        if (!ids.length) return;
        const result = await bulkApproveMutation.mutateAsync(ids);
        setBulkResult({ type: 'approve', ...result });
        clearSelection();
    };

    const handleBulkDelete = async () => {
        const ids = selectedList.filter((r: any) => r.status === 'Draft' || r.status === 'Rejected').map((r: any) => r.id);
        if (!ids.length) return;
        const result = await bulkDeleteMutation.mutateAsync(ids);
        setBulkResult({ type: 'delete', ...result });
        setBulkConfirm(null);
        clearSelection();
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

            {/* Bulk result feedback */}
            {bulkResult && (
                <div style={{
                    padding: '0.875rem 1.25rem',
                    borderRadius: '8px',
                    marginBottom: '1rem',
                    background: (bulkResult.errors?.length || 0) > 0 ? 'rgba(239,68,68,0.08)' : 'rgba(34,197,94,0.08)',
                    border: `1px solid ${(bulkResult.errors?.length || 0) > 0 ? 'rgba(239,68,68,0.25)' : 'rgba(34,197,94,0.25)'}`,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.75rem',
                }}>
                    <div style={{ flex: 1, fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                        {bulkResult.type === 'approve' && (
                            <>
                                {(bulkResult.approved?.length || 0) > 0 && <div style={{ color: '#16a34a', fontWeight: 600 }}>✓ Approved: {bulkResult.approved!.map(r => r.number).join(', ')}</div>}
                                {(bulkResult.skipped?.length || 0) > 0 && <div style={{ color: '#92400e', marginTop: '0.25rem' }}>Skipped: {bulkResult.skipped!.map(r => `${r.number} (${r.reason})`).join(', ')}</div>}
                                {(bulkResult.errors?.length || 0) > 0 && <div style={{ color: '#dc2626', marginTop: '0.25rem' }}>Failed: {bulkResult.errors!.map(r => `${r.number}: ${r.reason}`).join('; ')}</div>}
                            </>
                        )}
                        {bulkResult.type === 'delete' && (
                            <>
                                {(bulkResult.deleted?.length || 0) > 0 && <div style={{ color: '#16a34a', fontWeight: 600 }}>✓ Deleted: {bulkResult.deleted!.map(r => r.number).join(', ')}</div>}
                                {(bulkResult.skipped?.length || 0) > 0 && <div style={{ color: '#92400e', marginTop: '0.25rem' }}>Skipped: {bulkResult.skipped!.map(r => `${r.number} (${r.reason})`).join(', ')}</div>}
                            </>
                        )}
                    </div>
                    <button onClick={() => setBulkResult(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', fontSize: '1.1rem', lineHeight: 1 }}>×</button>
                </div>
            )}

            {/* Delete confirmation modal */}
            {bulkConfirm === 'delete' && (
                <div style={{
                    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                    <div style={{
                        background: 'var(--color-surface)', borderRadius: '12px', padding: '2rem',
                        width: 'min(400px, 90vw)', boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
                    }}>
                        <h3 style={{ marginBottom: '0.75rem', color: 'var(--color-text)', fontWeight: 700 }}>Delete Requisitions</h3>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1.5rem' }}>
                            Delete {selectedList.filter((r: any) => r.status === 'Draft' || r.status === 'Rejected').length} requisition(s)?
                            Only Draft and Rejected PRs will be deleted. This cannot be undone.
                        </p>
                        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                            <button onClick={() => setBulkConfirm(null)}
                                style={{ padding: '0.5rem 1.25rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'transparent', color: 'var(--color-text)', cursor: 'pointer', fontWeight: 600 }}>
                                Cancel
                            </button>
                            <button onClick={handleBulkDelete} disabled={bulkDeleteMutation.isPending}
                                style={{ padding: '0.5rem 1.25rem', borderRadius: '6px', border: 'none', background: '#dc2626', color: 'white', cursor: 'pointer', fontWeight: 600 }}>
                                {bulkDeleteMutation.isPending ? 'Deleting…' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

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

            {/* Bulk action bar */}
            {someSelected && (
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.75rem 1.25rem',
                    marginBottom: '0.75rem',
                    background: 'rgba(79,70,229,0.07)',
                    border: '1px solid rgba(79,70,229,0.2)',
                    borderRadius: '8px',
                    flexWrap: 'wrap',
                }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <CheckSquare size={16} style={{ color: '#4f46e5' }} />
                        {selectedIds.size} selected
                    </span>
                    <div style={{ flex: 1 }} />

                    {/* Approve */}
                    <button
                        onClick={handleBulkApprove}
                        disabled={!canBulkApprove || bulkApproveMutation.isPending}
                        title={!canBulkApprove ? 'Select Pending PRs to approve' : undefined}
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                            padding: '0.4rem 1rem', borderRadius: '6px', border: 'none',
                            background: canBulkApprove ? 'rgba(34,197,94,0.12)' : 'rgba(156,163,175,0.08)',
                            color: canBulkApprove ? '#16a34a' : '#9ca3af',
                            cursor: canBulkApprove ? 'pointer' : 'not-allowed',
                            fontWeight: 600, fontSize: 'var(--text-sm)',
                        }}
                    >
                        <CheckCircle size={15} />
                        {bulkApproveMutation.isPending ? 'Approving…' : 'Approve'}
                    </button>

                    {/* Edit — single Draft only */}
                    <button
                        onClick={() => canEdit && navigate(`/procurement/requisitions/${selectedList[0].id}/edit`)}
                        disabled={!canEdit}
                        title={!canEdit ? (selectedIds.size > 1 ? 'Select a single Draft PR to edit' : 'Only Draft PRs can be edited') : undefined}
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                            padding: '0.4rem 1rem', borderRadius: '6px', border: 'none',
                            background: canEdit ? 'rgba(59,130,246,0.1)' : 'rgba(156,163,175,0.08)',
                            color: canEdit ? '#2563eb' : '#9ca3af',
                            cursor: canEdit ? 'pointer' : 'not-allowed',
                            fontWeight: 600, fontSize: 'var(--text-sm)',
                        }}
                    >
                        <Pencil size={15} />
                        Edit
                    </button>

                    {/* Delete */}
                    <button
                        onClick={() => canBulkDelete && setBulkConfirm('delete')}
                        disabled={!canBulkDelete}
                        title={!canBulkDelete ? 'Select Draft or Rejected PRs to delete' : undefined}
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                            padding: '0.4rem 1rem', borderRadius: '6px', border: 'none',
                            background: canBulkDelete ? 'rgba(239,68,68,0.1)' : 'rgba(156,163,175,0.08)',
                            color: canBulkDelete ? '#dc2626' : '#9ca3af',
                            cursor: canBulkDelete ? 'pointer' : 'not-allowed',
                            fontWeight: 600, fontSize: 'var(--text-sm)',
                        }}
                    >
                        <Trash2 size={15} />
                        Delete
                    </button>

                    <button onClick={clearSelection} style={{
                        background: 'none', border: 'none', color: 'var(--color-text-muted)',
                        cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 500, padding: '0.4rem 0.5rem',
                    }}>
                        Clear
                    </button>
                </div>
            )}

            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '1rem 1rem 1rem 1.5rem', width: 40 }}>
                                    <input
                                        type="checkbox"
                                        checked={allSelected}
                                        ref={el => { if (el) el.indeterminate = !allSelected && someSelected && allVisibleIds.some(id => selectedIds.has(id)); }}
                                        onChange={toggleAll}
                                        style={{ cursor: 'pointer', width: 16, height: 16 }}
                                        aria-label="Select all"
                                    />
                                </th>
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
                                    const isSelected = selectedIds.has(req.id);
                                    return (
                                        <tr
                                            key={req.id}
                                            style={{
                                                borderBottom: '1px solid var(--color-border)',
                                                background: isSelected ? 'rgba(79,70,229,0.04)' : undefined,
                                                animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                            }}
                                        >
                                            <td style={{ padding: '1rem 1rem 1rem 1.5rem' }}>
                                                <input
                                                    type="checkbox"
                                                    checked={isSelected}
                                                    onChange={() => toggleRow(req.id)}
                                                    style={{ cursor: 'pointer', width: 16, height: 16 }}
                                                    aria-label={`Select ${req.request_number}`}
                                                />
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)', fontWeight: 500 }}>
                                                {req.request_number}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)' }}>
                                                {req.description}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                {req.priority || '—'}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                {new Date(req.requested_date).toLocaleDateString('en-GB')}
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
                                                    {confirmAction?.id !== req.id && (req.status === 'Pending' || req.status === 'Draft') && (
                                                        <>
                                                            <button
                                                                onClick={() => setConfirmAction({ id: req.id, action: 'approve' })}
                                                                style={{
                                                                    padding: '0.375rem 0.75rem', borderRadius: '6px', border: 'none',
                                                                    background: 'rgba(34,197,94,0.1)', color: '#22c55e',
                                                                    cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                                    display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                                }}
                                                                title="Approve"
                                                            >
                                                                <CheckCircle size={14} />
                                                                Approve
                                                            </button>
                                                            <button
                                                                onClick={() => setConfirmAction({ id: req.id, action: 'reject' })}
                                                                style={{
                                                                    padding: '0.375rem 0.75rem', borderRadius: '6px', border: 'none',
                                                                    background: 'rgba(239,68,68,0.1)', color: '#ef4444',
                                                                    cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                                    display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                                }}
                                                                title="Reject"
                                                            >
                                                                <XCircle size={14} />
                                                                Reject
                                                            </button>
                                                        </>
                                                    )}
                                                    {confirmAction?.id !== req.id && req.status === 'Draft' && (
                                                        <button
                                                            onClick={() => navigate(`/procurement/requisitions/${req.id}/edit`)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem', borderRadius: '6px', border: 'none',
                                                                background: 'rgba(59,130,246,0.1)', color: '#2563eb',
                                                                cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                                display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                            }}
                                                            title="Edit"
                                                        >
                                                            <Pencil size={14} />
                                                            Edit
                                                        </button>
                                                    )}
                                                    {confirmAction?.id !== req.id && req.status === 'Approved' && !req.active_po_id && (
                                                        <button
                                                            onClick={() => navigate(`/procurement/requisitions/${req.id}/convert`)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem', borderRadius: '6px', border: 'none',
                                                                background: 'rgba(36,113,163,0.1)', color: '#2471a3',
                                                                cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                                display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                            }}
                                                            title="Convert to PO"
                                                        >
                                                            <ArrowRight size={14} />
                                                            Convert to PO
                                                        </button>
                                                    )}
                                                    {confirmAction?.id !== req.id && req.active_po_id && (
                                                        <button
                                                            onClick={() => navigate(`/procurement/orders/${req.active_po_id}`)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem', borderRadius: '6px',
                                                                border: '1px solid rgba(22,163,74,0.3)', background: 'rgba(22,163,74,0.08)',
                                                                color: '#15803d', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                                display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                            }}
                                                            title={`Already converted to ${req.active_po_number} (${req.active_po_status})`}
                                                        >
                                                            View {req.active_po_number}
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
                                    <td colSpan={8} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
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
