import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Save, X, Plus, Trash2, AlertCircle, Banknote, Lock, ArrowLeft, Paperclip, Eye } from 'lucide-react';
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
    useProposedEntries,
    useUpdatePaymentDocument,
    useUploadPaymentDocumentAttachment,
    useViewPaymentDocumentAttachment,
    type PaymentDocumentInput,
    type PaymentDocumentLineInput,
} from '../hooks/usePaymentDocuments';

/**
 * Payment Document form — SAP F-53–style multi-line outgoing payment.
 *
 * The user picks an **MDA** (required) and a **Bank Account**, enters the
 * **Amount** credited out of that bank, and the form auto-adds a LOCKED line
 * crediting the bank's GL account for that Amount. The user then adds the
 * **debit** lines being settled (each with an optional **vendor**). The whole
 * balanced set (bank credit line + debit lines) must balance — Σdebit ==
 * Σcredit — and is sent to the API as entered; **Post & Pay** saves the draft
 * then posts it through the gated API.
 */

interface PDLine {
    id: string;
    account: string;
    vendor: string;
    debit: string;
    credit: string;
}

// Shape used by the account/dimension pickers (mirror JournalForm's toCodeOptions).
type Coded = { id: number | string; code?: string; name?: string };

interface BankAccountRow {
    id: number | string;
    account_name?: string;
    account_number?: string;
    bank_name?: string;
    // The bank's GL (cash/bank) account — the credit leg's account. The
    // `/accounting/bank-accounts/` serializer exposes all three (see
    // BankAccountSerializer: gl_account PK + gl_account_code/name read-only).
    gl_account?: number | string | null;
    gl_account_code?: string;
    gl_account_name?: string;
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

/**
 * Accounting Entries (balanced) — the FULL journal effect this document posts,
 * including the header bank-credit leg, so Σdebit == Σcredit. Fetches its own
 * data via useProposedEntries; renders a compact Account / Debit / Credit table
 * with a Totals row. Rendered for both the posted read-only view and an existing
 * Draft (as a preview); never for the blank /new create form.
 */
function AccountingEntriesSection({ id, caption }: { id: number | string; caption?: string }) {
    const { formatCurrency } = useCurrency();
    const { data, isLoading } = useProposedEntries(id);
    const entries = data?.entries ?? [];
    const totalDebit = entries.reduce((s, e) => s + (parseFloat(e.debit) || 0), 0);
    const totalCredit = entries.reduce((s, e) => s + (parseFloat(e.credit) || 0), 0);

    return (
        <div className="card" style={{ marginTop: '2.5rem', padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '1rem 1rem 0.75rem' }}>
                <h3 style={{ margin: 0, fontSize: 'var(--text-base)' }}>Accounting Entries (balanced)</h3>
                {caption && (
                    <p style={{ margin: '0.35rem 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>{caption}</p>
                )}
            </div>
            {isLoading ? (
                <div style={{ padding: '1rem', color: 'var(--text-muted)' }}>Loading entries…</div>
            ) : entries.length === 0 ? (
                <div style={{ padding: '1rem', color: 'var(--text-muted)' }}>No accounting entries.</div>
            ) : (
                <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 600 }}>
                        <thead>
                            <tr style={{ background: 'var(--background)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Account</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '160px', textAlign: 'right' }}>Debit</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '160px', textAlign: 'right' }}>Credit</th>
                            </tr>
                        </thead>
                        <tbody>
                            {entries.map((e, i) => (
                                <tr key={`${e.account}-${i}`} style={{ borderBottom: '1px solid var(--border)' }}>
                                    <td style={{ padding: '0.75rem 1rem' }}>{e.account_name ? `${e.account} — ${e.account_name}` : e.account}</td>
                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>{formatCurrency(parseFloat(e.debit) || 0)}</td>
                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>{formatCurrency(parseFloat(e.credit) || 0)}</td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot>
                            <tr style={{ background: 'var(--surface)' }}>
                                <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>Totals</td>
                                <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(totalDebit)}</td>
                                <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(totalCredit)}</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            )}
        </div>
    );
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

    const { data: banks = [], isFetched: banksFetched } = useBankAccounts();
    const { data: vendors = [] } = useVendors();
    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const createDoc = useCreatePaymentDocument();
    const postDoc = usePostPaymentDocument();
    const updateDoc = useUpdatePaymentDocument();
    const uploadAttachment = useUploadPaymentDocumentAttachment();
    const viewAttachment = useViewPaymentDocumentAttachment();
    const { data: existingDoc, isLoading: docLoading } = usePaymentDocument(isEditMode ? id : null);

    const [bankAccount, setBankAccount] = useState('');
    // Cash credited out of the bank. Drives the LOCKED bank-credit line at the
    // top of the grid (credit = Amount) — the user never edits that line directly.
    const [amount, setAmount] = useState('');
    const [description, setDescription] = useState('');
    const [referenceNumber, setReferenceNumber] = useState('');
    const [documentDate, setDocumentDate] = useState(todayLocalISO());
    // User settlement (debit) lines only — the bank-credit line is derived from
    // the header (Bank + Amount) and rendered as a locked row, not stored here.
    const [lines, setLines] = useState<PDLine[]>([blankLine()]);
    // Source-document scan (image/PDF) chosen by the operator. Uploaded via a
    // dedicated endpoint AFTER the document exists (create/save), never as part
    // of the create payload — the endpoint keys off the doc id.
    const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
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
    }, [bankAccount, amount, description, referenceNumber, documentDate, lines]);

    // Edit-mode hydration — runs once when the detail finishes loading. Maps the
    // server document (header + lines) into local form state. Runs for any
    // status (Draft or Posted/Void); the read-only branch below then decides
    // whether the fields are editable.
    // Gated on ``banksFetched`` so the bank's GL account is resolvable — that's
    // how we recognise the persisted bank-credit line among the doc's lines and
    // split it back out into the Amount field (the rest become user lines).
    useEffect(() => {
        if (!isEditMode || hydrated || !existingDoc || !banksFetched) return;
        setBankAccount(existingDoc.bank_account != null ? String(existingDoc.bank_account) : '');
        setDescription(existingDoc.description ?? '');
        setReferenceNumber(existingDoc.reference_number ?? '');
        setDocumentDate(existingDoc.document_date || todayLocalISO());

        // The bank-credit line = account is the bank's GL account, credit-only.
        const selBank = banks.find((b) => String(b.id) === String(existingDoc.bank_account));
        const bankGlId = selBank?.gl_account != null ? String(selBank.gl_account) : null;
        const incoming = Array.isArray(existingDoc.lines) ? existingDoc.lines : [];
        const userLines: PDLine[] = [];
        let derivedAmount = '';
        let bankLineConsumed = false;
        for (const l of incoming) {
            const acct = l.account != null ? String(l.account) : '';
            const db = parseFloat(l.debit) || 0;
            const cr = parseFloat(l.credit) || 0;
            const isBankCredit =
                !bankLineConsumed && bankGlId != null && acct === bankGlId && cr > 0 && db === 0;
            if (isBankCredit) {
                derivedAmount = String(l.credit ?? '');
                bankLineConsumed = true;
                continue;
            }
            userLines.push({
                id: crypto.randomUUID(),
                account: acct,
                vendor: l.vendor != null ? String(l.vendor) : '',
                debit: String(l.debit ?? '0'),
                credit: String(l.credit ?? '0'),
            });
        }
        setAmount(derivedAmount);
        setLines(userLines.length ? userLines : [blankLine()]);
        setHydrated(true);
    }, [isEditMode, hydrated, existingDoc, banksFetched, banks]);

    const bankOptions = useMemo(
        () =>
            [...banks].map((b) => ({
                value: String(b.id),
                // Account NAME on top; account code (number) — with the bank
                // name for context when a distinct account name is present — beneath.
                label: b.account_name || b.bank_name || 'Bank account',
                sublabel: [b.account_name ? b.bank_name : null, b.account_number].filter(Boolean).join(' — ') || undefined,
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

    // Selected bank + its GL (cash) account — the bank-credit line's account.
    const selectedBank = useMemo(
        () => banks.find((b) => String(b.id) === bankAccount),
        [banks, bankAccount],
    );
    const bankGlAccountId = selectedBank?.gl_account != null ? String(selectedBank.gl_account) : '';
    const bankGlLabel = selectedBank
        ? selectedBank.gl_account_code
            ? `${selectedBank.gl_account_code} — ${selectedBank.gl_account_name ?? ''}`
            : (selectedBank.gl_account_name ?? '')
        : '';
    // A picked bank with no GL account can't credit anything — block posting.
    const bankGlMissing = !!bankAccount && !!selectedBank && !bankGlAccountId;

    const amountNum = parseFloat(amount) || 0;

    // Totals span ALL lines, including the locked bank-credit line: its debit
    // is 0 and its credit is the Amount. So debits = Σ user debits and credits
    // = Σ user credits + Amount.
    const userDebit = lines.reduce((sum, l) => sum + (parseFloat(l.debit) || 0), 0);
    const userCredit = lines.reduce((sum, l) => sum + (parseFloat(l.credit) || 0), 0);
    const totalDebit = userDebit;
    const totalCredit = userCredit + amountNum;
    // Compare at 2dp to dodge float noise (all amounts are 2-decimal currency).
    const round2 = (n: number) => Math.round(n * 100) / 100;
    const isBalanced = round2(totalDebit) === round2(totalCredit) && totalDebit > 0;

    const validLines = lines.filter(
        (l) => l.account && ((parseFloat(l.debit) || 0) > 0 || (parseFloat(l.credit) || 0) > 0),
    );
    // Posted / Void documents are read-only — the backend serializer also
    // rejects edits, so this is belt-and-suspenders. Only a Draft is editable.
    const docStatus = existingDoc?.status;
    const isReadOnly = isEditMode && docStatus != null && docStatus !== 'Draft';
    // Floor for both actions: Bank (with a GL account), a positive Amount and a
    // Reference. Post & Pay adds the balance requirement; a Draft may be saved
    // unbalanced so the operator can come back and finish it.
    const baseReady =
        !!bankAccount &&
        !bankGlMissing &&
        amountNum > 0 &&
        referenceNumber.trim() !== '' &&
        !createDoc.isPending &&
        !postDoc.isPending &&
        !updateDoc.isPending;
    const canSaveDraft = baseReady;
    const canPostAndPay = baseReady && isBalanced;

    const addLine = () => setLines((prev) => [...prev, blankLine()]);
    const removeLine = (index: number) => setLines((prev) => prev.filter((_, i) => i !== index));
    const updateLine = (index: number, field: keyof PDLine, value: string) =>
        setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));

    // The FULL balanced set: the auto bank-credit line first (bank's GL
    // account, debit 0, credit = Amount), then each user settlement line.
    const buildPayload = (): PaymentDocumentInput => {
        const bankLine: PaymentDocumentLineInput = {
            account: bankGlAccountId,
            debit: '0',
            credit: String(amountNum),
        };
        const userPayloadLines = validLines.map<PaymentDocumentLineInput>((l) => ({
            account: l.account,
            vendor: l.vendor || null,
            debit: String(parseFloat(l.debit) || 0),
            credit: String(parseFloat(l.credit) || 0),
        }));
        return {
            bank_account: bankAccount,
            description,
            reference_number: referenceNumber,
            document_date: documentDate,
            lines: [bankLine, ...userPayloadLines],
        };
    };

    // Upload the chosen source document to the (now-existing) doc id, then clear
    // it so a later retry doesn't re-upload the same file. Runs only when a file
    // is staged; upload errors propagate to the caller's toast.
    const uploadIfPresent = async (docId: number | string) => {
        if (!attachmentFile) return;
        await uploadAttachment.mutateAsync({ id: docId, file: attachmentFile });
        setAttachmentFile(null);
    };

    // Open the persisted attachment in a new tab; surface any error via toast.
    const handleViewAttachment = async (docId: number | string) => {
        try {
            await viewAttachment.mutateAsync(docId);
        } catch (err: unknown) {
            addToast(extractError(err, 'Could not open attachment'), 'error');
        }
    };

    const onSaveDraft = async () => {
        try {
            if (isEditMode && id) {
                // EDIT: PATCH the existing draft in place — never create a new one.
                await updateDoc.mutateAsync({ id, payload: buildPayload() });
                await uploadIfPresent(id);
                addToast('Draft saved', 'success');
                navigate('/accounting/payment-documents');
                return;
            }
            // CREATE: if a Post & Pay attempt already persisted this (unchanged)
            // draft, it is saved — reuse that id rather than create a duplicate.
            let docId = createdIdRef.current;
            if (docId == null) {
                const created = await createDoc.mutateAsync(buildPayload());
                docId = created.id as number | string;
            }
            // Attachment upload needs the doc id, so it happens here — after the
            // document exists, never before create.
            await uploadIfPresent(docId);
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
                // EDIT: persist any edits, upload the attachment (if any), then
                // post the EXISTING id. Never create a second document in edit mode.
                await updateDoc.mutateAsync({ id, payload: buildPayload() });
                await uploadIfPresent(id);
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
            // Upload the source document (if staged) BEFORE posting, so the
            // scan is attached to the document the operator is about to post.
            await uploadIfPresent(docId);
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
                    {existingDoc.has_attachment && (
                        <div className="card">
                            <label className="label">Source Document</label>
                            {/* Single-line layout (filename left, compact View right) so this
                                card matches the height of the other detail cards — a grid row
                                stretches every cell to its tallest sibling. */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
                                {existingDoc.attachment_name && (
                                    <span title={existingDoc.attachment_name} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', minWidth: 0, overflow: 'hidden', fontSize: 'var(--text-sm)' }}>
                                        <Paperclip size={13} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{existingDoc.attachment_name}</span>
                                    </span>
                                )}
                                <button type="button" className="btn btn-outline" style={{ marginLeft: 'auto', flexShrink: 0, fontSize: 'var(--text-xs)', padding: '0.3rem 0.6rem' }} onClick={() => handleViewAttachment(existingDoc.id)} disabled={viewAttachment.isPending} title="View source document">
                                    <Eye size={14} /> View
                                </button>
                            </div>
                        </div>
                    )}
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
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot>
                                <tr style={{ background: 'var(--surface)' }}>
                                    <td colSpan={2} style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>Totals</td>
                                    <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(roDebit)}</td>
                                    <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(roCredit)}</td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                </div>

                <AccountingEntriesSection
                    id={existingDoc.id}
                    caption="As posted to the general ledger — the full balanced journal including the bank credit leg."
                />
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
                    subtitle="A multi-line outgoing payment. The Amount credits the bank (cash out) on a locked line; add the debit lines being settled until the document balances."
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

                <div className="pd-header-fields" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
                    <div className="card" style={{ padding: '14px 20px' }}>
                        <label className="label">Bank Account<span className="required-mark"> *</span></label>
                        <SearchableSelect
                            options={bankOptions}
                            value={bankAccount}
                            onChange={setBankAccount}
                            placeholder="Search bank account…"
                            required
                        />
                        {bankGlMissing && (
                            <p style={{ margin: '0.35rem 0 0', fontSize: 'var(--text-xs)', color: 'var(--error)' }}>
                                This bank has no GL account configured — set one on the bank account before paying.
                            </p>
                        )}
                    </div>
                    <div className="card" style={{ padding: '14px 20px' }}>
                        <label className="label">Amount (CR)<span className="required-mark"> *</span></label>
                        <AmountInput value={amount} onChange={setAmount} required />
                    </div>
                    <div className="card" style={{ padding: '14px 20px' }}>
                        <label className="label">Reference #<span className="required-mark"> *</span></label>
                        <input type="text" placeholder="e.g. PAY-2026-001" value={referenceNumber} onChange={(e) => setReferenceNumber(e.target.value)} required />
                    </div>
                    <div className="card" style={{ padding: '14px 20px' }}>
                        <label className="label">Document Date<span className="required-mark"> *</span></label>
                        <input type="date" value={documentDate} onChange={(e) => setDocumentDate(e.target.value || todayLocalISO())} required />
                    </div>
                    <div className="card" style={{ padding: '14px 20px', gridColumn: 'span 2' }}>
                        <label className="label">Description</label>
                        <input type="text" placeholder="Purpose of this payment" value={description} onChange={(e) => setDescription(e.target.value)} />
                    </div>
                    {/* Source Document — optional image/PDF scan of the payment
                        voucher/supporting doc. Uploaded via a dedicated endpoint
                        AFTER the doc is saved/created (see uploadIfPresent). */}
                    <div className="card" style={{ padding: '14px 20px', gridColumn: 'span 2' }}>
                        <label className="label">Source Document</label>
                        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem' }}>
                            {/* Attachment already persisted on the loaded doc (edit mode). */}
                            {isEditMode && existingDoc?.has_attachment && (
                                <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', borderRadius: '7px', background: 'rgba(25,30,106,0.05)', border: '1px solid rgba(25,30,106,0.18)', fontSize: 'var(--text-xs)', minWidth: 0 }}>
                                    <Paperclip size={13} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 240 }}>
                                        {existingDoc.attachment_name}
                                    </span>
                                    <button type="button" className="btn btn-outline" style={{ fontSize: 'var(--text-xs)', padding: '0.25rem 0.5rem' }} onClick={() => handleViewAttachment(existingDoc.id)} disabled={viewAttachment.isPending}>
                                        <Eye size={14} /> View
                                    </button>
                                </div>
                            )}
                            {/* File picker — attach (or replace) an image/PDF. */}
                            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.75rem', borderRadius: '7px', border: '1.5px dashed var(--border)', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>
                                <Paperclip size={14} />
                                <span>{isEditMode && existingDoc?.has_attachment ? 'Replace image/PDF' : 'Attach image/PDF'}</span>
                                <input type="file" accept="image/*,application/pdf" style={{ display: 'none' }} onChange={(e) => setAttachmentFile(e.target.files?.[0] ?? null)} />
                            </label>
                            {/* Staged (not-yet-uploaded) file chip. */}
                            {attachmentFile && (
                                <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.35rem 0.6rem', borderRadius: '7px', background: 'rgba(22,163,74,0.08)', border: '1px solid rgba(22,163,74,0.3)', fontSize: 'var(--text-xs)', minWidth: 0 }}>
                                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 240 }}>{attachmentFile.name}</span>
                                    <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>({(attachmentFile.size / 1024).toFixed(0)} KB)</span>
                                    <button type="button" onClick={() => setAttachmentFile(null)} title="Remove selected file" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--error)', padding: 0, display: 'flex', flexShrink: 0 }}>
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            )}
                        </div>
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
                                    <th style={{ padding: '1rem', width: '50px' }}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {/* Locked bank-credit line — the cash out. Account is the
                                    selected bank's GL account, credit = Amount; driven by the
                                    header, never edited directly. Shown once a bank is picked. */}
                                {bankAccount && (
                                    <tr style={{ borderBottom: '1px solid var(--border)', background: 'rgba(25,30,106,0.05)' }}>
                                        <td style={{ padding: '0.75rem' }}>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                                                    <Lock size={12} /> Bank (cash out)
                                                </span>
                                                {bankGlMissing ? (
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--error)' }}>
                                                        No GL account on this bank.
                                                    </span>
                                                ) : (
                                                    <span style={{ fontSize: 'var(--text-sm)' }}>{bankGlLabel || '—'}</span>
                                                )}
                                            </div>
                                        </td>
                                        <td style={{ padding: '0.75rem', color: 'var(--text-muted)' }}>—</td>
                                        <td style={{ padding: '0.75rem', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(0)}</td>
                                        <td style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(amountNum)}</td>
                                        <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                                            <Lock size={14} style={{ color: 'var(--text-muted)' }} />
                                        </td>
                                    </tr>
                                )}
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
                                            {lines.length > 1 && (
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
                                    <td style={{ padding: '1rem' }} />
                                </tr>
                                <tr style={{ background: 'var(--surface)' }}>
                                    <td colSpan={2} style={{ padding: '1rem', fontWeight: 700 }}>
                                        {isBalanced ? (
                                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', color: 'var(--success, #16a34a)' }}>
                                                Balanced ✓
                                            </span>
                                        ) : (
                                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', color: 'var(--error)' }}>
                                                <AlertCircle size={14} /> Debits {formatCurrency(totalDebit)} ≠ Credits {formatCurrency(totalCredit)}
                                            </span>
                                        )}
                                    </td>
                                    <td colSpan={3} style={{ padding: '1rem', textAlign: 'right', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                                        {isBalanced
                                            ? 'Debits equal credits — ready to Post & Pay.'
                                            : 'Add debit lines until they equal the bank credit (the Amount).'}
                                    </td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                </div>

                {/* Existing Draft only — a preview of the balanced journal this
                    document will post. Never shown on the blank /new form. */}
                {isEditMode && id && (
                    <AccountingEntriesSection
                        id={id}
                        caption="Preview of the balanced journal this draft will post, including the bank credit leg."
                    />
                )}
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
                /* Compact header fields — scoped to THIS form only. Overrides the
                   global 13px input padding (and SearchableSelect's inline
                   padding, hence !important) so the header inputs, the amount
                   field and the bank picker read as one shorter, denser row.
                   Only vertical padding changes; the hidden file input is
                   display:none, so unaffected. */
                .pd-header-fields input {
                    padding-top: 0.375rem !important;
                    padding-bottom: 0.375rem !important;
                }
            `}</style>
        </AccountingLayout>
    );
}
