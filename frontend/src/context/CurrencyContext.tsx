import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import axios from 'axios';

interface CurrencyInfo {
  code: string;
  symbol: string;
  name: string;
}

interface CurrencyContextType {
  baseCurrency: CurrencyInfo;
  currencySymbol: string;
  currencyCode: string;
  formatCurrency: (amount: number | string) => string;
  formatCompact: (amount: number | string) => string;
  isLoading: boolean;
}

const FALLBACK: CurrencyInfo = { code: 'NGN', symbol: '₦', name: 'Nigerian Naira' };

// Map of supported platform currency codes to their display info.
// This avoids a second API call just to resolve a symbol from a code.
const CURRENCY_MAP: Record<string, CurrencyInfo> = {
  NGN: { code: 'NGN', symbol: '₦', name: 'Nigerian Naira' },
  USD: { code: 'USD', symbol: '$', name: 'US Dollar' },
  EUR: { code: 'EUR', symbol: '€', name: 'Euro' },
  GBP: { code: 'GBP', symbol: '£', name: 'British Pound' },
};

function currencyFromCode(code: string): CurrencyInfo {
  return CURRENCY_MAP[code] || { code, symbol: code, name: code };
}

const CurrencyContext = createContext<CurrencyContextType | undefined>(undefined);

function toNumber(v: number | string): number {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}

function compactNumber(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + 'B';
  if (abs >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (abs >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return n.toFixed(2);
}

const API_ROOT = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1`;

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const isAuthenticated = !!(
    localStorage.getItem('authToken') ?? sessionStorage.getItem('authToken')
  );
  const hasTenant = !!(
    localStorage.getItem('tenantDomain') ?? sessionStorage.getItem('tenantDomain')
  );

  // Check if user is a superadmin (authenticated but no tenant context)
  const userRaw = localStorage.getItem('user') ?? sessionStorage.getItem('user');
  let isSuperAdmin = false;
  try {
    if (userRaw) {
      const parsed = JSON.parse(userRaw);
      isSuperAdmin = parsed?.is_superuser === true;
    }
  } catch { /* ignore parse errors */ }

  // Path 1: Tenant user → fetch from accounting settings
  const { data: tenantCurrencyData, isLoading: tenantLoading } = useQuery({
    queryKey: ['currency-defaults', 'tenant'],
    queryFn: async () => {
      const { data } = await apiClient.get('/accounting/currencies/defaults/');
      return data;
    },
    enabled: isAuthenticated && hasTenant,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  // Path 2: Superadmin user → fetch from superadmin platform settings
  const { data: superadminSettings, isLoading: superadminLoading } = useQuery({
    queryKey: ['currency-defaults', 'superadmin'],
    queryFn: async () => {
      const { data } = await apiClient.get('/superadmin/settings');
      return data;
    },
    enabled: isAuthenticated && !hasTenant && isSuperAdmin,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  // Path 3: Public pages (no auth) → fetch from public platform-info endpoint
  const { data: publicInfo, isLoading: publicLoading } = useQuery({
    queryKey: ['currency-defaults', 'public'],
    queryFn: async () => {
      const { data } = await axios.get(`${API_ROOT}/superadmin/public/platform-info`);
      return data;
    },
    enabled: !isAuthenticated,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const isLoading = tenantLoading || superadminLoading || publicLoading;

  const value = useMemo<CurrencyContextType>(() => {
    let base: CurrencyInfo = FALLBACK;

    if (isAuthenticated && hasTenant) {
      // Tenant path: use accounting settings detail
      const detail = tenantCurrencyData?.default_currency_1_detail;
      if (detail) {
        base = { code: detail.code, symbol: detail.symbol || detail.code, name: detail.name };
      }
    } else if (isAuthenticated && isSuperAdmin && superadminSettings?.default_currency) {
      // Superadmin path: resolve code from platform settings
      base = currencyFromCode(superadminSettings.default_currency);
    } else if (!isAuthenticated && publicInfo?.default_currency) {
      // Public path: resolve code from public platform-info
      base = currencyFromCode(publicInfo.default_currency);
    }

    return {
      baseCurrency: base,
      currencySymbol: base.symbol,
      currencyCode: base.code,
      formatCurrency: (amount) => {
        const n = toNumber(amount);
        return base.symbol + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      },
      formatCompact: (amount) => {
        const n = toNumber(amount);
        return base.symbol + compactNumber(n);
      },
      isLoading,
    };
  }, [tenantCurrencyData, superadminSettings, publicInfo, isAuthenticated, hasTenant, isSuperAdmin, isLoading]);

  return (
    <CurrencyContext.Provider value={value}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency() {
  const context = useContext(CurrencyContext);
  if (!context) {
    throw new Error('useCurrency must be used within a CurrencyProvider');
  }
  return context;
}
