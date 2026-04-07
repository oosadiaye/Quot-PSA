import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../../api/client';
import type { BudgetSummary, BudgetUtilization, BudgetAlert, VarianceAnalysisResult } from '../types/budget.types';

const API_BASE = '/accounting/budgets';

// Fetch budget summary
const fetchBudgetSummary = async (periodId: number): Promise<BudgetSummary> => {
    const { data } = await apiClient.get(`${API_BASE}/summary/`, {
        params: { period: periodId },
    });
    return data;
};

// Fetch budget utilization
const fetchBudgetUtilization = async (periodId: number): Promise<BudgetUtilization[]> => {
    const { data } = await apiClient.get(`${API_BASE}/utilization/`, {
        params: { period: periodId },
    });
    return data;
};

// Fetch budget alerts
const fetchBudgetAlerts = async (periodId: number): Promise<BudgetAlert[]> => {
    const { data } = await apiClient.get(`${API_BASE}/alerts/`, {
        params: { period: periodId },
    });
    return data;
};

// Fetch variance analysis
const fetchVarianceAnalysis = async (periodId: number, compareToPeriodId?: number): Promise<VarianceAnalysisResult[]> => {
    const params: any = { period: periodId };
    if (compareToPeriodId) {
        params.compare_to = compareToPeriodId;
    }

    const { data } = await apiClient.get(`${API_BASE}/variance_analysis/`, { params });
    return data;
};

// Fetch top spending accounts
const fetchTopSpending = async (periodId: number, limit: number = 10): Promise<any[]> => {
    const { data } = await apiClient.get(`${API_BASE}/top_spending/`, {
        params: { period: periodId, limit },
    });
    return data;
};

/**
 * Custom hook for budget analytics
 */
export const useBudgetAnalytics = (periodId: number | null) => {
    const summaryQuery = useQuery({
        queryKey: ['budget-summary', periodId],
        queryFn: () => fetchBudgetSummary(periodId!),
        enabled: !!periodId,
        staleTime: 30000, // 30 seconds
    });

    const utilizationQuery = useQuery({
        queryKey: ['budget-utilization', periodId],
        queryFn: () => fetchBudgetUtilization(periodId!),
        enabled: !!periodId,
        staleTime: 30000,
    });

    const alertsQuery = useQuery({
        queryKey: ['budget-alerts', periodId],
        queryFn: () => fetchBudgetAlerts(periodId!),
        enabled: !!periodId,
        staleTime: 30000,
    });

    const topSpendingQuery = useQuery({
        queryKey: ['budget-top-spending', periodId],
        queryFn: () => fetchTopSpending(periodId!),
        enabled: !!periodId,
        staleTime: 30000,
    });

    return {
        summary: summaryQuery.data,
        isSummaryLoading: summaryQuery.isLoading,

        utilization: utilizationQuery.data,
        isUtilizationLoading: utilizationQuery.isLoading,

        alerts: alertsQuery.data,
        isAlertsLoading: alertsQuery.isLoading,

        topSpending: topSpendingQuery.data,
        isTopSpendingLoading: topSpendingQuery.isLoading,

        isLoading: summaryQuery.isLoading || utilizationQuery.isLoading || alertsQuery.isLoading,

        refetchAll: () => {
            summaryQuery.refetch();
            utilizationQuery.refetch();
            alertsQuery.refetch();
            topSpendingQuery.refetch();
        },
    };
};

/**
 * Custom hook for variance analysis
 */
export const useVarianceAnalysis = (periodId: number | null, compareToPeriodId?: number) => {
    return useQuery({
        queryKey: ['budget-variance', periodId, compareToPeriodId],
        queryFn: () => fetchVarianceAnalysis(periodId!, compareToPeriodId),
        enabled: !!periodId,
        staleTime: 30000,
    });
};
