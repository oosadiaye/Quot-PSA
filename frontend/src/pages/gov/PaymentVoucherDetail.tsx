/**
 * Payment Voucher Detail Page — Quot PSE
 * Route: /accounting/payment-vouchers/:id
 * Shows PV details + action buttons (Approve, Schedule, Pay, Print)
 */
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, Send, CreditCard, Printer, AlertCircle, Edit3, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import Sidebar from '../../components/Sidebar';
import { usePaymentVoucherDetail, usePVAction, useUpdatePV } from '../../hooks/useGovForms';
import { formatApiError } from '../../utils/apiError';
import apiClient from '../../api/client';

const fmtNGN = (v: number | string) => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (n || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const GOV = { green: '#008751', blue: '#1e4d8c', gold: '#C89B3C', red: '#c0392b' };
const card: React.CSSProperties = { background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', padding: '24px', marginBottom: '20px' };
const fieldLabel: React.CSSProperties = { fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', marginBottom: '4px' };
const fieldValue: React.CSSProperties = { fontSize: '14px', fontWeight: 500, color: '#1e293b' };
const inlineInput: React.CSSProperties = { width: '100%', padding: '6px 10px', fontSize: '14px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', color: '#1e293b', outline: 'none' };

export default function PaymentVoucherDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { data: pv, isLoading, error } = usePaymentVoucherDetail(id);
    const pvAction = usePVAction();
    const updatePV = useUpdatePV();
    const [actionError, setActionError] = useState('');
    // Double-submit guard. ``pvAction.isPending`` only reflects the
    // first caller's state, so a user clicking Approve immediately
    // followed by Schedule Payment would queue both requests. This
    // local flag toggles around every async action handler so a
    // second click bails out before mutateAsync fires.
    const [actionInFlight, setActionInFlight] = useState(false);

    // Edit-in-place mode for DRAFT vouchers. The auto-create-from-IPC
    // flow pre-fills most fields from the contract / vendor master, but
    // operators usually want to refine the narration, payee account, or
    // gross amount before approving. Once status leaves DRAFT, edits go
    // through workflow actions instead.
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState<{
        payee_name: string; payee_account: string; payee_bank: string;
        gross_amount: string; narration: string;
        source_document: string; invoice_number: string;
    }>({
        payee_name: '', payee_account: '', payee_bank: '',
        gross_amount: '', narration: '',
        source_document: '', invoice_number: '',
    });

    // Re-seed the edit buffer whenever the loaded PV changes (e.g.,
    // after a successful PATCH refetch).
    useEffect(() => {
        if (!pv) return;
        setDraft({
            payee_name:      pv.payee_name      ?? '',
            payee_account:   pv.payee_account   ?? '',
            payee_bank:      pv.payee_bank      ?? '',
            gross_amount:    String(pv.gross_amount ?? ''),
            narration:       pv.narration       ?? '',
            source_document: pv.source_document ?? '',
            invoice_number:  pv.invoice_number  ?? '',
        });
    }, [pv]);

    const doAction = async (action: string, extraData?: Record<string, unknown>) => {
        if (!pv?.id) return;
        // Double-submit guard. Bail out immediately if any action is
        // already in flight — prevents the operator from firing
        // approve + schedule + mark-paid simultaneously by clicking
        // multiple buttons before the first request resolves.
        if (actionInFlight) return;
        setActionInFlight(true);
        setActionError('');
        try {
            await pvAction.mutateAsync({ id: pv.id, action, data: extraData });
        } catch (err: any) {
            setActionError(formatApiError(err));
        } finally {
            setActionInFlight(false);
        }
    };

    const saveDraft = async () => {
        if (!pv?.id) return;
        setActionError('');
        // Strict numeric validation. ``Number(...) || 0`` previously
        // coerced any non-finite or NaN string into 0 silently — a
        // user could zero out a payment voucher amount by typing
        // garbage. We now reject explicitly with a user-facing error.
        const grossNum = Number(draft.gross_amount);
        if (!Number.isFinite(grossNum) || grossNum < 0 || grossNum > 999_999_999_999.99) {
            setActionError(
                'Gross Amount must be a positive number with at most 12 digits and 2 decimal places.'
            );
            return;
        }
        try {
            await updatePV.mutateAsync({
                id: pv.id,
                payload: {
                    payee_name:      draft.payee_name,
                    payee_account:   draft.payee_account,
                    payee_bank:      draft.payee_bank,
                    gross_amount:    grossNum,
                    narration:       draft.narration,
                    source_document: draft.source_document,
                    invoice_number:  draft.invoice_number,
                },
            });
            setEditing(false);
        } catch (err: any) {
            setActionError(formatApiError(err));
        }
    };

    const openPrint = async () => {
        // The print endpoint requires the same Token auth as the rest
        // of the SPA. ``window.open`` can't attach Authorization headers,
        // so we fetch via ``apiClient`` (which injects the token), then
        // render the HTML in a new tab via a blob URL.
        if (!id) return;
        setActionError('');
        try {
            const { data } = await apiClient.get(
                `/accounting/print/payment-voucher/${id}/`,
                { responseType: 'text' },
            );
            const blob = new Blob([data as string], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            const win = window.open(url, '_blank');
            // Revoke after the new tab has had a chance to load.
            if (win) {
                setTimeout(() => URL.revokeObjectURL(url), 60_000);
            } else {
                URL.revokeObjectURL(url);
                setActionError('Pop-up blocked. Allow pop-ups for this site to print.');
            }
        } catch (err: any) {
            setActionError(formatApiError(err) || 'Failed to load print view');
        }
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
                            {pv.status === 'DRAFT' && !editing && (
                                <button onClick={() => setEditing(true)} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', color: '#1e293b', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                    <Edit3 size={16} /> Edit Draft
                                </button>
                            )}
                            {pv.status === 'DRAFT' && editing && (
                                <>
                                    <button onClick={saveDraft} disabled={updatePV.isPending} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.blue, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                        <CheckCircle size={16} /> {updatePV.isPending ? 'Saving…' : 'Save Changes'}
                                    </button>
                                    <button onClick={() => setEditing(false)} disabled={updatePV.isPending} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', color: '#64748b', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                        <X size={16} /> Cancel
                                    </button>
                                </>
                            )}
                            {!editing && ['DRAFT', 'CHECKED', 'AUDITED'].includes(pv.status) && (
                                <button onClick={() => doAction('approve')} disabled={pvAction.isPending || actionInFlight} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.green, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                    <CheckCircle size={16} /> Approve
                                </button>
                            )}
                            {(pv.status === 'APPROVED' || pv.status === 'SCHEDULED') && (
                                <button
                                    onClick={async () => {
                                        if (!pv.id) return;
                                        setActionError('');
                                        try {
                                            // Schedule materialises the bank instruction and a
                                            // draft Payment row in Outgoing Payments. Idempotent:
                                            // re-clicking on an already-SCHEDULED PV that's
                                            // missing only the Payment row (legacy data) backfills
                                            // it without re-flipping the PV status. Backend
                                            // response shape: {instruction, payment}.
                                            const result: any = await pvAction.mutateAsync({
                                                id: pv.id, action: 'schedule_payment',
                                            });
                                            const paymentNumber = result?.payment?.payment_number;
                                            if (paymentNumber) {
                                                // Hand off to Outgoing Payments — operator finalises
                                                // method/bank account and posts.
                                                navigate('/accounting/outgoing-payments');
                                            }
                                        } catch (err: any) {
                                            setActionError(formatApiError(err));
                                        }
                                    }}
                                    disabled={pvAction.isPending || actionInFlight}
                                    style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.blue, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}
                                    title={pv.status === 'APPROVED'
                                        ? 'Schedule for payment — creates a draft Payment in Outgoing Payments for Treasury to finalise'
                                        : 'Open this PV in Outgoing Payments (creates the draft Payment row if missing)'}
                                >
                                    <Send size={16} /> {pv.status === 'APPROVED' ? 'Schedule Payment' : 'Open in Outgoing Payments'}
                                </button>
                            )}
                            {pv.status === 'SCHEDULED' && (
                                <button onClick={() => doAction('mark_paid')} disabled={pvAction.isPending || actionInFlight} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', borderRadius: '8px', border: 'none', background: GOV.gold, color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
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
                            <div>
                                <div style={fieldLabel}>Payee Name</div>
                                {editing ? (
                                    <input value={draft.payee_name} onChange={(e) => setDraft({ ...draft, payee_name: e.target.value })} style={inlineInput} />
                                ) : (
                                    <div style={fieldValue}>{pv.payee_name}</div>
                                )}
                            </div>
                            <div>
                                <div style={fieldLabel}>Bank</div>
                                {editing ? (
                                    <input value={draft.payee_bank} onChange={(e) => setDraft({ ...draft, payee_bank: e.target.value })} style={inlineInput} />
                                ) : (
                                    <div style={fieldValue}>{pv.payee_bank}</div>
                                )}
                            </div>
                            <div>
                                <div style={fieldLabel}>Account</div>
                                {editing ? (
                                    <input value={draft.payee_account} onChange={(e) => setDraft({ ...draft, payee_account: e.target.value })} style={inlineInput} />
                                ) : (
                                    <div style={fieldValue}>{pv.payee_account}</div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Amounts */}
                    <div style={card}>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Payment Amount</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
                            <div>
                                <div style={fieldLabel}>Gross Amount</div>
                                {editing ? (
                                    <input
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        max="999999999999.99"
                                        value={draft.gross_amount}
                                        onKeyDown={(e) => {
                                            // Block characters that produce scientific notation
                                            // / Infinity / negatives. Without this guard the
                                            // submit handler coerces "1e5" to a number it
                                            // shouldn't have accepted.
                                            if (['e', 'E', '+', '-'].includes(e.key)) {
                                                e.preventDefault();
                                            }
                                        }}
                                        onChange={(e) => setDraft({ ...draft, gross_amount: e.target.value })}
                                        style={{ ...inlineInput, fontFamily: 'monospace' }}
                                    />
                                ) : (
                                    <div style={{ ...fieldValue, fontFamily: 'monospace', fontSize: '18px' }}>{fmtNGN(pv.gross_amount)}</div>
                                )}
                            </div>
                            <div><div style={fieldLabel}>WHT Deduction</div><div style={{ ...fieldValue, fontFamily: 'monospace', color: GOV.red }}>{fmtNGN(pv.wht_amount)}</div></div>
                            <div><div style={fieldLabel}>Net Amount</div><div style={{ ...fieldValue, fontFamily: 'monospace', fontSize: '18px', fontWeight: 800, color: GOV.green }}>{fmtNGN(pv.net_amount)}</div></div>
                        </div>
                        <div style={{ marginTop: '12px' }}>
                            <div style={fieldLabel}>Narration</div>
                            {editing ? (
                                <textarea rows={2} value={draft.narration} onChange={(e) => setDraft({ ...draft, narration: e.target.value })} style={{ ...inlineInput, resize: 'vertical', fontFamily: 'inherit' }} />
                            ) : (
                                <div style={fieldValue}>{pv.narration}</div>
                            )}
                        </div>
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
                            <div>
                                <div style={fieldLabel}>Source Doc</div>
                                {editing ? (
                                    <input value={draft.source_document} onChange={(e) => setDraft({ ...draft, source_document: e.target.value })} style={inlineInput} />
                                ) : (
                                    <div style={fieldValue}>{pv.source_document || '—'}</div>
                                )}
                            </div>
                            <div>
                                <div style={fieldLabel}>Invoice No.</div>
                                {editing ? (
                                    <input value={draft.invoice_number} onChange={(e) => setDraft({ ...draft, invoice_number: e.target.value })} style={inlineInput} />
                                ) : (
                                    <div style={fieldValue}>{pv.invoice_number || '—'}</div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
