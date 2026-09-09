import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

export type PaymentBatchStatus = 'Draft' | 'Dispatched' | 'Confirmed' | 'Cancelled';

export interface PaymentBatchLine {
  id: number;
  sequence: number;
  payment: number | null;
  payment_number: string;
  payee_name: string;
  payee_bank: string;
  payee_account: string;
  purpose: string;
  amount: string;
  is_active_membership: boolean;
}

export interface PaymentBatch {
  id: number;
  batch_number: string;
  batch_date: string;
  source_bank_account: number;
  source_bank_account_name: string;
  addressee_bank_name: string;
  addressee_account_no: string;
  status: PaymentBatchStatus;
  total_amount: string;
  line_count: number;
  lines: PaymentBatchLine[];
  notes: string;
  cancelled_reason: string;
  dispatched_at: string | null;
  confirmed_at: string | null;
  /** The bank's advice reference, recorded when the batch was confirmed. */
  bank_reference: string;
}

export interface BankLetterSettings {
  id: number;
  ministry_name: string;
  office_name: string;
  office_address: string;
  letterhead_logo: string | null;
  accountant_general_name: string;
  accountant_general_title: string;
  accountant_general_signature: string | null;
  director_treasury_name: string;
  director_treasury_title: string;
  director_treasury_signature: string | null;
  director_mgmt_acct_name: string;
  director_mgmt_acct_title: string;
  director_mgmt_acct_signature: string | null;
}

const BASE = '/accounting/payment-batches';

export function usePaymentBatches(params?: { status?: PaymentBatchStatus }) {
  return useQuery({
    queryKey: ['payment-batches', params],
    queryFn: async () => {
      const { data } = await apiClient.get(`${BASE}/`, { params });
      return (data.results ?? data) as PaymentBatch[];
    },
  });
}

export function usePaymentBatch(id: number | undefined) {
  return useQuery({
    queryKey: ['payment-batch', id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await apiClient.get(`${BASE}/${id}/`);
      return data as PaymentBatch;
    },
  });
}

export function useEligiblePayments(bankAccountId: number | undefined) {
  return useQuery({
    queryKey: ['payment-batch-eligible', bankAccountId],
    enabled: !!bankAccountId,
    queryFn: async () => {
      const { data } = await apiClient.get(`${BASE}/eligible_payments/`, {
        params: { bank_account: bankAccountId },
      });
      return (data.results ?? data) as Array<Record<string, unknown>>;
    },
  });
}

export function useBatchLetter(id: number | undefined) {
  return useQuery({
    queryKey: ['payment-batch-letter', id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await apiClient.get(`${BASE}/${id}/letter/`);
      return data as { batch: PaymentBatch; settings: BankLetterSettings };
    },
  });
}

function useBatchMutation<TVars>(fn: (vars: TVars) => Promise<PaymentBatch>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (batch) => {
      qc.invalidateQueries({ queryKey: ['payment-batches'] });
      qc.invalidateQueries({ queryKey: ['payment-batch', batch.id] });
      qc.invalidateQueries({ queryKey: ['payment-batch-eligible'] });
    },
  });
}

export function useCreatePaymentBatch() {
  return useBatchMutation<{ source_bank_account: number; batch_date?: string; payment_ids: number[] }>(
    async (vars) => (await apiClient.post(`${BASE}/`, vars)).data,
  );
}

export function useAddBatchLines(id: number) {
  return useBatchMutation<{ payment_ids: number[] }>(
    async (vars) => (await apiClient.post(`${BASE}/${id}/add_lines/`, vars)).data,
  );
}

export function useRemoveBatchLine(id: number) {
  return useBatchMutation<{ line_id: number }>(
    async (vars) => (await apiClient.post(`${BASE}/${id}/remove_line/`, vars)).data,
  );
}

export function useDispatchBatch(id: number) {
  return useBatchMutation<void>(
    async () => (await apiClient.post(`${BASE}/${id}/dispatch/`)).data,
  );
}

export function useConfirmBatch(id: number) {
  return useBatchMutation<{ bank_reference: string }>(
    async (vars) => (await apiClient.post(`${BASE}/${id}/confirm/`, vars)).data,
  );
}

export function useCancelBatch(id: number) {
  return useBatchMutation<{ reason: string }>(
    async (vars) => (await apiClient.post(`${BASE}/${id}/cancel/`, vars)).data,
  );
}

export function useBankLetterSettings() {
  return useQuery({
    queryKey: ['bank-letter-settings'],
    queryFn: async () => {
      const { data } = await apiClient.get('/accounting/bank-letter-settings/current/');
      return data as BankLetterSettings;
    },
  });
}
