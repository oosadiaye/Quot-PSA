/**
 * Financial Report Hooks — Trial Balance, Balance Sheet, P&L, Cash Flow, Period-Close Checklist
 *
 * All reports are backed by the GLBalance aggregation table, so they are fast
 * even on large tenants. Queries are stale-time-gated at 5 minutes for reports
 * (user-driven refresh is preferred for financial data).
 *
 * Backend responses are wrapped in the standard api_response envelope:
 *   { data: <payload>, error: string|null, meta: {} }
 * Each queryFn unwraps the envelope so that components receive the inner
 * payload directly — the envelope is absorbed at the query layer.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const REPORT_STALE_TIME = 5 * 60 * 1000; // 5 minutes

// ---------------------------------------------------------------------------
// Shared envelope unwrapper
// ---------------------------------------------------------------------------

/** Extract inner payload from the api_response envelope. */
function unwrap<T>(envelope: { data: T; error: string | null; meta: Record<string, unknown> }): T {
    if (envelope.error) {
        throw new Error(envelope.error);
    }
    return envelope.data;
}

// ---------------------------------------------------------------------------
// Trial Balance
// ---------------------------------------------------------------------------

export interface TrialBalanceParams {
    fiscal_year?: number;
    period?: number;
    as_of_date?: string;  // YYYY-MM-DD
    fund?: number;
    function?: number;
    program?: number;
    geo?: number;
    mda?: number;
    // Trial balance endpoint also accepts POST with start_date/end_date
    start_date?: string;
    end_date?: string;
}

export const useTrialBalance = (params: TrialBalanceParams = {}) => {
    return useQuery({
        queryKey: ['trial-balance', params],
        queryFn: async () => {
            const { data: envelope } = await apiClient.post('/accounting/reports/trial-balance/', params);
            return unwrap(envelope);
        },
        staleTime: REPORT_STALE_TIME,
        enabled: Object.keys(params).length > 0,
    });
};

// ---------------------------------------------------------------------------
// Balance Sheet
// ---------------------------------------------------------------------------

export interface BalanceSheetParams {
    start_date: string;  // YYYY-MM-DD required
    end_date: string;    // YYYY-MM-DD required
    fund?: number;
    mda?: number;
}

export const useBalanceSheet = (params: BalanceSheetParams | null) => {
    return useQuery({
        queryKey: ['balance-sheet', params],
        queryFn: async () => {
            const { data: envelope } = await apiClient.post('/accounting/reports/balance-sheet/', params);
            return unwrap(envelope);
        },
        staleTime: REPORT_STALE_TIME,
        enabled: !!params?.start_date && !!params?.end_date,
    });
};

// ---------------------------------------------------------------------------
// Profit & Loss / Income Statement
// ---------------------------------------------------------------------------

export interface ProfitLossParams {
    start_date: string;
    end_date: string;
    fund?: number;
    mda?: number;
    compare_prior_period?: boolean;
}

export const useProfitLoss = (params: ProfitLossParams | null) => {
    return useQuery({
        queryKey: ['profit-loss', params],
        queryFn: async () => {
            const { data: envelope } = await apiClient.post('/accounting/reports/income-statement/', params);
            return unwrap(envelope);
        },
        staleTime: REPORT_STALE_TIME,
        enabled: !!params?.start_date && !!params?.end_date,
    });
};

// ---------------------------------------------------------------------------
// Cash Flow Statement
// ---------------------------------------------------------------------------

export type CashFlowMethod = 'direct' | 'indirect';

export interface CashFlowParams {
    start_date: string;
    end_date: string;
    method?: CashFlowMethod;
}

export const useCashFlow = (params: CashFlowParams | null) => {
    return useQuery({
        queryKey: ['cash-flow', params],
        queryFn: async () => {
            const { data: envelope } = await apiClient.post('/accounting/reports/cash-flow/', params);
            return unwrap(envelope);
        },
        staleTime: REPORT_STALE_TIME,
        enabled: !!params?.start_date && !!params?.end_date,
    });
};

// ---------------------------------------------------------------------------
// Period-Close Pre-Flight Checklist
// ---------------------------------------------------------------------------

export interface PeriodCloseChecklistItem {
    unposted_journals: number;
    open_grn_without_invoice: number;
    unreconciled_payments: number;
    unreconciled_receipts: number;
    pending_approvals: number;
}

export interface PeriodCloseChecklist {
    fiscal_period: string | number | null;
    period_name: string | null;
    is_clear_to_close: boolean;
    items: PeriodCloseChecklistItem;
}

export const usePeriodCloseChecklist = (fiscalPeriodId?: number | null) => {
    return useQuery({
        queryKey: ['period-close-checklist', fiscalPeriodId],
        queryFn: async () => {
            const params = fiscalPeriodId ? { fiscal_period_id: fiscalPeriodId } : {};
            const { data: envelope } = await apiClient.get('/accounting/period-close/checklist/', { params });
            return unwrap(envelope) as PeriodCloseChecklist;
        },
        staleTime: 60 * 1000, // 1 minute — checklist should stay fresh
        enabled: true,
    });
};
