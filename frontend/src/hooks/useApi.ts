import { useState, useEffect, useCallback, useRef } from 'react';

interface UseApiOptions extends RequestInit {
  skip?: boolean;
  timeout?: number;
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
  options: UseApiOptions = {}
): UseApiReturn<T> {
  const { skip = false, timeout = 30000, ...fetchOptions } = options;
  
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!skip);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  
  const abortControllerRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const fetchData = useCallback(() => {
    if (!url || skip) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setError(null);
    setStatus(null);

    const timeoutId = setTimeout(() => {
      controller.abort();
      setError('Request timeout');
      setLoading(false);
    }, timeout);

    timeoutRef.current = timeoutId;

    fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
    })
      .then((response) => {
        setStatus(response.status);
        if (!response.ok) {
          if (response.status === 401) {
            window.location.href = '/login';
            throw new Error('Unauthorized');
          }
          return response.json().then((err) => {
            throw new Error(err.detail || `HTTP ${response.status}`);
          });
        }
        return response.json();
      })
      .then((result) => {
        clearTimeout(timeoutId);
        setData(result);
        setError(null);
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        if (err.name !== 'AbortError') {
          setError(err.message || 'An unexpected error occurred');
        }
      })
      .finally(() => {
        setLoading(false);
        clearTimeout(timeoutId);
      });
  }, [url, skip, timeout, fetchOptions]);

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
  }, []);

  useEffect(() => {
    fetchData();
    return () => {
      abort();
    };
  }, [fetchData, abort]);

  return { data, loading, error, status, refetch: fetchData, abort };
}

export function useMutation<TData = unknown, TVariables = unknown>(
  mutationFn: (variables: TVariables) => Promise<TData>
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
    [mutationFn]
  );

  return { mutate, data, loading, error, reset: () => { setData(null); setError(null); } };
}