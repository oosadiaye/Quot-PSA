import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, CheckCircle, XCircle, Search, FileText, Eye } from 'lucide-react';
import {
    useInvoiceMatchings,
    useMatchInvoice,
    useRejectMatching,
} from './hooks/useProcurement';
import { useDialog } from '../../hooks/useDialog';
import AccountingLayout from '../accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import { useCurrency } from '../../context/CurrencyContext';
import '../accounting/styles/glassmorphism.css';

// Shared button styles for the action cell — keeps row markup compact and
// makes it easy to evolve the visual language in one place.
const baseBtn: React.CSSProperties = {
    padding: '0.375rem 0.75rem',
    border: 'none',
    borderRadius: '6px',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '0.25rem',
};
const btnStyles = {
    success: { ...baseBtn, background: 'rgba(34, 197, 94, 0.1)', color: '#22c55e' },
    danger:  { ...baseBtn, background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' },
    primary: { ...baseBtn, background: 'rgba(36, 113, 163, 0.1)', color: '#2471a3' },
    post:    { ...baseBtn, background: '#22c55e', color: 'white' },
    outline: { ...baseBtn, background: 'transparent', color: 'var(--color-text-muted)', border: '1px solid var(--color-border)' },
} as const;

export default function InvoiceMatchingPage() {
    const navigate = useNavigate();
    const { showPrompt } = useDialog();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const { formatCurrency } = useCurrency();

    const { data: matchings, isLoading } = useInvoiceMatchings({ status: statusFilter });
    const matchMutation = useMatchInvoice();
    const rejectMutation = useRejectMatching();
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 5000);
    };

    const matchingsList = matchings?.results || matchings || [];

    const filteredMatchings = Array.isArray(matchingsList) ? matchingsList.filter((m: any) =>
        m.invoice_reference?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        m.po_number?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    // Variance override (with reason) — only available action that remains
    // on the list because Variance rows can't be auto-resolved by the
    // create flow; they need a human decision after the fact.
    const handleMatch = async (id: number) => {
        const reason = await showPrompt('Enter variance reason (required to override):');
        if (!reason) return;
        matchMutation.mutate({ id, variance_reason: reason }, {
            onSuccess: () => flash('Variance overridden — open the row and click Post inside the verification page.'),
            onError: (err: any) => flash(err?.response?.data?.error || 'Failed to override', false),
        });
    };

    const handleReject = async (id: number) => {
        const reason = await showPrompt('Enter rejection reason:');
        if (reason) {
            rejectMutation.mutate({ id, reason }, {
                onSuccess: () => flash('Verification rejected.'),
                onError: (err: any) => flash(err?.response?.data?.error || 'Failed to reject', false),
            });
        }
    };

    const getStatusBadge = (status: string) => {
        const colors: any = {
            'Draft': 'rgba(156, 163, 175, 0.1)',
            'Pending_Review': 'rgba(251, 191, 36, 0.1)',
            'Matched': 'rgba(34, 197, 94, 0.1)',
            'Variance': 'rgba(251, 191, 36, 0.1)',
            'Approved': 'rgba(36, 113, 163, 0.1)',
            'Rejected': 'rgba(239, 68, 68, 0.1)',
        };
        const textColors: any = {
            'Draft': '#9ca3af',
            'Pending_Review': '#fbbf24',
            'Matched': '#22c55e',
            'Variance': '#fbbf24',
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
                {status.replace('_', ' ')}
            </span>
        );
    };

    const getMatchBadge = (matchType: string) => {
        const colors: any = {
            'Full': 'rgba(34, 197, 94, 0.1)',
            'Partial': 'rgba(251, 191, 36, 0.1)',
            'None': 'rgba(239, 68, 68, 0.1)',
        };
        const textColors: any = {
            'Full': '#22c55e',
            'Partial': '#fbbf24',
            'None': '#ef4444',
        };
        return (
            <span style={{
                display: 'inline-block',
                padding: '0.25rem 0.75rem',
                borderRadius: '9999px',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                background: colors[matchType] || 'rgba(156, 163, 175, 0.1)',
                color: textColors[matchType] || '#9ca3af',
            }}>
                {matchType}
            </span>
        );
    };

    if (isLoading) return <LoadingScreen message="Loading Invoice Verifications..." />;

    return (
        <AccountingLayout>
            <div style={{ padding: '1.5rem' }}>
                {toast && (
                    <div style={{
                        padding: '0.75rem 1rem', marginBottom: '1rem', borderRadius: '8px',
                        background: toast.ok ? '#ecfdf5' : '#fef2f2',
                        border: `1px solid ${toast.ok ? '#a7f3d0' : '#fecaca'}`,
                        color: toast.ok ? '#065f46' : '#991b1b',
                        fontSize: 'var(--text-sm)', fontWeight: 500,
                    }}>
                        {toast.msg}
                    </div>
                )}
                <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Invoice Verification
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                            Three-way verification: PO vs GRN vs Invoice
                        </p>
                    </div>
                    <button
                        onClick={() => navigate('/procurement/matching/new')}
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
                        New Verification
                    </button>
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
                            placeholder="Search verifications..."
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
                        <option value="Pending_Review">Pending Review</option>
                        <option value="Matched">Matched</option>
                        <option value="Variance">Variance</option>
                        <option value="Approved">Approved</option>
                        <option value="Rejected">Rejected</option>
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
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Invoice Ref</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Vendor</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>PO Number</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Invoice Amt</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Variance</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Match</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredMatchings.length === 0 ? (
                                <tr>
                                    <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <FileText size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No invoice verifications found</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredMatchings.map((m: any) => (
                                    <tr key={m.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{m.invoice_reference}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{m.vendor_name}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{m.po_number}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace' }}>
                                            {formatCurrency(parseFloat(m.invoice_amount || 0))}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace', color: m.variance_amount > 0 ? '#ef4444' : '#22c55e' }}>
                                            {m.variance_amount ? formatCurrency(parseFloat(m.variance_amount)) : '-'}
                                            {m.variance_percentage > 0 && <span style={{ fontSize: 'var(--text-xs)', marginLeft: '0.25rem' }}>({m.variance_percentage}%)</span>}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{getMatchBadge(m.match_type || 'None')}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{getStatusBadge(m.status)}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            <div style={{ display: 'inline-flex', gap: '0.4rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                                {/* The list is read-only — verification + posting both
                                                    happen on the New Verification page (SAP MIRO-style
                                                    real-time post). Clicking "View" opens the detail
                                                    page; for Variance rows, the override+reject
                                                    actions stay here as an exception because they
                                                    operate on already-created matchings that the
                                                    initial create flow couldn't auto-resolve. */}
                                                {m.status === 'Variance' && (
                                                    <>
                                                        <button onClick={() => handleMatch(m.id)} style={btnStyles.success} title="Override variance with a reason">
                                                            <CheckCircle size={14} /> Override
                                                        </button>
                                                        <button onClick={() => handleReject(m.id)} style={btnStyles.danger} title="Reject this invoice">
                                                            <XCircle size={14} /> Reject
                                                        </button>
                                                    </>
                                                )}
                                                {/* View — always available */}
                                                <button
                                                    onClick={() => navigate(`/procurement/matching/${m.id}`)}
                                                    style={btnStyles.outline}
                                                    title="View verification details"
                                                >
                                                    <Eye size={14} /> View
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </AccountingLayout>
    );
}
