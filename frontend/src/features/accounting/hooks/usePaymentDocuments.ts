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

export function usePaymentDocuments(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['payment-documents', params],
    queryFn: async () => {
      const { data } = await apiClient.get(BASE, { params });
      return Array.isArray(data) ? data : (data?.results ?? []);
    },
  });
}

export function useCreatePaymentDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PaymentDocumentInput) => (await apiClient.post(BASE, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-documents'] }),
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
