import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, ShoppingCart, Send, CheckCircle, XCircle, FileText, Lock, Package, AlertCircle } from 'lucide-react';
import { usePurchaseOrders, usePostPO, useSubmitPOForApproval, useApprovePO, useRejectPO, useClosePO } from './hooks/useProcurement';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from '../accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import PageHeader from '../../components/PageHeader';
import '../accounting/styles/glassmorphism.css';

/** Pull the best human-readable message out of the backend's
 * standard error envelope: { error, detail, code, budget_violations? }
 * falling back through the possibilities so nothing the server sends
 * gets silently dropped. */
function extractActionError(err: any): { headline: string; detail: string; code?: string; violations?: any[] } {
    const data = err?.response?.data || {};
    const headline =
        data.error
        || data.detail
        || data.message
        || data.non_field_errors?.[0]
        || err?.message
        || 'Action failed. Please try again.';
    const detail = data.detail && data.detail !== headline ? data.detail : '';
    return {
        headline: typeof headline === 'string' ? headline : JSON.stringify(headline),
        detail:   typeof detail   === 'string' ? detail   : '',
        code: data.code,
        violations: data.budget_violations,
    };
}

export default function PurchaseOrderList() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 20;
    const [confirmAction, setConfirmAction] = useState<{ id: number; action: string } | null>(null);

    const { data: orders, isLoading } = usePurchaseOrders({ status: statusFilter, search: searchTerm || undefined, page: currentPage, page_size: pageSize });
    const postMutation = usePostPO();
    const submitMutation = useSubmitPOForApproval();
    const approveMutation = useApprovePO();
    const rejectMutation = useRejectPO();
    const closeMutation = useClosePO();

    const ordersList = orders?.results || orders || [];
    const totalCount = orders?.count || (Array.isArray(orders) ? orders.length : 0);
    const totalPages = Math.ceil(totalCount / pageSize);

    // Structured error surface — when any PO action returns a 400 with
    // a reason (budget block, duplicate, period closed, status
    // mismatch, etc.) we show that message instead of letting the UI
    // look broken.
    const [actionError, setActionError] = useState<{
        headline: string; detail: string; code?: string;
        violations?: Array<{ account?: string; account_name?: string; message?: string }>;
    } | null>(null);

    const handleConfirmedAction = (id: number, action: string) => {
        setActionError(null);
        const opts = {
            onError: (err: any) => setActionError(extractActionError(err)),
        };
        if (action === 'submit') submitMutation.mutate(id, opts);
        else if (action === 'approve') {
            // SAP-FB60-style "Approve & Post" — chain the two
            // mutations so a single click flips Pending → Approved
            // → Posted in one user gesture. The endpoints stay
            // separate on the backend so each remains individually
            // retryable: if post fails (warrant ceiling, missing
            // GL, period closed) the PO is left Approved and the
            // standalone Post button below picks up the retry.
            approveMutation.mutate(id, {
                onError: opts.onError,
                onSuccess: () => {
                    postMutation.mutate(id, opts);
                },
            });
        }
        else if (action === 'reject') rejectMutation.mutate(id, opts);
        else if (action === 'post') postMutation.mutate(id, opts);
        else if (action === 'close') closeMutation.mutate(id, opts);
        setConfirmAction(null);
    };

    const getStatusBadge = (status: string) => {
        const colors: Record<string, string> = {
            'Draft': 'rgba(156, 163, 175, 0.1)',
            'Pending': 'rgba(251, 191, 36, 0.1)',
            'Approved': 'rgba(36, 113, 163, 0.1)',
            'Posted': 'rgba(34, 197, 94, 0.1)',
            'Rejected': 'rgba(239, 68, 68, 0.1)',
            'Closed': 'rgba(107, 114, 128, 0.1)',
        };
        const textColors: Record<string, string> = {
            'Draft': '#9ca3af',
            'Pending': '#fbbf24',
            'Approved': '#2471a3',
            'Posted': '#22c55e',
            'Rejected': '#ef4444',
            'Closed': '#6b7280',
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
                <LoadingScreen message="Loading purchase orders..." />
            </AccountingLayout>
        );
    }

    return (
        <AccountingLayout>
            <PageHeader
                title="Purchase Orders"
                subtitle="Manage purchase orders and track vendor commitments"
                icon={<ShoppingCart size={22} />}
                actions={
                    <button
                        onClick={() => navigate('/procurement/orders/new')}
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
                        New Purchase Order
                    </button>
                }
            />

            {/* Action error banner — surfaces any 400 from submit / approve
                / reject / post / close so users know WHY a button didn't
                do what they expected. Sticks until dismissed so the user
                has time to read the full reason. */}
            {actionError && (
                <div
                    style={{
                        marginBottom: '1rem',
                        padding: '0.875rem 1rem',
                        borderRadius: '10px',
                        background: 'rgba(239, 68, 68, 0.08)',
                        border: '1px solid rgba(239, 68, 68, 0.25)',
                        color: '#b91c1c',
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '0.625rem',
                    }}
                    role="alert"
                >
                    <AlertCircle size={18} style={{ marginTop: 2, flexShrink: 0 }} />
                    <div style={{ flex: 1, fontSize: 'var(--text-sm)', lineHeight: 1.5 }}>
                        <div style={{ fontWeight: 700, marginBottom: 2 }}>
                            Action failed{actionError.code ? ` — ${actionError.code}` : ''}
                        </div>
                        <div>{actionError.headline}</div>
                        {actionError.violations && actionError.violations.length > 0 && (
                            <ul style={{ margin: '0.375rem 0 0', paddingLeft: '1.25rem', fontSize: 'var(--text-xs)' }}>
                                {actionError.violations.map((v, i) => (
                                    <li key={i} style={{ marginBottom: '0.125rem' }}>
                                        <b>{v.account}</b>{v.account_name ? ` — ${v.account_name}` : ''}: {v.message}
                                    </li>
                                ))}
                            </ul>
                        )}
                        {actionError.detail && (
                            <details style={{ marginTop: '0.375rem' }}>
                                <summary style={{ fontSize: 'var(--text-xs)', cursor: 'pointer', color: '#7f1d1d' }}>
                                    Technical detail
                                </summary>
                                <div style={{
                                    marginTop: '0.25rem',
                                    padding: '0.375rem 0.625rem',
                                    background: 'rgba(0,0,0,0.04)',
                                    borderRadius: 4,
                                    fontSize: '0.7rem',
                                    color: '#7f1d1d',
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                }}>
                                    {actionError.detail}
                                </div>
                            </details>
                        )}
                    </div>
                    <button
                        onClick={() => setActionError(null)}
                        style={{
                            background: 'transparent', border: 'none', color: '#b91c1c',
                            cursor: 'pointer', padding: '0 4px', fontSize: '1.25rem',
                            lineHeight: 1, fontWeight: 700,
                        }}
                        aria-label="Dismiss"
                    >
                        ×
                    </button>
                </div>
            )}

            <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem' }}>
                    <div style={{ position: 'relative' }}>
                        <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} size={20} />
                        <input
                            type="text"
                            placeholder="Search by PO number or vendor..."
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
                        <option value="Posted">Posted</option>
                        <option value="Rejected">Rejected</option>
                        <option value="Closed">Closed</option>
                    </select>
                </div>
            </div>

            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>PO Number</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Vendor</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Order Date</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Delivery Date</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Total Amount</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Status</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {ordersList.length > 0 ? (
                                ordersList.map((po: any, index: number) => (
                                    <tr
                                        key={po.id}
                                        style={{
                                            borderBottom: '1px solid var(--color-border)',
                                            animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                        }}
                                    >
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)', fontWeight: 500 }}>
                                            {po.po_number}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)' }}>
                                            {po.vendor_name}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                            {new Date(po.order_date).toLocaleDateString()}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                            {po.expected_delivery_date ? new Date(po.expected_delivery_date).toLocaleDateString() : '—'}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 500, color: 'var(--color-text)' }}>
                                            {formatCurrency(Number(po.total_amount || 0))}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                            {getStatusBadge(po.status)}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                {confirmAction?.id === po.id && (
                                                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                                        <span style={{ fontSize: '0.85rem', color: '#dc2626' }}>Confirm?</span>
                                                        <button onClick={() => handleConfirmedAction(po.id, confirmAction.action)}
                                                            style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer' }}>Yes</button>
                                                        <button onClick={() => setConfirmAction(null)}
                                                            style={{ background: '#e2e8f0', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer' }}>No</button>
                                                    </div>
                                                )}
                                                {confirmAction?.id !== po.id && po.status === 'Draft' && (
                                                    <button
                                                        onClick={() => setConfirmAction({ id: po.id, action: 'submit' })}
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
                                                        title="Submit for Approval"
                                                    >
                                                        <Send size={14} />
                                                        Submit
                                                    </button>
                                                )}
                                                {confirmAction?.id !== po.id && po.status === 'Pending' && (
                                                    <>
                                                        <button
                                                            onClick={() => setConfirmAction({ id: po.id, action: 'approve' })}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                borderRadius: '6px',
                                                                border: 'none',
                                                                background: 'rgba(34, 197, 94, 0.12)',
                                                                color: '#15803d',
                                                                cursor: 'pointer',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '0.25rem',
                                                            }}
                                                            title="Approve and post to GL in one step"
                                                        >
                                                            <CheckCircle size={14} />
                                                            Approve &amp; Post
                                                        </button>
                                                        <button
                                                            onClick={() => setConfirmAction({ id: po.id, action: 'reject' })}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                borderRadius: '6px',
                                                                border: 'none',
                                                                background: 'rgba(239, 68, 68, 0.1)',
                                                                color: '#dc2626',
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
                                                {confirmAction?.id !== po.id && po.status === 'Approved' && (
                                                    <button
                                                        onClick={() => setConfirmAction({ id: po.id, action: 'post' })}
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
                                                        title="Post Order"
                                                    >
                                                        <CheckCircle size={14} />
                                                        Post
                                                    </button>
                                                )}
                                                {confirmAction?.id !== po.id && ['Approved', 'Posted'].includes(po.status) && (
                                                    <>
                                                        {!po.has_active_grns && (
                                                        <button
                                                            onClick={() => navigate(`/procurement/grn/new?po=${po.id}`)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                borderRadius: '6px',
                                                                border: 'none',
                                                                background: 'rgba(59, 130, 246, 0.1)',
                                                                color: '#3b82f6',
                                                                cursor: 'pointer',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '0.25rem',
                                                            }}
                                                            title="Create GRN"
                                                        >
                                                            <Package size={14} />
                                                            Receive
                                                        </button>
                                                        )}
                                                        <button
                                                            onClick={() => setConfirmAction({ id: po.id, action: 'close' })}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                borderRadius: '6px',
                                                                border: 'none',
                                                                background: 'rgba(107, 114, 128, 0.1)',
                                                                color: '#6b7280',
                                                                cursor: 'pointer',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '0.25rem',
                                                            }}
                                                            title="Close Order"
                                                        >
                                                            <Lock size={14} />
                                                            Close
                                                        </button>
                                                    </>
                                                )}
                                                <button
                                                    onClick={() => navigate(`/procurement/orders/${po.id}`)}
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
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={7} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <ShoppingCart size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block' }} />
                                        <p>No purchase orders found</p>
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
