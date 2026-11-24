import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../../api/client';

export interface CashJournal {
    id: number;
    code: string;
    name: string;
    mda: number | null;
    mda_name: string;
    cash_account: number;
    cash_account_name: string;
    cash_account_type: string;
    float_amount: string;
    difference_account: number | null;
    difference_account_name: string;
    allow_negative_balance: boolean;
    overdraft_limit: string;
    is_active: boolean;
    last_closed_date: string | null;
    balance: string;
}

export interface CashDocumentLine {
    id?: number;
    account: number;
    account_code?: string;
    account_name?: string;
    description: string;
    amount: string;
}

export interface CashDocument {
    id: number;
    document_number: string;
    cash_journal: number;
    cash_journal_name: string;
    posting_date: string;
    transaction_type: 'EXPENSE' | 'REVENUE' | 'BANK_WITHDRAWAL' | 'BANK_DEPOSIT';
    transaction_type_label: string;
    is_receipt: boolean;
    amount: string;
    signed_amount: string;
    description: string;
    reference: string;
    recipient: string;
    offset_account: number | null;
    offset_account_code: string;
    offset_account_name: string;
    bank_account: number | null;
    bank_account_name: string;
    mda: number | null;
    mda_name: string;
    fund: number | null;
    function: number | null;
    program: number | null;
    geo: number | null;
    status: 'Draft' | 'Posted' | 'Reversed';
    journal_entry: number | null;
    journal_number: string;
    reversal_journal: number | null;
    posted_at: string | null;
    lines: CashDocumentLine[];
}

export interface CashBook {
    opening_balance: string;
    receipts: string;
    payments: string;
    closing_balance: string;
    draft_receipts: string;
    draft_payments: string;
    balance_including_drafts: string;
    current_balance: string;
    last_closed_date: string | null;
    float_amount: string;
    draft_documents: number;
    last_count: { closing_date: string; book_balance: string; counted_amount: string; difference: string } | null;
}

export interface Replenishment {
    float_amount: string;
    balance: string;
    amount: string;
}

export interface HistoryEntry {
    account_code: string;
    account_name: string;
    debit: string;
    credit: string;
    memo: string;
}

export interface CashDocumentHistory {
    document_number: string;
    status: string;
    events: { event: string; label: string; by: string; at: string | null }[];
    entries: HistoryEntry[];
    entries_are_projected: boolean;
    note: string;
    journal_number: string | null;
    reversal_journal_number: string | null;
    reversal_entries: HistoryEntry[];
}

interface Page<T> {
    count: number;
    results: T[];
}

const BASE = '/accounting';

/** A sentence for the cashier from an API error: the server's own reason, a field problem, or a plain fallback. */
export function errorSentence(err: unknown, fallback = 'That did not work. Please try again.'): string {
    const data = (err as { response?: { data?: unknown } })?.response?.data;
    if (typeof data === 'string' && !data.trim().startsWith('<')) return data;
    if (data && typeof data === 'object') {
        const body = data as Record<string, unknown>;
        if (typeof body.error === 'string') return body.error;
        if (typeof body.detail === 'string') return body.detail;
        const first = Object.entries(body).find(([, v]) => v);
        if (first) {
            const [field, value] = first;
            const text = Array.isArray(value) ? String(value[0]) : typeof value === 'string' ? value : '';
            if (text) return field === 'non_field_errors' ? text : `${field.replace(/_/g, ' ')}: ${text}`;
        }
    }
    const message = (err as { message?: string })?.message;
    return message && !message.startsWith('Request failed') ? message : fallback;
}

export function useCashJournals() {
    return useQuery<CashJournal[]>({
        queryKey: ['cash-journals'],
        queryFn: async () => {
            const { data } = await apiClient.get(`${BASE}/cash-journals/`, { params: { page_size: 200, is_active: true } });
            return Array.isArray(data) ? data : data.results ?? [];
        },
    });
}

export function useCashBook(journalId: number | null, from: string, to: string) {
    return useQuery<CashBook>({
        queryKey: ['cash-book', journalId, from, to],
        queryFn: async () => (await apiClient.get(`${BASE}/cash-journals/${journalId}/book/`, { params: { date_from: from, date_to: to } })).data,
        enabled: !!journalId && !!from && !!to,
        placeholderData: keepPreviousData,
    });
}

export function useReplenishment(journalId: number | null, enabled: boolean) {
    return useQuery<Replenishment>({
        queryKey: ['cash-replenishment', journalId],
        queryFn: async () => (await apiClient.get(`${BASE}/cash-journals/${journalId}/replenishment/`)).data,
        enabled: !!journalId && enabled,
    });
}

export interface DocumentFilters {
    journal: number | null;
    from: string;
    to: string;
    status: string;
    search: string;
    page: number;
    pageSize: number;
}

export function useCashDocuments(f: DocumentFilters) {
    return useQuery<Page<CashDocument>>({
        queryKey: ['cash-documents', f],
        queryFn: async () => {
            const params: Record<string, unknown> = { cash_journal: f.journal, posting_date__gte: f.from, posting_date__lte: f.to, page: f.page, page_size: f.pageSize };
            if (f.status) params.status = f.status;
            if (f.search.trim()) params.search = f.search.trim();
            return (await apiClient.get(`${BASE}/cash-documents/`, { params })).data;
        },
        enabled: !!f.journal,
        placeholderData: keepPreviousData,
    });
}

export function useCashDocumentHistory(id: number | null) {
    return useQuery<CashDocumentHistory>({
        queryKey: ['cash-document-history', id],
        queryFn: async () => (await apiClient.get(`${BASE}/cash-documents/${id}/history/`)).data,
        enabled: !!id,
    });
}

export function useCashClosings(journalId: number | null, enabled: boolean) {
    return useQuery<{ id: number; closing_date: string; book_balance: string; counted_amount: string; difference: string; note: string }[]>({
        queryKey: ['cash-closings', journalId],
        queryFn: async () => (await apiClient.get(`${BASE}/cash-journals/${journalId}/closings/`)).data,
        enabled: !!journalId && enabled,
    });
}

/** Everything a posting, reversal or count can change on screen. */
function useRefresh() {
    const qc = useQueryClient();
    return () => Promise.all(['cash-journals', 'cash-book', 'cash-documents', 'cash-document-history', 'cash-replenishment', 'cash-closings', 'journals', 'gl-balances']
        .map(key => qc.invalidateQueries({ queryKey: [key] })));
}

export function useSaveCashDocument() {
    const refresh = useRefresh();
    return useMutation<CashDocument, unknown, { id?: number; body: Record<string, unknown> }>({
        mutationFn: async ({ id, body }) => (id
            ? await apiClient.put(`${BASE}/cash-documents/${id}/`, body)
            : await apiClient.post(`${BASE}/cash-documents/`, body)).data,
        onSuccess: refresh,
    });
}

export function usePostCashDocument() {
    const refresh = useRefresh();
    return useMutation<CashDocument, unknown, number>({
        mutationFn: async id => (await apiClient.post(`${BASE}/cash-documents/${id}/post_document/`)).data,
        onSuccess: refresh,
    });
}

export function useReverseCashDocument() {
    const refresh = useRefresh();
    return useMutation<CashDocument, unknown, { id: number; reason: string }>({
        mutationFn: async ({ id, reason }) => (await apiClient.post(`${BASE}/cash-documents/${id}/reverse/`, { reason })).data,
        onSuccess: refresh,
    });
}

export function useDeleteCashDocument() {
    const refresh = useRefresh();
    return useMutation<void, unknown, number>({
        mutationFn: async id => { await apiClient.delete(`${BASE}/cash-documents/${id}/`); },
        onSuccess: refresh,
    });
}

export function useCloseCashJournal() {
    const refresh = useRefresh();
    return useMutation<unknown, unknown, { id: number; closing_date: string; counted_amount: string; note: string }>({
        mutationFn: async ({ id, ...body }) => (await apiClient.post(`${BASE}/cash-journals/${id}/close/`, body)).data,
        onSuccess: refresh,
    });
}

export function useSaveJournalSettings() {
    const refresh = useRefresh();
    return useMutation<CashJournal, unknown, { id: number; body: Record<string, unknown> }>({
        mutationFn: async ({ id, body }) => (await apiClient.patch(`${BASE}/cash-journals/${id}/settings/`, body)).data,
        onSuccess: refresh,
    });
}
