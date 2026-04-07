import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../../api/client';
import type { BudgetPeriod } from '../types/budget.types';

const API_BASE = '/accounting/budget-periods';

// ─── Month name helper (shared) ───────────────────────────────────────────────
export const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * Returns a human-readable label for a BudgetPeriod, e.g.:
 *   MONTHLY period 3  →  "March"
 *   QUARTERLY period 2 →  "Q2"
 *   ANNUAL period 1   →  "Annual"
 */
export const periodLabel = (p: BudgetPeriod): string => {
    if (p.period_type === 'MONTHLY') {
        return MONTH_NAMES[p.period_number - 1] ?? `Month ${p.period_number}`;
    }
    if (p.period_type === 'QUARTERLY') return `Q${p.period_number}`;
    return 'Annual';
};

/** Full option label used in dropdowns: "FY2026 – March (Active)" */
export const periodOptionLabel = (p: BudgetPeriod): string => {
    const base = `FY${p.fiscal_year} – ${periodLabel(p)}`;
    const suffix = p.status === 'OPEN' ? ' (Open)' : p.status === 'ACTIVE' ? ' (Active)' : '';
    return base + suffix;
};

// ─── API functions ────────────────────────────────────────────────────────────

const fetchBudgetPeriods = async (filters: Record<string, any> = {}): Promise<BudgetPeriod[]> => {
    const { data } = await apiClient.get(`${API_BASE}/`, { params: { page_size: 500, ...filters } });
    return data.results ?? data;
};

const fetchBudgetPeriod = async (id: number): Promise<BudgetPeriod> => {
    const { data } = await apiClient.get(`${API_BASE}/${id}/`);
    return data;
};

const createBudgetPeriod = async (periodData: Partial<BudgetPeriod>): Promise<BudgetPeriod> => {
    const { data } = await apiClient.post(`${API_BASE}/`, periodData);
    return data;
};

const updateBudgetPeriod = async ({ id, ...periodData }: Partial<BudgetPeriod> & { id: number }): Promise<BudgetPeriod> => {
    const { data } = await apiClient.put(`${API_BASE}/${id}/`, periodData);
    return data;
};

const deleteBudgetPeriod = async (id: number): Promise<void> => {
    await apiClient.delete(`${API_BASE}/${id}/`);
};

// ─── Hooks ────────────────────────────────────────────────────────────────────

/**
 * Fetch budget periods with optional filters.
 * Pass `{ fiscal_year: 2026 }` to get only periods for a specific year.
 * Pass `{ period_type: 'MONTHLY' }` to limit to monthly periods only.
 */
export const useBudgetPeriods = (filters: Record<string, any> = {}) => {
    const queryClient = useQueryClient();

    const periodsQuery = useQuery({
        queryKey: ['budget-periods', filters],
        queryFn: () => fetchBudgetPeriods(filters),
        staleTime: 60_000,
    });

    const createMutation = useMutation({
        mutationFn: createBudgetPeriod,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['budget-periods'] }),
    });

    const updateMutation = useMutation({
        mutationFn: updateBudgetPeriod,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['budget-periods'] }),
    });

    const deleteMutation = useMutation({
        mutationFn: deleteBudgetPeriod,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['budget-periods'] }),
    });

    return {
        periods: periodsQuery.data,
        isLoading: periodsQuery.isLoading,
        isError: periodsQuery.isError,
        error: periodsQuery.error,
        refetch: periodsQuery.refetch,

        createPeriod: createMutation.mutate,
        createPeriodAsync: createMutation.mutateAsync,
        isCreating: createMutation.isPending,

        updatePeriod: updateMutation.mutate,
        updatePeriodAsync: updateMutation.mutateAsync,
        isUpdating: updateMutation.isPending,

        deletePeriod: deleteMutation.mutate,
        deletePeriodAsync: deleteMutation.mutateAsync,
        isDeleting: deleteMutation.isPending,
    };
};

/** Single budget period by ID */
export const useBudgetPeriod = (id: number | null) => {
    return useQuery({
        queryKey: ['budget-period', id],
        queryFn: () => fetchBudgetPeriod(id!),
        enabled: !!id,
    });
};

/** Convenience: get the currently active/open period */
export const useActiveBudgetPeriod = () => {
    const { periods, isLoading } = useBudgetPeriods();
    const activePeriod = periods?.find(p => p.status === 'ACTIVE' || p.status === 'OPEN');
    return { activePeriod, isLoading };
};

/**
 * Returns all available fiscal years that have budget periods,
 * sorted descending. Useful for year-filter dropdowns.
 */
export const useBudgetFiscalYears = () => {
    const { periods, isLoading } = useBudgetPeriods();
    const years = [...new Set((periods ?? []).map(p => p.fiscal_year))].sort((a, b) => b - a);
    return { years, isLoading };
};
