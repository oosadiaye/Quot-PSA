import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

export interface PayrollRunRow {
  id: number;
  run_number: string;
  period_name: string;
  status: string;
  total_gross: string;
}

export interface FundingCandidate {
  id: number;
  mda: string;
  economic_code: string;
  economic_name: string;
  approved: string;
  available: string;
  covers: boolean;
}

export interface FundingSuggestions {
  payroll_run: number;
  run_number: string;
  gross: string;
  candidates: FundingCandidate[];
}

export interface BindingRow {
  id: number;
  payroll_run: number;
  appropriation_line: number;
  bound_amount: string;
  remaining_at_binding: string;
  check_level: string;
}

const list = <T,>(data: any): T[] => (Array.isArray(data) ? data : data?.results ?? []);
const KEY = ['payroll-funding'];
/** Runs whose funding line can still change. */
const OPEN_STATUSES = ['Draft', 'In Progress', 'Approved'];

/** The server's own reason for a refusal, else a plain fallback. */
export function fundingError(err: unknown, fallback = 'That did not work. Please try again.'): string {
  const data = (err as { response?: { data?: any; status?: number } })?.response?.data;
  if (data?.error) return String(data.error);
  if (data?.detail) return String(data.detail);
  return fallback;
}

/** True when the HR module (which owns payroll runs) is switched off or the user may not see payroll. */
export function isModuleOffError(err: unknown): boolean {
  const r = (err as { response?: { status?: number; data?: any } })?.response;
  return r?.status === 403;
}

export const usePayrollRuns = () =>
  useQuery<PayrollRunRow[]>({
    queryKey: [...KEY, 'runs'],
    queryFn: async () => {
      const rows = list<PayrollRunRow>((await apiClient.get('/hrm/payroll-runs/', { params: { page_size: 100 } })).data);
      return rows.filter((r) => OPEN_STATUSES.includes(r.status));
    },
    retry: false,
  });

export const useFundingSuggestions = (runId: number | null) =>
  useQuery<FundingSuggestions>({
    queryKey: [...KEY, 'suggest', runId],
    queryFn: async () => (await apiClient.get('/personnel-budget/payroll-bindings/suggest/', { params: { payroll_run: runId } })).data,
    enabled: !!runId,
  });

export const useRunBinding = (runId: number | null) =>
  useQuery<BindingRow | null>({
    queryKey: [...KEY, 'binding', runId],
    queryFn: async () =>
      list<BindingRow>((await apiClient.get('/personnel-budget/payroll-bindings/', { params: { payroll_run: runId } })).data)[0] ?? null,
    enabled: !!runId,
  });

export function useFundRun() {
  const qc = useQueryClient();
  return useMutation<BindingRow, unknown, { runId: number; appropriationId: number; existingBindingId?: number }>({
    mutationFn: async ({ runId, appropriationId, existingBindingId }) =>
      existingBindingId
        ? (await apiClient.patch(`/personnel-budget/payroll-bindings/${existingBindingId}/`, { appropriation_line: appropriationId })).data
        : (await apiClient.post('/personnel-budget/payroll-bindings/', { payroll_run: runId, appropriation_line: appropriationId })).data,
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: KEY }),
      qc.invalidateQueries({ queryKey: ['personnel_budget'] }),
    ]),
  });
}
