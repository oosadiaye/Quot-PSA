/**
 * useGovDashboard — data hooks for the Government IFMIS Dashboard.
 * Fetches from the Phase 4-7 API endpoints:
 *   /accounting/ipsas/tsa-cash-position/
 *   /accounting/ipsas/financial-performance/
 *   /accounting/ipsas/budget-vs-actual/
 *   /accounting/revenue-collections/summary/
 *   /accounting/tsa-accounts/cash_position/
 *   /budget/execution-report/
 */
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';

export interface TSACashPosition {
    total_balance: number;
    account_count: number;
    by_account_type: { account_type: string; balance: number; count: number }[];
    top_mda_balances: { mda__name: string; mda__code: string; balance: number }[];
}

export interface RevenueCollectionSummary {
    total_collected: number;
    by_revenue_head: {
        revenue_head__name: string;
        revenue_head__code: string;
        total: number;
        count: number;
    }[];
    by_status: { status: string; total: number; count: number }[];
}

export interface BudgetExecutionItem {
    id: number;
    mda: string;
    account: string;
    fund: string;
    approved: string;
    expended: string;
    available: string;
    execution_pct: number;
}

export interface FinancialPerformance {
    revenue: { total: number };
    expenditure: { total: number };
    surplus_deficit: number;
}

export function useTSACashPosition() {
    return useQuery<TSACashPosition>({
        queryKey: ['gov-tsa-cash-position'],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/tsa-cash-position/')).data,
        staleTime: 30_000,
    });
}

export function useRevenueCollectionSummary(dateFrom?: string, dateTo?: string) {
    return useQuery<RevenueCollectionSummary>({
        queryKey: ['gov-revenue-summary', dateFrom, dateTo],
        queryFn: async () => {
            const params: Record<string, string> = {};
            if (dateFrom) params.date_from = dateFrom;
            if (dateTo) params.date_to = dateTo;
            return (await apiClient.get('/accounting/revenue-collections/summary/', { params })).data;
        },
        staleTime: 60_000,
    });
}

export function useBudgetExecution(fiscalYear?: string) {
    return useQuery<BudgetExecutionItem[]>({
        queryKey: ['gov-budget-execution', fiscalYear],
        queryFn: async () => {
            const params: Record<string, string> = {};
            if (fiscalYear) params.fiscal_year = fiscalYear;
            return (await apiClient.get('/budget/execution-report/', { params })).data;
        },
        staleTime: 60_000,
    });
}

export function useFinancialPerformance(fiscalYear: number = new Date().getFullYear()) {
    return useQuery<FinancialPerformance>({
        queryKey: ['gov-financial-performance', fiscalYear],
        queryFn: async () => (
            await apiClient.get('/accounting/ipsas/financial-performance/', {
                params: { fiscal_year: fiscalYear },
            })
        ).data,
        staleTime: 60_000,
    });
}
