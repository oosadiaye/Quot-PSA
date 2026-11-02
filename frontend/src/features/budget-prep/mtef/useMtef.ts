import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

export type RuleStatus = 'pass' | 'warn' | 'fail';
export type MtefStatus = 'draft' | 'reviewed' | 'approved';

export interface Finding {
  rule: string;
  status: RuleStatus;
  message: string;
  value: string | null;
  limit: string | null;
}

export interface CeilingRow {
  type: 'personnel' | 'overhead' | 'capital';
  envelope: string;
  allocated: string;
  headroom: string;
  over: boolean;
}

export interface Outturn {
  year: number;
  personnel: string;
  overhead: string;
  capital: string;
  other: string;
  total: string;
}

export interface YearView {
  year: number;
  missing: boolean;
  id?: number;
  status?: MtefStatus;
  assumptions?: { inflation: string; exchange_rate: string; oil_price: string | null; oil_sensitivity: string; gdp: string; opening_debt_stock: string };
  revenue?: Record<string, string>;
  expenditure?: Record<string, string>;
  financing?: Record<string, string>;
  totals?: {
    revenue: string; recurrent_revenue: string; expenditure: string; recurrent_expenditure: string;
    balance: string; financing: string; unfinanced_gap: string;
  };
  ratios?: {
    debt_service_pct_revenue: string | null; personnel_pct_recurrent_revenue: string | null;
    capital_pct_expenditure: string | null; borrowing_pct_revenue: string | null;
    deficit_pct_gdp: string | null; debt_stock_pct_gdp: string | null;
  };
  findings?: Finding[];
  overall?: RuleStatus;
  prior_outturn?: Outturn | null;
  ceilings?: CeilingRow[];
  approved_by?: string;
  approved_at?: string | null;
  override_reason?: string;
}

export interface Framework {
  base_year: number;
  years: YearView[];
  overall: RuleStatus | 'empty';
  complete: boolean;
  policy: Record<string, string | boolean>;
}

export interface ScenarioYear {
  year: number;
  before: NonNullable<YearView['totals']>;
  after: NonNullable<YearView['totals']>;
  balance_change: string;
  findings: Finding[];
  newly_failing: Finding[];
  overall: RuleStatus;
}

export interface Scenario {
  base_year: number;
  shock: { oil_price_change_pct: string; igr_change_pct: string; cost_change_pct: string };
  years: ScenarioYear[];
}

export interface PolicyValues {
  max_debt_service_pct: string;
  max_personnel_pct: string;
  min_capital_pct: string;
  max_borrowing_pct: string;
  max_revenue_growth_pct: string;
  max_outturn_jump_pct: string;
  max_deficit_pct_gdp: string;
  max_debt_stock_pct_gdp: string;
  enforce_golden_rule: boolean;
}

/** The server's own reason for a refusal, else a plain fallback. */
export function mtefError(err: unknown, fallback = 'That did not work. Please try again.'): string {
  const data = (err as { response?: { data?: any } })?.response?.data;
  if (!data) return fallback;
  const pick = (v: unknown) => (Array.isArray(v) ? String(v[0]) : String(v));
  if (data.error) return pick(data.error);
  if (data.detail) return pick(data.detail);
  const first = Object.entries(data).find(([, v]) => v);
  return first ? `${first[0].replace(/_/g, ' ')}: ${pick(first[1])}` : fallback;
}

const BASE = '/budget-prep/mtef-projections';
// Under the register's own list key, so saving a year in the form refreshes this view too.
const FRAMEWORK_KEY = (year: number) => ['budget_prep', 'list', 'mtef-framework', year];

export const useFramework = (baseYear: number | null) =>
  useQuery<Framework>({
    queryKey: FRAMEWORK_KEY(baseYear ?? 0),
    queryFn: async () => (await apiClient.get(`${BASE}/framework/`, { params: { base_year: baseYear } })).data,
    enabled: !!baseYear,
  });

function useRefresh() {
  const qc = useQueryClient();
  return () => Promise.all([qc.invalidateQueries({ queryKey: ['budget_prep'] })]);
}

export const useRollForward = () => {
  const refresh = useRefresh();
  return useMutation<{ created: number[]; kept: number[] }, unknown, { base_year: number }>({
    mutationFn: async (body) => (await apiClient.post(`${BASE}/roll-forward/`, body)).data,
    onSuccess: refresh,
  });
};

export const useApprove = () => {
  const refresh = useRefresh();
  return useMutation<{ status: MtefStatus; findings: Finding[] }, unknown, { id: number; override_reason?: string }>({
    mutationFn: async ({ id, override_reason }) => (await apiClient.post(`${BASE}/${id}/approve/`, { override_reason: override_reason ?? '' })).data,
    onSuccess: refresh,
  });
};

export const useReopen = () => {
  const refresh = useRefresh();
  return useMutation<{ status: MtefStatus }, unknown, { id: number; reason: string }>({
    mutationFn: async ({ id, reason }) => (await apiClient.post(`${BASE}/${id}/reopen/`, { reason })).data,
    onSuccess: refresh,
  });
};

export const useScenario = () =>
  useMutation<Scenario, unknown, { base_year: number; oil_price_change_pct: number; igr_change_pct: number; cost_change_pct: number }>({
    mutationFn: async (body) => (await apiClient.post(`${BASE}/scenario/`, body)).data,
  });

export const usePolicy = () =>
  useQuery<PolicyValues>({
    queryKey: ['budget_prep', 'list', 'mtef-policy'],
    queryFn: async () => (await apiClient.get('/budget-prep/mtef-policy/current/')).data,
  });

export const useSavePolicy = () => {
  const refresh = useRefresh();
  return useMutation<PolicyValues, unknown, Partial<PolicyValues>>({
    mutationFn: async (body) => (await apiClient.patch('/budget-prep/mtef-policy/current/', body)).data,
    onSuccess: refresh,
  });
};

/** The full record for the form: the framework view carries figures, not every field. */
export async function fetchProjection(id: number): Promise<Record<string, any>> {
  return (await apiClient.get(`${BASE}/${id}/`)).data;
}
