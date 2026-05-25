/**
 * TanStack Query hooks for ContractYearPlan — multi-year contract
 * payment-plan slices.
 *
 * Each ContractYearPlan row is one fiscal year of spend on a contract:
 *   - sum(year_plans.planned_amount) === contract.original_sum (enforced
 *     server-side at activation)
 *   - the row's fiscal_year gates IPC posting in that year
 *   - the row's appropriation hosts the year's budget commitment
 *
 * Single-year contracts have exactly one year plan row, auto-created
 * by the activation flow (or backfilled by migration for legacy rows),
 * so this hook is safe to call on any contract regardless of duration.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

export const YEAR_PLANS_BASE = '/contracts/year-plans/';

export interface ContractYearPlan {
  id: number;
  contract: number;
  fiscal_year: number;
  fiscal_year_label: string;
  appropriation: number | null;
  appropriation_label: string;
  planned_amount: string;
  carried_forward_from_prior_year: string;
  total_authorised_for_year: string;
  sequence: number;
  created_at: string;
  updated_at: string;
}

export interface YearPlanCreatePayload {
  contract: number;
  fiscal_year: number;
  appropriation?: number | null;
  planned_amount: string | number;
  carried_forward_from_prior_year?: string | number;
  sequence: number;
}

export interface YearPlanUpdatePayload {
  appropriation?: number | null;
  planned_amount?: string | number;
  carried_forward_from_prior_year?: string | number;
  sequence?: number;
}

/**
 * List year plans, typically filtered by ``contract`` so the
 * Year-Plan tab on a contract page sees only its own rows.
 */
export const useYearPlans = (
  filters: Record<string, unknown> = {},
): ReturnType<typeof useQuery<{ results: ContractYearPlan[]; count: number }>> => {
  return useQuery({
    queryKey: ['contract-year-plans', filters],
    queryFn: async () => {
      const { data } = await apiClient.get(YEAR_PLANS_BASE, { params: filters });
      return {
        results: (data.results ?? data) as ContractYearPlan[],
        count: data.count ?? (Array.isArray(data) ? data.length : 0),
      };
    },
    staleTime: 60 * 1000,
  });
};

export const useCreateYearPlan = (): ReturnType<typeof useMutation<ContractYearPlan, unknown, YearPlanCreatePayload>> => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: YearPlanCreatePayload) => {
      const { data } = await apiClient.post<ContractYearPlan>(YEAR_PLANS_BASE, payload);
      return data;
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['contract-year-plans'] });
      qc.invalidateQueries({ queryKey: ['contract', vars.contract] });
    },
  });
};

export const useUpdateYearPlan = (): ReturnType<
  typeof useMutation<ContractYearPlan, unknown, { id: number; payload: YearPlanUpdatePayload; contract: number }>
> => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }) => {
      const { data } = await apiClient.patch<ContractYearPlan>(`${YEAR_PLANS_BASE}${id}/`, payload);
      return data;
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['contract-year-plans'] });
      qc.invalidateQueries({ queryKey: ['contract', vars.contract] });
    },
  });
};

export const useDeleteYearPlan = (): ReturnType<
  typeof useMutation<void, unknown, { id: number; contract: number }>
> => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id }) => {
      await apiClient.delete(`${YEAR_PLANS_BASE}${id}/`);
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['contract-year-plans'] });
      qc.invalidateQueries({ queryKey: ['contract', vars.contract] });
    },
  });
};
