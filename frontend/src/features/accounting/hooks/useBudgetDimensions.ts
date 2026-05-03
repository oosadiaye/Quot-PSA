import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';

// ============================================================================
// MDA TYPES & HOOKS
// ============================================================================

export interface MDA {
    id: number;
    code: string;
    name: string;
    short_name: string;
    mda_type: string;
    parent_mda: number | null;
    is_active: boolean;
}

export const useMDAs = (params?: { mda_type?: string; is_active?: boolean }) => {
    return useQuery<MDA[]>({
        queryKey: ['mdas', params],
        queryFn: async () => {
            const response = await apiClient.get('/accounting/mdas/', { params });
            return response.data.results;
        },
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
    });
};

// ============================================================================
// ACCOUNT TYPES & HOOKS
// ============================================================================

export interface AccountOption {
    id: number;
    code: string;
    name: string;
    account_type: string;
    is_active: boolean;
}

export const useAccounts = (params?: { account_type?: string; is_active?: boolean }) => {
    return useQuery<AccountOption[]>({
        queryKey: ['accounts', params],
        queryFn: async () => {
            // Every caller of this hook is a dropdown that expects the
            // full account list (Expense picker on PR/PO/AP/JV forms,
            // Asset picker on Fixed Assets, etc.). DRF paginates by
            // default — without page_size we'd silently truncate at
            // ~20 rows. 9999 covers any realistic Chart of Accounts,
            // and the response.data.results slice still works whether
            // the API returns paginated or a plain list.
            const response = await apiClient.get('/accounting/accounts/', {
                params: { ...(params || {}), page_size: 9999 },
            });
            return Array.isArray(response.data)
                ? response.data
                : (response.data.results || []);
        },
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
    });
};
