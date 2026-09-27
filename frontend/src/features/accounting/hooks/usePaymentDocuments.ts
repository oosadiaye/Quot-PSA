import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const BASE = '/accounting/payment-documents/';

export interface PaymentDocumentLineInput {
  account: number | string;
  vendor?: number | string | null;
  debit: string;
  credit: string;
  memo?: string;
  is_deduction?: boolean;
}

export interface PaymentDocumentInput {
  bank_account: number | string;
  description?: string;
  reference_number?: string;
  document_date?: string;
  mda?: number | string | null;
  fund?: number | string | null;
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
  memo?: string;
  is_deduction?: boolean;
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

export function usePostPaymentDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number | string) => (await apiClient.post(`${BASE}${id}/post/`, {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-documents'] }),
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
