import React, { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    Plus, Trash2, FileText, Layers, Paperclip,
    ReceiptText, ArrowLeftRight, CheckCircle, AlertCircle, Eye, X as XIcon,
} from 'lucide-react';
import {
    useCreateVendorInvoice, useUpdateVendorInvoice, useVendorInvoiceDetail,
    useApproveVendorInvoice, usePostCreditMemo,
    useTaxCodes, useWithholdingTaxes,
} from '../hooks/useAccountingEnhancements';
import { useVendors } from '../../procurement/hooks/useProcurement';
import { useDimensions } from '../hooks/useJournal';
import { useIsDimensionsEnabled } from '../../../hooks/useTenantModules';
import { useAuth } from '../../../context/AuthContext';
import { useCurrency } from '../../../context/CurrencyContext';
import { useToast } from '../../../context/ToastContext';
import AccountingLayout from '../AccountingLayout';
import BackButton from '../../../components/BackButton';
import SearchableSelect from '../../../components/SearchableSelect';
import apiClient from '../../../api/client';
import '../styles/glassmorphism.css';

type TabType = 'invoice' | 'credit_memo';

let _lineUid = 0;
const nextLineUid = () => String(++_lineUid);

type LineType = 'expense' | 'asset' | 'gl';

interface InvoiceLine {
    _uid: string;
    line_type: LineType;
    account: string;
    description: string;
    amount: string;
    tax_code: string;
    withholding_tax: string;
}

interface Props {
    onCancel: () => void;
    onSuccess: () => void;
    /**
     * When set, the form opens in EDIT mode for the given Draft invoice id.
     * Backend rejects PUTs unless status === 'Draft' (payables.py:update),
     * and the hydration effect bounces the user out if a non-Draft id slips
     * through (defense in depth).
     */
    editingInvoiceId?: number | null;
}

const VendorInvoiceForm: React.FC<Props> = ({ onCancel, onSuccess, editingInvoiceId = null }) => {
    const { hasRole } = useAuth();
    const { addToast } = useToast();
    // SoD: Credit Memo requires manager or admin role
    // Users who create invoices (officer/user) cannot create credit memos
    const canCreateCreditMemo = hasRole('manager');

    const isEditMode = editingInvoiceId !== null && editingInvoiceId !== undefined;
    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { isEnabled: dimensionsEnabled } = useIsDimensionsEnabled();
    const { formatCurrency, currencySymbol } = useCurrency();
    const createInvoice = useCreateVendorInvoice();
    const updateInvoice = useUpdateVendorInvoice();
    const approveInvoice = useApproveVendorInvoice();
    const postCreditMemo = usePostCreditMemo();
    const { data: existingInvoice, isLoading: invoiceLoading } = useVendorInvoiceDetail(isEditMode ? editingInvoiceId! : null);
    const { data: vendors } = useVendors({ is_active: true });

    // ── Reference data (Tax / WHT / Accounts) ─────────────────────
    // Uses the SAME React Query hooks that the working Tax Management
    // page uses, plus a parallel ``useQuery`` for the CoA. Earlier
    // revisions hand-rolled imperative fetches "to bypass cache
    // staleness" — but that diverged from the proven path and left the
    // form without invalidation when codes were created elsewhere.
    // React Query's ``refetchOnMount: 'always'`` + ``refetchOnWindowFocus``
    // gives us fresh data on mount and on tab return, with no manual
    // useEffect ceremony.
    const {
        data: taxCodes = [],
        isLoading: taxLoading,
        isError: taxIsError,
        error: taxError,
        refetch: refetchTax,
    } = useTaxCodes({ is_active: true });
    const {
        data: whtList = [],
        isLoading: whtLoading,
        isError: whtIsError,
        error: whtError,
        refetch: refetchWht,
    } = useWithholdingTaxes({ is_active: true });
    const {
        data: accountsResp,
        isLoading: accLoading,
        isError: accIsError,
        error: accError,
        refetch: refetchAccounts,
    } = useQuery({
        queryKey: ['accounts', 'ap-form', 'all-active'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { is_active: true, page_size: 10000, ordering: 'code' },
            });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: 30_000,
        refetchOnMount: 'always',
        refetchOnWindowFocus: true,
        retry: false,
    });
    const directAccounts: any[] = Array.isArray(accountsResp) ? accountsResp : [];

    // MDA list — VendorInvoice.mda is FK to legacy ``accounting.MDA``,
    // NOT the NCoA AdministrativeSegment that the operator sees in the
    // Chart of Accounts UI. Posting an NCoA-segment id into the legacy
    // FK fails with ``Invalid pk - object does not exist``. Same fix
    // applied to Journal form in commit 2aad4bb.
    const { data: mdasResp } = useQuery({
        queryKey: ['mdas', 'ap-form', 'active'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/mdas/', {
                params: { is_active: true, page_size: 10000, ordering: 'code' },
            });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: 60_000,
        refetchOnMount: 'always',
        refetchOnWindowFocus: true,
        retry: false,
    });
    const mdas: any[] = Array.isArray(mdasResp) ? mdasResp : [];
    // Combined error message for the status strip — first non-empty wins.
    const refDataError =
        (taxIsError  && ((taxError  as any)?.response?.status ? `${(taxError  as any).response.status} ${(taxError  as any).response.statusText || ''}` : (taxError  as any)?.message)) ||
        (whtIsError  && ((whtError  as any)?.response?.status ? `${(whtError  as any).response.status} ${(whtError  as any).response.statusText || ''}` : (whtError  as any)?.message)) ||
        (accIsError  && ((accError  as any)?.response?.status ? `${(accError  as any).response.status} ${(accError  as any).response.statusText || ''}` : (accError  as any)?.message)) ||
        '';
    const refDataLoading = taxLoading || whtLoading || accLoading;
    const refetchAll = () => { refetchTax(); refetchWht(); refetchAccounts(); };

    // One-shot hydration guard — populating state only the first time the
    // invoice data arrives prevents a background refetch from wiping the
    // user's in-progress edits.
    const [hydrated, setHydrated] = useState(false);

    // Fetch fixed assets for the selected MDA (used in Asset line type)
    const [activeTab, setActiveTab] = useState<TabType>('invoice');
    const [header, setHeader] = useState({
        mda: '',
        vendor: '', reference: '', description: '',
        invoice_date: new Date().toISOString().split('T')[0],
        due_date: '', vendor_credit_amount: '',
        fund: '', function: '', program: '', geo: '',
    });
    const [lines, setLines] = useState<InvoiceLine[]>([
        { _uid: nextLineUid(), line_type: 'expense', account: '', description: '', amount: '0', tax_code: '', withholding_tax: '' },
    ]);
    const [attachment, setAttachment] = useState<File | null>(null);
    const [formError, setFormError] = useState('');
    const [showPreview, setShowPreview] = useState(false);

    // Edit-mode hydration — runs once when the invoice detail finishes loading.
    // Non-Draft invoices are never editable: redirect back via onCancel().
    useEffect(() => {
        if (!isEditMode || hydrated || !existingInvoice) return;
        if (existingInvoice.status && existingInvoice.status !== 'Draft') {
            setFormError(`Cannot edit a ${String(existingInvoice.status).toLowerCase()} invoice. Issue a credit memo to reverse it.`);
            // Defer to the parent so it can clear its showForm state cleanly.
            setTimeout(onCancel, 0);
            return;
        }
        if (existingInvoice.document_type === 'Credit Memo') {
            setActiveTab('credit_memo');
        }
        setHeader({
            mda: existingInvoice.mda ? String(existingInvoice.mda) : '',
            vendor: existingInvoice.vendor ? String(existingInvoice.vendor) : '',
            reference: existingInvoice.reference ?? '',
            description: existingInvoice.description ?? '',
            invoice_date: existingInvoice.invoice_date ?? new Date().toISOString().split('T')[0],
            due_date: existingInvoice.due_date ?? '',
            vendor_credit_amount: existingInvoice.vendor_credit_amount != null ? String(existingInvoice.vendor_credit_amount) : '',
            fund: existingInvoice.fund ? String(existingInvoice.fund) : '',
            function: existingInvoice.function ? String(existingInvoice.function) : '',
            program: existingInvoice.program ? String(existingInvoice.program) : '',
            geo: existingInvoice.geo ? String(existingInvoice.geo) : '',
        });
        const incomingLines = Array.isArray(existingInvoice.lines) ? existingInvoice.lines : [];
        setLines(
            incomingLines.length
                ? incomingLines.map((l: any) => ({
                      _uid: nextLineUid(),
                      line_type: (l.line_type as LineType) || 'expense',
                      account: l.account != null ? String(l.account) : '',
                      description: l.description ?? '',
                      amount: l.amount != null ? String(l.amount) : '0',
                      tax_code: l.tax_code != null ? String(l.tax_code) : '',
                      withholding_tax: l.withholding_tax != null ? String(l.withholding_tax) : '',
                  }))
                : [{ _uid: nextLineUid(), line_type: 'expense', account: '', description: '', amount: '0', tax_code: '', withholding_tax: '' }],
        );
        setHydrated(true);
    }, [isEditMode, hydrated, existingInvoice, onCancel]);

    // Fetch fixed assets for the selected MDA
    const { data: fixedAssets } = useQuery({
        queryKey: ['fixed-assets-mda', header.mda],
        queryFn: async () => {
            const params: Record<string, string> = { status: 'Active', page_size: '500' };
            if (header.mda) params.mda = header.mda;
            const res = await apiClient.get('/accounting/fixed-assets/', { params });
            const d = res.data;
            return Array.isArray(d) ? d : d?.results || [];
        },
        enabled: !!header.mda,
        staleTime: 60_000,
    });

    // Single source of truth: the dedicated useQuery above. We no
    // longer fall back to ``dims?.accounts`` because that path was
    // shadowing fresh data with a stale cached payload on new tenants.
    // If accounts are needed and missing, the status strip surfaces
    // the empty count so the operator knows to seed the CoA.
    const allAccounts = directAccounts;
    // ``account_type`` is an optional classification on Account; on a
    // freshly-seeded NCoA-driven CoA those records may not yet be
    // classified into Asset/Expense, so a strict filter would return
    // an empty dropdown even though the GLs exist. Backend never reads
    // ``line_type`` (purely a UI tag — see grep over models/views) so
    // any active account is a valid posting target. Show the full CoA
    // and let the operator search by code or name.

    // ── Searchable option lists ─────────────────────────────────────────────
    // Sort by code ascending (numeric-aware) and shape for SearchableSelect.
    // Belt-and-braces: useDimensions also sorts accounts, but a stale React
    // Query cache (pre-upgrade) would otherwise display unsorted.
    type Coded = { id: number | string; code?: string; name?: string };
    const toCodeOptions = (list: Coded[]) =>
        [...list]
            .sort((a, b) => (a.code ?? '').localeCompare(b.code ?? '', undefined, { numeric: true }))
            .map(x => ({
                value: String(x.id),
                // Full ``code — name`` label in both the dropdown panel and
                // the closed/selected display so the line cell shows the
                // descriptive text. The cell truncates with text-overflow:
                // ellipsis when it overflows; the SearchableSelect's
                // ``title`` attribute exposes the full label on hover so
                // operators can read the descriptor without expanding.
                label: x.code ? `${x.code} — ${x.name ?? ''}` : (x.name ?? ''),
                sublabel: x.code ? x.name : undefined,
            }));

    const vendorOptions = useMemo(() =>
        [...((vendors as any[]) ?? [])]
            .sort((a: any, b: any) => (a.name ?? '').localeCompare(b.name ?? ''))
            .map((v: any) => ({
                value: String(v.id),
                label: v.code ? `${v.code} — ${v.name}` : v.name,
                sublabel: v.tin ? `TIN ${v.tin}` : undefined,
            })),
    [vendors]);

    const fundOptions     = useMemo(() => toCodeOptions((dims?.funds ?? []) as Coded[]),     [dims?.funds]);
    const functionOptions = useMemo(() => toCodeOptions((dims?.functions ?? []) as Coded[]), [dims?.functions]);
    const programOptions  = useMemo(() => toCodeOptions((dims?.programs ?? []) as Coded[]),  [dims?.programs]);
    const geoOptions      = useMemo(() => toCodeOptions((dims?.geos ?? []) as Coded[]),      [dims?.geos]);

    const allAccountOptions = useMemo(() => toCodeOptions(allAccounts as Coded[]), [allAccounts]);

    // Account options are uniform across line types now — line_type is
    // a cosmetic tag (backend ignores it), so any active GL is valid.
    // Asset rows use ``fixedAssetOptions`` separately for the picker.
    const getAccountOptionsForLineType = (_lt: LineType) => allAccountOptions;

    // Fixed assets are picked on asset-type lines; sort by asset_number,
    // show category as sublabel. Full label shown in cell, truncated by
    // CSS ellipsis when it doesn't fit; full text exposed via tooltip.
    const fixedAssetOptions = useMemo(() =>
        [...((fixedAssets as any[]) ?? [])]
            .sort((a: any, b: any) => (a.asset_number ?? '').localeCompare(b.asset_number ?? '', undefined, { numeric: true }))
            .map((a: any) => ({
                value: String(a.id),
                label: `${a.asset_number} — ${a.name}`,
                sublabel: a.asset_category,
            })),
    [fixedAssets]);

    // Tax / WHT — full ``code — rate% (name)`` label so the rate is
    // visible at a glance. CSS handles truncation; tooltip handles
    // long names without page-shifting.
    const taxOptions = useMemo(() =>
        [...((taxCodes as any[]) ?? [])]
            .sort((a: any, b: any) => (a.code ?? '').localeCompare(b.code ?? '', undefined, { numeric: true }))
            .map((t: any) => ({
                value: String(t.id),
                label: `${t.code} — ${t.rate}%${t.name ? ` (${t.name})` : ''}`,
                sublabel: t.name,
            })),
    [taxCodes]);

    const whtOptions = useMemo(() =>
        [...((whtList as any[]) ?? [])]
            .sort((a: any, b: any) => (a.code ?? '').localeCompare(b.code ?? '', undefined, { numeric: true }))
            .map((w: any) => ({
                value: String(w.id),
                label: `${w.code} — ${w.rate}%${w.name ? ` (${w.name})` : ''}`,
                sublabel: w.name,
            })),
    [whtList]);

    // Totals — safe integer-cent arithmetic
    const { subtotal, taxTotal, whtTotal, grandTotal } = useMemo(() => {
        let subCents = 0, taxCents = 0, whtCents = 0;
        for (const line of lines) {
            const amtCents = Math.round(Number(line.amount || 0) * 100);
            subCents += amtCents;
            if (line.tax_code) {
                const tc = taxCodes?.find((t: any) => String(t.id) === line.tax_code);
                if (tc) taxCents += Math.round(amtCents * Number(tc.rate) / 100);
            }
            if (line.withholding_tax) {
                const wc = whtList?.find((w: any) => String(w.id) === line.withholding_tax);
                if (wc) whtCents += Math.round(amtCents * Number(wc.rate) / 100);
            }
        }
        return {
            subtotal: subCents / 100,
            taxTotal: taxCents / 100,
            whtTotal: whtCents / 100,
            grandTotal: (subCents + taxCents - whtCents) / 100,
        };
    }, [lines, taxCodes, whtList]);

    const [addLineType, setAddLineType] = useState<LineType>('expense');
    const addLine = (lt?: LineType) =>
        setLines(prev => [...prev, { _uid: nextLineUid(), line_type: lt || addLineType, account: '', description: '', amount: '0', tax_code: '', withholding_tax: '' }]);
    const removeLine = (idx: number) => setLines(prev => prev.filter((_, i) => i !== idx));
    const updateLine = (idx: number, field: keyof InvoiceLine, value: string) =>
        setLines(prev => { const n = [...prev]; n[idx][field] = value; return n; });

    const switchTab = (tab: TabType) => {
        setActiveTab(tab);
        setLines([{ _uid: nextLineUid(), line_type: 'expense', account: '', description: '', amount: '0', tax_code: '', withholding_tax: '' }]);
        setFormError('');
        setHeader(h => ({ ...h, vendor_credit_amount: '' }));
    };

    // ── Real-time per-line budget check ─────────────────────────────
    // Calls /budget/check-line/ as the operator types account + amount,
    // debounced by 400ms so we don't fire a request on every keystroke.
    // Result drives an inline status pill on each line: green (NONE /
    // within budget), amber (WARNING — appropriation missing or
    // utilisation above threshold), red (STRICT block — posting will
    // be rejected by backend). Same engine the backend uses on Save,
    // so the indicator is authoritative — what you see is what you
    // get on Post.
    interface LineCheck { level: 'NONE' | 'WARNING' | 'STRICT'; blocked: boolean; reason: string; warnings: string[]; }
    const [lineChecks, setLineChecks] = useState<Record<string, LineCheck>>({});
    useEffect(() => {
        if (!header.mda) {
            setLineChecks({});
            return;
        }
        // Sentinel funds: pick the header.fund if dimensions enabled,
        // otherwise the first known fund (some tenants store fund at
        // the appropriation level only and skip the form field).
        const fundId = header.fund || (dims?.funds?.[0]?.id ? String(dims.funds[0].id) : '');
        if (!fundId) return;
        const handle = setTimeout(async () => {
            const next: Record<string, LineCheck> = {};
            await Promise.all(lines.map(async (ln) => {
                if (!ln.account || ln.line_type === 'asset') {
                    // Asset lines pick from fixed-assets, not from
                    // expense GL — appropriation lookup doesn't apply.
                    next[ln._uid] = { level: 'NONE', blocked: false, reason: '', warnings: [] };
                    return;
                }
                try {
                    const { data } = await apiClient.get('/budget/appropriations/check-line/', {
                        params: {
                            mda: header.mda,
                            fund: fundId,
                            account: ln.account,
                            amount: ln.amount || '0',
                        },
                    });
                    next[ln._uid] = {
                        level: data?.level || 'NONE',
                        blocked: !!data?.blocked,
                        reason: data?.reason || '',
                        warnings: Array.isArray(data?.warnings) ? data.warnings : [],
                    };
                } catch {
                    // Failure is non-fatal — fall back to NONE so the
                    // user can still submit and let backend be the
                    // authoritative gate.
                    next[ln._uid] = { level: 'NONE', blocked: false, reason: '', warnings: [] };
                }
            }));
            setLineChecks(next);
        }, 400);
        return () => clearTimeout(handle);
    }, [lines, header.mda, header.fund, dims?.funds]);
    const anyLineBlocked = Object.values(lineChecks).some(c => c.blocked);
    // Derive line-number lists for the banner. We surface ROW NUMBERS,
    // not GL codes/names — the operator already sees the offending row
    // marked BLOCK / WARN inline; the banner's job is to explain
    // "what does this state mean?" without re-stating the GL identity
    // (avoids visual noise and any incidental information leak when a
    // screenshot is shared with someone outside the procurement team).
    const blockedLineNumbers = lines
        .map((ln, idx) => ({ uid: ln._uid, n: idx + 1 }))
        .filter(({ uid }) => lineChecks[uid]?.blocked)
        .map(({ n }) => n);
    const warningLineNumbers = lines
        .map((ln, idx) => ({ uid: ln._uid, n: idx + 1 }))
        .filter(({ uid }) => {
            const c = lineChecks[uid];
            return c && c.level === 'WARNING' && !c.blocked;
        })
        .map(({ n }) => n);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        // Payload semantics — important for downstream budget reports:
        //   subtotal     = sum of line.amount (the EXPENSE recognised
        //                  against appropriation; line gross, ex-VAT).
        //                  This is what the GL Expense debit will be
        //                  and what rolls up into appropriation
        //                  ``cached_total_expended``.
        //   tax_amount   = computed VAT to be debited to Input VAT GL.
        //   total_amount = subtotal + tax_amount (vendor invoice gross
        //                  before WHT). WHT is a payment-stage
        //                  deduction and is computed by the backend
        //                  from line withholding_tax codes — it must
        //                  NOT be subtracted into total_amount here,
        //                  otherwise the expense recognised against
        //                  the appropriation gets understated by the
        //                  WHT amount (which is what produced the
        //                  ₦975k-instead-of-₦1M expended bug).
        const invoiceTotal = subtotal + taxTotal;
        const jsonPayload: any = {
            mda: header.mda ? Number(header.mda) : null,
            vendor: Number(header.vendor),
            reference: header.reference,
            description: header.description,
            invoice_date: header.invoice_date,
            due_date: header.due_date || header.invoice_date,
            vendor_credit_amount: parseFloat(header.vendor_credit_amount || '0').toFixed(2),
            subtotal: subtotal.toFixed(2),
            tax_amount: taxTotal.toFixed(2),
            total_amount: invoiceTotal.toFixed(2),
            document_type: isCreditMemo ? 'Credit Memo' : 'Invoice',
            lines: lines.map(l => ({
                account: Number(l.account),
                description: l.description,
                amount: parseFloat(l.amount),
                tax_code: l.tax_code ? Number(l.tax_code) : null,
                withholding_tax: l.withholding_tax ? Number(l.withholding_tax) : null,
            })),
            ...(dimensionsEnabled ? {
                fund: header.fund ? Number(header.fund) : null,
                function: header.function ? Number(header.function) : null,
                program: header.program ? Number(header.program) : null,
                geo: header.geo ? Number(header.geo) : null,
            } : {}),
        };

        let payload: any = jsonPayload;
        if (attachment) {
            const fd = new FormData();
            Object.entries(jsonPayload).forEach(([k, v]) => {
                if (k === 'lines') fd.append(k, JSON.stringify(v));
                else if (v !== null && v !== undefined) fd.append(k, String(v));
            });
            fd.append('attachment', attachment);
            payload = fd;
        }

        try {
            // Step 1 — Save (create or update). Backend creates a
            // Draft invoice (or leaves the existing Draft alone).
            let saved: { id: number; status?: string } | undefined;
            if (isEditMode && editingInvoiceId !== null && editingInvoiceId !== undefined) {
                saved = await updateInvoice.mutateAsync({ id: editingInvoiceId, payload });
            } else {
                saved = await createInvoice.mutateAsync(payload);
            }

            // Step 2 — Auto-post. The save action returned a Draft;
            // immediately call the SAP-FB60-style approve_invoice
            // endpoint (or post_credit_memo for credit memos) so the
            // operator gets one-click "save = post" UX. The backend
            // action runs the appropriation check, GL posting, and
            // commitment closure in one transaction.
            //
            // If post fails (warrant ceiling, missing GL accounts,
            // budget block, period closed), the Draft invoice still
            // exists — the operator can re-attempt via the AP list
            // once the underlying issue is fixed. The post failure
            // surfaces through the same toast + inline banner as a
            // save failure so it doesn't go unnoticed.
            if (saved?.id && (saved.status ?? 'Draft') !== 'Posted') {
                if (isCreditMemo) {
                    await postCreditMemo.mutateAsync(saved.id);
                } else {
                    await approveInvoice.mutateAsync(saved.id);
                }
            }
            onSuccess();
        } catch (err: any) {
            const data = err.response?.data;
            // Priority: structured budget/warrant errors go first — they
            // carry the full human-readable message in a known field.
            // Fall back to the dump of all error fields for other cases.
            const msg =
                typeof data === 'string' ? data :
                data?.budget ? (Array.isArray(data.budget) ? data.budget.join(' ') : data.budget) :
                data?.error ? data.error :
                data?.detail ? data.detail :
                data && typeof data === 'object'
                    ? Object.entries(data)
                        .filter(([k]) => !['appropriation_exceeded', 'warrant_exceeded', 'no_appropriation',
                                           'missing_dimensions', 'dimensions', 'appropriation_id',
                                           'requested', 'available', 'deficit', 'warrant_info'].includes(k))
                        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
                        .join(' | ')
                    : err.message || 'Failed to save document.';
            const finalMsg = msg || 'Failed to save document.';
            // Inline banner stays for in-context reading; toast gives
            // global visibility (and the longer 30s default duration
            // we set in ToastContext) so the operator can also catch
            // it if they've scrolled away from the form's red banner.
            // ``duration: 0`` makes the toast sticky — posting errors
            // often need to be screenshot or shared with a colleague,
            // and a 30s timer is still arbitrary. The user can dismiss
            // by clicking the toast or its × button.
            setFormError(finalMsg);
            addToast(finalMsg, 'error', 0);
        }
    };

    // ── Derived flags ────────────────────────────────────────────
    // ⚠ HOOK-ORDER NOTE: every hook below (useMemo for previewEntries,
    // and the three plain derivations off it) MUST live above the
    // early-return guards further down. React identifies hooks by
    // call-order position; a conditional return between hooks causes
    // "Rendered more hooks than during the previous render" the
    // moment the condition flips. Keep this block here and put any
    // new hooks above the dimsLoading return, not below.
    //
    // Balance is checked between the line gross (``subtotal``) and the
    // vendor AP credit amount (``creditAmount``). Tax and WHT are NOT
    // part of this equation — they post to their own configured GL
    // accounts (Input VAT, WHT Payable) at posting time, so they have
    // no business in the user-facing balance check. Earlier revisions
    // compared ``grandTotal = subtotal + tax - wht`` against
    // ``creditAmount``, which made a clean 10k/10k entry look ₦250
    // out-of-balance because of the tax/WHT delta.
    const isCreditMemo = activeTab === 'credit_memo';
    const creditAmount = parseFloat(header.vendor_credit_amount || '0');
    const isBalanced = isCreditMemo
        ? subtotal > 0
        : Math.abs(subtotal - creditAmount) < 0.01 && subtotal > 0;
    const balanceDiff = isCreditMemo ? 0 : subtotal - creditAmount;

    // ── Posting simulation ───────────────────────────────────────
    // Mirror what the backend will book at posting time so the
    // operator can confirm the GL impact BEFORE saving (SAP-style
    // ``Simulate``). Mirrors the rule-set in
    // accounting/services/procurement_posting.py: each line debits
    // its expense/asset/GL account; tax codes book Input VAT to
    // their ``input_tax_account``; WHT codes credit
    // ``withholding_account``; the residual credit hits AP.
    type Side = 'DR' | 'CR';
    interface PreviewLine { side: Side; account: string; description: string; amount: number; }
    const previewEntries: PreviewLine[] = useMemo(() => {
        const out: PreviewLine[] = [];
        const findAcc = (id: string | number | null | undefined) => {
            if (!id && id !== 0) return null;
            return (allAccounts as any[]).find(a => String(a.id) === String(id)) || null;
        };
        const accLabel = (a: any) => a ? `${a.code} — ${a.name}` : '— (account not set)';

        for (const ln of lines) {
            const amt = parseFloat(ln.amount || '0');
            if (!amt) continue;
            const acc = findAcc(ln.account);
            // Line gross — DR Expense (or CR for credit memo)
            out.push({
                side: isCreditMemo ? 'CR' : 'DR',
                account: accLabel(acc),
                description: ln.description || (isCreditMemo ? 'Credit memo line' : 'Invoice line'),
                amount: amt,
            });
            // Tax — DR Input VAT (purchase side). Pulls the
            // ``input_tax_account`` configured on the tax code; falls
            // back to the generic ``tax_account`` if input account
            // wasn't set (some tenants only configure one).
            if (ln.tax_code) {
                const tc = (taxCodes as any[]).find(t => String(t.id) === ln.tax_code);
                if (tc && Number(tc.rate) > 0) {
                    const taxAmt = Math.round(amt * Number(tc.rate)) / 100;
                    const taxAcc = findAcc(tc.input_tax_account ?? tc.tax_account);
                    out.push({
                        side: isCreditMemo ? 'CR' : 'DR',
                        account: taxAcc ? accLabel(taxAcc) : `Input VAT (${tc.code} — account not configured)`,
                        description: `Input VAT @ ${tc.rate}% (${tc.code})`,
                        amount: taxAmt,
                    });
                }
            }
            // WHT — CR WHT Payable. Pulls ``withholding_account``
            // from the WHT code. WHT reduces what the vendor receives
            // but never affects the expense GL.
            if (ln.withholding_tax) {
                const wc = (whtList as any[]).find(w => String(w.id) === ln.withholding_tax);
                if (wc && Number(wc.rate) > 0) {
                    const whtAmt = Math.round(amt * Number(wc.rate)) / 100;
                    const whtAcc = findAcc(wc.withholding_account);
                    out.push({
                        side: isCreditMemo ? 'DR' : 'CR',
                        account: whtAcc ? accLabel(whtAcc) : `WHT Payable (${wc.code} — account not configured)`,
                        description: `WHT @ ${wc.rate}% (${wc.code})`,
                        amount: whtAmt,
                    });
                }
            }
        }
        // AP credit (vendor liability) — gross of tax, net of WHT.
        // Must use the *computed* grandTotal (= subtotal + tax − WHT)
        // not the operator-typed ``creditAmount``. Reason: when VAT
        // is on the line, AP = (subtotal + VAT) − WHT, which is what
        // the vendor effectively owes the books. Earlier code used
        // ``creditAmount − whtTotal`` and ignored tax, which made
        // the simulated journal go out of balance by exactly the
        // tax amount (DR side counted VAT, CR side didn't). Using
        // ``grandTotal`` ties the AP credit to the same number the
        // Total card shows, and makes DR sum exactly equal CR sum.
        // For credit memo this side flips to DR (reduces AP).
        const apAmount = grandTotal;
        if (apAmount > 0) {
            const vendorRow = (vendors as any[] | undefined)?.find((v: any) => String(v.id) === header.vendor);
            out.push({
                side: isCreditMemo ? 'DR' : 'CR',
                account: 'Accounts Payable',
                description: vendorRow ? `Vendor: ${vendorRow.code ? vendorRow.code + ' — ' : ''}${vendorRow.name}` : 'Vendor liability',
                amount: apAmount,
            });
        }
        return out;
    }, [lines, taxCodes, whtList, allAccounts, vendors, header.vendor, creditAmount, whtTotal, isCreditMemo]);

    const previewDrTotal = previewEntries.filter(e => e.side === 'DR').reduce((s, e) => s + e.amount, 0);
    const previewCrTotal = previewEntries.filter(e => e.side === 'CR').reduce((s, e) => s + e.amount, 0);
    const previewBalanced = Math.abs(previewDrTotal - previewCrTotal) < 0.01 && previewEntries.length > 0;

    // ── Early-return loading guards ──────────────────────────────
    // MUST come AFTER every hook in this component (useState,
    // useEffect, useMemo, useQuery and the imperative-fetch pieces
    // above). Returning before any hook leaves React unable to match
    // hook positions across renders → "Rendered more hooks than
    // during the previous render" crash. This is why these returns
    // were moved down from where they used to live (immediately
    // after handleSubmit).
    if (dimsLoading) return (
        <AccountingLayout>
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                Loading…
            </div>
        </AccountingLayout>
    );
    if (isEditMode && (invoiceLoading || !hydrated)) return (
        <AccountingLayout>
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                Loading invoice…
            </div>
        </AccountingLayout>
    );

    // ── Shared style tokens (compact) ────────────────────────────
    const inp: React.CSSProperties = {
        width: '100%', padding: '0.45rem 0.7rem', borderRadius: '7px',
        border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
        color: 'var(--color-text)', fontSize: 'var(--text-sm)',
        outline: 'none', fontFamily: 'inherit',
    };
    const lbl: React.CSSProperties = {
        display: 'block', marginBottom: '0.25rem',
        fontSize: '0.68rem', fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)',
    };
    const fieldGap: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '0.65rem' };
    const pill = (bg: string, color: string, text: string) => (
        <span style={{
            padding: '0.1rem 0.45rem', borderRadius: '4px',
            background: bg, color, fontWeight: 700, fontSize: '10px', letterSpacing: '0.03em',
        }}>{text}</span>
    );

    return (
        <form onSubmit={handleSubmit} style={{ height: '100%' }}>

            {/* ── TOP BAR: header + tabs on same row ──────────────── */}
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: '0.75rem', gap: '1rem',
            }}>
                {/* Left: back + title */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', minWidth: 0 }}>
                    {/* Back button calls onCancel directly via the
                        new BackButton onClick prop — wrapping it in
                        another <button> caused a React 19 hydration
                        error (button-inside-button is invalid HTML). */}
                    <BackButton onClick={onCancel} />
                    <h1 style={{ fontSize: 'var(--text-lg)', fontWeight: 800, margin: 0, color: 'var(--color-text)', whiteSpace: 'nowrap' }}>
                        {isCreditMemo ? 'Vendor Credit Memo' : 'Vendor Invoice'}
                    </h1>
                    <p style={{ margin: 0, fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>
                        {isCreditMemo ? 'Dr Accounts Payable · Cr Expense' : 'Dr Expense · Cr Accounts Payable'}
                    </p>
                </div>

                {/* Centre: tab switcher */}
                <div style={{
                    display: 'flex', borderRadius: '9px',
                    border: '1.5px solid var(--color-border)',
                    overflow: 'hidden', flexShrink: 0,
                }}>
                    {([
                        { key: 'invoice' as TabType, label: 'Vendor Invoice', Icon: FileText, restricted: false },
                        { key: 'credit_memo' as TabType, label: 'Credit Memo', Icon: ReceiptText, restricted: !canCreateCreditMemo },
                    ]).filter(t => !t.restricted).map(({ key, label, Icon }) => (
                        <button key={key} type="button" onClick={() => switchTab(key)} style={{
                            display: 'flex', alignItems: 'center', gap: '0.4rem',
                            padding: '0.45rem 1.1rem', border: 'none', cursor: 'pointer',
                            fontSize: 'var(--text-xs)', fontWeight: 600,
                            background: activeTab === key ? 'var(--color-primary)' : 'transparent',
                            color: activeTab === key ? '#fff' : 'var(--color-text-muted)',
                            transition: 'background 0.15s, color 0.15s',
                        }}>
                            <Icon size={13} />
                            {label}
                        </button>
                    ))}
                </div>

                {/* Right: action buttons */}
                <div style={{ display: 'flex', gap: '0.6rem', flexShrink: 0 }}>
                    <button type="button" className="btn btn-outline" onClick={onCancel}
                        style={{ padding: '0.45rem 1.1rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                        Cancel
                    </button>
                    {/* Simulate posting (SAP-style) — opens a modal with
                        the journal lines that will be booked at posting
                        time so the operator can verify the GL impact
                        before committing. */}
                    <button
                        type="button"
                        onClick={() => setShowPreview(true)}
                        disabled={previewEntries.length === 0}
                        title={previewEntries.length === 0 ? 'Add a line with an account & amount to preview' : 'Preview accounting entries'}
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
                            padding: '0.45rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 600,
                            borderRadius: '7px',
                            border: '1.5px solid var(--color-border)',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            cursor: previewEntries.length === 0 ? 'not-allowed' : 'pointer',
                            opacity: previewEntries.length === 0 ? 0.55 : 1,
                        }}
                    >
                        <Eye size={14} /> Preview Entry
                    </button>
                    <button type="submit" className="btn btn-primary"
                        disabled={createInvoice.isPending || updateInvoice.isPending || !isBalanced || anyLineBlocked}
                        title={
                            anyLineBlocked ? 'One or more lines are blocked by a strict budget rule — fix the line(s) flagged in red below.' :
                            !isBalanced ? 'Debit and credit must be equal before saving' : undefined
                        }
                        style={{ padding: '0.45rem 1.25rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                        {(createInvoice.isPending || updateInvoice.isPending)
                            ? 'Saving…'
                            : (approveInvoice.isPending || postCreditMemo.isPending)
                                ? 'Posting…'
                                : isEditMode
                                    ? 'Save & Post'
                                    : isCreditMemo ? 'Save & Post Credit Memo' : 'Save & Post Invoice'}
                    </button>
                </div>
            </div>

            {/* ── Info banner (compact 1-line) ─────────────────────── */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '0.6rem',
                padding: '0.45rem 0.875rem', borderRadius: '7px', marginBottom: '0.75rem',
                background: isCreditMemo ? 'rgba(13,148,136,0.07)' : 'rgba(25,30,106,0.06)',
                border: `1px solid ${isCreditMemo ? 'rgba(13,148,136,0.25)' : 'rgba(25,30,106,0.18)'}`,
                fontSize: '0.72rem', color: 'var(--color-text-secondary)',
            }}>
                <ArrowLeftRight size={13} style={{ flexShrink: 0, color: isCreditMemo ? '#0d9488' : 'var(--color-primary)' }} />
                {isCreditMemo
                    ? <span><strong>Credit Memo</strong> — Dr AP (reduces vendor liability) · Cr Expense/Asset (reverses original charge).</span>
                    : <span><strong>Vendor Invoice</strong> — Dr Expense/Asset/GL Account · Cr AP (records vendor liability). Add lines by type: Expense, Asset, or GL Account.</span>}
            </div>

            {formError && (
                <div style={{
                    padding: '0.7rem 0.95rem', background: '#fef2f2', color: '#991b1b',
                    border: '1.5px solid #fecaca',
                    borderRadius: '8px', marginBottom: '0.75rem',
                    fontSize: 'var(--text-xs)', fontWeight: 500,
                    whiteSpace: 'pre-wrap' as const,  // preserves \n in budget messages
                    fontFamily: 'inherit',
                }}>
                    <div style={{ fontWeight: 700, marginBottom: '0.3rem', fontSize: 'var(--text-sm)' }}>
                        ⚠ Budget Validation Failed
                    </div>
                    {formError}
                </div>
            )}

            {/* ══════════════════════════════════════════════════════
                MAIN BODY — left panel (fields) + right panel (lines)
                ══════════════════════════════════════════════════════ */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: '320px 1fr',
                gap: '1rem',
                alignItems: 'start',
            }}>

                {/* ── LEFT PANEL: all header fields ─────────────── */}
                <div className="card" style={{ padding: '1.1rem 1.25rem' }}>
                    <p style={{
                        fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
                        letterSpacing: '0.06em', color: 'var(--color-text-muted)',
                        marginBottom: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.4rem',
                    }}>
                        {isCreditMemo ? <ReceiptText size={12} /> : <FileText size={12} />}
                        {isCreditMemo ? 'Credit Memo Details' : 'Invoice Details'}
                    </p>

                    <div style={fieldGap}>

                        {/* MDA — first field, mandatory. Sourced from
                            legacy ``accounting.MDA`` (NOT NCoA admin
                            segments) because that is the FK target on
                            VendorInvoice.mda. */}
                        <div>
                            <label style={lbl}>Administrative (MDA) <span style={{ color: '#ef4444' }}>*</span></label>
                            <SearchableSelect
                                options={mdas.map((m: any) => ({
                                    value: String(m.id),
                                    label: `${m.code} - ${m.name}`,
                                    sublabel: m.mda_type,
                                }))}
                                value={header.mda}
                                onChange={v => setHeader(h => ({ ...h, mda: v }))}
                                placeholder="Type MDA name or code..."
                                required
                            />
                        </div>

                        {/* Vendor */}
                        <div>
                            <label style={lbl}>Vendor <span style={{ color: '#ef4444' }}>*</span></label>
                            <SearchableSelect
                                options={vendorOptions}
                                value={header.vendor}
                                onChange={v => setHeader(h => ({ ...h, vendor: v }))}
                                placeholder="Type vendor name or code…"
                                required
                            />
                        </div>

                        {/* Reference */}
                        <div>
                            <label style={lbl}>{isCreditMemo ? 'Credit Memo No.' : 'Invoice No. / Reference'} <span style={{ color: '#ef4444' }}>*</span></label>
                            <input style={inp} type="text"
                                placeholder={isCreditMemo ? 'CM-001' : 'INV-001'}
                                value={header.reference}
                                onChange={e => setHeader(h => ({ ...h, reference: e.target.value }))} required />
                        </div>

                        {/* Dates */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                            <div>
                                <label style={lbl}>{isCreditMemo ? 'CM Date' : 'Invoice Date'} <span style={{ color: '#ef4444' }}>*</span></label>
                                <input style={inp} type="date" value={header.invoice_date}
                                    onChange={e => setHeader(h => ({ ...h, invoice_date: e.target.value }))} required />
                            </div>
                            {!isCreditMemo && (
                                <div>
                                    <label style={lbl}>Due Date <span style={{ color: '#ef4444' }}>*</span></label>
                                    <input style={inp} type="date" value={header.due_date}
                                        onChange={e => setHeader(h => ({ ...h, due_date: e.target.value }))} required />
                                </div>
                            )}
                        </div>

                        {/* Description */}
                        <div>
                            <label style={lbl}>Description</label>
                            <textarea
                                style={{ ...inp, minHeight: '60px', maxHeight: '80px', resize: 'vertical' }}
                                placeholder={isCreditMemo ? 'Reason for credit memo…' : 'Invoice details…'}
                                value={header.description}
                                onChange={e => setHeader(h => ({ ...h, description: e.target.value }))}
                            />
                        </div>

                        {/* Vendor AP credit amount — invoice only */}
                        {!isCreditMemo && (
                            <div>
                                <label style={lbl}>Vendor Amount (Cr AP) <span style={{ color: '#ef4444' }}>*</span></label>
                                <div style={{ position: 'relative' }}>
                                    <span style={{
                                        position: 'absolute', left: '9px', top: '50%', transform: 'translateY(-50%)',
                                        fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)',
                                        fontWeight: 700, pointerEvents: 'none',
                                    }}>{currencySymbol}</span>
                                    <input style={{ ...inp, paddingLeft: '1.75rem' }}
                                        type="number" step="0.01" min="0" placeholder="0.00"
                                        value={header.vendor_credit_amount}
                                        onChange={e => setHeader(h => ({ ...h, vendor_credit_amount: e.target.value }))}
                                        required />
                                </div>
                                <p style={{ margin: '0.2rem 0 0', fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>
                                    Amount to credit to vendor's AP account.
                                </p>
                            </div>
                        )}

                        {/* Attachment */}
                        <div>
                            <label style={lbl}>Attachment (optional)</label>
                            {!attachment ? (
                                <label style={{
                                    display: 'flex', alignItems: 'center', gap: '0.4rem',
                                    padding: '0.45rem 0.75rem', borderRadius: '7px',
                                    border: '1.5px dashed var(--color-border)',
                                    cursor: 'pointer', color: 'var(--color-text-muted)',
                                    fontSize: 'var(--text-xs)',
                                }}>
                                    <Paperclip size={13} />
                                    <span>Attach image or PDF</span>
                                    <input type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                                        onChange={e => setAttachment(e.target.files?.[0] || null)} />
                                </label>
                            ) : (
                                <div style={{
                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                    padding: '0.4rem 0.75rem', borderRadius: '7px',
                                    background: 'rgba(25,30,106,0.05)',
                                    border: '1.5px solid rgba(25,30,106,0.18)',
                                    fontSize: 'var(--text-xs)',
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-text)', minWidth: 0 }}>
                                        <Paperclip size={12} color="var(--color-primary)" style={{ flexShrink: 0 }} />
                                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {attachment.name}
                                        </span>
                                        <span style={{ color: 'var(--color-text-muted)', flexShrink: 0 }}>
                                            ({(attachment.size / 1024).toFixed(0)} KB)
                                        </span>
                                    </div>
                                    <button type="button" onClick={() => setAttachment(null)}
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '2px', flexShrink: 0 }}>
                                        <Trash2 size={13} />
                                    </button>
                                </div>
                            )}
                        </div>

                        {/* Dimensions moved to RIGHT panel — sits under
                            Line Items card so the operator can see them
                            in context with the lines they apply to. */}

                    </div>
                </div>

                {/* ── RIGHT PANEL: line items + balance/totals ──────── */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>

                    {/* Line Items Card */}
                    <div className="card" style={{ padding: '1.1rem 1.25rem' }}>
                        <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            marginBottom: '0.75rem',
                        }}>
                            <p style={{
                                fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
                                letterSpacing: '0.06em', color: 'var(--color-text-muted)', margin: 0,
                                display: 'flex', alignItems: 'center', gap: '0.4rem',
                            }}>
                                Line Items
                            </p>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <button type="button" onClick={() => addLine('expense')}
                                    style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', background: 'none', border: '1px solid var(--color-border)', borderRadius: '5px', cursor: 'pointer', color: 'var(--color-primary)', fontSize: '0.62rem', fontWeight: 600, padding: '0.25rem 0.5rem' }}>
                                    <Plus size={11} /> Expense
                                </button>
                                <button type="button" onClick={() => addLine('asset')}
                                    style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', background: 'none', border: '1px solid var(--color-border)', borderRadius: '5px', cursor: 'pointer', color: '#0d9488', fontSize: '0.62rem', fontWeight: 600, padding: '0.25rem 0.5rem' }}>
                                    <Plus size={11} /> Asset
                                </button>
                                <button type="button" onClick={() => addLine('gl')}
                                    style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', background: 'none', border: '1px solid var(--color-border)', borderRadius: '5px', cursor: 'pointer', color: '#7c3aed', fontSize: '0.62rem', fontWeight: 600, padding: '0.25rem 0.5rem' }}>
                                    <Plus size={11} /> GL Account
                                </button>
                            </div>
                        </div>

                        {/* Always-visible reference-data status strip.
                            Previous version hid itself once everything
                            loaded, which left the operator with no
                            signal at all when they opened a dropdown
                            and (mis)read a placeholder as ``empty``.
                            Now: green when all three datasets are
                            populated, amber while loading, red on
                            error. ``Refresh`` re-runs the imperative
                            fetches on demand — same call the focus
                            handler makes automatically. */}
                        {(() => {
                            const accCount = allAccounts.length;
                            const taxCount = Array.isArray(taxCodes) ? taxCodes.length : 0;
                            const whtCount = Array.isArray(whtList) ? whtList.length : 0;
                            const isReady  = accCount > 0 && taxCount > 0 && whtCount > 0;
                            const palette  = refDataError
                                ? { bg: '#fee2e2', border: '#fecaca', fg: '#991b1b' }
                                : isReady
                                    ? { bg: '#ecfdf5', border: '#a7f3d0', fg: '#065f46' }
                                    : { bg: '#fef3c7', border: '#fde68a', fg: '#92400e' };
                            const headline = refDataError
                                ? 'Reference data error:'
                                : refDataLoading
                                    ? 'Loading reference data:'
                                    : isReady
                                        ? 'Reference data ready —'
                                        : 'No reference data found:';
                            return (
                                <div style={{
                                    padding: '0.5rem 0.75rem', marginBottom: '0.6rem',
                                    borderRadius: '6px',
                                    background: palette.bg,
                                    border: `1px solid ${palette.border}`,
                                    fontSize: '0.7rem',
                                    color: palette.fg,
                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                    gap: '0.5rem',
                                }}>
                                    <span>
                                        <strong>{headline}</strong>{' '}
                                        Accounts: {accCount} · Tax codes: {taxCount} · WHT codes: {whtCount}
                                        {refDataError && <span> — {refDataError}</span>}
                                    </span>
                                    <button
                                        type="button"
                                        onClick={refetchAll}
                                        style={{
                                            background: '#fff',
                                            border: '1px solid currentColor',
                                            borderRadius: '4px',
                                            padding: '0.25rem 0.6rem',
                                            fontSize: '0.65rem', fontWeight: 600,
                                            color: 'inherit', cursor: 'pointer',
                                        }}
                                    >
                                        Refresh
                                    </button>
                                </div>
                            );
                        })()}

                        {/* Inline budget-check banner. Surfaces the
                            STRICT block (red) or advisory WARNING
                            (amber) at line level. Deliberately
                            generic — uses row numbers ("Line 1",
                            "Lines 2 & 4") rather than GL codes/names,
                            so screenshots can be shared safely and
                            the operator's eye stays on the inline
                            BLOCK/WARN pill for the per-row identity.
                            Auto-hides when nothing is blocked or
                            warned. */}
                        {(blockedLineNumbers.length > 0 || warningLineNumbers.length > 0) && (() => {
                            const fmtList = (ns: number[]) => {
                                if (ns.length === 1) return `Line ${ns[0]}`;
                                if (ns.length === 2) return `Lines ${ns[0]} & ${ns[1]}`;
                                return `Lines ${ns.slice(0, -1).join(', ')} & ${ns[ns.length - 1]}`;
                            };
                            const isBlock = blockedLineNumbers.length > 0;
                            const palette = isBlock
                                ? { bg: '#fef2f2', border: '#fecaca', fg: '#991b1b', icon: '⛔' }
                                : { bg: '#fef3c7', border: '#fde68a', fg: '#92400e', icon: '⚠️' };
                            const subjectList = isBlock
                                ? fmtList(blockedLineNumbers)
                                : fmtList(warningLineNumbers);
                            const text = isBlock
                                ? `${subjectList} cannot be posted: the budget control for the selected economic code is set to STRICT and there is no active appropriation that covers it. Either create / activate an appropriation for that code, or change the rule level to WARNING in Settings → Budget Check Rules.`
                                : `${subjectList} will post with an advisory: no active appropriation covers the selected economic code (or the appropriation is near its utilisation threshold). Posting is permitted, but consider creating or topping up the appropriation.`;
                            return (
                                <div role="alert" style={{
                                    padding: '0.6rem 0.85rem',
                                    marginBottom: '0.6rem',
                                    borderRadius: '7px',
                                    background: palette.bg,
                                    border: `1px solid ${palette.border}`,
                                    color: palette.fg,
                                    fontSize: '0.72rem',
                                    lineHeight: 1.45,
                                    display: 'flex', alignItems: 'flex-start', gap: '0.5rem',
                                }}>
                                    <span style={{ flexShrink: 0, fontSize: '0.85rem' }}>{palette.icon}</span>
                                    <span>
                                        <strong>{isBlock ? 'Budget control — strict block' : 'Budget control — advisory'}.</strong>{' '}
                                        {text}
                                    </span>
                                </div>
                            );
                        })()}

                        <div style={{ overflowX: 'auto' }}>
                            {/* ``table-layout: fixed`` forces the column widths
                                declared on <th> to be authoritative, so a
                                long descriptor in a SearchableSelect can never
                                push the column wider than its allocation —
                                the cell content truncates with ellipsis
                                instead. Without this rule, the browser uses
                                ``table-layout: auto`` (intrinsic sizing),
                                which lets long account names shift the page
                                horizontally. */}
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '560px', tableLayout: 'fixed' }}>
                                <thead>
                                    <tr style={{ borderBottom: '1.5px solid var(--color-border)' }}>
                                        {[
                                            { label: '#', w: '28px' },
                                            { label: 'Type', w: '70px' },
                                            { label: 'Account', w: '28%' },
                                            { label: 'Description', w: 'auto' },
                                            { label: 'Amount', w: '110px' },
                                            { label: 'Tax', w: '100px' },
                                            { label: 'WHT', w: '100px' },
                                            { label: '', w: '28px' },
                                        ].map(({ label, w }, i) => (
                                            <th key={i} style={{
                                                width: w, padding: '0 0.4rem 0.5rem',
                                                textAlign: 'left', fontSize: '0.62rem', fontWeight: 700,
                                                textTransform: 'uppercase', letterSpacing: '0.05em',
                                                color: 'var(--color-text-muted)',
                                            }}>
                                                {label}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {lines.map((line, idx) => {
                                        const lineTypeColors: Record<LineType, { bg: string; color: string; label: string }> = {
                                            expense: { bg: 'rgba(25,30,106,0.08)', color: 'var(--color-primary)', label: 'EXP' },
                                            asset: { bg: 'rgba(13,148,136,0.08)', color: '#0d9488', label: 'AST' },
                                            gl: { bg: 'rgba(124,58,237,0.08)', color: '#7c3aed', label: 'GL' },
                                        };
                                        const ltc = lineTypeColors[line.line_type] || lineTypeColors.expense;
                                        // Inline budget-check status for this line. The
                                        // pill colour mirrors the rule level returned by
                                        // /budget/check-line/: green = NONE/within
                                        // budget, amber = WARNING (advisory), red =
                                        // STRICT block (Save will be rejected). Tooltip
                                        // carries the full reason / first warning so the
                                        // operator can read context without leaving the
                                        // form.
                                        const check = lineChecks[line._uid];
                                        const checkPill = (() => {
                                            if (!check || line.line_type === 'asset') return null;
                                            // Visual state derives from ``blocked`` first, then
                                            // ``level``. STRICT does NOT automatically mean BLOCK:
                                            // a strict rule with a sufficient appropriation passes
                                            // (blocked=False) and should look "OK", not red. Only
                                            // ``blocked=true`` means Save will actually reject.
                                            //   blocked=true                → red BLOCK
                                            //   level === 'WARNING'         → amber WARN
                                            //   else (NONE | STRICT-pass)   → green OK
                                            // This also matches anyLineBlocked (which already
                                            // gates the Save button on .blocked) so the pill
                                            // and the disabled-Save tooltip can never disagree.
                                            type Variant = 'OK' | 'WARN' | 'BLOCK';
                                            const variant: Variant = check.blocked
                                                ? 'BLOCK'
                                                : check.level === 'WARNING'
                                                    ? 'WARN'
                                                    : 'OK';
                                            const pillStyle: Record<Variant, { bg: string; fg: string; dot: string; label: string }> = {
                                                OK:    { bg: 'rgba(22,163,74,0.10)',  fg: '#15803d', dot: '#16a34a', label: 'OK' },
                                                WARN:  { bg: 'rgba(234,179,8,0.12)',  fg: '#a16207', dot: '#f59e0b', label: 'WARN' },
                                                BLOCK: { bg: 'rgba(220,38,38,0.10)',  fg: '#b91c1c', dot: '#dc2626', label: 'BLOCK' },
                                            };
                                            const s = pillStyle[variant];
                                            const tip = check.reason || (check.warnings[0] || `Budget check: ${check.level}${check.blocked ? ' (blocked)' : ''}`);
                                            return (
                                                <span
                                                    title={tip}
                                                    style={{
                                                        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                        marginLeft: '0.3rem',
                                                        padding: '0.1rem 0.35rem', borderRadius: '4px',
                                                        background: s.bg, color: s.fg,
                                                        fontWeight: 700, fontSize: '0.55rem', letterSpacing: '0.03em',
                                                    }}
                                                >
                                                    <span style={{ width: 5, height: 5, borderRadius: '50%', background: s.dot }} />
                                                    {s.label}
                                                </span>
                                            );
                                        })();
                                        return (
                                        <tr key={line._uid} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            {/* Row number */}
                                            <td style={{ padding: '0.3rem 0.4rem 0.3rem 0', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', textAlign: 'center' }}>
                                                {idx + 1}
                                            </td>
                                            {/* Line Type badge + inline budget pill */}
                                            <td style={{ padding: '0.3rem 0.3rem 0.3rem 0' }}>
                                                <span style={{
                                                    display: 'inline-block', padding: '0.15rem 0.4rem', borderRadius: '4px',
                                                    background: ltc.bg, color: ltc.color, fontWeight: 700,
                                                    fontSize: '0.58rem', letterSpacing: '0.03em',
                                                }}>{ltc.label}</span>
                                                {checkPill}
                                            </td>
                                            {/* Account — asset lines show fixed assets, others show GL accounts */}
                                            <td style={{ padding: '0.3rem 0.3rem 0.3rem 0' }}>
                                                {line.line_type === 'asset' ? (
                                                    <SearchableSelect
                                                        options={fixedAssetOptions}
                                                        value={line.account}
                                                        onChange={v => {
                                                            updateLine(idx, 'account', v);
                                                            // Auto-fill description from asset name
                                                            const asset = (fixedAssets || []).find((a: any) => String(a.id) === v);
                                                            if (asset) updateLine(idx, 'description', `${asset.asset_number} — ${asset.name}`);
                                                        }}
                                                        placeholder={header.mda ? 'Select asset…' : 'Select MDA first'}
                                                        required
                                                        style={{ fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem', borderColor: !header.mda ? '#fbbf24' : undefined }}
                                                    />
                                                ) : (
                                                    <SearchableSelect
                                                        options={getAccountOptionsForLineType(line.line_type)}
                                                        value={line.account}
                                                        onChange={v => updateLine(idx, 'account', v)}
                                                        placeholder="Search code or name…"
                                                        required
                                                        style={{ fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem' }}
                                                    />
                                                )}
                                            </td>
                                            {/* Description */}
                                            <td style={{ padding: '0.3rem' }}>
                                                <input style={{ ...inp, fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem' }}
                                                    type="text" placeholder="Description"
                                                    value={line.description}
                                                    onChange={e => updateLine(idx, 'description', e.target.value)} />
                                            </td>
                                            {/* Amount */}
                                            <td style={{ padding: '0.3rem' }}>
                                                <div style={{ position: 'relative' }}>
                                                    <span style={{
                                                        position: 'absolute', left: '7px', top: '50%', transform: 'translateY(-50%)',
                                                        fontSize: '0.65rem', color: 'var(--color-text-muted)', fontWeight: 700, pointerEvents: 'none',
                                                    }}>{currencySymbol}</span>
                                                    <input style={{ ...inp, fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem 0.38rem 1.35rem' }}
                                                        type="number" step="0.01" min="0"
                                                        value={line.amount}
                                                        onChange={e => updateLine(idx, 'amount', e.target.value)} required />
                                                </div>
                                            </td>
                                            {/* Tax */}
                                            <td style={{ padding: '0.3rem' }}>
                                                <SearchableSelect
                                                    options={taxOptions}
                                                    value={line.tax_code}
                                                    onChange={v => updateLine(idx, 'tax_code', v)}
                                                    placeholder={taxOptions.length ? 'Select tax…' : 'None'}
                                                    style={{ fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem' }}
                                                />
                                            </td>
                                            {/* WHT */}
                                            <td style={{ padding: '0.3rem' }}>
                                                <SearchableSelect
                                                    options={whtOptions}
                                                    value={line.withholding_tax}
                                                    onChange={v => updateLine(idx, 'withholding_tax', v)}
                                                    placeholder={whtOptions.length ? 'Select WHT…' : 'None'}
                                                    style={{ fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem' }}
                                                />
                                            </td>
                                            {/* Remove */}
                                            <td style={{ padding: '0.3rem', textAlign: 'center' }}>
                                                {lines.length > 1 && (
                                                    <button type="button" onClick={() => removeLine(idx)}
                                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '2px', lineHeight: 1 }}>
                                                        <Trash2 size={14} />
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* ── Dimensions card — horizontal under Line Items ───
                        4-up grid (Fund · Function · Program · Geo) so the
                        operator sees all NCoA classifiers side-by-side
                        directly under the lines they apply to. Was
                        previously stacked 2x2 in the LEFT panel which
                        forced the operator to scroll between the line
                        amount and the dimensions on every entry. */}
                    {dimensionsEnabled && (
                        <div className="card" style={{ padding: '1.1rem 1.25rem' }}>
                            <p style={{
                                fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
                                letterSpacing: '0.06em', color: 'var(--color-text-muted)',
                                margin: '0 0 0.6rem 0',
                                display: 'flex', alignItems: 'center', gap: '0.35rem',
                            }}>
                                <Layers size={11} /> Dimensions
                            </p>
                            <div style={{
                                display: 'grid',
                                // 4 columns on wide screens; auto-collapse to 2-up
                                // when the panel is narrow so dropdowns stay usable
                                // on a laptop without a horizontal scroll.
                                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                                gap: '0.6rem',
                            }}>
                                {[
                                    { key: 'fund',     label: 'Fund',     options: fundOptions },
                                    { key: 'function', label: 'Function', options: functionOptions },
                                    { key: 'program',  label: 'Program',  options: programOptions },
                                    { key: 'geo',      label: 'Geo',      options: geoOptions },
                                ].map(({ key, label, options }) => (
                                    <div key={key}>
                                        <label style={lbl}>{label} <span style={{ color: '#ef4444' }}>*</span></label>
                                        <SearchableSelect
                                            options={options}
                                            value={(header as any)[key]}
                                            onChange={v => setHeader(h => ({ ...h, [key]: v }))}
                                            placeholder={`Search ${label}…`}
                                            required
                                        />
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* ── Balance validator + totals (single card) ─────── */}
                    <div className="card" style={{
                        padding: '0.875rem 1.25rem',
                        border: grandTotal === 0
                            ? '1px solid var(--color-border)'
                            : isBalanced
                                ? '1px solid rgba(22,163,74,0.35)'
                                : '1px solid rgba(220,38,38,0.4)',
                        background: grandTotal === 0
                            ? 'var(--color-surface)'
                            : isBalanced
                                ? 'rgba(22,163,74,0.03)'
                                : 'rgba(220,38,38,0.03)',
                        transition: 'border-color 0.2s, background 0.2s',
                    }}>

                        {/* Balance row */}
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 1px 1fr 1px auto',
                            alignItems: 'center',
                            gap: '1rem',
                            paddingBottom: '0.75rem',
                            marginBottom: '0.75rem',
                            borderBottom: '1px solid var(--color-border)',
                        }}>
                            {/* DR side — line gross (subtotal). Tax/WHT
                                go to their own GL accounts at posting
                                time and don't belong in the operator's
                                DR vs CR balance check. */}
                            <div>
                                <p style={{ margin: '0 0 0.2rem', fontSize: '0.62rem', fontWeight: 600, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                    {pill('rgba(25,30,106,0.1)', 'var(--color-primary)', 'DR')}
                                    {isCreditMemo ? 'Accounts Payable' : 'Expense (Lines)'}
                                </p>
                                <p style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 800, color: 'var(--color-text)', letterSpacing: '-0.02em' }}>
                                    {formatCurrency(subtotal)}
                                </p>
                            </div>

                            <div style={{ width: 1, height: 36, background: 'var(--color-border)', justifySelf: 'center' }} />

                            {/* CR side */}
                            <div>
                                <p style={{ margin: '0 0 0.2rem', fontSize: '0.62rem', fontWeight: 600, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                    {pill('rgba(13,148,136,0.1)', '#0d9488', 'CR')}
                                    {isCreditMemo ? 'Expense (Lines)' : 'Accounts Payable'}
                                </p>
                                <p style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 800, color: 'var(--color-text)', letterSpacing: '-0.02em' }}>
                                    {isCreditMemo ? formatCurrency(subtotal) : formatCurrency(creditAmount)}
                                </p>
                            </div>

                            <div style={{ width: 1, height: 36, background: 'var(--color-border)', justifySelf: 'center' }} />

                            {/* Status */}
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.15rem', minWidth: '120px' }}>
                                {grandTotal === 0 ? (
                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                                        Enter amounts above
                                    </span>
                                ) : isBalanced ? (
                                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#16a34a', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                                        <CheckCircle size={15} /> Balanced
                                    </span>
                                ) : (
                                    <>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#dc2626', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                                            <AlertCircle size={15} /> Out of Balance
                                        </span>
                                        <span style={{ fontSize: 'var(--text-xs)', color: '#dc2626', fontWeight: 600 }}>
                                            Diff: {formatCurrency(Math.abs(balanceDiff))}
                                        </span>
                                    </>
                                )}
                            </div>
                        </div>

                        {/* Totals strip */}
                        <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            flexWrap: 'wrap', gap: '0.5rem',
                        }}>
                            <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
                                {[
                                    { label: 'Subtotal', value: subtotal },
                                    { label: 'Tax', value: taxTotal },
                                    { label: 'WHT', value: whtTotal },
                                ].map(({ label, value }) => (
                                    <div key={label}>
                                        <p style={{ margin: 0, fontSize: '0.62rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', letterSpacing: '0.04em' }}>
                                            {label}
                                        </p>
                                        <p style={{ margin: 0, fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)' }}>
                                            {formatCurrency(value)}
                                        </p>
                                    </div>
                                ))}
                            </div>

                            {/* Grand total highlight */}
                            <div style={{
                                padding: '0.4rem 1rem', borderRadius: '8px',
                                background: isCreditMemo
                                    ? 'linear-gradient(135deg, #0f766e, #0d9488)'
                                    : 'linear-gradient(135deg, #0f1240, #191e6a)',
                                color: '#fff',
                                textAlign: 'right',
                            }}>
                                <p style={{ margin: 0, fontSize: '0.62rem', fontWeight: 600, opacity: 0.8, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                                    Total
                                </p>
                                <p style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 800, letterSpacing: '-0.02em' }}>
                                    {formatCurrency(grandTotal)}
                                </p>
                            </div>
                        </div>
                    </div>

                </div>{/* /right panel */}
            </div>{/* /main grid */}

            {/* ── Posting simulation modal ──────────────────────────
                SAP-style ``Simulate``. Renders every DR/CR line the
                backend will book — line gross to expense/asset, tax
                to its configured Input VAT account, WHT to its
                Payable account, residual to AP. If totals don't
                balance OR an account is unresolved, the modal flags
                it visibly so the operator fixes config before
                posting. */}
            {showPreview && (
                <div
                    onClick={() => setShowPreview(false)}
                    style={{
                        position: 'fixed', inset: 0, zIndex: 9000,
                        background: 'rgba(15,18,64,0.55)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '1rem',
                    }}
                >
                    <div
                        onClick={e => e.stopPropagation()}
                        style={{
                            background: 'var(--color-surface, #fff)',
                            borderRadius: '10px',
                            width: 'min(820px, 96vw)',
                            maxHeight: '88vh',
                            overflow: 'auto',
                            boxShadow: '0 20px 50px rgba(0,0,0,0.25)',
                        }}
                    >
                        {/* Modal header */}
                        <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            padding: '1rem 1.25rem',
                            borderBottom: '1px solid var(--color-border)',
                        }}>
                            <div>
                                <h2 style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 800, color: 'var(--color-text)' }}>
                                    Simulated accounting entry
                                </h2>
                                <p style={{ margin: '0.2rem 0 0', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                                    Preview only — nothing is posted yet. Close and click <em>{isCreditMemo ? 'Save Credit Memo' : 'Save Invoice'}</em> to commit.
                                </p>
                            </div>
                            <button type="button" onClick={() => setShowPreview(false)}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: 4 }}
                                aria-label="Close preview"
                            >
                                <XIcon size={18} />
                            </button>
                        </div>

                        {/* Lines table */}
                        <div style={{ padding: '1rem 1.25rem' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
                                <thead>
                                    <tr style={{ borderBottom: '1.5px solid var(--color-border)' }}>
                                        {['#', 'Side', 'Account', 'Description', 'Debit', 'Credit'].map((h, i) => (
                                            <th key={i} style={{
                                                padding: '0.5rem 0.6rem', textAlign: i >= 4 ? 'right' : 'left',
                                                fontSize: '0.62rem', fontWeight: 700,
                                                textTransform: 'uppercase', letterSpacing: '0.05em',
                                                color: 'var(--color-text-muted)',
                                            }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {previewEntries.map((e, i) => {
                                        const isDr = e.side === 'DR';
                                        return (
                                            <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                                <td style={{ padding: '0.45rem 0.6rem', color: 'var(--color-text-muted)' }}>{i + 1}</td>
                                                <td style={{ padding: '0.45rem 0.6rem' }}>
                                                    <span style={{
                                                        padding: '0.1rem 0.4rem', borderRadius: 4,
                                                        fontSize: '0.6rem', fontWeight: 700,
                                                        background: isDr ? 'rgba(25,30,106,0.1)' : 'rgba(13,148,136,0.12)',
                                                        color: isDr ? 'var(--color-primary)' : '#0d9488',
                                                    }}>{e.side}</span>
                                                </td>
                                                <td style={{ padding: '0.45rem 0.6rem', fontWeight: 600, color: e.account.includes('not configured') || e.account.includes('not set') ? '#dc2626' : 'var(--color-text)' }}>
                                                    {e.account}
                                                </td>
                                                <td style={{ padding: '0.45rem 0.6rem', color: 'var(--color-text-muted)' }}>{e.description}</td>
                                                <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}>
                                                    {isDr ? formatCurrency(e.amount) : ''}
                                                </td>
                                                <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}>
                                                    {!isDr ? formatCurrency(e.amount) : ''}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                    <tr style={{ borderTop: '2px solid var(--color-border)', fontWeight: 800 }}>
                                        <td colSpan={4} style={{ padding: '0.6rem', textAlign: 'right', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)' }}>
                                            Totals
                                        </td>
                                        <td style={{ padding: '0.6rem', textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}>
                                            {formatCurrency(previewDrTotal)}
                                        </td>
                                        <td style={{ padding: '0.6rem', textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}>
                                            {formatCurrency(previewCrTotal)}
                                        </td>
                                    </tr>
                                </tbody>
                            </table>

                            {/* Balance status */}
                            <div style={{
                                marginTop: '0.8rem',
                                padding: '0.6rem 0.8rem',
                                borderRadius: 6,
                                background: previewBalanced ? 'rgba(22,163,74,0.08)' : 'rgba(220,38,38,0.08)',
                                border: `1px solid ${previewBalanced ? 'rgba(22,163,74,0.3)' : 'rgba(220,38,38,0.3)'}`,
                                color: previewBalanced ? '#15803d' : '#b91c1c',
                                fontSize: '0.75rem',
                                display: 'flex', alignItems: 'center', gap: '0.4rem',
                            }}>
                                {previewBalanced ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                                <span>
                                    {previewBalanced
                                        ? 'Balanced — debits equal credits.'
                                        : `Out of balance — Diff ${formatCurrency(Math.abs(previewDrTotal - previewCrTotal))}. Check that tax / WHT codes have GL accounts configured in Tax Management.`}
                                </span>
                            </div>
                        </div>

                        {/* Footer actions */}
                        <div style={{
                            display: 'flex', justifyContent: 'flex-end', gap: '0.6rem',
                            padding: '0.8rem 1.25rem',
                            borderTop: '1px solid var(--color-border)',
                            background: 'rgba(0,0,0,0.02)',
                        }}>
                            <button type="button" className="btn btn-outline"
                                onClick={() => setShowPreview(false)}
                                style={{ padding: '0.4rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </form>
    );
};

export default VendorInvoiceForm;
