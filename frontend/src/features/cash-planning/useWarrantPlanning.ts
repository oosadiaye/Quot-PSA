import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

export interface RecommendationRow {
  id: number;
  mda_name: string;
  fiscal_year: number | null;
  quarter: number | null;
  effective_from: string | null;
  effective_to: string | null;
  proposed_amount: string;
  status: 'proposed' | 'accepted' | 'converted' | 'rejected';
  rationale: string;
  warrant: number | null;
}

export interface GenerationSummary {
  created: number;
  replaced: number;
  total: string;
  scaled_to: string | null;
  skipped: { appropriation: number; reason: string }[];
}

const list = <T,>(data: any): T[] => (Array.isArray(data) ? data : data?.results ?? []);
const KEY = ['warrant-planning'];

/** The server's own reason for a refusal, else a plain fallback. */
export function planningError(err: unknown, fallback = 'That did not work. Please try again.'): string {
  const data = (err as { response?: { data?: any } })?.response?.data;
  if (data?.error) return String(data.error);
  if (data?.detail) return String(data.detail);
  return fallback;
}

export const PAGE_SIZE = 20;

export interface RecommendationPage {
  rows: RecommendationRow[];
  count: number;
}

export const useRecommendations = (fiscalYear: number, quarter: number, page: number) =>
  useQuery<RecommendationPage>({
    queryKey: [...KEY, 'rows', fiscalYear, quarter, page],
    queryFn: async () => {
      const data = (await apiClient.get('/cash-planning/recommendations/', {
        params: { fiscal_year: fiscalYear, quarter, page },
      })).data;
      const rows = list<RecommendationRow>(data);
      return { rows, count: typeof data?.count === 'number' ? data.count : rows.length };
    },
    placeholderData: (previous) => previous,
  });

function useRefresh() {
  const qc = useQueryClient();
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: KEY }),
    qc.invalidateQueries({ queryKey: ['cash_planning'] }),
  ]);
}

export function useGenerate() {
  const refresh = useRefresh();
  return useMutation<GenerationSummary, unknown, { fiscal_year: number; quarter: number; available_cash?: string }>({
    mutationFn: async (body) => (await apiClient.post('/cash-planning/recommendations/generate/', body)).data,
    onSuccess: refresh,
  });
}

export function useRecommendationAction() {
  const refresh = useRefresh();
  return useMutation<unknown, unknown, { id: number; action: 'accept' | 'reject' | 'convert'; body?: Record<string, string> }>({
    mutationFn: async ({ id, action, body }) => (await apiClient.post(`/cash-planning/recommendations/${id}/${action}/`, body ?? {})).data,
    onSuccess: refresh,
  });
}
