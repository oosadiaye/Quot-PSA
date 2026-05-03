/**
 * TanStack Query hooks for ContractVariation CRUD + workflow.
 *
 * Tier mapping (computed server-side, surfaced via `approval_tier`):
 *   LOCAL        ≤ 15% cumulative variation
 *   BOARD        ≤ 25%
 *   BPP_REQUIRED > 25%      ← requires BPP No-Objection
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

export const VARIATIONS_BASE = '/contracts/variations/';

export interface VariationSummary {
  id: number;
  variation_number: string;
  contract: number;
  contract_reference?: string;
  delta_amount: string;
  cumulative_pct: number;
  approval_tier: 'LOCAL' | 'BOARD' | 'BPP_REQUIRED';
  status: string;
  submitted_at?: string;
}

export const useVariations = (filters: Record<string, any> = {}) => {
  return useQuery({
    queryKey: ['variations', filters],
    queryFn: async () => {
      const { data } = await apiClient.get(VARIATIONS_BASE, { params: filters });
      return {
        results: (data.results ?? data) as VariationSummary[],
        count: data.count ?? (Array.isArray(data) ? data.length : 0),
      };
    },
    staleTime: 60 * 1000,
  });
};

export const useVariation = (id: number | null | undefined) => {
  return useQuery({
    queryKey: ['variation', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`${VARIATIONS_BASE}${id}/`);
      return data;
    },
    enabled: !!id,
  });
};

export const useCreateVariation = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: any) => {
      const { data } = await apiClient.post(VARIATIONS_BASE, payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['variations'] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
};

const useVariationAction = (action: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload?: Record<string, unknown> }) => {
      const { data } = await apiClient.post(`${VARIATIONS_BASE}${id}/${action}/`, payload ?? {});
      return data;
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['variations'] });
      qc.invalidateQueries({ queryKey: ['variation', vars.id] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
};

export const useReviewVariation  = () => useVariationAction('review');
export const useApproveVariation = () => useVariationAction('approve');
export const useRejectVariation  = () => useVariationAction('reject');
