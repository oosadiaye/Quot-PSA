import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const DIMENSIONS_STALE_TIME = 10 * 60 * 1000; // 10 minutes

export const useJournals = (filters: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['journals', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/journals/', { params: filters });
            return { results: data.results, count: data.count };
        },
        staleTime: 2 * 60 * 1000, // 2 minutes
    });
};

/**
 * Single journal header + line detail. Used by the AP Invoice View
 * modal to show the DR/CR breakdown linked to a posted invoice.
 */
export const useJournal = (id: number | null | undefined) => {
    return useQuery({
        queryKey: ['journal', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/journals/${id}/`);
            return data;
        },
        enabled: !!id,
        staleTime: 2 * 60 * 1000,
    });
};

/**
 * Fetch the PROPOSED GL journal for an unposted invoice.
 *
 * Hits ``/accounting/vendor-invoices/{id}/simulate_posting/`` which
 * computes the DR/CR lines *without writing anything* — useful for the
 * AP View modal so the accounting entries are visible the moment the
 * invoice is drafted, not only after posting. The response shape is a
 * superset of ``JournalDetailSerializer`` (adds ``simulated: true``
 * and a ``warnings[]`` array), so the same render component can handle
 * both proposed and actual journals.
 */
export const useSimulatedInvoiceJournal = (
    invoiceId: number | null | undefined,
    enabled: boolean = true,
) => {
    return useQuery({
        queryKey: ['vendor-invoice-simulated-journal', invoiceId],
        queryFn: async () => {
            const { data } = await apiClient.get(
                `/accounting/vendor-invoices/${invoiceId}/simulate_posting/`,
            );
            return data;
        },
        enabled: !!invoiceId && enabled,
        // Simulated journals are deterministic from invoice data, but the
        // invoice fields can change before Post — keep the cache short so
        // edits to amounts are reflected quickly in the modal.
        staleTime: 30 * 1000,
    });
};

export const useCreateJournal = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (journalData: any) => {
            const { data } = await apiClient.post('/accounting/journals/', journalData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const usePostJournal = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/accounting/journals/${id}/post_journal/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const useUnpostJournal = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, reason }: { id: number; reason: string }) => {
            const { data } = await apiClient.post(`/accounting/journals/${id}/unpost_journal/`, {
                reason,
                reversal_type: 'Reverse'
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const useUpdateJournalDescription = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, description }: { id: number; description: string }) => {
            const { data } = await apiClient.patch(`/accounting/journals/${id}/update_description/`, {
                description,
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['journals'] });
        },
    });
};

export const useDeleteJournal = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/journals/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['journals'] });
        },
    });
};

export const useBulkDeleteJournals = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (ids: number[]) => {
            const { data } = await apiClient.post('/accounting/journals/bulk-delete/', { ids });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const useJournalDetail = (id: number | null) => {
    return useQuery({
        queryKey: ['journal-detail', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/journals/${id}/`);
            return data;
        },
        enabled: !!id,
    });
};

export const useDownloadJournalTemplate = () => {
    return useMutation({
        mutationFn: async () => {
            const response = await apiClient.get('/accounting/journals/import-template/', {
                responseType: 'blob',
            });
            const url = window.URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = 'journal_import_template.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        },
    });
};

export const useBulkImportJournals = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (file: File) => {
            const formData = new FormData();
            formData.append('file', file);
            const { data } = await apiClient.post('/accounting/journals/bulk-import/', formData);
            return data as { created: number; skipped: number; errors: string[] };
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const useDimensions = () => {
    return useQuery({
        queryKey: ['dimensions'],
        queryFn: async () => {
            const [funds, functions, programs, geos, accounts] = await Promise.all([
                apiClient.get('/accounting/funds/', { params: { page_size: 9999 } }),
                apiClient.get('/accounting/functions/', { params: { page_size: 9999 } }),
                apiClient.get('/accounting/programs/', { params: { page_size: 9999 } }),
                apiClient.get('/accounting/geos/', { params: { page_size: 9999 } }),
                apiClient.get('/accounting/accounts/', { params: { page_size: 9999 } }),
            ]);
            return {
                funds: funds.data.results,
                functions: functions.data.results,
                programs: programs.data.results,
                geos: geos.data.results,
                accounts: accounts.data.results,
            };
        },
        staleTime: DIMENSIONS_STALE_TIME,
        gcTime: 30 * 60 * 1000, // 30 minutes
    });
};
