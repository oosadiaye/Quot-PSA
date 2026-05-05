/**
 * useApi.ts
 * ---------
 * **Deprecated.** Prefer ``apiClient`` (from ``src/api/client.ts``)
 * via TanStack Query (``useQuery`` / ``useMutation``) for all new
 * code. ``apiClient`` injects:
 *   • ``Authorization`` header from the auth context
 *   • ``X-Tenant-Domain`` and ``X-Organization-Id`` headers
 *   • 401 → ``auth-expired`` event (handled by ``AuthContext``)
 *
 * The previous implementation here used raw ``fetch`` with NO header
 * injection — every caller would have gone unauthenticated. There
 * are currently zero callers in the codebase, but this file is kept
 * (and rewritten as a thin ``apiClient`` wrapper) so any future
 * accidental import doesn't silently bypass auth.
 *
 * ``useMutation`` re-export is preserved for callers that still use
 * the lightweight pattern, but it now uses ``apiClient`` under the
 * hood when a URL is supplied.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import apiClient from '../api/client';
import type { AxiosRequestConfig } from 'axios';

interface UseApiOptions {
  skip?: boolean;
  timeout?: number;
  method?: AxiosRequestConfig['method'];
  data?: unknown;
  params?: Record<string, unknown>;
}

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  status: number | null;
}

interface UseApiReturn<T> extends UseApiState<T> {
  refetch: () => void;
  abort: () => void;
}

export function useApi<T = unknown>(
  url: string | null,
  options: UseApiOptions = {},
): UseApiReturn<T> {
  const { skip = false, timeout = 30000, method = 'GET', data: body, params } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!skip);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(() => {
    if (!url || skip) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setLoading(true);
    setError(null);

    apiClient
      .request<T>({
        url,
        method,
        data: body,
        params,
        signal: controller.signal,
        timeout,
      })
      .then((res) => {
        setStatus(res.status);
        setData(res.data);
        setError(null);
      })
      .catch((err) => {
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
        setStatus(err?.response?.status ?? null);
        setError(err?.response?.data?.detail || err?.message || 'Request failed');
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, skip, timeout, method, JSON.stringify(body ?? null), JSON.stringify(params ?? null)]);

  const abort = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    fetchData();
    return () => abort();
  }, [fetchData, abort]);

  return { data, loading, error, status, refetch: fetchData, abort };
}

export function useMutation<TData = unknown, TVariables = unknown>(
  mutationFn: (variables: TVariables) => Promise<TData>,
) {
  const [data, setData] = useState<TData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutate = useCallback(
    async (variables: TVariables) => {
      setLoading(true);
      setError(null);
      try {
        const result = await mutationFn(variables);
        setData(result);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Mutation failed';
        setError(message);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [mutationFn],
  );

  return {
    mutate,
    data,
    loading,
    error,
    reset: () => {
      setData(null);
      setError(null);
    },
  };
}
