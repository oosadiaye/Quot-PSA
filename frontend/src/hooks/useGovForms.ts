/**
 * useGovForms — Shared hooks for government IFMIS form pages.
 *
 * Provides:
 * 1. Mutation hooks for creating government documents (PV, Revenue, Appropriation, etc.)
 * 2. Data loading hooks for form dropdowns (NCoA segments, TSA accounts, revenue heads)
 *
 * Pattern: useMutation + queryClient.invalidateQueries on success
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import { invalidateLedgerCaches } from '../features/accounting/hooks/invalidateLedger';

// ─── Data Loading Hooks (for form dropdowns) ──────────────────────────

/** Load all 6 NCoA segment types in parallel for form selectors.
 *  Uses ``Promise.allSettled`` so a single failing segment endpoint
 *  doesn't blank the entire form — the fields whose segments loaded
 *  successfully remain usable; only the failed segment renders empty.
 *  Was ``Promise.all`` which fail-fasted on the first rejection. */
export function useNCoASegments() {
    return useQuery({
        queryKey: ['ncoa-segments-all'],
        queryFn: async () => {
            const endpoints = [
                '/accounting/ncoa/administrative/',
                '/accounting/ncoa/economic/',
                '/accounting/ncoa/functional/',
                '/accounting/ncoa/programme/',
                '/accounting/ncoa/fund/',
                '/accounting/ncoa/geographic/',
            ];
            const results = await Promise.allSettled(
                endpoints.map((url) =>
                    apiClient.get(url, { params: { page_size: 9999, is_active: true } }),
                ),
            );
            const extract = (idx: number) => {
                const r = results[idx];
                if (r.status !== 'fulfilled') return [];
                const d = r.value.data;
                return Array.isArray(d) ? d : d?.results || [];
            };
            return {
                administrative: extract(0),
                economic: extract(1),
                functional: extract(2),
                programme: extract(3),
                fund: extract(4),
                geographic: extract(5),
            };
        },
        staleTime: 10 * 60 * 1000,
    });
}

/** Load TSA accounts for dropdown */
export function useTSAAccounts() {
    return useQuery({
        queryKey: ['tsa-accounts-dropdown'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/tsa-accounts/', { params: { page_size: 9999, is_active: true } });
            return Array.isArray(data) ? data : data?.results || [];
        },
        staleTime: 5 * 60 * 1000,
    });
}

/** Load revenue heads for dropdown */
export function useRevenueHeadsList() {
    return useQuery({
        queryKey: ['revenue-heads-dropdown'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/revenue-heads/', { params: { page_size: 9999, is_active: true } });
            return Array.isArray(data) ? data : data?.results || [];
        },
        staleTime: 5 * 60 * 1000,
    });
}

/** Load appropriations for dropdown (active only) */
export function useAppropriationsList() {
    return useQuery({
        queryKey: ['appropriations-dropdown'],
        queryFn: async () => {
            const { data } = await apiClient.get('/budget/appropriations/', { params: { page_size: 9999, status: 'ACTIVE' } });
            return Array.isArray(data) ? data : data?.results || [];
        },
        staleTime: 2 * 60 * 1000,
    });
}

/** Load fiscal years for dropdown */
export function useFiscalYears() {
    return useQuery({
        queryKey: ['fiscal-years-dropdown'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/fiscal-years/', { params: { page_size: 100 } });
            return Array.isArray(data) ? data : data?.results || [];
        },
        staleTime: 10 * 60 * 1000,
    });
}

// ─── Mutation Hooks (for form submission) ─────────────────────────────

/** Create Payment Voucher */
export function useCreatePV() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Record<string, unknown>) => {
            const { data } = await apiClient.post('/accounting/payment-vouchers/', payload);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/payment-vouchers/'] });
            qc.invalidateQueries({ queryKey: ['gov-tsa-cash-position'] });
        },
    });
}

/** Update Payment Voucher (PATCH). Use only on DRAFT vouchers — the
 *  backend serializer guards immutable fields (voucher_number,
 *  net_amount, journal) via read_only_fields, but business validation
 *  for non-draft transitions still belongs in workflow actions. */
export function useUpdatePV() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, payload }: { id: number; payload: Record<string, unknown> }) => {
            const { data } = await apiClient.patch(`/accounting/payment-vouchers/${id}/`, payload);
            return data;
        },
        onSuccess: (_d, vars) => {
            qc.invalidateQueries({ queryKey: ['payment-voucher-detail', String(vars.id)] });
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/payment-vouchers/'] });
        },
    });
}

/** PV Actions: approve, schedule, mark_paid — any of these can post a
 *  GL journal (notably ``pay``/``mark_paid``), so we invalidate the
 *  full ledger cache surface (Trial Balance, Balance Sheet, P&L, Cash
 *  Flow, GL balances) so the next paint reflects the posting. */
export function usePVAction() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, action, data }: { id: number; action: string; data?: Record<string, unknown> }) => {
            const { data: resp } = await apiClient.post(`/accounting/payment-vouchers/${id}/${action}/`, data || {});
            return resp;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['payment-voucher-detail'] });
            // ``schedule_payment`` materialises a draft ``Payment`` row
            // for the Outgoing Payments page; bust that list too so it
            // shows up the moment the user navigates over.
            qc.invalidateQueries({ queryKey: ['payments'] });
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/payments/'] });
            invalidateLedgerCaches(qc);
        },
    });
}

/** Create Revenue Collection */
export function useCreateRevenueCollection() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Record<string, unknown>) => {
            const { data } = await apiClient.post('/accounting/revenue-collections/', payload);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/revenue-collections/'] });
            qc.invalidateQueries({ queryKey: ['gov-revenue-summary'] });
        },
    });
}

/** Revenue Collection Actions: confirm, post_to_gl.
 *
 *  ``post_to_gl`` writes a balanced JournalHeader (DR Cash / CR
 *  Revenue), so every report derived from posted journals (Trial
 *  Balance, Income Statement, Cash Flow) must refresh on next paint.
 *  Calling ``invalidateLedgerCaches`` busts the full report surface
 *  alongside the revenue-specific keys. */
export function useRevenueAction() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, action }: { id: number; action: string }) => {
            const { data } = await apiClient.post(`/accounting/revenue-collections/${id}/${action}/`);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/revenue-collections/'] });
            qc.invalidateQueries({ queryKey: ['revenue-collection-detail'] });
            qc.invalidateQueries({ queryKey: ['gov-revenue-summary'] });
            invalidateLedgerCaches(qc);
        },
    });
}

/** Create Appropriation */
export function useCreateAppropriation() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Record<string, unknown>) => {
            const { data } = await apiClient.post('/budget/appropriations/', payload);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/budget/appropriations/'] });
            qc.invalidateQueries({ queryKey: ['gov-budget-execution'] });
        },
    });
}

/** Appropriation Actions: enact */
export function useAppropriationAction() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, action }: { id: number; action: string }) => {
            const { data } = await apiClient.post(`/budget/appropriations/${id}/${action}/`);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/budget/appropriations/'] });
            qc.invalidateQueries({ queryKey: ['gov-budget-execution'] });
        },
    });
}

/** Create Warrant — also busts the appropriation cache so the
 *  expended/available figures the user just affected refresh on
 *  the next paint. */
export function useCreateWarrant() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Record<string, unknown>) => {
            const { data } = await apiClient.post('/budget/warrants/', payload);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/budget/warrants/'] });
            qc.invalidateQueries({ queryKey: ['generic-list', '/budget/appropriations/'] });
            qc.invalidateQueries({ queryKey: ['contract-appropriation'] });
        },
    });
}

/** Warrant Actions: release / suspend / cancel — same cross-resource
 *  invalidation so any card showing appropriation totals (Appropriation
 *  list, Warrant list, Contract Detail's appropriation panel) sees
 *  the new figures immediately. */
export function useWarrantAction() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, action }: { id: number; action: string }) => {
            const { data } = await apiClient.post(`/budget/warrants/${id}/${action}/`);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/budget/warrants/'] });
            qc.invalidateQueries({ queryKey: ['generic-list', '/budget/appropriations/'] });
            qc.invalidateQueries({ queryKey: ['contract-appropriation'] });
        },
    });
}

/** Create TSA Account */
export function useCreateTSAAccount() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Record<string, unknown>) => {
            const { data } = await apiClient.post('/accounting/tsa-accounts/', payload);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/tsa-accounts/'] });
            qc.invalidateQueries({ queryKey: ['tsa-accounts-dropdown'] });
        },
    });
}

/**
 * Fetch a single TSA Account by id — used by the edit form to hydrate
 * existing values. Disabled when ``id`` is falsy so the create-mode
 * route doesn't trigger a wasted GET.
 */
export function useTSAAccount(id: string | number | undefined) {
    return useQuery({
        queryKey: ['tsa-account-detail', String(id ?? '')],
        queryFn: async () => {
            if (!id) return null;
            const { data } = await apiClient.get(`/accounting/tsa-accounts/${id}/`);
            return data;
        },
        enabled: !!id,
    });
}

/**
 * Update an existing TSA Account. Mirrors the create hook's cache-bust
 * keys so list, dropdown, and detail caches all stay in sync after a
 * save — the user lands back on the list and sees the new values
 * without a manual refetch.
 */
export function useUpdateTSAAccount() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, payload }: { id: string | number; payload: Record<string, unknown> }) => {
            const { data } = await apiClient.patch(`/accounting/tsa-accounts/${id}/`, payload);
            return data;
        },
        onSuccess: (_data, vars) => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/tsa-accounts/'] });
            qc.invalidateQueries({ queryKey: ['tsa-accounts-dropdown'] });
            qc.invalidateQueries({ queryKey: ['tsa-account-detail', String(vars.id)] });
        },
    });
}

// ─── Fetch Single Record (for detail pages) ───────────────────────────

export function usePaymentVoucherDetail(id: string | undefined) {
    return useQuery({
        queryKey: ['payment-voucher-detail', id],
        queryFn: async () => {
            if (!id) return null;
            const { data } = await apiClient.get(`/accounting/payment-vouchers/${id}/`);
            return data;
        },
        enabled: !!id,
    });
}

export function useRevenueCollectionDetail(id: string | undefined) {
    return useQuery({
        queryKey: ['revenue-collection-detail', id],
        queryFn: async () => {
            if (!id) return null;
            const { data } = await apiClient.get(`/accounting/revenue-collections/${id}/`);
            return data;
        },
        enabled: !!id,
    });
}
