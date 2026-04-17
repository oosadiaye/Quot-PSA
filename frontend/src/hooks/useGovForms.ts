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

// ─── Data Loading Hooks (for form dropdowns) ──────────────────────────

/** Load all 6 NCoA segment types in parallel for form selectors */
export function useNCoASegments() {
    return useQuery({
        queryKey: ['ncoa-segments-all'],
        queryFn: async () => {
            const [admin, economic, functional, programme, fund, geo] = await Promise.all([
                apiClient.get('/accounting/ncoa/administrative/', { params: { page_size: 9999, is_active: true } }),
                apiClient.get('/accounting/ncoa/economic/', { params: { page_size: 9999, is_active: true } }),
                apiClient.get('/accounting/ncoa/functional/', { params: { page_size: 9999, is_active: true } }),
                apiClient.get('/accounting/ncoa/programme/', { params: { page_size: 9999, is_active: true } }),
                apiClient.get('/accounting/ncoa/fund/', { params: { page_size: 9999, is_active: true } }),
                apiClient.get('/accounting/ncoa/geographic/', { params: { page_size: 9999, is_active: true } }),
            ]);
            const extract = (res: { data: any }) => {
                const d = res.data;
                return Array.isArray(d) ? d : d?.results || [];
            };
            return {
                administrative: extract(admin),
                economic: extract(economic),
                functional: extract(functional),
                programme: extract(programme),
                fund: extract(fund),
                geographic: extract(geo),
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

/** PV Actions: approve, schedule, mark_paid */
export function usePVAction() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, action, data }: { id: number; action: string; data?: Record<string, unknown> }) => {
            const { data: resp } = await apiClient.post(`/accounting/payment-vouchers/${id}/${action}/`, data || {});
            return resp;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/payment-vouchers/'] });
            qc.invalidateQueries({ queryKey: ['payment-voucher-detail'] });
            qc.invalidateQueries({ queryKey: ['gov-tsa-cash-position'] });
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

/** Revenue Collection Actions: confirm, post_to_gl */
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

/** Create Warrant */
export function useCreateWarrant() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Record<string, unknown>) => {
            const { data } = await apiClient.post('/budget/warrants/', payload);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/budget/warrants/'] });
        },
    });
}

/** Warrant Actions: release */
export function useWarrantAction() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, action }: { id: number; action: string }) => {
            const { data } = await apiClient.post(`/budget/warrants/${id}/${action}/`);
            return data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list', '/budget/warrants/'] });
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
