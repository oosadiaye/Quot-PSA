import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

export interface DebtInstrumentRow {
  id: number;
  instrument_number: string;
  instrument_type: string;
  creditor: string;
  principal_amount: string;
  status: string;
  outstanding_principal: string;
  drawn_amount: string;
  principal_repaid: string;
  liability_account: number | null;
  liability_account_name: string;
  current_portion_account: number | null;
  current_portion_account_name: string;
  interest_expense_account: number | null;
  interest_expense_account_name: string;
  fee_expense_account: number | null;
  bank_account: number | null;
  bank_account_name: string;
  current_portion_booked: string;
}

export interface DebtPosition {
  as_of: string;
  facility: string;
  drawn: string;
  principal_repaid: string;
  outstanding_principal: string;
  current_portion: string;
  non_current_portion: string;
  due_within_12_months: string;
  suggested_current_portion: string;
  reclassification_needed: string;
}

export interface CouponRow {
  id: number;
  schedule: number;
  due_date: string;
  principal_amount: string;
  interest_amount: string;
  commitment_fee: string;
  total_amount: string;
  status: string;
  journal_number?: string;
}

export interface BankRow {
  id: number;
  name?: string;
  account_name?: string;
  account_number?: string;
  gl_account?: number | null;
}

export interface DrawdownRow {
  id: number;
  drawdown_date: string;
  amount: string;
  bank_account_name: string;
  reference: string;
  journal_number: string;
}

export interface ClassificationRow {
  id: number;
  as_of: string;
  current_portion: string;
  adjustment: string;
  journal_number: string;
}

const list = <T,>(data: any): T[] => (Array.isArray(data) ? data : data?.results ?? []);

/** The sentence to show for a failed action: the server's own reason, else a plain fallback. */
export function debtError(err: unknown, fallback = 'That did not work. Please try again.'): string {
  const data = (err as { response?: { data?: any } })?.response?.data;
  if (data?.error) return String(data.error);
  if (data?.detail) return String(data.detail);
  if (data && typeof data === 'object') {
    const first = Object.entries(data).find(([, v]) => v);
    if (first) return `${first[0].replace(/_/g, ' ')}: ${Array.isArray(first[1]) ? first[1][0] : first[1]}`;
  }
  return fallback;
}

export const useInstruments = () =>
  useQuery<DebtInstrumentRow[]>({
    queryKey: ['debt-gl', 'instruments'],
    queryFn: async () => list((await apiClient.get('/debt/instruments/', { params: { page_size: 200 } })).data),
  });

export const usePosition = (id: number | null) =>
  useQuery<DebtPosition>({
    queryKey: ['debt-gl', 'position', id],
    queryFn: async () => (await apiClient.get(`/debt/instruments/${id}/position/`)).data,
    enabled: !!id,
  });

export const useCoupons = (instrumentId: number | null) =>
  useQuery<CouponRow[]>({
    queryKey: ['debt-gl', 'coupons', instrumentId],
    queryFn: async () => list((await apiClient.get('/debt/coupons/', { params: { schedule__instrument: instrumentId, page_size: 200 } })).data),
    enabled: !!instrumentId,
  });

export const useBankAccounts = () =>
  useQuery<BankRow[]>({
    queryKey: ['debt-gl', 'banks'],
    queryFn: async () => list((await apiClient.get('/accounting/bank-accounts/', { params: { page_size: 500 } })).data),
    staleTime: 5 * 60 * 1000,
  });

export const useDrawdowns = (id: number | null) =>
  useQuery<DrawdownRow[]>({
    queryKey: ['debt-gl', 'drawdowns', id],
    queryFn: async () => list((await apiClient.get(`/debt/instruments/${id}/drawdowns/`)).data),
    enabled: !!id,
  });

export const useClassifications = (id: number | null) =>
  useQuery<ClassificationRow[]>({
    queryKey: ['debt-gl', 'classifications', id],
    queryFn: async () => list((await apiClient.get(`/debt/instruments/${id}/classifications/`)).data),
    enabled: !!id,
  });

/** Everything a GL action can change on screen, including the generic register below the panel. */
function useRefresh() {
  const qc = useQueryClient();
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: ['debt-gl'] }),
    qc.invalidateQueries({ queryKey: ['debt'] }),
  ]);
}

export function useStandardAccounts() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (id: number) => (await apiClient.post(`/debt/instruments/${id}/standard-accounts/`)).data,
    onSuccess: refresh,
  });
}

export function useSaveMapping() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Record<string, number | null> }) =>
      (await apiClient.patch(`/debt/instruments/${id}/`, body)).data,
    onSuccess: refresh,
  });
}

export function useDrawdown() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      (await apiClient.post(`/debt/instruments/${id}/drawdown/`, body)).data,
    onSuccess: refresh,
  });
}

export function useReclassify() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async ({ id, as_of }: { id: number; as_of: string }) =>
      (await apiClient.post(`/debt/instruments/${id}/reclassify/`, { as_of })).data,
    onSuccess: refresh,
  });
}

export function usePayCoupon() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      (await apiClient.post(`/debt/coupons/${id}/pay/`, body)).data,
    onSuccess: refresh,
  });
}
