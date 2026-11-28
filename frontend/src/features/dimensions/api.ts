/**
 * Custom dimensions (Ward, Zone, ...): what a form should show, reading and setting a record's tags, and the settings lists.
 * With no dimensions defined every list is empty and callers render nothing extra.
 */
import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

export type RecordType = 'journal_line' | 'purchase_request' | 'purchase_order' | 'appropriation';

export const RECORD_TYPE_LABELS: Record<RecordType, string> = {
  journal_line: 'Journal lines',
  purchase_request: 'Purchase requests',
  purchase_order: 'Purchase orders',
  appropriation: 'Budget appropriations',
};

export interface FormDimensionValue { code: string; name: string; parent: string | null }
export interface FormDimension {
  code: string;
  name: string;
  parent_type: string | null;
  required: boolean;
  values: FormDimensionValue[];
}
/** `{ dimension code: value code }` for one record. */
export type Tags = Record<string, string>;

export interface DimensionType {
  id: number;
  code: string;
  name: string;
  parent_type: number | null;
  parent_type_code: string | null;
  applies_to: RecordType[];
  required_on: RecordType[];
  is_active: boolean;
  value_count: number;
}
export interface DimensionValueRow {
  id: number;
  dimension_type: number;
  dimension_type_code: string;
  code: string;
  name: string;
  parent: number | null;
  parent_code: string | null;
  is_active: boolean;
}
export interface ReportRow { code: string; name: string; debit: string; credit: string; net: string; lines: number }
export interface DimensionReport { dimension: string; name: string; account_type: string; rows: ReportRow[] }

const asList = <T,>(data: unknown): T[] => (Array.isArray(data) ? data : ((data as { results?: T[] })?.results ?? [])) as T[];

export const apiMessage = (e: unknown): string => {
  const data = (e as { response?: { data?: Record<string, unknown> } })?.response?.data;
  if (!data) return 'Something went wrong. Try again.';
  if (typeof data.error === 'string') return data.error;
  if (typeof data.detail === 'string') return data.detail;
  const first = Object.entries(data)[0];
  return first ? `${first[0]}: ${Array.isArray(first[1]) ? first[1].join(' ') : String(first[1])}` : 'Something went wrong.';
};

/** The dimensions a form shows for a record type. A failure (e.g. a role that may not read them) shows none. */
export function useFormDimensions(recordType: RecordType) {
  return useQuery({
    queryKey: ['dimensions', 'for-record', recordType],
    queryFn: async () => (await apiClient.get('/dimensions/types/for-record/', { params: { record_type: recordType } })).data as FormDimension[],
    staleTime: 60_000,
    retry: false,
  });
}

export const getTags = async (recordType: RecordType, recordId: number): Promise<Tags> =>
  (await apiClient.get('/dimensions/tags/', { params: { record_type: recordType, record_id: recordId } })).data;

export const saveTags = async (recordType: RecordType, recordId: number, tags: Tags): Promise<Tags> =>
  (await apiClient.post('/dimensions/tags/set/', { record_type: recordType, record_id: recordId, tags })).data;

export function useDimensionTypes() {
  return useQuery({
    queryKey: ['dimensions', 'types'],
    queryFn: async () => asList<DimensionType>((await apiClient.get('/dimensions/types/', { params: { page_size: 200 } })).data),
  });
}

export function useDimensionValues(typeId: number | null) {
  return useQuery({
    queryKey: ['dimensions', 'values', typeId],
    enabled: typeId !== null,
    queryFn: async () => asList<DimensionValueRow>((await apiClient.get('/dimensions/values/', { params: { dimension_type: typeId, page_size: 1000 } })).data),
  });
}

export function useDimensionWrite<TBody extends Record<string, unknown>>(path: 'types' | 'values') {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { id?: number; body: TBody }) =>
      v.id ? (await apiClient.patch(`/dimensions/${path}/${v.id}/`, v.body)).data : (await apiClient.post(`/dimensions/${path}/`, v.body)).data,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['dimensions'] }); },
  });
}

export function useDimensionReport(code: string, parentValue: string | null, range: { from?: string; to?: string }) {
  return useQuery({
    queryKey: ['dimensions', 'report', code, parentValue, range.from, range.to],
    queryFn: async () => (await apiClient.get(`/dimensions/tags/report/${code}/`, {
      params: { parent_value: parentValue || undefined, date_from: range.from || undefined, date_to: range.to || undefined },
    })).data as DimensionReport,
  });
}

/**
 * The dimension values of one document (a purchase request, an order, an appropriation) while its form is open: what to
 * show, the chosen values, the ones still missing, loading them from a saved record or a source record, and saving them
 * against the record once it exists.
 */
export function useRecordDimensions(recordType: RecordType) {
  const { data: dimensions = [] } = useFormDimensions(recordType);
  const [tags, setTags] = useState<Tags>({});
  const missing = dimensions.filter((d) => d.required && !tags[d.code]).map((d) => d.name);
  const load = useCallback(async (fromType: RecordType, fromId: number) => {
    try { setTags(await getTags(fromType, fromId)); } catch { /* a role that may not read dimensions simply sees none */ }
  }, []);
  const save = useCallback(async (recordId: number) => {
    if (dimensions.length) await saveTags(recordType, recordId, tags);
  }, [dimensions.length, recordType, tags]);
  return { dimensions, tags, setTags, missing, load, save };
}
