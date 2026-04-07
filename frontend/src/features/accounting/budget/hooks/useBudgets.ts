import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../../api/client';
import type { Budget, BudgetFilters, BudgetFormData } from '../types/budget.types';

const API_BASE = '/accounting/budgets';

// Fetch budgets with filters
const fetchBudgets = async (filters: BudgetFilters = {}): Promise<Budget[]> => {
    const params = new URLSearchParams();

    Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            params.append(key, String(value));
        }
    });

    const { data } = await apiClient.get(`${API_BASE}/?${params.toString()}`);
    return data.results;
};

// Fetch single budget
const fetchBudget = async (id: number): Promise<Budget> => {
    const { data } = await apiClient.get(`${API_BASE}/${id}/`);
    return data;
};

// Create budget
const createBudget = async (budgetData: BudgetFormData): Promise<Budget> => {
    const { data } = await apiClient.post(`${API_BASE}/`, budgetData);
    return data;
};

// Update budget
const updateBudget = async ({ id, ...budgetData }: Partial<Budget> & { id: number }): Promise<Budget> => {
    const { data } = await apiClient.put(`${API_BASE}/${id}/`, budgetData);
    return data;
};

// Delete budget
const deleteBudget = async (id: number): Promise<void> => {
    await apiClient.delete(`${API_BASE}/${id}/`);
};

// Bulk import budgets
const bulkImportBudgets = async (file: File, periodId: number): Promise<any> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('period_id', String(periodId));

    const { data } = await apiClient.post(`${API_BASE}/bulk_import/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
};

// Bulk export budgets
const bulkExportBudgets = async (filters: BudgetFilters = {}): Promise<Blob> => {
    const params = new URLSearchParams();

    Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            params.append(key, String(value));
        }
    });

    const { data } = await apiClient.get(`${API_BASE}/bulk_export/?${params.toString()}`, {
        responseType: 'blob',
    });
    return data;
};

// Check budget availability
const checkBudgetAvailability = async (budgetId: number, amount: string): Promise<any> => {
    const { data } = await apiClient.post(`${API_BASE}/${budgetId}/check_availability/`, { amount });
    return data;
};

/**
 * Custom hook for budget management
 */
export const useBudgets = (filters: BudgetFilters = {}) => {
    const queryClient = useQueryClient();

    // Fetch budgets query
    const budgetsQuery = useQuery({
        queryKey: ['budgets', filters],
        queryFn: () => fetchBudgets(filters),
        staleTime: 30000, // 30 seconds
    });

    // Create budget mutation
    const createMutation = useMutation({
        mutationFn: createBudget,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['budgets'] });
            queryClient.invalidateQueries({ queryKey: ['budget-summary'] });
        },
    });

    // Update budget mutation
    const updateMutation = useMutation({
        mutationFn: updateBudget,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['budgets'] });
            queryClient.invalidateQueries({ queryKey: ['budget-summary'] });
        },
    });

    // Delete budget mutation
    const deleteMutation = useMutation({
        mutationFn: deleteBudget,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['budgets'] });
            queryClient.invalidateQueries({ queryKey: ['budget-summary'] });
        },
    });

    // Bulk import mutation
    const importMutation = useMutation({
        mutationFn: ({ file, periodId }: { file: File; periodId: number }) =>
            bulkImportBudgets(file, periodId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['budgets'] });
            queryClient.invalidateQueries({ queryKey: ['budget-summary'] });
        },
    });

    return {
        budgets: budgetsQuery.data,
        isLoading: budgetsQuery.isLoading,
        isError: budgetsQuery.isError,
        error: budgetsQuery.error,
        refetch: budgetsQuery.refetch,

        createBudget: createMutation.mutate,
        createBudgetAsync: createMutation.mutateAsync,
        isCreating: createMutation.isPending,

        updateBudget: updateMutation.mutate,
        updateBudgetAsync: updateMutation.mutateAsync,
        isUpdating: updateMutation.isPending,

        deleteBudget: deleteMutation.mutate,
        deleteBudgetAsync: deleteMutation.mutateAsync,
        isDeleting: deleteMutation.isPending,

        importBudgets: importMutation.mutate,
        importBudgetsAsync: importMutation.mutateAsync,
        isImporting: importMutation.isPending,
    };
};

/**
 * Custom hook for single budget
 */
export const useBudget = (id: number | null) => {
    return useQuery({
        queryKey: ['budget', id],
        queryFn: () => fetchBudget(id!),
        enabled: !!id,
    });
};

/**
 * Custom hook for budget export
 */
export const useBudgetExport = () => {
    const exportMutation = useMutation({
        mutationFn: bulkExportBudgets,
    });

    const exportBudgets = async (filters: BudgetFilters = {}) => {
        const blob = await exportMutation.mutateAsync(filters);
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `budgets_${new Date().toISOString().split('T')[0]}.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    };

    return {
        exportBudgets,
        isExporting: exportMutation.isPending,
    };
};
