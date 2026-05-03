/**
 * TanStack Query hooks for Interim Payment Certificates.
 *
 * The backend exposes workflow transitions as @action endpoints:
 *   POST {base}/{id}/certify/       → mark as CERTIFIER_REVIEWED
 *   POST {base}/{id}/approve/       → mark as APPROVED
 *   POST {base}/{id}/raise_voucher/ → mark as VOUCHER_RAISED
 *   POST {base}/{id}/mark_paid/     → mark as PAID
 *   POST {base}/{id}/reject/        → mark as REJECTED
 * Each transition funnels through the D2 service layer which enforces
 * the ceiling/retention/mobilization invariants. A 400/409 here means
 * a structural control tripped — render via formatServiceError().
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

export const IPCS_BASE = '/contracts/ipcs/';

export interface IPCSummary {
  id: number;
  ipc_number: string;
  contract: number;
  contract_reference?: string;
  this_certificate_gross: string;
  this_certificate_net?: string;
  status: string;
  posting_date: string;
  submitted_at?: string;
}

export const useIPCs = (filters: Record<string, any> = {}) => {
  return useQuery({
    queryKey: ['ipcs', filters],
    queryFn: async () => {
      const { data } = await apiClient.get(IPCS_BASE, { params: filters });
      return {
        results: (data.results ?? data) as IPCSummary[],
        count: data.count ?? (Array.isArray(data) ? data.length : 0),
      };
    },
    staleTime: 60 * 1000,
  });
};

export const useIPC = (id: number | null | undefined) => {
  return useQuery({
    queryKey: ['ipc', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`${IPCS_BASE}${id}/`);
      return data;
    },
    enabled: !!id,
    staleTime: 30 * 1000,
  });
};

export const useCreateIPC = () => {
  const qc = useQueryClient();
  return useMutation({
    // IPCViewSet is ReadOnly — creation goes through the dedicated
    // /submit/ action which runs the full ceiling + monotonicity +
    // fiscal-year guard set (ipc_service.submit_ipc). Posting directly
    // to the collection URL returns 405.
    mutationFn: async (payload: any) => {
      const { data } = await apiClient.post(`${IPCS_BASE}submit/`, payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ipcs'] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
};

/** Generic workflow-action mutation factory. */
const useIPCAction = (action: string, extraInvalidate: string[] = []) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload?: Record<string, unknown> }) => {
      const { data } = await apiClient.post(`${IPCS_BASE}${id}/${action}/`, payload ?? {});
      return data;
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['ipcs'] });
      qc.invalidateQueries({ queryKey: ['ipc', vars.id] });
      qc.invalidateQueries({ queryKey: ['contract-balance'] });
      extraInvalidate.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
  });
};

export const useCertifyIPC     = () => useIPCAction('certify');
export const useApproveIPC     = () => useIPCAction('approve');
export const useRaiseVoucher   = () => useIPCAction('raise_voucher', ['payment-vouchers']);
export const useMarkIPCPaid    = () => useIPCAction('mark_paid');
export const useRejectIPC      = () => useIPCAction('reject');

/**
 * POST /contracts/ipcs/{id}/set-wht-exemption/
 *
 * Per-IPC WHT exemption override (parity with Invoice Verification's
 * exempt flag). When ``wht_exempt=true``, ``IPCService._derive_taxes``
 * skips the WHT computation at ``mark_paid`` time even if the vendor
 * master has a default WHT code. ``false`` clears the override.
 *
 * Refuses to mutate IPCs in terminal states (PAID / REJECTED).
 */
export const useSetIPCWhtExemption = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, wht_exempt }: { id: number; wht_exempt: boolean }) => {
      const { data } = await apiClient.post(
        `${IPCS_BASE}${id}/set-wht-exemption/`,
        { wht_exempt },
      );
      return data;
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['ipc', vars.id] });
      qc.invalidateQueries({ queryKey: ['ipcs'] });
    },
  });
};
