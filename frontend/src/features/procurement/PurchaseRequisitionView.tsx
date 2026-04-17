/**
 * Purchase Requisition Detail View + Approval Workflow
 * Route: /procurement/requisitions/:id
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    FileText, CheckCircle, XCircle, ArrowRight, Send, Clock,
    Building2, Layers, AlertTriangle,
} from 'lucide-react';
import apiClient from '../../api/client';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from '../accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import LoadingScreen from '../../components/common/LoadingScreen';
import '../accounting/styles/glassmorphism.css';

const statusConfig: Record<string, { bg: string; color: string; border: string }> = {
    Draft:    { bg: '#f1f5f9', color: '#64748b', border: '#cbd5e1' },
    Pending:  { bg: '#fffbeb', color: '#d97706', border: '#fde68a' },
    Approved: { bg: '#ecfdf5', color: '#059669', border: '#a7f3d0' },
    Rejected: { bg: '#fef2f2', color: '#dc2626', border: '#fecaca' },
};

export default function PurchaseRequisitionView() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const qc = useQueryClient();
    const [confirmAction, setConfirmAction] = useState<string | null>(null);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const flash = (msg: string, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 5000); };

    const { data: pr, isLoading, error } = useQuery({
        queryKey: ['purchase-request', id],
        queryFn: async () => {
            const res = await apiClient.get(`/procurement/requests/${id}/`);
            return res.data;
        },
        enabled: !!id,
    });

    const submitMutation = useMutation({
        mutationFn: () => apiClient.post(`/procurement/requests/${id}/submit_for_approval/`),
        onSuccess: () => { flash('Submitted for approval'); qc.invalidateQueries({ queryKey: ['purchase-request', id] }); qc.invalidateQueries({ queryKey: ['purchase-requests'] }); },
        onError: (err: any) => flash(err?.response?.data?.error || err?.response?.data?.detail || 'Failed to submit', false),
    });

    const approveMutation = useMutation({
        mutationFn: () => apiClient.post(`/procurement/requests/${id}/approve/`),
        onSuccess: () => { flash('Purchase Requisition Approved'); qc.invalidateQueries({ queryKey: ['purchase-request', id] }); qc.invalidateQueries({ queryKey: ['purchase-requests'] }); },
        onError: (err: any) => flash(err?.response?.data?.error || err?.response?.data?.detail || 'Failed to approve', false),
    });

    const rejectMutation = useMutation({
        mutationFn: () => apiClient.post(`/procurement/requests/${id}/reject/`),
        onSuccess: () => { flash('Purchase Requisition Rejected'); qc.invalidateQueries({ queryKey: ['purchase-request', id] }); qc.invalidateQueries({ queryKey: ['purchase-requests'] }); },
        onError: (err: any) => flash(err?.response?.data?.error || err?.response?.data?.detail || 'Failed to reject', false),
    });

    const handleAction = (action: string) => {
        if (action === 'submit') submitMutation.mutate();
        else if (action === 'approve') approveMutation.mutate();
        else if (action === 'reject') rejectMutation.mutate();
        setConfirmAction(null);
    };

    if (isLoading) return <AccountingLayout><LoadingScreen message="Loading requisition..." /></AccountingLayout>;
    if (error || !pr) return (
        <AccountingLayout>
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                <AlertTriangle size={32} style={{ marginBottom: '1rem' }} />
                <p>Purchase Requisition not found.</p>
                <button className="btn btn-outline" onClick={() => navigate('/procurement/requisitions')} style={{ marginTop: '1rem' }}>Back to List</button>
            </div>
        </AccountingLayout>
    );

    const estTotal = pr.lines?.reduce((sum: number, l: any) => sum + Number(l.quantity || 0) * Number(l.estimated_unit_price || 0), 0) || 0;
    const sc = statusConfig[pr.status] || statusConfig.Draft;

    const thStyle: React.CSSProperties = {
        padding: '0.625rem 0.75rem', textAlign: 'left', fontSize: 'var(--text-xs)',
        fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)',
    };
    const tdStyle: React.CSSProperties = {
        padding: '0.625rem 0.75rem', fontSize: 'var(--text-sm)', color: 'var(--color-text)',
    };

    return (
        <AccountingLayout>
            <PageHeader
                title={pr.request_number}
                subtitle={pr.description?.substring(0, 80) || 'Purchase Requisition'}
                icon={<FileText size={22} />}
                onBack={() => navigate('/procurement/requisitions')}
                actions={
                    <span style={{
                        padding: '0.35rem 1rem', borderRadius: '20px', fontSize: 'var(--text-sm)', fontWeight: 700,
                        background: sc.bg, color: sc.color, border: `1.5px solid ${sc.border}`,
                    }}>{pr.status}</span>
                }
            />

            {/* Toast */}
            {toast && (
                <div style={{
                    padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                    background: toast.ok ? 'rgba(34,197,94,0.08)' : '#fee2e2',
                    border: `1px solid ${toast.ok ? 'rgba(34,197,94,0.2)' : '#fecaca'}`,
                    color: toast.ok ? '#166534' : '#dc2626', fontSize: 'var(--text-sm)',
                }}>{toast.msg}</div>
            )}

            {/* Confirmation bar */}
            {confirmAction && (
                <div style={{
                    padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                    background: '#fffbeb', border: '1px solid #fde68a',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    fontSize: 'var(--text-sm)',
                }}>
                    <span style={{ color: '#92400e', fontWeight: 600 }}>
                        Are you sure you want to {confirmAction} this requisition?
                    </span>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button onClick={() => handleAction(confirmAction)}
                            className="btn btn-primary" style={{ padding: '0.35rem 1rem', fontSize: 'var(--text-sm)' }}>
                            Yes, {confirmAction}
                        </button>
                        <button onClick={() => setConfirmAction(null)}
                            className="btn btn-outline" style={{ padding: '0.35rem 1rem', fontSize: 'var(--text-sm)' }}>
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1.5rem', alignItems: 'start' }}>
                {/* LEFT — Details + Lines */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    {/* Header info */}
                    <div className="card" style={{ padding: '1.5rem' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                                    <Building2 size={12} style={{ verticalAlign: 'middle', marginRight: 3 }} /> MDA
                                </div>
                                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{pr.mda_name || '—'}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '0.25rem' }}>Requested Date</div>
                                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{pr.requested_date ? new Date(pr.requested_date).toLocaleDateString() : '—'}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '0.25rem' }}>Requested By</div>
                                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{pr.requested_by_name || '—'}</div>
                            </div>
                        </div>

                        {/* Dimensions */}
                        {(pr.fund_name || pr.function_name || pr.program_name || pr.geo_name) && (
                            <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '0.75rem' }}>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                    <Layers size={12} /> NCoA Dimensions
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0.5rem', fontSize: 'var(--text-xs)' }}>
                                    <div><span style={{ color: 'var(--color-text-muted)' }}>Fund:</span> <strong>{pr.fund_name || '—'}</strong></div>
                                    <div><span style={{ color: 'var(--color-text-muted)' }}>Function:</span> <strong>{pr.function_name || '—'}</strong></div>
                                    <div><span style={{ color: 'var(--color-text-muted)' }}>Program:</span> <strong>{pr.program_name || '—'}</strong></div>
                                    <div><span style={{ color: 'var(--color-text-muted)' }}>Geo:</span> <strong>{pr.geo_name || '—'}</strong></div>
                                </div>
                            </div>
                        )}

                        {/* Description */}
                        {pr.description && (
                            <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '0.75rem', marginTop: '0.75rem' }}>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, marginBottom: '0.25rem' }}>Description</div>
                                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)', lineHeight: 1.5 }}>{pr.description}</div>
                            </div>
                        )}
                    </div>

                    {/* Line Items */}
                    <div className="card" style={{ padding: '1.5rem' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <FileText size={16} color="#4f46e5" /> Line Items ({pr.lines?.length || 0})
                        </h3>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                                    <th style={thStyle}>#</th>
                                    <th style={thStyle}>Description</th>
                                    <th style={thStyle}>Account</th>
                                    <th style={{ ...thStyle, textAlign: 'center' }}>Qty</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Unit Price</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(pr.lines || []).map((line: any, idx: number) => (
                                    <tr key={line.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ ...tdStyle, fontWeight: 600, color: 'var(--color-text-muted)' }}>{idx + 1}</td>
                                        <td style={tdStyle}>
                                            <div style={{ fontWeight: 500 }}>{line.item_description}</div>
                                            {line.asset_name && <div style={{ fontSize: 'var(--text-xs)', color: '#7c3aed' }}>Asset: {line.asset_name}</div>}
                                            {line.item_name && <div style={{ fontSize: 'var(--text-xs)', color: '#059669' }}>Item: {line.item_name}</div>}
                                        </td>
                                        <td style={{ ...tdStyle, fontSize: 'var(--text-xs)' }}>
                                            {line.account_code ? (
                                                <div>
                                                    <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#4f46e5' }}>{line.account_code}</span>
                                                    <div style={{ color: 'var(--color-text-muted)', marginTop: 1 }}>{line.account_name}</div>
                                                </div>
                                            ) : line.account_name ? (
                                                <span>{line.account_name}</span>
                                            ) : '—'}
                                        </td>
                                        <td style={{ ...tdStyle, textAlign: 'center' }}>{line.quantity}</td>
                                        <td style={{ ...tdStyle, textAlign: 'right' }}>{formatCurrency(Number(line.estimated_unit_price || 0))}</td>
                                        <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>{formatCurrency(Number(line.total_estimated_price || 0))}</td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot>
                                <tr>
                                    <td colSpan={5} style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, borderTop: '2px solid var(--color-border)' }}>Total Estimated:</td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#4f46e5', borderTop: '2px solid var(--color-border)', fontSize: 'var(--text-base)' }}>{formatCurrency(estTotal)}</td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                </div>

                {/* RIGHT — Summary + Actions */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    {/* Summary */}
                    <div style={{
                        borderRadius: '12px', padding: '1.5rem',
                        background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 50%, #7c3aed 100%)',
                        color: '#fff',
                    }}>
                        <p style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', opacity: 0.85, marginBottom: '0.25rem' }}>Total Estimated</p>
                        <p style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-0.025em', marginBottom: '1rem' }}>
                            {formatCurrency(estTotal)}
                        </p>
                        <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', paddingTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: 'var(--text-sm)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ opacity: 0.85 }}>Line Items</span>
                                <span style={{ fontWeight: 600 }}>{pr.lines?.length || 0}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ opacity: 0.85 }}>Status</span>
                                <span style={{ fontWeight: 600 }}>{pr.status}</span>
                            </div>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="card" style={{ padding: '1.5rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: '1rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)' }}>Actions</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                            {pr.status === 'Draft' && (
                                <button onClick={() => setConfirmAction('submit')}
                                    disabled={submitMutation.isPending}
                                    style={{
                                        width: '100%', padding: '0.65rem 1rem', borderRadius: '8px', border: 'none',
                                        background: 'linear-gradient(135deg, #f59e0b, #d97706)', color: '#fff',
                                        fontSize: 'var(--text-sm)', fontWeight: 700, cursor: 'pointer',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem',
                                    }}>
                                    <Send size={16} /> Submit for Approval
                                </button>
                            )}
                            {pr.status === 'Pending' && (
                                <>
                                    <button onClick={() => setConfirmAction('approve')}
                                        disabled={approveMutation.isPending}
                                        style={{
                                            width: '100%', padding: '0.65rem 1rem', borderRadius: '8px', border: 'none',
                                            background: 'linear-gradient(135deg, #059669, #047857)', color: '#fff',
                                            fontSize: 'var(--text-sm)', fontWeight: 700, cursor: 'pointer',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem',
                                        }}>
                                        <CheckCircle size={16} /> Approve
                                    </button>
                                    <button onClick={() => setConfirmAction('reject')}
                                        disabled={rejectMutation.isPending}
                                        style={{
                                            width: '100%', padding: '0.65rem 1rem', borderRadius: '8px',
                                            border: '1.5px solid #fecaca', background: '#fef2f2', color: '#dc2626',
                                            fontSize: 'var(--text-sm)', fontWeight: 700, cursor: 'pointer',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem',
                                        }}>
                                        <XCircle size={16} /> Reject
                                    </button>
                                </>
                            )}
                            {pr.status === 'Approved' && (
                                <button onClick={() => navigate(`/procurement/requisitions/${pr.id}/convert`)}
                                    style={{
                                        width: '100%', padding: '0.65rem 1rem', borderRadius: '8px', border: 'none',
                                        background: 'linear-gradient(135deg, #2563eb, #1d4ed8)', color: '#fff',
                                        fontSize: 'var(--text-sm)', fontWeight: 700, cursor: 'pointer',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem',
                                    }}>
                                    <ArrowRight size={16} /> Convert to Purchase Order
                                </button>
                            )}
                            {pr.status === 'Rejected' && (
                                <div style={{ padding: '0.75rem', borderRadius: '8px', background: '#fef2f2', border: '1px solid #fecaca', fontSize: 'var(--text-xs)', color: '#dc2626', textAlign: 'center' }}>
                                    This requisition was rejected.
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Audit info */}
                    <div className="card" style={{ padding: '1rem' }}>
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                <Clock size={11} /> Created: {pr.created_at ? new Date(pr.created_at).toLocaleString() : '—'}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                <Clock size={11} /> Updated: {pr.updated_at ? new Date(pr.updated_at).toLocaleString() : '—'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </AccountingLayout>
    );
}
