import { createContext, useContext, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';

export interface BrandingInfo {
    name: string;
    tagline: string;
    logo: string | null;
}

interface BrandingContextType {
    branding: BrandingInfo;
    isLoading: boolean;
}

const FALLBACK: BrandingInfo = { name: 'DTSG ERP', tagline: '', logo: null };

const BrandingContext = createContext<BrandingContextType>({
    branding: FALLBACK,
    isLoading: false,
});

/**
 * BrandingProvider fetches tenant branding (name, tagline, logo).
 *
 * - Uses the **public** endpoint (`/tenants/public-branding/`) which needs
 *   no auth token.  The tenant is resolved by django-tenants middleware
 *   from the hostname, so it works on the login page too.
 * - After login, the authenticated branding endpoint could provide richer
 *   data — but for name/logo display the public one is sufficient and
 *   avoids a redundant fetch.
 * - Data is cached for 5 minutes (staleTime) to avoid re-fetching on
 *   every route change.
 */
export function BrandingProvider({ children }: { children: ReactNode }) {
    const { data, isLoading } = useQuery<BrandingInfo>({
        queryKey: ['tenant-public-branding'],
        queryFn: async () => {
            const { data } = await apiClient.get('/tenants/public-branding/');
            return data;
        },
        staleTime: 5 * 60 * 1000,
        retry: 1,
    });

    const branding: BrandingInfo = data ?? FALLBACK;

    return (
        <BrandingContext.Provider value={{ branding, isLoading }}>
            {children}
        </BrandingContext.Provider>
    );
}

export function useBranding() {
    return useContext(BrandingContext);
}
