import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const BASE = '/accounting/payment-documents/';

export interface PaymentDocumentLineInput {
  // Nullable: a vendor-only line omits the GL account (resolved to the vendor's
  // AP account server-side).
  account: number | string | null;
  vendor?: number | string | null;
  debit: string;
  credit: string;
  is_deduction?: boolean;
}

export interface PaymentDocumentInput {
  bank_account: number | string;
  description?: string;
  reference_number?: string;
  document_date?: string;
  // Appropriation dimensions are optional and no longer captured by the
  // Payment Document form; kept on the type for other/legacy callers.
  mda?: number | string | null;
  fund?: number | string | null;
  // Full balanced set: the auto bank-credit line (account = bank's GL account,
  // debit 0, credit = Amount) PLUS each user settlement line. No `memo`.
  lines: PaymentDocumentLineInput[];
}

// Shape of a single line as the retrieve/detail endpoint returns it.
export interface PaymentDocumentLineDetail {
  id: number | string;
  account: number | string | null;
  account_code?: string;
  account_name?: string;
  vendor: number | string | null;
  vendor_name?: string;
  debit: string;
  credit: string;
  is_deduction?: boolean;
}

// Shape of the /proposed-entries/ response — the FULL balanced journal effect
// (all debit legs plus the header bank-credit leg), so Σdebit == Σcredit.
export interface ProposedEntries {
  entries: { account: string; account_name: string; debit: string; credit: string }[];
  net_amount: string;
}

// Shape of the retrieve/detail response (GET ${BASE}${id}/).
export interface PaymentDocumentDetail {
  id: number | string;
  document_number: string;
  document_date?: string;
  bank_account: number | string | null;
  bank_account_name?: string;
  reference_number?: string;
  description?: string;
  status: string;
  source?: string;
  mda: number | string | null;
  fund: number | string | null;
  function: number | string | null;
  program: number | string | null;
  geo: number | string | null;
  net_amount?: string | number;
  journal: number | string | null;
  lines: PaymentDocumentLineDetail[];
  // Source-document attachment metadata (image/PDF). The raw file URL is
  // never exposed by the serializer — download runs through the authenticated
  // ``attachment/download`` action, and upload through the ``attachment`` action.
  has_attachment?: boolean;
  attachment_name?: string | null;
}

export function usePaymentDocuments(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['payment-documents', params],
    queryFn: async () => {
      const { data } = await apiClient.get(BASE, { params });
      return Array.isArray(data) ? data : (data?.results ?? []);
    },
  });
}

export function usePaymentDocument(id?: number | string | null) {
  return useQuery<PaymentDocumentDetail>({
    queryKey: ['payment-document', id],
    queryFn: async () => (await apiClient.get(`${BASE}${id}/`)).data,
    enabled: id != null && id !== '',
  });
}

// Proposed accounting entries — the full balanced journal (incl. bank credit)
// this document posts. Works for Draft and Posted docs alike.
export function useProposedEntries(id?: number | string | null) {
  return useQuery<ProposedEntries>({
    queryKey: ['payment-document-entries', id],
    queryFn: async () => (await apiClient.get(`${BASE}${id}/proposed-entries/`)).data,
    enabled: id != null && id !== '',
  });
}

export function useCreatePaymentDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PaymentDocumentInput) => (await apiClient.post(BASE, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-documents'] }),
  });
}

export function useUpdatePaymentDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number | string; payload: PaymentDocumentInput }) =>
      (await apiClient.patch(`${BASE}${id}/`, payload)).data,
    onSuccess: (_data, { id }) => {
      void qc.invalidateQueries({ queryKey: ['payment-documents'] });
      void qc.invalidateQueries({ queryKey: ['payment-document', id] });
    },
  });
}

// Submit a Draft/Rejected document for approval. It does NOT post any GL — on
// approval a Draft Outgoing Payment is provisioned, and the cash-out happens
// only when that payment is posted in Outgoing Payments.
export function useSubmitPaymentDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number | string) => (await apiClient.post(`${BASE}${id}/submit/`, {})).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payment-documents'] });
      qc.invalidateQueries({ queryKey: ['payment-proposals'] });
    },
  });
}

export function useDownloadPaymentDocumentTemplate() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.get(`${BASE}download-template/`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = 'payment-document-template.csv'; a.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useBulkImportPaymentDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append('file', file);
      const { data } = await apiClient.post(`${BASE}import/`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-documents'] }),
  });
}

// Attach a source-document scan (image/PDF) to an EXISTING payment document.
// The endpoint keys off the doc id, so callers must create/save the document
// first and only then upload — never before the id exists.
export function useUploadPaymentDocumentAttachment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, file }: { id: number | string; file: File }) => {
      const form = new FormData();
      form.append('file', file);
      const { data } = await apiClient.post(`${BASE}${id}/attachment/`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return data as PaymentDocumentDetail;
    },
    onSuccess: (_data, { id }) => {
      void qc.invalidateQueries({ queryKey: ['payment-documents'] });
      void qc.invalidateQueries({ queryKey: ['payment-document', id] });
    },
  });
}

// How long a viewed-attachment blob URL is kept alive before it is revoked —
// long enough for the opened tab to fetch it, short enough to avoid a lasting
// memory leak from repeated views.
const ATTACHMENT_BLOB_TTL_MS = 60_000;

// Open a document's attachment in a new tab. The file is NOT served as a raw
// /media URL, so we fetch it as a BLOB through apiClient (which attaches the
// auth token + tenant headers), then open an object URL. Works for both images
// and PDFs. The object URL is revoked after a short delay.
export function useViewPaymentDocumentAttachment() {
  return useMutation({
    mutationFn: async (id: number | string) => {
      const { data } = await apiClient.get(`${BASE}${id}/attachment/download/`, {
        responseType: 'blob',
      });
      const blobUrl = URL.createObjectURL(data as Blob);
      window.open(blobUrl, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), ATTACHMENT_BLOB_TTL_MS);
    },
  });
}
