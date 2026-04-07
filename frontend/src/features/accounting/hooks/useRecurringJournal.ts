import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

export const useRecurringJournals = (filters = {}) => {
    return useQuery({
        queryKey: ['recurring-journals', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/recurring-journals/', { params: filters });
            return data.results || data;
        },
        staleTime: 2 * 60 * 1000,
    });
};

export const useRecurringJournal = (id: number) => {
    return useQuery({
        queryKey: ['recurring-journal', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/recurring-journals/${id}/`);
            return data;
        },
        enabled: !!id,
    });
};

export const useCreateRecurringJournal = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: response } = await apiClient.post('/accounting/recurring-journals/', data);
            return response;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['recurring-journals'] });
        },
    });
};

export const useUpdateRecurringJournal = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: response } = await apiClient.patch(`/accounting/recurring-journals/${id}/`, data);
            return response;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['recurring-journals'] });
        },
    });
};

export const useDeleteRecurringJournal = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/recurring-journals/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['recurring-journals'] });
        },
    });
};

export const useGenerateRecurringJournalNow = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/accounting/recurring-journals/${id}/generate_now/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['recurring-journals'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
        },
    });
};

export const useGenerateRecurringJournals = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            const { data } = await apiClient.post('/accounting/recurring-journals/generate/');
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['recurring-journals'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
        },
    });
};

export const useDefaultDates = () => {
    return useQuery({
        queryKey: ['default-dates'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/recurring-journals/default_dates/');
            return data;
        },
    });
};

export const useRecurringJournalRuns = (recurringId?: number) => {
    return useQuery({
        queryKey: ['recurring-journal-runs', recurringId],
        queryFn: async () => {
            const params = recurringId ? { recurring_journal: recurringId } : {};
            const { data } = await apiClient.get('/accounting/recurring-journal-runs/', { params });
            return data.results || data;
        },
        enabled: !!recurringId,
        staleTime: 2 * 60 * 1000,
    });
};

// Fetches ALL runs across all templates — used for the report/analytics view
export const useAllRecurringJournalRuns = () => {
    return useQuery({
        queryKey: ['recurring-journal-runs-all'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/recurring-journal-runs/', {
                params: { page_size: 5000 },
            });
            return (data.results || data) as any[];
        },
        staleTime: 2 * 60 * 1000,
        retry: false,
    });
};
