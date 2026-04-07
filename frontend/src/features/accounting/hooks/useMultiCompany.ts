import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const DEFAULT_STALE_TIME = 5 * 60 * 1000;

export const useCompanies = (filters: any = {}) => {
    return useQuery({
        queryKey: ['companies', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/companies/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCompany = (id: number) => {
    return useQuery({
        queryKey: ['company', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/companies/${id}/`);
            return data;
        },
        enabled: !!id,
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateCompany = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (companyData: any) => {
            const { data } = await apiClient.post('/accounting/companies/', companyData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['companies'] });
        },
    });
};

export const useUpdateCompany = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...data }: any) => {
            const { data: result } = await apiClient.patch(`/accounting/companies/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['companies'] });
        },
    });
};

export const useDeleteCompany = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/companies/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['companies'] });
        },
    });
};

export const useInterCompanyConfigs = (filters: any = {}) => {
    return useQuery({
        queryKey: ['ic-configs', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/ic-configs/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateInterCompanyConfig = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (configData: any) => {
            const { data } = await apiClient.post('/accounting/ic-configs/', configData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['ic-configs'] });
        },
    });
};

export const useICInvoices = (filters: any = {}) => {
    return useQuery({
        queryKey: ['ic-invoices', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/ic-invoices/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateICInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (invoiceData: any) => {
            const { data } = await apiClient.post('/accounting/ic-invoices/', invoiceData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['ic-invoices'] });
        },
    });
};

export const usePostICInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/accounting/ic-invoices/${id}/post_invoice/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['ic-invoices'] });
        },
    });
};

export const useConsolidationGroups = (filters: any = {}) => {
    return useQuery({
        queryKey: ['consolidation-groups', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/consolidation-groups/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateConsolidationGroup = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (groupData: any) => {
            const { data } = await apiClient.post('/accounting/consolidation-groups/', groupData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['consolidation-groups'] });
        },
    });
};

export const useConsolidationRuns = (filters: any = {}) => {
    return useQuery({
        queryKey: ['consolidation-runs', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/consolidation-runs/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useRunConsolidation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: { group_id: number; period_id: number }) => {
            const { data: result } = await apiClient.post('/accounting/consolidation-runs/run_consolidation/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['consolidation-runs'] });
        },
    });
};

export const useDeleteConsolidationGroup = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => { await apiClient.delete(`/accounting/consolidation-groups/${id}/`); },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['consolidation-groups'] }); },
    });
};

export const useConsolidations = (filters: any = {}) => {
    return useQuery({
        queryKey: ['consolidations', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/consolidations/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useICTransfers = (filters: any = {}) => {
    return useQuery({
        queryKey: ['ic-transfers', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/ic-transfers/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateICTransfer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/ic-transfers/', payload);
            return data;
        },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ic-transfers'] }); },
    });
};

export const useDeleteICTransfer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => { await apiClient.delete(`/accounting/ic-transfers/${id}/`); },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ic-transfers'] }); },
    });
};

export const useICCashTransfers = (filters: any = {}) => {
    return useQuery({
        queryKey: ['ic-cash-transfers', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/ic-cash-transfers/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateICCashTransfer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/ic-cash-transfers/', payload);
            return data;
        },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ic-cash-transfers'] }); },
    });
};

export const useDeleteICCashTransfer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => { await apiClient.delete(`/accounting/ic-cash-transfers/${id}/`); },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ic-cash-transfers'] }); },
    });
};

export const useICAllocations = (filters: any = {}) => {
    return useQuery({
        queryKey: ['ic-allocations', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/ic-allocations/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useCreateICAllocation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/ic-allocations/', payload);
            return data;
        },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ic-allocations'] }); },
    });
};

export const useDeleteICInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => { await apiClient.delete(`/accounting/ic-invoices/${id}/`); },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ic-invoices'] }); },
    });
};

export const useUpdateCompanyConfig = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...data }: any) => {
            const { data: result } = await apiClient.patch(`/accounting/ic-configs/${id}/`, data);
            return result;
        },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ic-configs'] }); },
    });
};

export const useDeleteICConfig = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => { await apiClient.delete(`/accounting/ic-configs/${id}/`); },
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ic-configs'] }); },
    });
};
