import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Save, X, Plus, Trash2, AlertCircle, Banknote } from 'lucide-react';
import apiClient from '../../../api/client';
import SearchableSelect from '../../../components/SearchableSelect';
import AmountInput from '../../../components/AmountInput';
import PageHeader from '../../../components/PageHeader';
import { useToast } from '../../../context/ToastContext';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '@/utils/date';
import AccountingLayout from '../AccountingLayout';
import { useDimensions } from '../hooks/useJournal';
import {
    useCreatePaymentDocument,
    usePostPaymentDocument,
    type PaymentDocumentLineInput,
} from '../hooks/usePaymentDocuments';

/**
 * Payment Document form — SAP F-53–style multi-line outgoing payment.
 *
 * Mirrors ``JournalForm`` for the DR/CR line grid, then adds the pieces a
 * payment needs: a header **bank account** (the single credit / cash out),
 * an optional **vendor** per line (settles that vendor's sub-ledger), a live
 * "Net to bank" = Σdebit − Σcredit total, and a **Post & Pay** action that
 * saves the draft then posts it through the gated API.
 */

interface PDLine {
    id: string;
    account: string;
    vendor: string;
    debit: string;
    credit: string;
    memo: string;
}

// Shape used by the account/dimension pickers (mirror JournalForm's toCodeOptions).
type Coded = { id: number | string; code?: string; name?: string };

interface BankAccountRow {
    id: number | string;
    account_name?: string;
    account_number?: string;
    bank_name?: string;
}

interface VendorRow {
    id: number | string;
    name?: string;
    code?: string;
}

const blankLine = (): PDLine => ({
    id: crypto.randomUUID(),
    account: '',
    vendor: '',
    debit: '0',
    credit: '0',
    memo: '',
});

function useBankAccounts() {
    return useQuery<BankAccountRow[]>({
        queryKey: ['bank-accounts-dropdown'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/bank-accounts/', { params: { page_size: 1000 } });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: 5 * 60 * 1000,
    });
}

function useVendors() {
    return useQuery<VendorRow[]>({
        queryKey: ['vendors-dropdown'],
        queryFn: async () => {
            const { data } = await apiClient.get('/procurement/vendors/', { params: { page_size: 1000, is_active: true } });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: 5 * 60 * 1000,
    });
}

/** Pull a clean, user-facing message from an API error, falling back gracefully. */
function extractError(err: unknown, fallback: string): string {
    const apiMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
    if (apiMsg) return apiMsg;
    return err instanceof Error ? err.message : fallback;
}

export default function PaymentDocumentForm() {
    const navigate = useNavigate();
    const { addToast } = useToast();
    const { formatCurrency } = useCurrency();

    const { data: banks = [] } = useBankAccounts();
    const { data: vendors = [] } = useVendors();
    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const createDoc = useCreatePaymentDocument();
    const postDoc = usePostPaymentDocument();

    const [bankAccount, setBankAccount] = useState('');
    const [description, setDescription] = useState('');
    const [referenceNumber, setReferenceNumber] = useState('');
    const [lines, setLines] = useState<PDLine[]>([blankLine(), blankLine()]);

    // Pickers — pre-sort by code and shape for SearchableSelect (mirror JournalForm).
    const toCodeOptions = (list: Coded[]) =>
        [...list]
            .sort((a, b) => (a.code ?? '').localeCompare(b.code ?? '', undefined, { numeric: true }))
            .map((x) => ({
                value: String(x.id),
                label: x.code ? `${x.code} — ${x.name ?? ''}` : (x.name ?? ''),
                sublabel: x.code ? x.name : undefined,
            }));

    const accountOptions = useMemo(() => toCodeOptions((dims?.accounts ?? []) as Coded[]), [dims?.accounts]);

    const bankOptions = useMemo(
        () =>
            [...banks].map((b) => ({
                value: String(b.id),
                label: b.account_number ? `${b.account_name ?? ''} — ${b.account_number}` : (b.account_name ?? ''),
                sublabel: b.bank_name,
            })),
        [banks],
    );

    const vendorOptions = useMemo(
        () =>
            [...vendors].map((v) => ({
                value: String(v.id),
                label: v.code ? `${v.code} — ${v.name ?? ''}` : (v.name ?? ''),
                sublabel: v.code ? v.name : undefined,
            })),
        [vendors],
    );

    const totalDebit = lines.reduce((sum, l) => sum + (parseFloat(l.debit) || 0), 0);
    const totalCredit = lines.reduce((sum, l) => sum + (parseFloat(l.credit) || 0), 0);
    const net = totalDebit - totalCredit; // credited to the header bank (cash out)

    const validLines = lines.filter(
        (l) => l.account && ((parseFloat(l.debit) || 0) > 0 || (parseFloat(l.credit) || 0) > 0),
    );
    const canSaveDraft = !!bankAccount && validLines.length > 0 && !createDoc.isPending && !postDoc.isPending;
    const canPostAndPay = canSaveDraft && net > 0;

    const addLine = () => setLines((prev) => [...prev, blankLine()]);
    const removeLine = (index: number) => setLines((prev) => prev.filter((_, i) => i !== index));
    const updateLine = (index: number, field: keyof PDLine, value: string) =>
        setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));

    const buildPayload = () => ({
        bank_account: bankAccount,
        description,
        reference_number: referenceNumber,
        lines: validLines.map<PaymentDocumentLineInput>((l) => ({
            account: l.account,
            vendor: l.vendor || null,
            debit: String(parseFloat(l.debit) || 0),
            credit: String(parseFloat(l.credit) || 0),
            memo: l.memo,
        })),
    });

    const onSaveDraft = async () => {
        try {
            await createDoc.mutateAsync(buildPayload());
            addToast('Draft saved', 'success');
            navigate('/accounting/payment-documents');
        } catch (err: unknown) {
            addToast(extractError(err, 'Save failed'), 'error');
        }
    };

    const onPostAndPay = async () => {
        // Save the draft, then post it — the confirm guards a real cash movement.
        if (!window.confirm('Post & Pay — this credits the bank and moves funds. Continue?')) return;
        try {
            const created = await createDoc.mutateAsync(buildPayload());
            await postDoc.mutateAsync(created.id);
            addToast('Payment document posted', 'success');
            navigate('/accounting/payment-documents');
        } catch (err: unknown) {
            addToast(extractError(err, 'Post failed'), 'error');
        }
    };

    if (dimsLoading) {
        return <AccountingLayout><div>Loading dimensions...</div></AccountingLayout>;
    }

    return (
        <AccountingLayout>
            <form onSubmit={(e) => { e.preventDefault(); if (canSaveDraft) void onSaveDraft(); }}>
                <PageHeader
                    title="New Payment Document"
                    subtitle="A multi-line outgoing payment. The header bank account is the single credit (cash out); lines are the debit/credit legs."
                    icon={<Banknote size={22} />}
                    actions={
                        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                            <button type="button" className="btn btn-outline" onClick={() => navigate('/accounting/payment-documents')}>
                                <X size={18} /> Cancel
                            </button>
                            <button type="submit" className="btn btn-outline" disabled={!canSaveDraft}>
                                <Save size={18} /> Save Draft
                            </button>
                            <button type="button" className="btn btn-primary" onClick={onPostAndPay} disabled={!canPostAndPay}>
                                <Banknote size={18} /> Post &amp; Pay
                            </button>
                        </div>
                    }
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
                    <div className="card">
                        <label className="label">Bank Account<span className="required-mark"> *</span></label>
                        <SearchableSelect
                            options={bankOptions}
                            value={bankAccount}
                            onChange={setBankAccount}
                            placeholder="Search bank account…"
                            required
                        />
                    </div>
                    <div className="card">
                        <label className="label">Document Date</label>
                        <input type="text" value={formatDate(new Date())} readOnly disabled />
                    </div>
                    <div className="card">
                        <label className="label">Reference #</label>
                        <input type="text" placeholder="e.g. PAY-2026-001" value={referenceNumber} onChange={(e) => setReferenceNumber(e.target.value)} />
                    </div>
                    <div className="card" style={{ gridColumn: 'span 2' }}>
                        <label className="label">Description</label>
                        <input type="text" placeholder="Purpose of this payment" value={description} onChange={(e) => setDescription(e.target.value)} />
                    </div>
                </div>

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    {/* Horizontal scroll on narrow viewports keeps the line columns
                        readable rather than squashing dropdowns into tiny cells. */}
                    <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                            <thead>
                                <tr style={{ background: 'var(--background)', textAlign: 'left' }}>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>GL Account</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '220px' }} title="Tag this line to a Vendor to settle that vendor's sub-ledger">
                                        Vendor <span style={{ fontWeight: 400, color: 'var(--color-text-muted)' }}>(optional)</span>
                                    </th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '150px' }}>Debit</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '150px' }}>Credit</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Memo</th>
                                    <th style={{ padding: '1rem', width: '50px' }}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {lines.map((line, idx) => (
                                    <tr key={line.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                        <td style={{ padding: '0.75rem' }}>
                                            <SearchableSelect
                                                options={accountOptions}
                                                value={line.account}
                                                onChange={(v) => updateLine(idx, 'account', v)}
                                                placeholder="Search code or name…"
                                                required
                                            />
                                        </td>
                                        <td style={{ padding: '0.75rem' }}>
                                            <SearchableSelect
                                                options={vendorOptions}
                                                value={line.vendor}
                                                onChange={(v) => updateLine(idx, 'vendor', v)}
                                                placeholder="— No vendor —"
                                            />
                                        </td>
                                        <td style={{ padding: '0.75rem' }}>
                                            <AmountInput value={line.debit} onChange={(v) => updateLine(idx, 'debit', v)} />
                                        </td>
                                        <td style={{ padding: '0.75rem' }}>
                                            <AmountInput value={line.credit} onChange={(v) => updateLine(idx, 'credit', v)} />
                                        </td>
                                        <td style={{ padding: '0.75rem' }}>
                                            <input type="text" placeholder="Line memo" value={line.memo} onChange={(e) => updateLine(idx, 'memo', e.target.value)} />
                                        </td>
                                        <td style={{ padding: '0.75rem' }}>
                                            {lines.length > 2 && (
                                                <button type="button" onClick={() => removeLine(idx)} style={{ color: 'var(--error)', background: 'none', border: 'none', cursor: 'pointer' }}>
                                                    <Trash2 size={18} />
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot>
                                <tr style={{ background: 'var(--surface)' }}>
                                    <td style={{ padding: '1rem' }}>
                                        <button type="button" className="btn btn-outline" style={{ fontSize: 'var(--text-xs)' }} onClick={addLine}>
                                            <Plus size={14} /> Add Line
                                        </button>
                                    </td>
                                    <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>Totals</td>
                                    <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(totalDebit)}</td>
                                    <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(totalCredit)}</td>
                                    <td colSpan={2} style={{ padding: '1rem' }} />
                                </tr>
                                <tr style={{ background: 'var(--surface)' }}>
                                    <td colSpan={2} style={{ padding: '1rem', fontWeight: 700 }}>Net to bank (cash out)</td>
                                    <td colSpan={2} style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', color: net > 0 ? 'var(--primary)' : 'var(--error)' }}>
                                        {formatCurrency(net)}
                                    </td>
                                    <td colSpan={2} style={{ padding: '1rem' }}>
                                        {net <= 0 && (
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--error)', fontSize: 'var(--text-xs)' }}>
                                                <AlertCircle size={14} /> Net to bank must be positive to Post &amp; Pay
                                            </div>
                                        )}
                                    </td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                </div>
            </form>
            <style>{`
                .label {
                    display: block;
                    margin-bottom: 0.5rem;
                    font-size: 0.75rem;
                    font-weight: 600;
                    text-transform: uppercase;
                    color: var(--text-muted);
                }
            `}</style>
        </AccountingLayout>
    );
}
