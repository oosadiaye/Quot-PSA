/**
 * TanStack Query hooks for /api/v1/contracts/contracts/ CRUD.
 *
 * Mirrors the useJournal.ts shape so developers moving between modules
 * don't pay a cognitive tax. All writes invalidate the list cache; the
 * detail cache is keyed by id so individual reads stay hot.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

export interface ContractSummary {
  id: number;
  reference: string;
  title: string;
  vendor_name?: string;
  contract_ceiling: string;
  status: string;
  start_date: string;
  end_date: string;
  cumulative_gross_certified?: string;
  ceiling_utilization_pct?: number;
}

export const CONTRACTS_BASE = '/contracts/contracts/';

export const useContracts = (filters: Record<string, any> = {}) => {
  return useQuery({
    queryKey: ['contracts', filters],
    queryFn: async () => {
      const { data } = await apiClient.get(CONTRACTS_BASE, { params: filters });
      return {
        results: (data.results ?? data) as ContractSummary[],
        count: data.count ?? (Array.isArray(data) ? data.length : 0),
      };
    },
    staleTime: 2 * 60 * 1000,
  });
};

export const useContract = (id: number | null | undefined) => {
  return useQuery({
    queryKey: ['contract', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`${CONTRACTS_BASE}${id}/`);
      return data;
    },
    enabled: !!id,
    staleTime: 60 * 1000,
  });
};

export const useContractBalance = (id: number | null | undefined) => {
  return useQuery({
    queryKey: ['contract-balance', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`${CONTRACTS_BASE}${id}/balance/`);
      return data;
    },
    enabled: !!id,
    staleTime: 30 * 1000,
  });
};

export const useCreateContract = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<ContractSummary>) => {
      const { data } = await apiClient.post(CONTRACTS_BASE, payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
};

export const useUpdateContract = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: Partial<ContractSummary> }) => {
      const { data } = await apiClient.patch(`${CONTRACTS_BASE}${id}/`, payload);
      return data;
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['contract', vars.id] });
    },
  });
};

/**
 * POST /contracts/contracts/{id}/activate/
 * Backend: ContractActivationService.activate — assigns contract_number,
 * materializes ContractBalance, fires post-activation signals.
 * Legal only when status === 'DRAFT'.
 */
export const useActivateContract = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, notes }: { id: number; notes?: string }) => {
      const { data } = await apiClient.post(`${CONTRACTS_BASE}${id}/activate/`, { notes: notes ?? '' });
      return data;
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['contract', vars.id] });
      qc.invalidateQueries({ queryKey: ['contract-balance', vars.id] });
    },
  });
};

/**
 * POST /contracts/contracts/{id}/close/
 * Legal only when status === 'FINAL_COMPLETION'.
 */
export const useCloseContract = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, notes }: { id: number; notes?: string }) => {
      const { data } = await apiClient.post(`${CONTRACTS_BASE}${id}/close/`, { notes: notes ?? '' });
      return data;
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['contract', vars.id] });
    },
  });
};

export const useDeleteContract = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`${CONTRACTS_BASE}${id}/`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
};

/**
 * POST /contracts/milestones/  — create a milestone schedule entry.
 *
 * Milestones are the "physical contractual checkpoints" of a contract
 * (Foundation Laid, Roof On, Practical Completion, etc.) — distinct
 * from IPCs which are the financial settlement documents that pay
 * for the value certified at each milestone or measurement.
 *
 * The backend enforces a unique (contract, milestone_number) and the
 * serializer leaves milestone_number as the caller's responsibility.
 * Frontend assigns ``count(existing) + 1`` so the next milestone
 * always picks up the next sequential number; if that races with a
 * concurrent insert the unique constraint catches it and the user
 * gets a re-try chance.
 */
export const useCreateMilestone = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      contract: number;
      milestone_number: number;
      description: string;
      scheduled_value: string | number;
      percentage_weight: string | number;
      target_date: string;        // YYYY-MM-DD
      notes?: string;
    }) => {
      const { data } = await apiClient.post('/contracts/milestones/', payload);
      return data;
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['contract', vars.contract] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
};

/**
 * PATCH /contracts/milestones/{id}/ — partial update.
 *
 * Used to transition status (PENDING → IN_PROGRESS → COMPLETED), set
 * the ``actual_completion_date`` when marking a milestone done, or
 * edit the description / scheduled value while still PENDING.
 *
 * Note on lifecycle: this codebase has no separate "approval" step —
 * the engineer's certification IS the approval. Once a milestone is
 * COMPLETED, an IPC can be raised against it for payment.
 */
export const useUpdateMilestone = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      contractId,
      patch,
    }: {
      id: number;
      contractId: number;
      patch: Partial<{
        status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED';
        actual_completion_date: string | null;
        description: string;
        scheduled_value: string | number;
        percentage_weight: string | number;
        target_date: string;
        notes: string;
      }>;
    }) => {
      const { data } = await apiClient.patch(`/contracts/milestones/${id}/`, patch);
      return { data, contractId };
    },
    onSuccess: ({ contractId }) => {
      qc.invalidateQueries({ queryKey: ['contract', contractId] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
};

/**
 * POST /contracts/milestones/{id}/start/  — PENDING → IN_PROGRESS.
 * The site has begun work on this milestone but it isn't certified
 * complete yet. No IPC may be raised until status is COMPLETED.
 */
export const useStartMilestone = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, contractId }: { id: number; contractId: number }) => {
      const { data } = await apiClient.post(`/contracts/milestones/${id}/start/`);
      return { data, contractId };
    },
    onSuccess: ({ contractId }) => {
      qc.invalidateQueries({ queryKey: ['contract', contractId] });
    },
  });
};

/**
 * POST /contracts/milestones/{id}/approve/  — anything → COMPLETED.
 *
 * "Approve" in this codebase is the engineer/QS certification of
 * physical completion. After approval an IPC may be raised against
 * the milestone for payment. Permission gate: tenant admins always
 * pass; other users need ``contracts.certify_milestone`` or
 * ``contracts.certify_ipc``.
 *
 * Body (optional):
 *   actual_completion_date  YYYY-MM-DD; defaults to today server-side
 *   notes                   free-text certification narrative
 */
export const useApproveMilestone = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id, contractId, actual_completion_date, notes,
    }: {
      id: number;
      contractId: number;
      actual_completion_date?: string;
      notes?: string;
    }) => {
      const { data } = await apiClient.post(
        `/contracts/milestones/${id}/approve/`,
        { actual_completion_date, notes },
      );
      return { data, contractId };
    },
    onSuccess: ({ contractId }) => {
      qc.invalidateQueries({ queryKey: ['contract', contractId] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
};

/**
 * POST /contracts/milestones/{id}/reopen/  — COMPLETED → IN_PROGRESS.
 * Used when a defect is discovered post-certification and the work
 * needs to be re-done. Requires the same permission as approve.
 */
export const useReopenMilestone = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, contractId, reason }: {
      id: number;
      contractId: number;
      reason?: string;
    }) => {
      const { data } = await apiClient.post(
        `/contracts/milestones/${id}/reopen/`,
        { reason },
      );
      return { data, contractId };
    },
    onSuccess: ({ contractId }) => {
      qc.invalidateQueries({ queryKey: ['contract', contractId] });
    },
  });
};

/**
 * POST /contracts/milestones/{id}/convert-to-ipc/
 *
 * Converts an APPROVED (status=COMPLETED) milestone into an
 * Interim Payment Certificate. The IPC is created in SUBMITTED
 * status; downstream certification / approval / voucher flows
 * follow the standard IPC lifecycle. Tax + WHT default from the
 * vendor master so the eventual PaymentVoucher applies the right
 * deductions automatically.
 *
 * Permission: ``CanDraftIPC`` — tenant admins always pass; other
 * users need ``contracts.add_interimpaymentcertificate``.
 */
export const useConvertMilestoneToIPC = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      milestoneId, contractId, posting_date, notes,
    }: {
      milestoneId: number;
      contractId: number;
      posting_date?: string;
      notes?: string;
    }) => {
      const { data } = await apiClient.post(
        `/contracts/milestones/${milestoneId}/convert-to-ipc/`,
        { posting_date, notes },
      );
      return { data, contractId };
    },
    onSuccess: ({ contractId }) => {
      qc.invalidateQueries({ queryKey: ['contract', contractId] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['ipcs'] });
    },
  });
};

/**
 * GET /contracts/mobilization-payments/?contract={id}
 *
 * Fetches the (at most one) MobilizationPayment row for a contract.
 * Returns ``null`` when no advance has been issued yet — the UI uses
 * this to decide between "Issue Mobilization" and "View Status".
 */
export const useContractMobilization = (contractId: number | null) => {
  return useQuery({
    queryKey: ['contract-mobilization', contractId],
    queryFn: async () => {
      const { data } = await apiClient.get('/contracts/mobilization-payments/', {
        params: { contract: contractId, page_size: 1 },
      });
      const rows = Array.isArray(data) ? data : (data?.results ?? []);
      return rows[0] ?? null;
    },
    enabled: !!contractId,
    staleTime: 30 * 1000,
  });
};

/**
 * POST /contracts/mobilization-payments/issue/{contract_pk}/
 *
 * Issues the mobilization advance — creates a MobilizationPayment row
 * in PENDING status. Backend runs three guards:
 *   • Contract has mobilization_rate > 0
 *   • No prior MobilizationPayment exists (one-per-contract)
 *   • Strict appropriation availability check (raises with deficit
 *     detail when budget is insufficient)
 *
 * Permission: ``CanDraftIPC`` — tenant admins always pass.
 */
export const useIssueMobilization = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (contractId: number) => {
      const { data } = await apiClient.post(
        `/contracts/mobilization-payments/issue/${contractId}/`,
      );
      return { data, contractId };
    },
    onSuccess: ({ contractId }) => {
      qc.invalidateQueries({ queryKey: ['contract-mobilization', contractId] });
      qc.invalidateQueries({ queryKey: ['contract', contractId] });
    },
  });
};

/**
 * GET /contracts/retention-releases/?contract={id}
 * — list all retention releases on a contract (typically 0–2:
 * Practical Completion 50%, Final Completion remainder).
 */
export const useContractRetentionReleases = (contractId: number | null) => {
  return useQuery({
    queryKey: ['contract-retention-releases', contractId],
    queryFn: async () => {
      const { data } = await apiClient.get('/contracts/retention-releases/', {
        params: { contract: contractId, page_size: 5 },
      });
      return Array.isArray(data) ? data : (data?.results ?? []);
    },
    enabled: !!contractId,
    staleTime: 30 * 1000,
  });
};

/**
 * POST /contracts/retention-releases/create-release/
 *
 * Creates a PENDING RetentionRelease at Practical or Final
 * Completion. The contract must be in the matching status:
 *   PRACTICAL_COMPLETION → 50% of retention_held released
 *   FINAL_COMPLETION     → remaining 50% released
 *
 * The actual cash disbursement is via PaymentVoucher (Treasury).
 * Backend enforces the status gate, the unique-per-type rule, and
 * caps the released amount at the remaining held balance.
 */
export const useCreateRetentionRelease = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      contractId, release_type,
    }: {
      contractId: number;
      release_type: 'PRACTICAL_COMPLETION' | 'FINAL_COMPLETION';
    }) => {
      const { data } = await apiClient.post(
        '/contracts/retention-releases/create-release/',
        { contract: contractId, release_type },
      );
      return { data, contractId };
    },
    onSuccess: ({ contractId }) => {
      qc.invalidateQueries({ queryKey: ['contract-retention-releases', contractId] });
      qc.invalidateQueries({ queryKey: ['contract', contractId] });
    },
  });
};
