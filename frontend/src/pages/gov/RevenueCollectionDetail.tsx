/**
 * Revenue Collection Detail Page — Quot PSE
 * Route: /accounting/revenue-collections/:id
 * Shows collection details + action buttons (Confirm, Post to GL, Print)
 */
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, BookOpen, Printer, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import Sidebar from '../../components/Sidebar';
import { useRevenueCollectionDetail, useRevenueAction } from '../../hooks/useGovForms';
import { formatApiError } from '../../utils/apiError';

const fmtNGN = (v: number | string) => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (n || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const GOV = { green: '#008751', blue: '#1e4d8c' };
const card: React.CSSProperties = { background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', padding: '24px', marginBottom: '20px' };
const fieldLabel: React.CSSProperties = { fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', marginBottom: '4px' };
const fieldValue: React.CSSProperties = { fontSize: '14px', fontWeight: 500, color: '#1e293b' };

export default function RevenueCollectionDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { data: col, isLoading, error } = useRevenueCollectionDetail(id);
    const revAction = useRevenueAction();
    const [actionError, setActionError] = useState('');

    const doAction = async (action: string) => {
        if (!col?.id) return;
        setActionError('');
        try {
            await revAction.mutateAsync({ id: col.id, action });
        } catch (err: any) {
            setActionError(formatApiError(err));
        }
    };

    const openPrint = () => {
        window.open(`/api/v1/accounting/print/revenue-receipt/${id}/`, '_blank');
    };

    if (isLoading) return <div style={{ background: '#f1f5f9', minHeight: '100vh' }}><Sidebar /><main style={{ marginLeft: '260px', padding: '32px', color: '#94a3b8' }}>Loading...</main></div>;
    if (error || !col) return <div style={{ background: '#f1f5f9', minHeight: '100vh' }}><Sidebar /><main style={{ marginLeft: '260px', padding: '32px', color: '#dc2626' }}>Revenue Collection not found.</main></div>;

    const statusColor = { PENDING: '#d97706', CONFIRMED: '#2563eb', POSTED: '#16a34a', REVERSED: '#64748b', CANCELLED: '#dc2626' }[col.status] || '#64748b';

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ maxWidth: '900px' }}>
                    {/* Header */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                            <button onClick={() => navigate(-1)} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', border: '1px solid #e2e8f0', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px', color: '#64748b' }}>
                                <ArrowLeft size={16} /> Back
                            </button>
                            <div>
                                <h1 style={{ fontSize: '22px', fontWeight: 800, color: '#1e293b', margin: 0 }}>Receipt {col.receipt_number}</h1>
                                <span style={{ display: 'inline-block', padding: '3px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: 700, background: `${statusColor}14`, color: statusColor, marginTop: '4px' }}>{col.status}</span>
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                            {col.status === 'PENDING' && (
                                <button onClick={() => doAction('confirm')} disabled={revAction.isPending} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.blue, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                    <CheckCircle size={16} /> Confirm
                                </button>
                            )}
                            {col.status === 'CONFIRMED' && (
                                <button onClick={() => doAction('post_to_gl')} disabled={revAction.isPending} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.green, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                    <BookOpen size={16} /> Post to GL
                                </button>
                            )}
                            <button onClick={openPrint} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', color: '#1e293b', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                <Printer size={16} /> Print Receipt
                            </button>
                        </div>
                    </div>

                    {actionError && (
                        <div style={{ padding: '12px 16px', borderRadius: '8px', marginBottom: '16px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px' }}>
                            <AlertCircle size={16} /> {actionError}
                        </div>
                    )}

                    {/* Amount */}
                    <div style={{ ...card, background: '#f0fdf4', border: '2px solid #22c55e', textAlign: 'center' }}>
                        <div style={{ fontSize: '12px', fontWeight: 700, color: '#16a34a', textTransform: 'uppercase' }}>Amount Received</div>
                        <div style={{ fontSize: '32px', fontWeight: 800, color: GOV.green, fontFamily: 'monospace', marginTop: '4px' }}>{fmtNGN(col.amount)}</div>
                    </div>

                    {/* Revenue Details */}
                    <div style={card}>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Revenue Details</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
                            <div><div style={fieldLabel}>Revenue Head</div><div style={fieldValue}>{col.revenue_head_name}</div></div>
                            <div><div style={fieldLabel}>Collection Date</div><div style={fieldValue}>{col.collection_date}</div></div>
                            <div><div style={fieldLabel}>Channel</div><div style={fieldValue}>{col.collection_channel}</div></div>
                            <div><div style={fieldLabel}>Payment Ref</div><div style={fieldValue}>{col.payment_reference}</div></div>
                            <div><div style={fieldLabel}>RRR (Remita)</div><div style={fieldValue}>{col.rrr || '---'}</div></div>
                            <div><div style={fieldLabel}>TSA Account</div><div style={fieldValue}>{col.tsa_account_number || '---'}</div></div>
                        </div>
                        {col.description && <div style={{ marginTop: '12px' }}><div style={fieldLabel}>Description</div><div style={fieldValue}>{col.description}</div></div>}
                    </div>

                    {/* Payer */}
                    <div style={card}>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Payer Details</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
                            <div><div style={fieldLabel}>Name</div><div style={fieldValue}>{col.payer_name}</div></div>
                            <div><div style={fieldLabel}>TIN</div><div style={fieldValue}>{col.payer_tin || '---'}</div></div>
                            <div><div style={fieldLabel}>Phone</div><div style={fieldValue}>{col.payer_phone || '---'}</div></div>
                        </div>
                    </div>

                    {/* NCoA */}
                    {col.ncoa_full_code && (
                        <div style={{ ...card, background: '#f8fafc' }}>
                            <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: '12px' }}>NCoA Classification</div>
                            <div style={{ fontFamily: 'monospace', fontSize: '13px', color: GOV.blue, fontWeight: 600, background: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', wordBreak: 'break-all' }}>
                                {col.ncoa_full_code}
                            </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
