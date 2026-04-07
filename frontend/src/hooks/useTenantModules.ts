import { useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';

export interface TenantModules {
    enabled_modules: Record<string, boolean>;
    dimensions_enabled: boolean;
}

/**
 * Sentinel: used only as initialData so the first render shows nothing while
 * the real request is in-flight.  An empty enabled_modules map signals
 * "no config yet" — consumers treat this as "show all" (graceful degradation
 * for fresh tenants) but we distinguish it from a real API response by
 * checking `isLoading`.
 */
const EMPTY_MODULES: TenantModules = { enabled_modules: {}, dimensions_enabled: false };

/**
 * Fetches the current tenant's enabled module map.
 *
 * Polls every 15 seconds so superadmin toggles propagate in near real-time
 * without requiring a WebSocket/SSE connection.  The staleTime is set to 0
 * so the first access after a superadmin toggle always fetches fresh data;
 * the 15 s refetchInterval ensures background refresh even on static pages.
 *
 * Error handling: errors are re-thrown so React Query retains the PREVIOUS
 * successful data instead of overwriting it with an empty fallback.  The
 * retry:1 policy gives one automatic retry before marking the query as
 * errored.
 */
export const useTenantModules = () => {
    return useQuery<TenantModules>({
        queryKey: ['tenantModules'],
        queryFn: async () => {
            // Let errors propagate — React Query will keep previous data on
            // failure instead of overwriting with an empty fallback.
            const response = await apiClient.get('/tenants/enabled-modules/');
            return response.data as TenantModules;
        },
        staleTime: 0,               // always re-validate on next mount
        gcTime: 60 * 1000,
        refetchInterval: 15_000,    // poll every 15 s — propagates admin toggles
        retry: 1,                   // one retry before marking errored
        // Keep previous data visible during background re-fetches; use EMPTY
        // only when there is genuinely no previous data (first load).
        placeholderData: (prev) => prev ?? EMPTY_MODULES,
    });
};

/**
 * Returns a function that imperatively invalidates the tenantModules cache.
 * Call this immediately after a superadmin performs a module toggle so the
 * current session sidebar/guard re-renders without waiting for the next poll.
 */
export const useInvalidateTenantModules = () => {
    const qc = useQueryClient();
    return () => qc.invalidateQueries({ queryKey: ['tenantModules'] });
};

export const useIsDimensionsEnabled = () => {
    const { data, isLoading, error } = useTenantModules();
    return {
        isEnabled: data?.dimensions_enabled ?? true,
        isLoading,
        error,
    };
};
