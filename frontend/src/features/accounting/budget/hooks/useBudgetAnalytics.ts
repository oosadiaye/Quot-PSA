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
const fetchVarianceAnalysis = async (
    periodId: number,
    compareToPeriodId?: number,
    mdaId?: number,
    fundId?: number,
): Promise<VarianceAnalysisResult[]> => {
    const params: Record<string, string | number> = { period: periodId };
    if (compareToPeriodId) params.compare_to = compareToPeriodId;
    if (mdaId) params.mda = mdaId;
    if (fundId) params.fund = fundId;

    const { data } = await apiClient.get(`${API_BASE}/variance_analysis/`, { params });
    return data;
};

export interface VarianceSummary {
    fiscal_year: number;
    period_id: number;
    appropriation_count: number;
    total_allocated: string;
    total_committed: string;
    total_expended: string;
    total_used: string;
    total_available: string;
    overall_utilization_pct: string;
    status_counts: { UNDER: number; ON_TRACK: number; OVER: number };
}

const fetchVarianceSummary = async (
    periodId: number,
    mdaId?: number,
    fundId?: number,
): Promise<VarianceSummary> => {
    const params: Record<string, string | number> = { period: periodId };
    if (mdaId) params.mda = mdaId;
    if (fundId) params.fund = fundId;
    const { data } = await apiClient.get(`${API_BASE}/variance_summary/`, { params });
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
export const useVarianceAnalysis = (
    periodId: number | null,
    compareToPeriodId?: number,
    mdaId?: number,
    fundId?: number,
) => {
    return useQuery({
        queryKey: ['budget-variance', periodId, compareToPeriodId, mdaId, fundId],
        queryFn: () => fetchVarianceAnalysis(periodId!, compareToPeriodId, mdaId, fundId),
        enabled: !!periodId,
        staleTime: 30000,
    });
};

export const useVarianceSummary = (
    periodId: number | null,
    mdaId?: number,
    fundId?: number,
) => {
    return useQuery({
        queryKey: ['budget-variance-summary', periodId, mdaId, fundId],
        queryFn: () => fetchVarianceSummary(periodId!, mdaId, fundId),
        enabled: !!periodId,
        staleTime: 30000,
    });
};
