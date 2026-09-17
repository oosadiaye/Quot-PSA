/**
 * Payment Voucher Detail Page — Quot PSE
 * Route: /accounting/payment-vouchers/:id
 * Shows PV details + action buttons (Approve, Schedule, Pay, Print)
 */
import { useParams, useNavigate } from 'react-router-dom';
import {
    CheckCircle, Send, CreditCard, Printer, AlertCircle, Edit3, X,
    Receipt, Building2, Banknote, Hash, FileText,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import AccountingLayout from '../../features/accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import { usePaymentVoucherDetail, usePVAction, useUpdatePV } from '../../hooks/useGovForms';
import { formatApiError } from '../../utils/apiError';
import apiClient from '../../api/client';

const fmtNGN = (v: number | string) => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (n || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const GOV = { green: '#008751', blue: '#1e4d8c', gold: '#C89B3C', red: '#c0392b' };
const fieldLabel: React.CSSProperties = { fontSize: '0.7rem', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.3rem' };
const fieldValue: React.CSSProperties = { fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' };
const inlineInput: React.CSSProperties = { width: '100%', padding: '0.5rem 0.7rem', fontSize: 'var(--text-sm)', borderRadius: 8, border: '1px solid var(--color-border)', background: 'var(--color-background, #fff)', color: 'var(--color-text)', outline: 'none' };

const STATUS_COLOR: Record<string, string> = {
    DRAFT: '#d97706', CHECKED: '#2563eb', AUDITED: '#7c3aed', APPROVED: '#008751',
    SCHEDULED: '#0369a1', PAID: '#16a34a', CANCELLED: '#dc2626', REVERSED: '#64748b',
};

/** A titled card with a small tinted section icon — the house detail-card look. */
function Section({ icon, title, children, tint }: { icon: React.ReactNode; title: string; children: React.ReactNode; tint?: string }) {
    return (
        <div className="card" style={{ marginBottom: '1.25rem', ...(tint ? { background: tint } : {}) }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1.1rem' }}>
                <span style={{ display: 'inline-flex', width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center', background: 'rgba(79,70,229,0.1)', color: '#4f46e5', flexShrink: 0 }}>{icon}</span>
                <h3 style={{ margin: 0, fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>{title}</h3>
            </div>
            {children}
        </div>
    );
}

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

    if (isLoading) return <AccountingLayout><div style={{ color: 'var(--color-text-muted)' }}>Loading…</div></AccountingLayout>;
    if (error || !pv) return <AccountingLayout><div style={{ color: 'var(--color-error, #dc2626)' }}>Payment Voucher not found.</div></AccountingLayout>;

    const statusColor = STATUS_COLOR[pv.status] || '#64748b';
    const btnBase: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.55rem 1rem', borderRadius: 8, fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer', border: 'none' };
    const btnLight: React.CSSProperties = { ...btnBase, background: '#fff', color: '#1e293b', border: '1px solid rgba(255,255,255,0.6)' };

    const actions = (
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', padding: '0.3rem 0.75rem', borderRadius: 999, fontSize: 12, fontWeight: 700, letterSpacing: '0.03em', background: statusColor, color: '#fff' }}>{pv.status}</span>
            {pv.status === 'DRAFT' && !editing && (
                <button onClick={() => setEditing(true)} style={btnLight}><Edit3 size={16} /> Edit Draft</button>
            )}
            {pv.status === 'DRAFT' && editing && (
                <>
                    <button onClick={saveDraft} disabled={updatePV.isPending} style={{ ...btnBase, background: GOV.blue, color: '#fff' }}>
                        <CheckCircle size={16} /> {updatePV.isPending ? 'Saving…' : 'Save Changes'}
                    </button>
                    <button onClick={() => setEditing(false)} disabled={updatePV.isPending} style={btnLight}><X size={16} /> Cancel</button>
                </>
            )}
            {!editing && ['DRAFT', 'CHECKED', 'AUDITED'].includes(pv.status) && (
                <button onClick={() => doAction('approve')} disabled={pvAction.isPending || actionInFlight} style={{ ...btnBase, background: GOV.green, color: '#fff' }}>
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
                    style={{ ...btnBase, background: GOV.blue, color: '#fff' }}
                    title={pv.status === 'APPROVED'
                        ? 'Schedule for payment — creates a draft Payment in Outgoing Payments for Treasury to finalise'
                        : 'Open this PV in Outgoing Payments (creates the draft Payment row if missing)'}
                >
                    <Send size={16} /> {pv.status === 'APPROVED' ? 'Schedule Payment' : 'Open in Outgoing Payments'}
                </button>
            )}
            {pv.status === 'SCHEDULED' && (
                <button onClick={() => doAction('mark_paid')} disabled={pvAction.isPending || actionInFlight} style={{ ...btnBase, background: GOV.gold, color: '#fff' }}>
                    <CreditCard size={16} /> Mark Paid
                </button>
            )}
            <button onClick={openPrint} style={btnLight}><Printer size={16} /> Print PV</button>
        </div>
    );

    return (
        <AccountingLayout>
            <PageHeader
                title={`PV ${pv.voucher_number}`}
                subtitle={pv.payee_name ? `Payment voucher for ${pv.payee_name}` : 'Payment voucher'}
                icon={<Receipt size={22} />}
                actions={actions}
            />

            <div style={{ maxWidth: 1040 }}>
                {actionError && (
                    <div style={{ padding: '0.8rem 1.1rem', borderRadius: 8, marginBottom: '1.25rem', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-sm)' }}>
                        <AlertCircle size={16} /> {actionError}
                    </div>
                )}

                {/* Payee */}
                <Section icon={<Building2 size={16} />} title="Payee Details">
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                        <div>
                            <div style={fieldLabel}>Payee Name</div>
                            {editing
                                ? <input value={draft.payee_name} onChange={(e) => setDraft({ ...draft, payee_name: e.target.value })} style={inlineInput} />
                                : <div style={fieldValue}>{pv.payee_name || '—'}</div>}
                        </div>
                        <div>
                            <div style={fieldLabel}>Bank</div>
                            {editing
                                ? <input value={draft.payee_bank} onChange={(e) => setDraft({ ...draft, payee_bank: e.target.value })} style={inlineInput} />
                                : <div style={fieldValue}>{pv.payee_bank || '—'}</div>}
                        </div>
                        <div>
                            <div style={fieldLabel}>Account</div>
                            {editing
                                ? <input value={draft.payee_account} onChange={(e) => setDraft({ ...draft, payee_account: e.target.value })} style={inlineInput} />
                                : <div style={{ ...fieldValue, fontFamily: 'monospace' }}>{pv.payee_account || '—'}</div>}
                        </div>
                    </div>
                </Section>

                {/* Amounts */}
                <Section icon={<Banknote size={16} />} title="Payment Amount">
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                        {/* Gross */}
                        <div style={{ padding: '0.85rem 1rem', borderRadius: 10, background: 'rgba(148,163,184,0.08)', border: '1px solid var(--color-border)' }}>
                            <div style={fieldLabel}>Gross Amount</div>
                            {editing ? (
                                <input
                                    type="number" step="0.01" min="0" max="999999999999.99"
                                    value={draft.gross_amount}
                                    onKeyDown={(e) => { if (['e', 'E', '+', '-'].includes(e.key)) e.preventDefault(); }}
                                    onChange={(e) => setDraft({ ...draft, gross_amount: e.target.value })}
                                    style={{ ...inlineInput, fontFamily: 'monospace' }}
                                />
                            ) : (
                                <div style={{ fontFamily: 'monospace', fontSize: '1.05rem', fontWeight: 700, color: 'var(--color-text)' }}>{fmtNGN(pv.gross_amount)}</div>
                            )}
                        </div>
                        {/* WHT */}
                        <div style={{ padding: '0.85rem 1rem', borderRadius: 10, background: 'rgba(192,57,43,0.06)', border: '1px solid rgba(192,57,43,0.2)' }}>
                            <div style={fieldLabel}>WHT Deduction</div>
                            <div style={{ fontFamily: 'monospace', fontSize: '1.05rem', fontWeight: 700, color: GOV.red }}>{fmtNGN(pv.wht_amount)}</div>
                        </div>
                        {/* Net */}
                        <div style={{ padding: '0.85rem 1rem', borderRadius: 10, background: 'rgba(0,135,81,0.08)', border: '1px solid rgba(0,135,81,0.25)' }}>
                            <div style={fieldLabel}>Net Amount</div>
                            <div style={{ fontFamily: 'monospace', fontSize: '1.25rem', fontWeight: 800, color: GOV.green }}>{fmtNGN(pv.net_amount)}</div>
                        </div>
                    </div>
                    <div style={{ marginTop: '1rem' }}>
                        <div style={fieldLabel}>Narration</div>
                        {editing
                            ? <textarea rows={2} value={draft.narration} onChange={(e) => setDraft({ ...draft, narration: e.target.value })} style={{ ...inlineInput, resize: 'vertical', fontFamily: 'inherit' }} />
                            : <div style={{ ...fieldValue, fontWeight: 500, lineHeight: 1.5 }}>{pv.narration || '—'}</div>}
                    </div>
                </Section>

                {/* NCoA */}
                {pv.ncoa_full_code && (
                    <Section icon={<Hash size={16} />} title="NCoA Classification">
                        <div style={{ fontFamily: 'monospace', fontSize: 'var(--text-sm)', color: GOV.blue, fontWeight: 600, background: 'rgba(30,77,140,0.06)', padding: '0.7rem 0.85rem', borderRadius: 8, border: '1px solid rgba(30,77,140,0.2)', wordBreak: 'break-all' }}>
                            {pv.ncoa_full_code}
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
                            <div><div style={fieldLabel}>MDA</div><div style={fieldValue}>{pv.ncoa_mda_name || '—'}</div></div>
                            <div><div style={fieldLabel}>Account</div><div style={fieldValue}>{pv.ncoa_account_name || '—'}</div></div>
                        </div>
                    </Section>
                )}

                {/* References */}
                <Section icon={<FileText size={16} />} title="References">
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
                        <div><div style={fieldLabel}>Payment Type</div><div style={fieldValue}>{pv.payment_type || '—'}</div></div>
                        <div><div style={fieldLabel}>TSA Account</div><div style={{ ...fieldValue, fontFamily: 'monospace' }}>{pv.tsa_account_number || '—'}</div></div>
                        <div>
                            <div style={fieldLabel}>Source Doc</div>
                            {editing
                                ? <input value={draft.source_document} onChange={(e) => setDraft({ ...draft, source_document: e.target.value })} style={inlineInput} />
                                : <div style={fieldValue}>{pv.source_document || '—'}</div>}
                        </div>
                        <div>
                            <div style={fieldLabel}>Invoice No.</div>
                            {editing
                                ? <input value={draft.invoice_number} onChange={(e) => setDraft({ ...draft, invoice_number: e.target.value })} style={inlineInput} />
                                : <div style={fieldValue}>{pv.invoice_number || '—'}</div>}
                        </div>
                    </div>
                </Section>
            </div>
        </AccountingLayout>
    );
}
