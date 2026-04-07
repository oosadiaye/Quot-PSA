import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const STALE = 2 * 60 * 1000;

// ─── Budget Periods ──────────────────────────────────────────────────────────

export const useBudgetPeriods = (filters: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['budget-periods', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/budget-periods/', { params: filters });
            return data.results || data;
        },
        staleTime: STALE,
    });
};

// ─── Accruals ────────────────────────────────────────────────────────────────

export const useAccruals = (filters: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['accruals', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accruals/', { params: filters });
            return data.results || data;
        },
        staleTime: STALE,
    });
};

export const useAccrual = (id: number, enabled = true) => {
    return useQuery({
        queryKey: ['accrual', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/accruals/${id}/`);
            return data;
        },
        enabled: !!id && enabled,
        retry: false,
    });
};

export const useCreateAccrual = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/accruals/', payload);
            return data;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accruals'] }),
    });
};

export const useUpdateAccrual = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: res } = await apiClient.patch(`/accounting/accruals/${id}/`, data);
            return res;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accruals'] }),
    });
};

export const useDeleteAccrual = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/accruals/${id}/`);
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accruals'] }),
    });
};

export const usePostAccrual = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/accounting/accruals/${id}/post/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['accruals'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const useReverseAccrual = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/accounting/accruals/${id}/reverse/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['accruals'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

// ─── Deferrals ───────────────────────────────────────────────────────────────

export const useDeferrals = (filters: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['deferrals', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/deferrals/', { params: filters });
            return data.results || data;
        },
        staleTime: STALE,
    });
};

export const useDeferral = (id: number, enabled = true) => {
    return useQuery({
        queryKey: ['deferral', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/deferrals/${id}/`);
            return data;
        },
        enabled: !!id && enabled,
        retry: false,
    });
};

export const useCreateDeferral = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/deferrals/', payload);
            return data;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deferrals'] }),
    });
};

export const useUpdateDeferral = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: res } = await apiClient.patch(`/accounting/deferrals/${id}/`, data);
            return res;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deferrals'] }),
    });
};

export const useDeleteDeferral = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/deferrals/${id}/`);
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deferrals'] }),
    });
};

export const useRecognizeDeferral = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/accounting/deferrals/${id}/recognize/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['deferrals'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};
