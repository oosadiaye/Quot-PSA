import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const DEFAULT_STALE_TIME = 5 * 60 * 1000;

export const useFiscalYears = (filters: any = {}) => {
    return useQuery({
        queryKey: ['fiscal-years', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/fiscal-years/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useFiscalYear = (id: number) => {
    return useQuery({
        queryKey: ['fiscal-year', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/fiscal-years/${id}/`);
            return data;
        },
        enabled: !!id,
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateFiscalYear = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (yearData: any) => {
            const { data } = await apiClient.post('/accounting/fiscal-years/create_year/', yearData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fiscal-years'] });
        },
    });
};

export const useSetActiveFiscalYear = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/accounting/fiscal-years/${id}/set_active/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fiscal-years'] });
        },
    });
};

export const useCloseFiscalYear = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, reason }: { id: number; reason: string }) => {
            const { data } = await apiClient.post(`/accounting/fiscal-years/${id}/close_year/`, { reason });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fiscal-years'] });
            queryClient.invalidateQueries({ queryKey: ['fiscal-periods'] });
        },
    });
};

export const useFiscalPeriods = (filters: any = {}) => {
    return useQuery({
        queryKey: ['fiscal-periods', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/fiscal-periods/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useClosePeriods = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (closeData: any) => {
            const { data } = await apiClient.post('/accounting/fiscal-periods/close_periods/', closeData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fiscal-periods'] });
            queryClient.invalidateQueries({ queryKey: ['fiscal-years'] });
        },
    });
};

export const useReopenPeriod = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, reason }: { id: number; reason: string }) => {
            const { data } = await apiClient.post(`/accounting/fiscal-periods/${id}/reopen/`, { reason });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fiscal-periods'] });
            queryClient.invalidateQueries({ queryKey: ['fiscal-years'] });
        },
    });
};

export const useGrantPeriodAccess = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ periodId, accessData }: { periodId: number; accessData: any }) => {
            const { data } = await apiClient.post(`/accounting/fiscal-periods/${periodId}/grant_access/`, accessData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['period-access'] });
        },
    });
};

export const usePeriodAccessList = (periodId: number) => {
    return useQuery({
        queryKey: ['period-access-list', periodId],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/fiscal-periods/${periodId}/access_list/`);
            return data;
        },
        enabled: !!periodId,
        staleTime: DEFAULT_STALE_TIME,
    });
};
