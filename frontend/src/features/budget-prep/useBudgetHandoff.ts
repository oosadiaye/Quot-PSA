import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

export interface SubmissionRow {
  id: number;
  fiscal_year: number;
  mda_name: string;
  stage: string;
  total_personnel: string;
  total_overhead: string;
  total_capital: string;
}

export type AdoptionBasis = 'outturn' | 'appropriation' | 'run_rate';

export interface AdoptionPreview {
  basis: AdoptionBasis;
  source_year: number;
  total: string;
  rows: { economic_code: string; baseline: string }[];
}

export interface AdoptionResult {
  basis: AdoptionBasis;
  source_year: number;
  created: number;
  replaced: number;
  total_proposed: string;
  skipped: { economic: string; reason: string }[];
}

export interface HandoffResult {
  created: number;
  updated: number;
  removed: number;
  appropriation_ids: number[];
  fiscal_year: number;
}

export interface CeilingRow {
  line_type: 'personnel' | 'overhead' | 'capital';
  proposed: string;
  ceiling: string | null;
  over_by: string;
}

export interface CeilingCheck {
  has_ceiling: boolean;
  ok: boolean;
  rows: CeilingRow[];
}

export interface MilestoneRow {
  id: number;
  fiscal_year: number;
  name: string;
  due_date: string;
  completed_on: string | null;
  status: 'completed' | 'overdue' | 'due_soon' | 'upcoming';
  days_to_due: number | null;
}

export interface HandoffProblem {
  line: number;
  missing?: string[];
  conflict?: string;
}

const list = <T,>(data: any): T[] => (Array.isArray(data) ? data : data?.results ?? []);

/** The sentence to show for a refused action, with the offending lines spelled out when the server names them. */
export function handoffError(err: unknown, fallback = 'That did not work. Please try again.'): string {
  const data = (err as { response?: { data?: any } })?.response?.data;
  if (!data) return fallback;
  if (data.detail) return String(data.detail);
  const lines: HandoffProblem[] = Array.isArray(data.lines) ? data.lines : [];
  const detail = lines
    .map((l) => (l.missing ? `line ${l.line} has no ${l.missing.join(', ')}` : `line ${l.line}: ${l.conflict}`))
    .join('; ');
  if (data.error) return detail ? `${data.error} ${detail}.` : String(data.error);
  return fallback;
}

const KEY = ['budget-handoff'];

export const useSubmissions = () =>
  useQuery<SubmissionRow[]>({
    queryKey: [...KEY, 'submissions'],
    queryFn: async () => list((await apiClient.get('/budget-prep/submissions/', { params: { page_size: 200 } })).data),
  });

export const useAdoptionPreview = (id: number | null, basis: AdoptionBasis, enabled: boolean) =>
  useQuery<AdoptionPreview>({
    queryKey: [...KEY, 'preview', id, basis],
    queryFn: async () => (await apiClient.get(`/budget-prep/submissions/${id}/adoption-preview/`, { params: { basis } })).data,
    enabled: !!id && enabled,
    retry: false,
  });

/** Everything the actions can change on screen, including the generic register below the panel. */
function useRefresh() {
  const qc = useQueryClient();
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: KEY }),
    qc.invalidateQueries({ queryKey: ['budget_prep'] }),
  ]);
}

export const useCeilingCheck = (id: number | null) =>
  useQuery<CeilingCheck>({
    queryKey: [...KEY, 'ceiling', id],
    queryFn: async () => (await apiClient.get(`/budget-prep/submissions/${id}/ceiling-check/`)).data,
    enabled: !!id,
  });

export function useSubmitSubmission() {
  const refresh = useRefresh();
  return useMutation<{ stage: string; check: CeilingCheck }, unknown, { id: number; override_reason?: string }>({
    mutationFn: async ({ id, override_reason }) =>
      (await apiClient.post(`/budget-prep/submissions/${id}/submit/`, { override_reason: override_reason ?? '' })).data,
    onSuccess: refresh,
  });
}

export const useUpcomingMilestones = (days = 30) =>
  useQuery<MilestoneRow[]>({
    queryKey: [...KEY, 'milestones', days],
    queryFn: async () => (await apiClient.get('/budget-prep/milestones/upcoming/', { params: { days } })).data,
  });

export function useSeedCalendar() {
  const refresh = useRefresh();
  return useMutation<{ created: number; existing: number; anchor: string }, unknown, { fiscal_year: number; anchor_date?: string }>({
    mutationFn: async (body) => (await apiClient.post('/budget-prep/milestones/seed-standard/', body)).data,
    onSuccess: refresh,
  });
}

export function useAdoptActuals() {
  const refresh = useRefresh();
  return useMutation<AdoptionResult, unknown, { id: number; basis: AdoptionBasis; growth_pct: number }>({
    mutationFn: async ({ id, ...body }) => (await apiClient.post(`/budget-prep/submissions/${id}/adopt-actuals/`, body)).data,
    onSuccess: refresh,
  });
}

export function useIncorporate() {
  const refresh = useRefresh();
  return useMutation<HandoffResult, unknown, { id: number }>({
    mutationFn: async ({ id }) => (await apiClient.post(`/budget-prep/submissions/${id}/incorporate/`, {})).data,
    onSuccess: refresh,
  });
}
