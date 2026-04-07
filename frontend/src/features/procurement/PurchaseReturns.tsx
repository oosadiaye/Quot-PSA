import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, FileText, CheckCircle, XCircle, Send, RotateCcw } from 'lucide-react';
import {
    usePurchaseReturns,
    useSubmitPurchaseReturn,
    useApprovePurchaseReturn,
    useCompletePurchaseReturn,
    useCancelPurchaseReturn,
} from './hooks/useProcurement';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from '../accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
    Draft:     { bg: 'rgba(156, 163, 175, 0.12)', text: '#9ca3af' },
    Pending:   { bg: 'rgba(251, 191, 36, 0.12)',  text: '#f59e0b' },
    Approved:  { bg: 'rgba(36, 113, 163, 0.12)',  text: '#2471a3' },
    Completed: { bg: 'rgba(34, 197, 94, 0.12)',   text: '#22c55e' },
    Cancelled: { bg: 'rgba(239, 68, 68, 0.12)',   text: '#ef4444' },
};

const StatusBadge = ({ status }: { status: string }) => {
    const { bg, text } = STATUS_COLORS[status] ?? { bg: 'rgba(156, 163, 175, 0.1)', text: '#9ca3af' };
    return (
        <span style={{
            display: 'inline-block',
            padding: '0.25rem 0.75rem',
            borderRadius: '9999px',
            fontSize: 'var(--text-xs)',
            fontWeight: 700,
            background: bg,
            color: text,
        }}>
            {status}
        </span>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// Action button
// ─────────────────────────────────────────────────────────────────────────────
const ActionBtn = ({
    label, color, bg, onClick, icon, loading,
}: {
    label: string; color: string; bg: string;
    onClick: () => void; icon?: React.ReactNode; loading?: boolean;
}) => (
    <button
        onClick={onClick}
        disabled={loading}
        style={{
            padding: '0.3rem 0.65rem',
            background: bg,
            color,
            border: 'none',
            borderRadius: '6px',
            fontSize: 'var(--text-xs)',
            fontWeight: 700,
            cursor: loading ? 'wait' : 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            opacity: loading ? 0.6 : 1,
        }}
    >
        {icon}
        {label}
    </button>
);

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────
export default function PurchaseReturns() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');

    const { data: purchaseReturns, isLoading } = usePurchaseReturns(
        statusFilter ? { status: statusFilter } : {},
    );

    const submitMutation    = useSubmitPurchaseReturn();
    const approveMutation   = useApprovePurchaseReturn();
    const completeMutation  = useCompletePurchaseReturn();
    const cancelMutation    = useCancelPurchaseReturn();

    const returnsList = purchaseReturns?.results || purchaseReturns || [];
    const filteredReturns = Array.isArray(returnsList)
        ? returnsList.filter((r: any) =>
            r.return_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            r.vendor_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            r.po_number?.toLowerCase().includes(searchTerm.toLowerCase()),
          )
        : [];

    if (isLoading) return <LoadingScreen message="Loading purchase returns..." />;

    return (
        <AccountingLayout>
            <div style={{ padding: '1.5rem' }}>

                {/* ── Header ──────────────────────────────────────────────── */}
                <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                    <div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Purchase Returns
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                            Manage goods returned to vendors
                        </p>
                    </div>
                    <button
                        onClick={() => navigate('/procurement/returns/new')}
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
                            fontSize: 'var(--text-sm)',
                        }}
                    >
                        <Plus size={16} />
                        New Return
                    </button>
                </div>

                {/* ── Filters ─────────────────────────────────────────────── */}
                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search
                            size={16}
                            style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }}
                        />
                        <input
                            type="text"
                            placeholder="Search by return #, vendor, or PO…"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            style={{
                                width: '100%',
                                padding: '0.625rem 0.75rem 0.625rem 2.5rem',
                                border: '1px solid var(--color-border)',
                                borderRadius: '8px',
                                background: 'var(--color-surface)',
                                color: 'var(--color-text)',
                                fontSize: 'var(--text-sm)',
                                boxSizing: 'border-box',
                            }}
                        />
                    </div>
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
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
                        <option value="Pending">Pending</option>
                        <option value="Approved">Approved</option>
                        <option value="Completed">Completed</option>
                        <option value="Cancelled">Cancelled</option>
                    </select>
                </div>

                {/* ── Table ───────────────────────────────────────────────── */}
                <div style={{
                    background: 'var(--color-surface)',
                    borderRadius: '12px',
                    border: '1px solid var(--color-border)',
                    overflow: 'hidden',
                }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-surface-elevated, rgba(0,0,0,0.02))' }}>
                                {[
                                    { label: 'Return #',    align: 'left'  },
                                    { label: 'Vendor',      align: 'left'  },
                                    { label: 'PO Reference',align: 'left'  },
                                    { label: 'Date',        align: 'left'  },
                                    { label: 'Reason',      align: 'left'  },
                                    { label: 'Total Value', align: 'right' },
                                    { label: 'Status',      align: 'center'},
                                    { label: 'Actions',     align: 'right' },
                                ].map(col => (
                                    <th
                                        key={col.label}
                                        style={{
                                            padding: '0.75rem 1rem',
                                            textAlign: col.align as any,
                                            fontSize: 'var(--text-xs)',
                                            fontWeight: 700,
                                            color: 'var(--color-text-muted)',
                                            textTransform: 'uppercase',
                                            letterSpacing: '0.04em',
                                            whiteSpace: 'nowrap',
                                        }}
                                    >
                                        {col.label}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {filteredReturns.length === 0 ? (
                                <tr>
                                    <td colSpan={8} style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <RotateCcw size={48} style={{ margin: '0 auto 1rem', opacity: 0.25, display: 'block' }} />
                                        <p style={{ margin: 0, fontWeight: 500 }}>No purchase returns found</p>
                                        <p style={{ margin: '0.375rem 0 0', fontSize: 'var(--text-sm)' }}>
                                            {statusFilter
                                                ? `No ${statusFilter} returns match your search.`
                                                : 'Click "New Return" to initiate a return to a vendor.'}
                                        </p>
                                    </td>
                                </tr>
                            ) : (
                                filteredReturns.map((ret: any) => (
                                    <tr
                                        key={ret.id}
                                        style={{ borderBottom: '1px solid var(--color-border)' }}
                                    >
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                            {ret.return_number || <span style={{ color: 'var(--color-text-muted)' }}>—</span>}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)' }}>{ret.vendor_name || '—'}</td>
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                            {ret.po_number || '—'}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', whiteSpace: 'nowrap' }}>
                                            {ret.return_date ? new Date(ret.return_date).toLocaleDateString() : '—'}
                                        </td>
                                        <td style={{
                                            padding: '0.75rem 1rem',
                                            maxWidth: '180px',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            whiteSpace: 'nowrap',
                                            fontSize: 'var(--text-sm)',
                                            color: 'var(--color-text-muted)',
                                        }}>
                                            {ret.reason}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-sm)', whiteSpace: 'nowrap' }}>
                                            {ret.total_amount ? formatCurrency(ret.total_amount) : '—'}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <StatusBadge status={ret.status} />
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            <div style={{ display: 'flex', gap: '0.375rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>

                                                {/* Draft → Submit for approval */}
                                                {ret.status === 'Draft' && (
                                                    <ActionBtn
                                                        label="Submit"
                                                        color="#2471a3"
                                                        bg="rgba(36, 113, 163, 0.1)"
                                                        icon={<Send size={12} />}
                                                        loading={submitMutation.isPending}
                                                        onClick={() => submitMutation.mutate(ret.id)}
                                                    />
                                                )}

                                                {/* Pending → Approve */}
                                                {ret.status === 'Pending' && (
                                                    <ActionBtn
                                                        label="Approve"
                                                        color="#2471a3"
                                                        bg="rgba(36, 113, 163, 0.1)"
                                                        icon={<CheckCircle size={12} />}
                                                        loading={approveMutation.isPending}
                                                        onClick={() => approveMutation.mutate(ret.id)}
                                                    />
                                                )}

                                                {/* Approved → Complete (posts GL + credit note) */}
                                                {ret.status === 'Approved' && (
                                                    <ActionBtn
                                                        label="Complete"
                                                        color="#22c55e"
                                                        bg="rgba(34, 197, 94, 0.1)"
                                                        icon={<CheckCircle size={12} />}
                                                        loading={completeMutation.isPending}
                                                        onClick={() => completeMutation.mutate({ id: ret.id })}
                                                    />
                                                )}

                                                {/* Cancel — available while return is not yet completed */}
                                                {['Draft', 'Pending', 'Approved'].includes(ret.status) && (
                                                    <ActionBtn
                                                        label="Cancel"
                                                        color="#ef4444"
                                                        bg="rgba(239, 68, 68, 0.1)"
                                                        icon={<XCircle size={12} />}
                                                        loading={cancelMutation.isPending}
                                                        onClick={() => cancelMutation.mutate(ret.id)}
                                                    />
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* ── Totals footer ────────────────────────────────────────── */}
                {filteredReturns.length > 0 && (
                    <div style={{ marginTop: '0.75rem', textAlign: 'right', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                        {filteredReturns.length} return{filteredReturns.length !== 1 ? 's' : ''}
                        {' — '}
                        Total returned value:{' '}
                        <strong style={{ color: 'var(--color-text)' }}>
                            {formatCurrency(
                                filteredReturns.reduce((s: number, r: any) => s + parseFloat(r.total_amount || '0'), 0),
                            )}
                        </strong>
                    </div>
                )}
            </div>
        </AccountingLayout>
    );
}
