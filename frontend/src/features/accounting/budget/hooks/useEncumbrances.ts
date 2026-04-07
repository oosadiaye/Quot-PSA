import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../../api/client';
import type { BudgetEncumbrance } from '../types/budget.types';

const API_BASE = '/accounting/budget-encumbrances';

// Fetch encumbrances
const fetchEncumbrances = async (budgetId?: number): Promise<BudgetEncumbrance[]> => {
    const params = budgetId ? { budget: budgetId } : {};
    const { data } = await apiClient.get(`${API_BASE}/`, { params });
    return data.results;
};

// Fetch single encumbrance
const fetchEncumbrance = async (id: number): Promise<BudgetEncumbrance> => {
    const { data } = await apiClient.get(`${API_BASE}/${id}/`);
    return data;
};

/**
 * Custom hook for budget encumbrances
 */
export const useEncumbrances = (budgetId?: number) => {
    const encumbrancesQuery = useQuery({
        queryKey: ['budget-encumbrances', budgetId],
        queryFn: () => fetchEncumbrances(budgetId),
        staleTime: 30000, // 30 seconds
    });

    return {
        encumbrances: encumbrancesQuery.data,
        isLoading: encumbrancesQuery.isLoading,
        isError: encumbrancesQuery.isError,
        error: encumbrancesQuery.error,
        refetch: encumbrancesQuery.refetch,
    };
};

/**
 * Custom hook for single encumbrance
 */
export const useEncumbrance = (id: number | null) => {
    return useQuery({
        queryKey: ['budget-encumbrance', id],
        queryFn: () => fetchEncumbrance(id!),
        enabled: !!id,
    });
};

/**
 * Custom hook for active encumbrances (not fully liquidated)
 */
export const useActiveEncumbrances = (budgetId?: number) => {
    const { encumbrances, isLoading, isError, error, refetch } = useEncumbrances(budgetId);

    const activeEncumbrances = encumbrances?.filter(
        enc => enc.status === 'ACTIVE' || enc.status === 'PARTIALLY_LIQUIDATED'
    );

    return {
        encumbrances: activeEncumbrances,
        isLoading,
        isError,
        error,
        refetch,
    };
};
