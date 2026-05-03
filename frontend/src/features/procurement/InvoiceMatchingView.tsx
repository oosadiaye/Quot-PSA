/**
 * InvoiceMatching Detail View — read-only display of the 3-way match plus
 * status-aware action buttons (Submit, Post, Match-with-reason, Reject).
 * Route: /procurement/matching/:id
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    FileText, CheckCircle, XCircle, Send, AlertTriangle, ArrowLeft,
    Building2, Calendar, Receipt, Scale, TrendingUp, TrendingDown,
    RotateCcw,
} from 'lucide-react';
import {
    useInvoiceMatching,
    useSubmitMatchingForApproval,
    usePostMatching,
    useMatchInvoice,
    useRejectMatching,
    useReverseMatching,
} from './hooks/useProcurement';
import { useJournal } from '../accounting/hooks/useJournal';
import { useDialog } from '../../hooks/useDialog';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from '../accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import LoadingScreen from '../../components/common/LoadingScreen';
import '../accounting/styles/glassmorphism.css';

const statusConfig: Record<string, { bg: string; color: string; border: string; label: string }> = {
    Draft:          { bg: '#f1f5f9', color: '#475569', border: '#cbd5e1', label: 'Draft' },
    Pending_Review: { bg: '#fef3c7', color: '#a16207', border: '#fde68a', label: 'Pending Review' },
    Matched:        { bg: '#dcfce7', color: '#15803d', border: '#86efac', label: 'Matched' },
    Variance:       { bg: '#fef3c7', color: '#a16207', border: '#fde68a', label: 'Variance' },
    Approved:       { bg: '#dbeafe', color: '#1d4ed8', border: '#93c5fd', label: 'Approved' },
    Rejected:       { bg: '#fee2e2', color: '#b91c1c', border: '#fecaca', label: 'Rejected' },
};

export default function InvoiceMatchingView() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { showPrompt } = useDialog();
    const { formatCurrency } = useCurrency();
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const matchingId = id ? Number(id) : null;
    const { data: m, isLoading, error } = useInvoiceMatching(matchingId);
    // Pull the posted journal (header + lines) once it exists, so we can
    // render the DR/CR breakdown the user expects to see post-posting.
    const journalId: number | null =
        m?.journal_entry_id ? Number(m.journal_entry_id) : null;
    const { data: journal } = useJournal(journalId);

    const matchMutation   = useMatchInvoice();
    const rejectMutation  = useRejectMatching();
    const submitMutation  = useSubmitMatchingForApproval();
    const postMutation    = usePostMatching();
    const reverseMutation = useReverseMatching();

    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 5000);
    };

    if (isLoading) return <AccountingLayout><LoadingScreen message="Loading verification..." /></AccountingLayout>;

    if (error || !m) {
        return (
            <AccountingLayout>
                <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                    <AlertTriangle size={32} style={{ marginBottom: '1rem' }} />
                    <p>Invoice verification not found.</p>
                    <button className="btn btn-outline" onClick={() => navigate('/procurement/matching')} style={{ marginTop: '1rem' }}>
                        <ArrowLeft size={14} style={{ marginRight: '0.35rem' }} /> Back to Verification List
                    </button>
                </div>
            </AccountingLayout>
        );
    }

    const status: string = m.status;
    const cfg = statusConfig[status] || statusConfig.Draft;

    const poAmount      = parseFloat(m.po_amount || 0);
    const grnAmount     = parseFloat(m.grn_amount || 0);
    const invoiceAmount = parseFloat(m.invoice_amount || 0);
    const variance      = parseFloat(m.variance_amount || 0);
    const variancePct   = parseFloat(m.variance_percentage || 0);
    const taxAmount     = parseFloat(m.invoice_tax_amount || 0);
    const subtotal      = parseFloat(m.invoice_subtotal || 0) || invoiceAmount - taxAmount;
    const downPayment   = parseFloat(m.down_payment_applied || 0);
    const netPayable    = parseFloat(m.net_payable || invoiceAmount) - downPayment;

    // The GL is now auto-posted when the matching reaches 'Approved'
    // (see InvoiceMatchingViewSet.submit_for_approval + workflow grant).
    // Detect "already posted" via the linked Vendor Invoice being Posted
    // OR a journal_entry_id having been attached — so the "Post to GL"
    // button disappears automatically after the auto-post succeeds.
    const isAlreadyPosted = (
        m.vendor_invoice_status === 'Posted' ||
        !!m.journal_entry_id ||
        !!m.journal_reference
    );
    // Once a journal is reversed (REV-* journal exists, original carries
    // ``is_reversed=True``), no further reversal is possible. The
    // backend serializer surfaces this via the journal it references; we
    // also accept an explicit ``journal_is_reversed`` flag if the
    // serializer adds one in future.
    const isAlreadyReversed = !!journal?.is_reversed || !!m.journal_is_reversed;
    const canMatchOverride = status === 'Variance';
    const canReject        = !['Approved', 'Rejected'].includes(status) && !isAlreadyPosted;
    const canSubmit        = status === 'Matched';
    const canPost          = ['Matched', 'Approved'].includes(status) && !isAlreadyPosted;
    // Reverse is the ONLY corrective action available once posted.
    const canReverse       = isAlreadyPosted && !isAlreadyReversed;

    const handleMatch = async () => {
        const reason = await showPrompt('Enter variance reason (required for override):');
        if (!reason) return;
        matchMutation.mutate({ id: matchingId!, variance_reason: reason }, {
            onSuccess: () => flash('Variance overridden — invoice matched.'),
            onError: (err: any) => flash(err?.response?.data?.error || 'Failed to match', false),
        });
    };
    const handleReject = async () => {
        const reason = await showPrompt('Enter rejection reason:');
        if (!reason) return;
        rejectMutation.mutate({ id: matchingId!, reason }, {
            onSuccess: () => flash('Verification rejected.'),
            onError: (err: any) => flash(err?.response?.data?.error || 'Failed to reject', false),
        });
    };
    const handleSubmit = () => {
        submitMutation.mutate(matchingId!, {
            onSuccess: (data: any) => flash(data?.status || 'Submitted for approval.'),
            onError: (err: any) => flash(err?.response?.data?.error || 'Failed to submit', false),
        });
    };
    const handlePost = () => {
        postMutation.mutate(matchingId!, {
            onSuccess: (data: any) => flash(
                data?.journal_reference
                    ? `Posted to GL. Journal: ${data.journal_reference}`
                    : 'Invoice posted to GL.',
            ),
            onError: (err: any) => flash(err?.response?.data?.error || 'Failed to post', false),
        });
    };
    const handleReverse = async () => {
        const reason = await showPrompt(
            'Enter reversal reason (required — recorded on the audit trail):',
        );
        if (!reason) return;
        reverseMutation.mutate({ id: matchingId!, reason }, {
            onSuccess: (data: any) => flash(
                data?.reversal_journal_reference
                    ? `Reversed. Reversing journal: ${data.reversal_journal_reference}`
                    : 'Invoice verification reversed.',
            ),
            onError: (err: any) => flash(
                err?.response?.data?.error || 'Failed to reverse', false,
            ),
        });
    };

    return (
        <AccountingLayout>
            <PageHeader
                title={`Invoice Verification ${m.verification_number || `IV-${m.id}`}`}
                subtitle={
                    `Vendor Invoice: ${m.invoice_reference || '—'} · `
                    + `PO ${m.po_number || ''} — ${m.vendor_name || 'Vendor'}`
                }
                icon={<Receipt size={22} />}
                onBack={() => navigate('/procurement/matching')}
                actions={
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {canMatchOverride && (
                            <button onClick={handleMatch} disabled={matchMutation.isPending} style={hdrBtn.warn}>
                                <CheckCircle size={16} /> Override Variance
                            </button>
                        )}
                        {canSubmit && (
                            <button onClick={handleSubmit} disabled={submitMutation.isPending} style={hdrBtn.info}>
                                <Send size={16} /> {submitMutation.isPending ? 'Submitting…' : 'Submit for Approval'}
                            </button>
                        )}
                        {canPost && (
                            <button onClick={handlePost} disabled={postMutation.isPending} style={hdrBtn.success}>
                                <CheckCircle size={16} /> {postMutation.isPending ? 'Posting…' : 'Post to GL'}
                            </button>
                        )}
                        {canReverse && (
                            <button onClick={handleReverse} disabled={reverseMutation.isPending} style={hdrBtn.warn}>
                                <RotateCcw size={16} /> {reverseMutation.isPending ? 'Reversing…' : 'Reverse'}
                            </button>
                        )}
                        {canReject && (
                            <button onClick={handleReject} disabled={rejectMutation.isPending} style={hdrBtn.dangerOutline}>
                                <XCircle size={16} /> Reject
                            </button>
                        )}
                    </div>
                }
            />

            {toast && (
                <div style={{
                    padding: '0.75rem 1rem', marginBottom: '1.25rem', borderRadius: '8px',
                    background: toast.ok ? '#ecfdf5' : '#fef2f2',
                    border: `1px solid ${toast.ok ? '#a7f3d0' : '#fecaca'}`,
                    color: toast.ok ? '#065f46' : '#991b1b',
                    fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem',
                }}>
                    {toast.ok ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
                    {toast.msg}
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1.5rem', alignItems: 'start' }}>
                {/* LEFT */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                    {/* Header card with status + invoice basics */}
                    <div className="card" style={{ padding: '1.75rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                            <div>
                                <div style={{
                                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                    padding: '0.25rem 0.7rem', borderRadius: '999px',
                                    background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
                                    fontSize: 'var(--text-xs)', fontWeight: 700, marginBottom: '0.6rem',
                                }}>
                                    <Receipt size={12} />
                                    {cfg.label}
                                </div>
                                <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700 }}>{m.invoice_reference}</h2>
                                <p style={{ margin: '0.2rem 0 0', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                    {m.notes || 'No notes'}
                                </p>
                            </div>
                            {m.payment_hold && (
                                <div style={{
                                    padding: '0.4rem 0.7rem', background: '#fef2f2',
                                    border: '1px solid #fecaca', borderRadius: '6px',
                                    color: '#b91c1c', fontSize: 'var(--text-xs)', fontWeight: 700,
                                    display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
                                }}>
                                    <AlertTriangle size={12} /> PAYMENT HOLD
                                </div>
                            )}
                        </div>

                        <div style={{
                            display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem',
                            marginTop: '1.5rem', paddingTop: '1.25rem', borderTop: '1px solid var(--color-border)',
                        }}>
                            <DetailRow icon={<FileText size={14} />} label="PO Number" value={m.po_number || '—'} />
                            <DetailRow icon={<FileText size={14} />} label="GRN Number" value={m.grn_number || '—'} />
                            <DetailRow icon={<Building2 size={14} />} label="Vendor" value={m.vendor_name || '—'} />
                            <DetailRow icon={<Calendar size={14} />} label="Invoice Date" value={m.invoice_date ? new Date(m.invoice_date).toLocaleDateString() : '—'} />
                            <DetailRow icon={<Scale size={14} />} label="Match Type" value={m.match_type || 'None'} />
                            <DetailRow icon={<Calendar size={14} />} label="Matched Date" value={m.matched_date ? new Date(m.matched_date).toLocaleDateString() : '—'} />
                        </div>
                    </div>

                    {/* Three-way comparison card */}
                    <div className="card" style={{ padding: '1.75rem' }}>
                        <h3 style={{ margin: '0 0 1rem', fontSize: 'var(--text-base)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Scale size={16} color="#4f46e5" /> Three-Way Match
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                            <ComparisonCard label="Purchase Order" sublabel="Committed" amount={poAmount} formatter={formatCurrency} />
                            <ComparisonCard label="Goods Received" sublabel="Posted GRN" amount={grnAmount} formatter={formatCurrency} />
                            <ComparisonCard label="Vendor Invoice" sublabel="Billed" amount={invoiceAmount} formatter={formatCurrency} highlight />
                        </div>

                        {/* Variance breakdown */}
                        {(variance !== 0 || variancePct !== 0) && (
                            <div style={{
                                marginTop: '1.25rem', padding: '0.875rem 1rem',
                                background: m.payment_hold ? '#fef2f2' : '#fffbeb',
                                border: `1px solid ${m.payment_hold ? '#fecaca' : '#fde68a'}`,
                                borderRadius: '8px',
                                display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: '1rem', alignItems: 'center',
                            }}>
                                {variance >= 0
                                    ? <TrendingUp size={20} color={m.payment_hold ? '#dc2626' : '#d97706'} />
                                    : <TrendingDown size={20} color="#059669" />}
                                <div>
                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: m.payment_hold ? '#991b1b' : '#92400e' }}>
                                        Variance: {formatCurrency(Math.abs(variance))}
                                        <span style={{ marginLeft: '0.4rem', fontWeight: 500, opacity: 0.85 }}>
                                            ({variancePct.toFixed(2)}% of PO)
                                        </span>
                                    </div>
                                    {m.variance_reason && (
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.2rem' }}>
                                            Reason: {m.variance_reason}
                                        </div>
                                    )}
                                </div>
                                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                                    Threshold: 5%
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Invoice breakdown */}
                    <div className="card" style={{ padding: '1.75rem' }}>
                        <h3 style={{ margin: '0 0 1rem', fontSize: 'var(--text-base)', fontWeight: 700 }}>Invoice Breakdown</h3>
                        <table style={{ width: '100%', fontSize: 'var(--text-sm)' }}>
                            <tbody>
                                <BreakdownRow label="Subtotal (net of tax)" value={formatCurrency(subtotal)} />
                                <BreakdownRow label="Tax / VAT" value={formatCurrency(taxAmount)} />
                                <BreakdownRow label="Invoice Total" value={formatCurrency(invoiceAmount)} bold />
                                {downPayment > 0 && (
                                    <BreakdownRow
                                        label="Less: Down Payment Applied"
                                        value={`− ${formatCurrency(downPayment)}`}
                                        muted
                                    />
                                )}
                                <BreakdownRow label="Net Payable" value={formatCurrency(netPayable)} bold accent />
                            </tbody>
                        </table>
                    </div>

                    {/* Posted GL Entries — visible once Post to GL has run */}
                    {journalId && journal && Array.isArray(journal.lines) && journal.lines.length > 0 && (
                        <PostedGlEntries
                            journal={journal}
                            formatCurrency={formatCurrency}
                        />
                    )}
                </div>

                {/* RIGHT — workflow next-step card */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    <NextStepCard
                        status={status}
                        payment_hold={!!m.payment_hold}
                        isAlreadyPosted={isAlreadyPosted}
                        isAlreadyReversed={isAlreadyReversed}
                    />

                    {/* What happens on Post */}
                    {canPost && (
                        <div className="card" style={{ padding: '1.25rem' }}>
                            <h4 style={{ margin: '0 0 0.6rem', fontSize: 'var(--text-sm)', fontWeight: 700 }}>
                                What "Post to GL" does
                            </h4>
                            <ul style={{ margin: 0, paddingLeft: '1.1rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', lineHeight: 1.7 }}>
                                <li>Locates the linked Vendor Invoice (auto-created at GRN time)</li>
                                <li>Refreshes its amounts from this verification</li>
                                <li>Posts journal: <strong>DR GR/IR Clearing / CR Accounts Payable</strong></li>
                                <li>Posts tax + WHT lines if applicable</li>
                                <li>Closes the budget commitment <strong>INVOICED → CLOSED</strong></li>
                                <li>Liability sits on AP until the Payment Voucher pays it</li>
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </AccountingLayout>
    );
}

// ── Tiny presentational helpers ──────────────────────────────────────────────

interface JournalLineDto {
    id: number;
    account_code?: string;
    account_name?: string;
    debit?: string | number | null;
    credit?: string | number | null;
    memo?: string | null;
}

interface JournalDto {
    id: number;
    document_number?: string | null;
    reference_number?: string | null;
    posting_date?: string | null;
    description?: string | null;
    lines: JournalLineDto[];
    total_debit?: string | number | null;
    total_credit?: string | number | null;
}

interface PostedGlEntriesProps {
    journal: JournalDto;
    formatCurrency: (v: number) => string;
}

function PostedGlEntries({ journal, formatCurrency }: PostedGlEntriesProps) {
    const lines = journal.lines || [];
    const totalDr = lines.reduce(
        (sum, l) => sum + (parseFloat(String(l.debit ?? 0)) || 0), 0,
    );
    const totalCr = lines.reduce(
        (sum, l) => sum + (parseFloat(String(l.credit ?? 0)) || 0), 0,
    );
    const balanced = Math.abs(totalDr - totalCr) < 0.005;
    const journalRef =
        journal.document_number || journal.reference_number || `JV-${journal.id}`;
    const postingDate = journal.posting_date
        ? new Date(journal.posting_date).toLocaleDateString('en-GB')
        : '';

    return (
        <div className="card" style={{ padding: '1.75rem' }}>
            <div style={{
                display: 'flex', justifyContent: 'space-between',
                alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem',
            }}>
                <h3 style={{
                    margin: 0, fontSize: 'var(--text-base)', fontWeight: 700,
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                }}>
                    <FileText size={16} color="#4f46e5" />
                    Posted GL Entries
                </h3>
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '0.75rem',
                    fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)',
                }}>
                    <span>
                        Journal: <strong style={{ color: 'var(--color-text)' }}>{journalRef}</strong>
                    </span>
                    {postingDate && <span>Posted: <strong style={{ color: 'var(--color-text)' }}>{postingDate}</strong></span>}
                    <span style={{
                        padding: '0.15rem 0.55rem', borderRadius: '999px',
                        background: balanced ? '#dcfce7' : '#fef2f2',
                        color: balanced ? '#15803d' : '#b91c1c',
                        border: `1px solid ${balanced ? '#86efac' : '#fecaca'}`,
                        fontWeight: 700,
                    }}>
                        {balanced ? 'Balanced' : 'Out of balance'}
                    </span>
                </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', fontSize: 'var(--text-sm)', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{
                            background: 'rgba(148, 163, 184, 0.08)',
                            borderBottom: '1px solid var(--color-border)',
                        }}>
                            <th style={glHeader}>GL Code</th>
                            <th style={glHeader}>Account</th>
                            <th style={glHeader}>Memo</th>
                            <th style={{ ...glHeader, textAlign: 'right' }}>Debit</th>
                            <th style={{ ...glHeader, textAlign: 'right' }}>Credit</th>
                        </tr>
                    </thead>
                    <tbody>
                        {lines.map((line) => {
                            const dr = parseFloat(String(line.debit ?? 0)) || 0;
                            const cr = parseFloat(String(line.credit ?? 0)) || 0;
                            return (
                                <tr key={line.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <td style={{ ...glCell, fontFamily: 'monospace', fontWeight: 600 }}>
                                        {line.account_code || '—'}
                                    </td>
                                    <td style={glCell}>{line.account_name || '—'}</td>
                                    <td style={{ ...glCell, color: 'var(--color-text-muted)' }}>
                                        {line.memo || '—'}
                                    </td>
                                    <td style={{ ...glCell, textAlign: 'right', fontFamily: 'monospace' }}>
                                        {dr > 0 ? formatCurrency(dr) : ''}
                                    </td>
                                    <td style={{ ...glCell, textAlign: 'right', fontFamily: 'monospace' }}>
                                        {cr > 0 ? formatCurrency(cr) : ''}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                    <tfoot>
                        <tr style={{
                            background: 'rgba(79, 70, 229, 0.04)',
                            borderTop: '2px solid var(--color-border)',
                        }}>
                            <td style={{ ...glCell, fontWeight: 700 }} colSpan={3}>Total</td>
                            <td style={{ ...glCell, textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                {formatCurrency(totalDr)}
                            </td>
                            <td style={{ ...glCell, textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                {formatCurrency(totalCr)}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    );
}

const glHeader: React.CSSProperties = {
    padding: '0.6rem 0.75rem', textAlign: 'left',
    fontSize: 'var(--text-xs)', textTransform: 'uppercase',
    letterSpacing: '0.05em', color: 'var(--color-text-muted)', fontWeight: 700,
};
const glCell: React.CSSProperties = {
    padding: '0.55rem 0.75rem', verticalAlign: 'top',
};

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', marginBottom: '0.25rem', fontWeight: 600 }}>
                {icon}
                {label}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                {value}
            </div>
        </div>
    );
}

function ComparisonCard({ label, sublabel, amount, formatter, highlight }: {
    label: string; sublabel: string; amount: number; formatter: (v: number) => string; highlight?: boolean;
}) {
    return (
        <div style={{
            padding: '1rem', borderRadius: '10px',
            background: highlight ? 'rgba(79, 70, 229, 0.06)' : 'rgba(148, 163, 184, 0.06)',
            border: `1px solid ${highlight ? 'rgba(79, 70, 229, 0.25)' : 'var(--color-border)'}`,
            textAlign: 'center',
        }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)', marginBottom: '0.2rem' }}>
                {label}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginBottom: '0.6rem' }}>
                {sublabel}
            </div>
            <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: highlight ? '#4f46e5' : 'var(--color-text)' }}>
                {formatter(amount)}
            </div>
        </div>
    );
}

function BreakdownRow({ label, value, bold, muted, accent }: {
    label: string; value: string; bold?: boolean; muted?: boolean; accent?: boolean;
}) {
    return (
        <tr>
            <td style={{
                padding: '0.4rem 0', color: muted ? 'var(--color-text-muted)' : 'inherit',
                fontWeight: bold ? 600 : 400,
            }}>{label}</td>
            <td style={{
                padding: '0.4rem 0', textAlign: 'right', fontFamily: 'monospace',
                fontWeight: bold ? 700 : 500,
                color: accent ? '#4f46e5' : (muted ? 'var(--color-text-muted)' : 'inherit'),
                borderTop: accent ? '1px solid var(--color-border)' : 'none',
            }}>{value}</td>
        </tr>
    );
}

interface NextStepCardProps {
    status: string;
    payment_hold: boolean;
    isAlreadyPosted: boolean;
    isAlreadyReversed: boolean;
}

function NextStepCard({ status, payment_hold, isAlreadyPosted, isAlreadyReversed }: NextStepCardProps) {
    let title = 'Next step';
    let body = '';
    let bg = 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)';

    // Highest-priority states: Reversed > Posted > status-based.
    if (isAlreadyReversed) {
        title = 'Reversed';
        body = 'This verification was reversed. The reversing journal is on the books; no further action is available on this record.';
        bg = 'linear-gradient(135deg, #6b7280 0%, #9ca3af 100%)';
    } else if (isAlreadyPosted) {
        title = 'Posted';
        body = 'This invoice has been posted to the GL. It cannot be posted again. The only corrective action is to Reverse — that writes a REV-* journal and reopens the budget commitment.';
        bg = 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)';
    } else if (status === 'Draft') {
        body = 'Calculate the match to compare PO/GRN/Invoice and assign a status.';
    } else if (status === 'Matched') {
        body = 'Click "Submit for Approval" to route this to finance. Small invoices auto-approve.';
    } else if (status === 'Pending_Review') {
        body = 'Awaiting finance approval. Once approved, you can post to the GL.';
        bg = 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)';
    } else if (status === 'Variance') {
        title = 'Action required';
        body = payment_hold
            ? 'Variance exceeds the 5% threshold. Either override with a reason or reject the invoice.'
            : 'Variance is within tolerance. You can override with a reason to proceed.';
        bg = 'linear-gradient(135deg, #dc2626 0%, #ef4444 100%)';
    } else if (status === 'Approved') {
        body = 'Click "Post to GL" to clear the GR/IR accrual, recognise AP, and close the commitment.';
        bg = 'linear-gradient(135deg, #059669 0%, #10b981 100%)';
    } else if (status === 'Rejected') {
        body = 'This verification was rejected. No further action available.';
        bg = 'linear-gradient(135deg, #6b7280 0%, #9ca3af 100%)';
    }
    return (
        <div style={{ borderRadius: '12px', padding: '1.5rem', background: bg, color: '#fff' }}>
            <p style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '0.5rem', opacity: 0.85 }}>
                {title}
            </p>
            <p style={{ fontSize: 'var(--text-sm)', lineHeight: 1.5 }}>{body}</p>
        </div>
    );
}

const baseHdrBtn: React.CSSProperties = {
    padding: '0.6rem 1.25rem', fontWeight: 600, borderRadius: '8px', cursor: 'pointer',
    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
};
const hdrBtn = {
    success: { ...baseHdrBtn, background: '#22c55e', color: 'white', border: '1px solid rgba(255,255,255,0.25)' },
    info:    { ...baseHdrBtn, background: '#2471a3', color: 'white', border: '1px solid rgba(255,255,255,0.25)' },
    warn:    { ...baseHdrBtn, background: '#f59e0b', color: 'white', border: '1px solid rgba(255,255,255,0.25)' },
    dangerOutline: { ...baseHdrBtn, background: 'rgba(255,255,255,0.18)', color: 'white', border: '1px solid rgba(255,255,255,0.25)' },
} as const;
