/**
 * Payment Voucher Detail Page — Quot PSE
 * Route: /accounting/payment-vouchers/:id
 * Shows PV details + action buttons (Approve, Schedule, Pay, Print)
 */
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, Send, CreditCard, Printer, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import Sidebar from '../../components/Sidebar';
import { usePaymentVoucherDetail, usePVAction } from '../../hooks/useGovForms';

const fmtNGN = (v: number | string) => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (n || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const GOV = { green: '#008751', blue: '#1e4d8c', gold: '#C89B3C', red: '#c0392b' };
const card: React.CSSProperties = { background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', padding: '24px', marginBottom: '20px' };
const fieldLabel: React.CSSProperties = { fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', marginBottom: '4px' };
const fieldValue: React.CSSProperties = { fontSize: '14px', fontWeight: 500, color: '#1e293b' };

export default function PaymentVoucherDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { data: pv, isLoading, error } = usePaymentVoucherDetail(id);
    const pvAction = usePVAction();
    const [actionError, setActionError] = useState('');

    const doAction = async (action: string, extraData?: Record<string, unknown>) => {
        if (!pv?.id) return;
        setActionError('');
        try {
            await pvAction.mutateAsync({ id: pv.id, action, data: extraData });
        } catch (err: any) {
            setActionError(err.response?.data?.error || err.message || 'Action failed');
        }
    };

    const openPrint = () => {
        window.open(`/api/v1/accounting/print/payment-voucher/${id}/`, '_blank');
    };

    if (isLoading) return <div style={{ background: '#f1f5f9', minHeight: '100vh' }}><Sidebar /><main style={{ marginLeft: '260px', padding: '32px', color: '#94a3b8' }}>Loading...</main></div>;
    if (error || !pv) return <div style={{ background: '#f1f5f9', minHeight: '100vh' }}><Sidebar /><main style={{ marginLeft: '260px', padding: '32px', color: '#dc2626' }}>Payment Voucher not found.</main></div>;

    const statusColor = { DRAFT: '#d97706', CHECKED: '#2563eb', AUDITED: '#7c3aed', APPROVED: '#008751', SCHEDULED: '#0369a1', PAID: '#16a34a', CANCELLED: '#dc2626', REVERSED: '#64748b' }[pv.status] || '#64748b';

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
                                <h1 style={{ fontSize: '22px', fontWeight: 800, color: '#1e293b', margin: 0 }}>PV {pv.voucher_number}</h1>
                                <span style={{ display: 'inline-block', padding: '3px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: 700, background: `${statusColor}14`, color: statusColor, marginTop: '4px' }}>{pv.status}</span>
                            </div>
                        </div>
                        {/* Action Buttons */}
                        <div style={{ display: 'flex', gap: '8px' }}>
                            {['DRAFT', 'CHECKED', 'AUDITED'].includes(pv.status) && (
                                <button onClick={() => doAction('approve')} disabled={pvAction.isPending} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.green, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                    <CheckCircle size={16} /> Approve
                                </button>
                            )}
                            {pv.status === 'APPROVED' && (
                                <button onClick={() => doAction('schedule_payment')} disabled={pvAction.isPending} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.blue, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                    <Send size={16} /> Schedule Payment
                                </button>
                            )}
                            {pv.status === 'SCHEDULED' && (
                                <button onClick={() => doAction('mark_paid')} disabled={pvAction.isPending} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.gold, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                    <CreditCard size={16} /> Mark Paid
                                </button>
                            )}
                            <button onClick={openPrint} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', color: '#1e293b', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                <Printer size={16} /> Print PV
                            </button>
                        </div>
                    </div>

                    {actionError && (
                        <div style={{ padding: '12px 16px', borderRadius: '8px', marginBottom: '16px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px' }}>
                            <AlertCircle size={16} /> {actionError}
                        </div>
                    )}

                    {/* Payee */}
                    <div style={card}>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Payee Details</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
                            <div><div style={fieldLabel}>Payee Name</div><div style={fieldValue}>{pv.payee_name}</div></div>
                            <div><div style={fieldLabel}>Bank</div><div style={fieldValue}>{pv.payee_bank}</div></div>
                            <div><div style={fieldLabel}>Account</div><div style={fieldValue}>{pv.payee_account}</div></div>
                        </div>
                    </div>

                    {/* Amounts */}
                    <div style={card}>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Payment Amount</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
                            <div><div style={fieldLabel}>Gross Amount</div><div style={{ ...fieldValue, fontFamily: 'monospace', fontSize: '18px' }}>{fmtNGN(pv.gross_amount)}</div></div>
                            <div><div style={fieldLabel}>WHT Deduction</div><div style={{ ...fieldValue, fontFamily: 'monospace', color: GOV.red }}>{fmtNGN(pv.wht_amount)}</div></div>
                            <div><div style={fieldLabel}>Net Amount</div><div style={{ ...fieldValue, fontFamily: 'monospace', fontSize: '18px', fontWeight: 800, color: GOV.green }}>{fmtNGN(pv.net_amount)}</div></div>
                        </div>
                        <div style={{ marginTop: '12px' }}><div style={fieldLabel}>Narration</div><div style={fieldValue}>{pv.narration}</div></div>
                    </div>

                    {/* NCoA */}
                    {pv.ncoa_full_code && (
                        <div style={{ ...card, background: '#f8fafc' }}>
                            <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: '12px' }}>NCoA Classification</div>
                            <div style={{ fontFamily: 'monospace', fontSize: '13px', color: GOV.blue, fontWeight: 600, background: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', wordBreak: 'break-all' }}>
                                {pv.ncoa_full_code}
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px' }}>
                                <div><div style={fieldLabel}>MDA</div><div style={fieldValue}>{pv.ncoa_mda_name}</div></div>
                                <div><div style={fieldLabel}>Account</div><div style={fieldValue}>{pv.ncoa_account_name}</div></div>
                            </div>
                        </div>
                    )}

                    {/* References */}
                    <div style={card}>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>References</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '16px' }}>
                            <div><div style={fieldLabel}>Payment Type</div><div style={fieldValue}>{pv.payment_type}</div></div>
                            <div><div style={fieldLabel}>TSA Account</div><div style={fieldValue}>{pv.tsa_account_number || '—'}</div></div>
                            <div><div style={fieldLabel}>Source Doc</div><div style={fieldValue}>{pv.source_document || '—'}</div></div>
                            <div><div style={fieldLabel}>Invoice No.</div><div style={fieldValue}>{pv.invoice_number || '—'}</div></div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
