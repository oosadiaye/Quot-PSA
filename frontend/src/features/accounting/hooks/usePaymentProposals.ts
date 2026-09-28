import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const BASE = '/accounting/payment-proposals/';

// One row of the unified register — a Payment Voucher OR a Payment Document,
// mapped to a common shape server-side. ``detail_path`` points at the source's
// own native detail page.
export interface PaymentProposalRow {
  source: 'pv' | 'pd';
  id: number | string;
  number: string;
  date: string | null;
  payee_or_description: string;
  amount: string;
  native_status: string;
  unified_status: string;
  detail_path: string;
}

/** Fetch the unified Payment Proposal register, filtered by unified status/source. */
export function usePaymentProposals(status?: string, source?: string) {
  return useQuery<PaymentProposalRow[]>({
    queryKey: ['payment-proposals', status ?? null, source ?? null],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (status) params.status = status;
      if (source) params.source = source;
      const { data } = await apiClient.get(BASE, { params });
      return (data?.results ?? []) as PaymentProposalRow[];
    },
  });
}
