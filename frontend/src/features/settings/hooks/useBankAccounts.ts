import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const DEFAULT_STALE_TIME = 5 * 60 * 1000;

export const useBankAccounts = (filters: any = {}) => {
    return useQuery({
        queryKey: ['bank-accounts', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/bank-accounts/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useBankAccount = (id: number) => {
    return useQuery({
        queryKey: ['bank-account', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/bank-accounts/${id}/`);
            return data;
        },
        enabled: !!id,
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateBankAccount = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (accountData: any) => {
            const { data } = await apiClient.post('/accounting/bank-accounts/', accountData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['bank-accounts'] });
        },
    });
};

export const useUpdateBankAccount = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...accountData }: any) => {
            const { data } = await apiClient.patch(`/accounting/bank-accounts/${id}/`, accountData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['bank-accounts'] });
        },
    });
};

export const useDeleteBankAccount = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/bank-accounts/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['bank-accounts'] });
        },
    });
};

export const useBankAccountSummary = () => {
    return useQuery({
        queryKey: ['bank-account-summary'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/bank-accounts/summary/');
            return data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useBankAccountTransactions = (id: number) => {
    return useQuery({
        queryKey: ['bank-account-transactions', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/bank-accounts/${id}/transactions/`);
            return data;
        },
        enabled: !!id,
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useBankReconciliations = (filters: any = {}) => {
    return useQuery({
        queryKey: ['bank-reconciliations', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/bank-reconciliations/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateBankReconciliation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/bank-reconciliations/', payload);
            return data;
        },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bank-reconciliations'] }); },
    });
};

export const useReconcileBank = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: { id: number; deposits_in_transit: number; outstanding_checks: number; bank_charges: number }) => {
            const { data } = await apiClient.post(`/accounting/bank-reconciliations/${id}/reconcile/`, payload);
            return data;
        },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bank-reconciliations'] }); },
    });
};
