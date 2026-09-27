import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Save, X, Plus, Trash2, AlertCircle, Banknote, ChevronDown, ChevronUp, Lock, ArrowLeft } from 'lucide-react';
import apiClient from '../../../api/client';
import SearchableSelect from '../../../components/SearchableSelect';
import AmountInput from '../../../components/AmountInput';
import PageHeader from '../../../components/PageHeader';
import { useToast } from '../../../context/ToastContext';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '@/utils/date';
import AccountingLayout from '../AccountingLayout';
import { useDimensions } from '../hooks/useJournal';
import { useMDAs } from '../hooks/useBudgetDimensions';
import {
    useCreatePaymentDocument,
    usePostPaymentDocument,
    usePaymentDocument,
    useUpdatePaymentDocument,
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

// Today's date as YYYY-MM-DD in the user's *local* timezone. ``toISOString()``
// converts to UTC first, which can roll the day backwards for users behind UTC
// (or WAT users in the late-evening UTC window) — so build it from local parts.
const todayLocalISO = (): string => {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
};

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

    // CREATE when there's no id (route /new); EDIT/DETAIL when an id is present
    // (route /:id). The literal "new" never reaches here — react-router ranks
    // the static /new segment above the dynamic /:id — but guard it anyway.
    const { id } = useParams<{ id?: string }>();
    const isEditMode = !!id && id !== 'new';

    const { data: banks = [] } = useBankAccounts();
    const { data: vendors = [] } = useVendors();
    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const createDoc = useCreatePaymentDocument();
    const postDoc = usePostPaymentDocument();
    const updateDoc = useUpdatePaymentDocument();
    const { data: existingDoc, isLoading: docLoading } = usePaymentDocument(isEditMode ? id : null);

    const [bankAccount, setBankAccount] = useState('');
    const [description, setDescription] = useState('');
    const [referenceNumber, setReferenceNumber] = useState('');
    const [documentDate, setDocumentDate] = useState(todayLocalISO());
    // Header-level appropriation. Required only when a line debits an Expense
    // account (the backend warrant gate fails closed with mda/fund = None for
    // expense debits); settlement-only documents leave these blank.
    const [mda, setMda] = useState('');
    const [fund, setFund] = useState('');
    const [showAppropriation, setShowAppropriation] = useState(false);
    const [lines, setLines] = useState<PDLine[]>([blankLine(), blankLine()]);
    // One-shot hydration guard — populate from the loaded doc only once so a
    // background refetch can't wipe in-progress edits (mirrors JournalForm).
    const [hydrated, setHydrated] = useState(false);

    // Retry safety: hold the id of the draft created by a Post & Pay attempt so
    // a failed post (MFA/warrant/period/network) that the operator retries posts
    // THAT draft instead of creating a second one. Cleared on a successful post,
    // on Save Draft, and whenever any payload-affecting field changes (below).
    const createdIdRef = useRef<number | string | null>(null);

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
    const fundOptions = useMemo(() => toCodeOptions((dims?.funds ?? []) as Coded[]), [dims?.funds]);
    const mdaOptions = useMemo(() => toCodeOptions(mdas as Coded[]), [mdas]);

    // Any change to a payload-affecting field invalidates a draft created by a
    // prior (failed) Post & Pay attempt, so the next attempt creates a fresh one.
    useEffect(() => {
        createdIdRef.current = null;
    }, [bankAccount, description, referenceNumber, documentDate, mda, fund, lines]);

    // Edit-mode hydration — runs once when the detail finishes loading. Maps the
    // server document (header + lines) into local form state. Runs for any
    // status (Draft or Posted/Void); the read-only branch below then decides
    // whether the fields are editable.
    useEffect(() => {
        if (!isEditMode || hydrated || !existingDoc) return;
        setBankAccount(existingDoc.bank_account != null ? String(existingDoc.bank_account) : '');
        setDescription(existingDoc.description ?? '');
        setReferenceNumber(existingDoc.reference_number ?? '');
        setDocumentDate(existingDoc.document_date || todayLocalISO());
        setMda(existingDoc.mda != null ? String(existingDoc.mda) : '');
        setFund(existingDoc.fund != null ? String(existingDoc.fund) : '');
        if (existingDoc.mda != null || existingDoc.fund != null) setShowAppropriation(true);
        const incoming = Array.isArray(existingDoc.lines) ? existingDoc.lines : [];
        if (incoming.length) {
            setLines(
                incoming.map((l) => ({
                    id: crypto.randomUUID(),
                    account: l.account != null ? String(l.account) : '',
                    vendor: l.vendor != null ? String(l.vendor) : '',
                    debit: String(l.debit ?? '0'),
                    credit: String(l.credit ?? '0'),
                    memo: l.memo ?? '',
                })),
            );
        }
        setHydrated(true);
    }, [isEditMode, hydrated, existingDoc]);

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
    // Posted / Void documents are read-only — the backend serializer also
    // rejects edits, so this is belt-and-suspenders. Only a Draft is editable.
    const docStatus = existingDoc?.status;
    const isReadOnly = isEditMode && docStatus != null && docStatus !== 'Draft';
    const canSaveDraft =
        !!bankAccount && validLines.length > 0 && !createDoc.isPending && !postDoc.isPending && !updateDoc.isPending;
    const canPostAndPay = canSaveDraft && net > 0;

    const addLine = () => setLines((prev) => [...prev, blankLine()]);
    const removeLine = (index: number) => setLines((prev) => prev.filter((_, i) => i !== index));
    const updateLine = (index: number, field: keyof PDLine, value: string) =>
        setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));

    const buildPayload = () => ({
        bank_account: bankAccount,
        description,
        reference_number: referenceNumber,
        document_date: documentDate,
        mda: mda || null,
        fund: fund || null,
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
            if (isEditMode && id) {
                // EDIT: PATCH the existing draft in place — never create a new one.
                await updateDoc.mutateAsync({ id, payload: buildPayload() });
                addToast('Draft saved', 'success');
                navigate('/accounting/payment-documents');
                return;
            }
            // CREATE: if a Post & Pay attempt already persisted this (unchanged)
            // draft, it is saved — just navigate rather than create a duplicate.
            if (createdIdRef.current == null) {
                await createDoc.mutateAsync(buildPayload());
            }
            createdIdRef.current = null;
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
            if (isEditMode && id) {
                // EDIT: persist any edits, then post the EXISTING id. Never
                // create a second document in edit mode.
                await updateDoc.mutateAsync({ id, payload: buildPayload() });
                await postDoc.mutateAsync(id);
                addToast('Payment document posted', 'success');
                navigate('/accounting/payment-documents');
                return;
            }
            // CREATE: reuse the draft from a prior failed attempt so a retry
            // never creates a second document (see createdIdRef above).
            let docId = createdIdRef.current;
            if (docId == null) {
                const created = await createDoc.mutateAsync(buildPayload());
                docId = created.id as number | string;
                createdIdRef.current = docId;
            }
            await postDoc.mutateAsync(docId);
            createdIdRef.current = null;
            addToast('Payment document posted', 'success');
            navigate('/accounting/payment-documents');
        } catch (err: unknown) {
            addToast(extractError(err, 'Post failed'), 'error');
        }
    };

    if (dimsLoading) {
        return <AccountingLayout><div>Loading dimensions...</div></AccountingLayout>;
    }
    if (isEditMode && (docLoading || !hydrated)) {
        return <AccountingLayout><div>Loading payment document…</div></AccountingLayout>;
    }

    // ── Posted / Void → read-only view ──
    // Show the header, lines, status, net and a journal reference. No Save /
    // Post buttons: a posted document is immutable (the API rejects edits too).
    if (isReadOnly && existingDoc) {
        const roLines = existingDoc.lines ?? [];
        const roDebit = roLines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0);
        const roCredit = roLines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0);
        const roNet = Number(existingDoc.net_amount ?? roDebit - roCredit);
        const mdaLabel =
            existingDoc.mda != null
                ? (mdaOptions.find((o) => o.value === String(existingDoc.mda))?.label ?? String(existingDoc.mda))
                : null;
        const fundLabel =
            existingDoc.fund != null
                ? (fundOptions.find((o) => o.value === String(existingDoc.fund))?.label ?? String(existingDoc.fund))
                : null;
        const statusColor =
            existingDoc.status === 'Posted'
                ? 'var(--success, #16a34a)'
                : existingDoc.status === 'Void'
                    ? 'var(--error, #dc2626)'
                    : 'var(--text)';

        return (
            <AccountingLayout>
                <PageHeader
                    title={`Payment Document — ${existingDoc.document_number}`}
                    subtitle="Posted payment document. Immutable once posted; reverse the underlying journal to correct it."
                    icon={<Banknote size={22} />}
                    actions={
                        <button type="button" className="btn btn-outline" onClick={() => navigate('/accounting/payment-documents')}>
                            <ArrowLeft size={18} /> Back to list
                        </button>
                    }
                />

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.75rem 1rem', marginBottom: '1.5rem', borderRadius: '8px', background: 'rgba(22,163,74,0.08)', border: '1px solid rgba(22,163,74,0.35)', color: 'var(--success, #16a34a)', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                    <Lock size={16} /> {existingDoc.status} — read only
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
                    <div className="card">
                        <label className="label">Bank Account</label>
                        <div>{existingDoc.bank_account_name ?? '—'}</div>
                    </div>
                    <div className="card">
                        <label className="label">Document Date</label>
                        <div>{formatDate(existingDoc.document_date)}</div>
                    </div>
                    <div className="card">
                        <label className="label">Reference #</label>
                        <div>{existingDoc.reference_number || '—'}</div>
                    </div>
                    <div className="card">
                        <label className="label">Status</label>
                        <div style={{ fontWeight: 700, color: statusColor }}>{existingDoc.status}</div>
                    </div>
                    <div className="card" style={{ gridColumn: 'span 2' }}>
                        <label className="label">Description</label>
                        <div>{existingDoc.description || '—'}</div>
                    </div>
                    <div className="card">
                        <label className="label">Net to Bank (cash out)</label>
                        <div style={{ fontWeight: 700 }}>{formatCurrency(roNet)}</div>
                    </div>
                    <div className="card">
                        <label className="label">Journal</label>
                        <div>{existingDoc.journal != null ? `Journal reference #${existingDoc.journal}` : 'Not posted'}</div>
                    </div>
                </div>

                {(mdaLabel || fundLabel) && (
                    <div className="card" style={{ marginBottom: '2.5rem' }}>
                        <h3 style={{ margin: '0 0 1rem', fontSize: 'var(--text-base)' }}>Budget Appropriation</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                            <div>
                                <label className="label">MDA</label>
                                <div>{mdaLabel ?? '—'}</div>
                            </div>
                            <div>
                                <label className="label">Fund</label>
                                <div>{fundLabel ?? '—'}</div>
                            </div>
                        </div>
                    </div>
                )}

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                            <thead>
                                <tr style={{ background: 'var(--background)', textAlign: 'left' }}>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>GL Account</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '220px' }}>Vendor</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '150px', textAlign: 'right' }}>Debit</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '150px', textAlign: 'right' }}>Credit</th>
                                    <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Memo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {roLines.map((l) => (
                                    <tr key={l.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                        <td style={{ padding: '0.75rem 1rem' }}>
                                            {l.account_code ? `${l.account_code} — ${l.account_name ?? ''}` : (l.account_name ?? '—')}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{l.vendor_name || '—'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>{formatCurrency(parseFloat(l.debit) || 0)}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>{formatCurrency(parseFloat(l.credit) || 0)}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{l.memo || '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot>
                                <tr style={{ background: 'var(--surface)' }}>
                                    <td colSpan={2} style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>Totals</td>
                                    <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(roDebit)}</td>
                                    <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(roCredit)}</td>
                                    <td style={{ padding: '1rem', borderTop: '2px solid var(--border)' }} />
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                </div>
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

    return (
        <AccountingLayout>
            <form onSubmit={(e) => { e.preventDefault(); if (canSaveDraft) void onSaveDraft(); }}>
                <PageHeader
                    title={isEditMode ? `Edit Payment Document${existingDoc?.document_number ? ` — ${existingDoc.document_number}` : ''}` : 'New Payment Document'}
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
                        <label className="label">Document Date<span className="required-mark"> *</span></label>
                        <input type="date" value={documentDate} onChange={(e) => setDocumentDate(e.target.value || todayLocalISO())} required />
                        <p style={{ margin: '0.35rem 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                            {formatDate(documentDate)} — back-date if the payment settled earlier.
                        </p>
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

                {/* ── Optional header-level Budget Appropriation ──
                    Required only when a line debits an expenditure (Expense)
                    account; the backend warrant gate fails closed when mda/fund
                    are None for such lines. Settlement-only docs leave it blank. */}
                <div className="card" style={{ marginTop: '2.5rem' }}>
                    <button
                        type="button"
                        onClick={() => setShowAppropriation((v) => !v)}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textAlign: 'left' }}
                    >
                        <h3 style={{ margin: 0, fontSize: 'var(--text-base)', flex: 1 }}>
                            Budget Appropriation <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>(optional)</span>
                        </h3>
                        {showAppropriation ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                    <p style={{ margin: '0.5rem 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                        Required only when a line debits an expenditure (Expense) account — the payment
                        stage matches these against the available warrant (AIE). Leave blank for pure
                        liability / vendor settlements.
                    </p>
                    {showAppropriation && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginTop: '1.25rem' }}>
                            <div>
                                <label className="label">MDA</label>
                                <SearchableSelect
                                    options={mdaOptions}
                                    value={mda}
                                    onChange={setMda}
                                    placeholder="Search MDA…"
                                />
                            </div>
                            <div>
                                <label className="label">Fund</label>
                                <SearchableSelect
                                    options={fundOptions}
                                    value={fund}
                                    onChange={setFund}
                                    placeholder="Search Fund…"
                                />
                            </div>
                        </div>
                    )}
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
