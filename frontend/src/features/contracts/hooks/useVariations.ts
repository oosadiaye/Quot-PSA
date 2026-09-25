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
    // Refresh the parent contract too — a write-up changes the contract amount,
    // so the detail page's Contract Sum / ceiling / Certified-Amount utilisation
    // (which read the ['contract'] and ['contract-balance'] queries) must update
    // in real time, not just the variations list.
    onSuccess: (data, payload) => {
      const contractId = data?.contract ?? payload?.contract;
      qc.invalidateQueries({ queryKey: ['variations'] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
      if (contractId != null) {
        qc.invalidateQueries({ queryKey: ['contract', contractId] });
        qc.invalidateQueries({ queryKey: ['contract-balance', contractId] });
        qc.invalidateQueries({ queryKey: ['contract-activity', contractId] });
      }
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
    // Approving a write-up applies the delta to the contract amount, so the
    // contract detail + balance must refresh live. The action response carries
    // the variation, whose ``contract`` is the parent id to invalidate.
    onSuccess: (data, vars) => {
      const contractId = (data as { contract?: number } | undefined)?.contract;
      qc.invalidateQueries({ queryKey: ['variations'] });
      qc.invalidateQueries({ queryKey: ['variation', vars.id] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
      if (contractId != null) {
        qc.invalidateQueries({ queryKey: ['contract', contractId] });
        qc.invalidateQueries({ queryKey: ['contract-balance', contractId] });
        qc.invalidateQueries({ queryKey: ['contract-activity', contractId] });
      }
    },
  });
};

export const useReviewVariation  = () => useVariationAction('review');
export const useApproveVariation = () => useVariationAction('approve');
export const useRejectVariation  = () => useVariationAction('reject');
