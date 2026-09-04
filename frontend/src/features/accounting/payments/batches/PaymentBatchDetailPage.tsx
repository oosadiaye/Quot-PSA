import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Printer, Send, CheckCircle, XCircle, Trash2 } from 'lucide-react';
import AccountingLayout from '../../AccountingLayout';
import PageHeader from '../../../../components/PageHeader';
import StatusBadge from '../../components/shared/StatusBadge';
import { useCurrency } from '../../../../context/CurrencyContext';
import {
    useCancelBatch, useConfirmBatch, useDispatchBatch, usePaymentBatch,
    useRemoveBatchLine, type PaymentBatchLine,
} from '../../hooks/usePaymentBatches';

interface SoDViolationPayload {
    rule_code: string;
    rule_name: string;
    reason: string;
}

function apiError(e: unknown): string {
    const r = (e as {
        response?: {
            data?: { error?: string; code?: string; violations?: SoDViolationPayload[] };
        };
    }).response;
    const data = r?.data;

    // Segregation-of-duties refusals name the rule that blocked the action.
    // Which rules apply is tenant configuration — an admin can deactivate or
    // re-scope any of them on the SoD rules page — so a generic "forbidden"
    // would leave the operator with no idea what to change or who to ask.
    if (data?.code === 'sod_violation' && data.violations?.length) {
        const rules = data.violations
            .map((v) => `${v.rule_name} (${v.rule_code})`)
            .join('; ');
        return `Blocked by segregation of duties — ${rules}. `
            + 'Another officer must perform this step, or an administrator can '
            + 'adjust the rule under Admin → SoD Rules.';
    }

    return data?.error || 'The operation failed. Please try again.';
}

function formatDate(iso: string | null): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB');
}

const th: React.CSSProperties = {
    padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#64748b',
    fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap',
};
const td: React.CSSProperties = { padding: '11px 14px', fontSize: '13px', color: '#334155' };

const btnBase: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: '6px',
    padding: '9px 16px', borderRadius: '9px', fontWeight: 700, fontSize: '13px',
    cursor: 'pointer', fontFamily: 'inherit', border: 'none',
};
const ghostBtn: React.CSSProperties = {
    ...btnBase, border: '1px solid #e2e8f0', background: '#fff', color: '#334155',
};

export default function PaymentBatchDetailPage() {
    const { id } = useParams<{ id: string }>();
    const batchId = Number(id);
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
    // Which justification dialog is open, if any. Both actions used to fire
    // straight through — cancel sent the literal string 'Cancelled by
    // operator', which satisfied the server's "reason required" check
    // without anyone ever explaining anything. A control the UI answers on
    // the operator's behalf is not a control.
    const [prompt, setPrompt] = useState<'confirm' | 'cancel' | null>(null);
    const [promptText, setPromptText] = useState('');

    const { data: batch, isLoading } = usePaymentBatch(batchId);
    const removeLine = useRemoveBatchLine(batchId);
    const dispatchBatch = useDispatchBatch(batchId);
    const confirmBatch = useConfirmBatch(batchId);
    const cancelBatch = useCancelBatch(batchId);

    if (isLoading || !batch) {
        return (
            <AccountingLayout>
                <PageHeader title="Payment Batch" subtitle="Treasury · Bank Payment Letter" />
                <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
                    Loading batch…
                </div>
            </AccountingLayout>
        );
    }

    const isDraft = batch.status === 'Draft';
    const lines = batch.lines.filter((l) => l.is_active_membership);

    const run = (p: Promise<unknown>, ok: string) =>
        p.then(() => setNotice({ kind: 'ok', text: ok }))
            .catch((e) => setNotice({ kind: 'err', text: apiError(e) }));

    const meta: { label: string; value: string; mono?: boolean }[] = [
        { label: 'Bank', value: batch.addressee_bank_name || '—' },
        { label: 'Account No.', value: batch.addressee_account_no || '—', mono: true },
        { label: 'Batch Date', value: formatDate(batch.batch_date) },
        { label: 'Lines', value: String(batch.line_count) },
        { label: 'Dispatched', value: formatDate(batch.dispatched_at) },
        { label: 'Confirmed', value: formatDate(batch.confirmed_at) },
        // Only meaningful once confirmed; showing an empty slot before that
        // just adds a dash to scan past.
        ...(batch.bank_reference
            ? [{ label: 'Bank Ref.', value: batch.bank_reference, mono: true }]
            : []),
    ];

    return (
        <AccountingLayout>
            <PageHeader
                title={batch.batch_number}
                subtitle="Treasury · Bank Payment/Confirmation Letter"
            />

            {notice && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '10px',
                    background: notice.kind === 'ok' ? '#f0fdf4' : '#fef2f2',
                    border: `1px solid ${notice.kind === 'ok' ? '#86efac' : '#fca5a5'}`,
                    color: notice.kind === 'ok' ? '#166534' : '#991b1b',
                    borderRadius: '12px', padding: '12px 16px', marginBottom: '18px',
                    fontSize: '13px', fontWeight: 600,
                }}>
                    {notice.kind === 'ok' ? <CheckCircle size={16} /> : <XCircle size={16} />}
                    {notice.text}
                </div>
            )}

            {/* Header card: status + totals + actions */}
            <div style={{
                background: '#fff', borderRadius: '12px', padding: '20px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)', marginBottom: '20px',
            }}>
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '12px',
                    flexWrap: 'wrap', marginBottom: '18px',
                }}>
                    <StatusBadge status={batch.status} />
                    <div style={{ flex: 1 }} />
                    <div style={{ textAlign: 'right' }}>
                        <div style={{
                            fontSize: '11px', fontWeight: 700, color: '#94a3b8',
                            textTransform: 'uppercase', letterSpacing: '0.05em',
                        }}>Total</div>
                        <div style={{ fontSize: '24px', fontWeight: 800, color: '#dc2626' }}>
                            {formatCurrency(Number(batch.total_amount || 0))}
                        </div>
                    </div>
                </div>

                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))',
                    gap: '14px', paddingTop: '16px', borderTop: '1px solid #f1f5f9',
                }}>
                    {meta.map((m) => (
                        <div key={m.label}>
                            <div style={{
                                fontSize: '11px', fontWeight: 700, color: '#94a3b8',
                                textTransform: 'uppercase', letterSpacing: '0.05em',
                            }}>{m.label}</div>
                            <div style={{
                                fontSize: '14px', color: '#0f172a', fontWeight: 600,
                                marginTop: '3px',
                                fontFamily: m.mono ? 'monospace' : 'inherit',
                            }}>{m.value}</div>
                        </div>
                    ))}
                </div>

                <div style={{
                    display: 'flex', gap: '10px', flexWrap: 'wrap',
                    paddingTop: '18px', marginTop: '16px', borderTop: '1px solid #f1f5f9',
                }}>
                    <button
                        style={ghostBtn}
                        onClick={() => navigate(`/accounting/payment-batches/${batchId}/letter`)}
                    >
                        <Printer size={15} /> View letter
                    </button>
                    {isDraft && (
                        <button
                            style={{
                                ...btnBase,
                                background: 'linear-gradient(135deg,#f59e0b,#ea8c00)', color: '#fff',
                            }}
                            onClick={() => run(dispatchBatch.mutateAsync(), 'Batch dispatched to the bank')}
                        >
                            <Send size={15} /> Dispatch
                        </button>
                    )}
                    {batch.status === 'Dispatched' && (
                        <button
                            style={{
                                ...btnBase,
                                background: 'linear-gradient(135deg,#10b981,#059669)', color: '#fff',
                            }}
                            onClick={() => setPrompt('confirm')}
                        >
                            <CheckCircle size={15} /> Mark confirmed
                        </button>
                    )}
                    {batch.status !== 'Confirmed' && batch.status !== 'Cancelled' && (
                        <button
                            style={{ ...ghostBtn, color: '#dc2626', borderColor: '#fecaca' }}
                            onClick={() => setPrompt('cancel')}
                        >
                            <XCircle size={15} /> Cancel batch
                        </button>
                    )}
                </div>
            </div>

            {prompt && (
                <div
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="batch-prompt-title"
                    style={{
                        position: 'fixed', inset: 0, zIndex: 50,
                        background: 'rgba(15,23,42,0.45)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '20px',
                    }}
                    onClick={() => setPrompt(null)}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                            background: '#fff', borderRadius: '12px', padding: '22px',
                            width: '100%', maxWidth: '480px',
                            boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
                        }}
                    >
                        <h3 id="batch-prompt-title" style={{
                            margin: '0 0 6px', fontSize: '16px', fontWeight: 700, color: '#0f172a',
                        }}>
                            {prompt === 'confirm'
                                ? 'Record the bank confirmation'
                                : 'Why is this batch being cancelled?'}
                        </h3>
                        <p style={{ margin: '0 0 14px', fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
                            {prompt === 'confirm'
                                ? `Confirming ${batch.batch_number} is final — it can no longer be `
                                  + 'cancelled. Enter the advice or transaction reference the bank gave you.'
                                : batch.status === 'Dispatched'
                                    ? `${batch.batch_number} is already with ${batch.addressee_bank_name}. `
                                      + 'Confirm with the bank that it was not actioned before releasing '
                                      + 'these payments, and record what you were told.'
                                    : 'This releases the batch\'s payments back into the eligible pool.'}
                        </p>
                        <input
                            autoFocus
                            value={promptText}
                            onChange={(e) => setPromptText(e.target.value)}
                            placeholder={prompt === 'confirm'
                                ? 'e.g. FT26090400123456'
                                : 'e.g. Bank confirmed instruction not actioned — ref 4471'}
                            style={{
                                width: '100%', padding: '10px 12px', fontSize: '13px',
                                border: '1px solid #cbd5e1', borderRadius: '8px',
                                fontFamily: 'inherit', boxSizing: 'border-box',
                            }}
                        />
                        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '16px' }}>
                            <button style={ghostBtn} onClick={() => { setPrompt(null); setPromptText(''); }}>
                                Back
                            </button>
                            <button
                                disabled={!promptText.trim()}
                                style={{
                                    ...btnBase,
                                    background: promptText.trim()
                                        ? (prompt === 'confirm'
                                            ? 'linear-gradient(135deg,#10b981,#059669)'
                                            : 'linear-gradient(135deg,#ef4444,#dc2626)')
                                        : '#e2e8f0',
                                    color: promptText.trim() ? '#fff' : '#94a3b8',
                                    cursor: promptText.trim() ? 'pointer' : 'not-allowed',
                                }}
                                onClick={() => {
                                    const text = promptText.trim();
                                    const action = prompt === 'confirm'
                                        ? run(confirmBatch.mutateAsync({ bank_reference: text }),
                                            'Batch confirmed by the bank')
                                        : run(cancelBatch.mutateAsync({ reason: text }),
                                            'Batch cancelled — its payments are eligible again');
                                    action.finally(() => { setPrompt(null); setPromptText(''); });
                                }}
                            >
                                {prompt === 'confirm' ? 'Mark confirmed' : 'Cancel batch'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Lines */}
            <div style={{
                background: '#fff', borderRadius: '12px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden',
            }}>
                <div style={{ padding: '18px 20px' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                        Letter Lines
                    </h3>
                    <p style={{ margin: '3px 0 0', fontSize: '13px', color: '#64748b' }}>
                        Payee details are frozen as at the moment each payment was added
                    </p>
                </div>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: '#f8fafc' }}>
                                {['S/N', 'Vendor Name', 'Bank', 'Account', 'Purpose', 'Amount']
                                    .map(h => (
                                        <th key={h} style={{
                                            ...th, textAlign: h === 'Amount' ? 'right' : 'left',
                                        }}>{h}</th>
                                    ))}
                                {isDraft && <th style={th} />}
                            </tr>
                        </thead>
                        <tbody>
                            {lines.length === 0 && (
                                <tr><td colSpan={isDraft ? 7 : 6} style={{
                                    ...td, textAlign: 'center', padding: '36px', color: '#94a3b8',
                                }}>No lines on this batch.</td></tr>
                            )}
                            {lines.map((line: PaymentBatchLine) => (
                                <tr key={line.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                    <td style={{ ...td, width: '56px', color: '#94a3b8' }}>
                                        {line.sequence}
                                    </td>
                                    <td style={{ ...td, fontWeight: 600, color: '#0f172a' }}>
                                        {line.payee_name}
                                    </td>
                                    <td style={td}>{line.payee_bank}</td>
                                    <td style={{ ...td, fontFamily: 'monospace', color: '#3b82f6' }}>
                                        {line.payee_account}
                                    </td>
                                    <td style={td}>{line.purpose}</td>
                                    <td style={{
                                        ...td, textAlign: 'right', fontWeight: 700, color: '#dc2626',
                                    }}>
                                        {formatCurrency(Number(line.amount || 0))}
                                    </td>
                                    {isDraft && (
                                        <td style={{ ...td, textAlign: 'right' }}>
                                            <button
                                                title="Remove this line"
                                                style={{
                                                    display: 'inline-flex', alignItems: 'center',
                                                    padding: '5px 8px', borderRadius: '7px',
                                                    border: '1px solid #fecaca', background: '#fef2f2',
                                                    color: '#dc2626', cursor: 'pointer',
                                                }}
                                                onClick={() => run(
                                                    removeLine.mutateAsync({ line_id: line.id }),
                                                    'Line removed',
                                                )}
                                            >
                                                <Trash2 size={13} />
                                            </button>
                                        </td>
                                    )}
                                </tr>
                            ))}
                        </tbody>
                        {lines.length > 0 && (
                            <tfoot>
                                <tr style={{ background: '#f8fafc', borderTop: '2px solid #e2e8f0' }}>
                                    <td colSpan={5} style={{
                                        ...td, fontWeight: 700, color: '#0f172a',
                                    }}>Total</td>
                                    <td style={{
                                        ...td, textAlign: 'right', fontWeight: 800, color: '#dc2626',
                                        fontSize: '14px',
                                    }}>
                                        {formatCurrency(Number(batch.total_amount || 0))}
                                    </td>
                                    {isDraft && <td style={td} />}
                                </tr>
                            </tfoot>
                        )}
                    </table>
                </div>
            </div>
        </AccountingLayout>
    );
}
