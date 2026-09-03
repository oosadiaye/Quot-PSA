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
  const qk = [moduleKey, 'list', filters];
  return useQuery({
    queryKey: qk,
    queryFn: async () => {
      const { data } = await apiClient.get(basePath, { params: filters });
      return normalizeList(data);
    },
    staleTime: 60 * 1000,
  });
}

export function useEntityCreate(moduleKey: string, basePath: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Record<string, any>) => {
      const { data } = await apiClient.post(basePath, payload);
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
      const { data } = await apiClient.patch(`${basePath}${id}/`, payload);
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
