/**
 * Generic TanStack Query CRUD hooks for the future-module registry pages.
 *
 * Each module declares an entity config (see `entityCrudConfig` in
 * `features/_base/types.ts`). All 15 future modules use the same shape, so a
 * single hook factory keeps the frontend consistent with the backend
 * DefaultRouter endpoints (`/api/v1/<module>/<entity>/`).
 *
 * The query key includes the module key + entity plural so lists across
 * modules never collide and writes invalidate the right list.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

export interface EntityFilters {
  search?: string;
  page?: number;
  page_size?: number;
  [key: string]: any;
}

const normalizeList = (data: any) => ({
  results: (data.results ?? data as any[] ?? []) as any[],
  count: data.count ?? (Array.isArray(data) ? data.length : 0),
});

export function useEntityList(
  moduleKey: string,
  basePath: string,
  filters: EntityFilters = {},
) {
  const qk = [moduleKey, 'list', basePath, filters];
  return useQuery({
    queryKey: qk,
    queryFn: async () => {
      const { data } = await apiClient.get(basePath, { params: filters });
      return normalizeList(data);
    },
    staleTime: 60 * 1000,
  });
}

/** A payload carrying a File must go as multipart; axios's JSON default would drop it. */
function toRequestBody(payload: Record<string, any>) {
  if (!Object.values(payload).some((v) => v instanceof File)) return { body: payload, config: undefined };
  const form = new FormData();
  for (const [k, v] of Object.entries(payload)) {
    if (v === null || v === undefined) continue;
    form.append(k, v instanceof File ? v : String(v));
  }
  return { body: form, config: { headers: { 'Content-Type': 'multipart/form-data' } } };
}

export function useEntityCreate(moduleKey: string, basePath: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Record<string, any>) => {
      const { body, config } = toRequestBody(payload);
      const { data } = await apiClient.post(basePath, body, config);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [moduleKey, 'list'] });
    },
  });
}

export function useEntityUpdate(moduleKey: string, basePath: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: Record<string, any> }) => {
      const { body, config } = toRequestBody(payload);
      const { data } = await apiClient.patch(`${basePath}${id}/`, body, config);
      return data;
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: [moduleKey, 'list'] });
      qc.invalidateQueries({ queryKey: [moduleKey, 'detail', vars.id] });
    },
  });
}

export function useEntityDelete(moduleKey: string, basePath: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await apiClient.delete(`${basePath}${id}/`);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [moduleKey, 'list'] });
    },
  });
}
