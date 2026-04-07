/**
 * usePricingCurrency — auto-detects visitor's currency via IP geolocation
 * and provides conversion utilities for public pricing pages.
 *
 * Flow:
 * 1. Fetch all active platform currencies with exchange rates
 * 2. Call detect-currency endpoint (server does IP → country → currency lookup)
 * 3. Provide convertPrice() and a currency switcher
 */
import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const API_ROOT = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/superadmin`;

export interface PlatformCurrency {
  currency_code: string;
  currency_name: string;
  symbol: string;
  symbol_position: 'prefix' | 'suffix';
  exchange_rate_to_base: string;
  decimal_places: number;
  is_default: boolean;
  country_codes: string[];
  flag_emoji: string;
}

interface DetectedCurrency {
  detected_country: string | null;
  currency_code: string;
  currency_name: string;
  symbol: string;
  symbol_position: string;
  exchange_rate_to_base: string;
  flag_emoji: string;
}

interface PricingCurrencyResult {
  /** All active platform currencies for the currency switcher */
  currencies: PlatformCurrency[];
  /** Currently selected currency code */
  selectedCode: string;
  /** Currently selected currency info */
  selectedCurrency: PlatformCurrency | null;
  /** Switch to a different currency */
  setCurrency: (code: string) => void;
  /** Convert a price (assumed in base/USD) to selected currency */
  convertPrice: (usdAmount: number | string) => number;
  /** Format a price in the selected currency */
  formatPrice: (usdAmount: number | string) => string;
  /** Currency symbol */
  symbol: string;
  /** Flag emoji for display */
  flagEmoji: string;
  /** Whether detection is still loading */
  isLoading: boolean;
  /** Detected country code (e.g. "NG") */
  detectedCountry: string | null;
}

const publicClient = axios.create();

export function usePricingCurrency(): PricingCurrencyResult {
  const [manualCode, setManualCode] = useState<string | null>(null);

  // Fetch all active currencies
  const { data: currencyData, isLoading: currenciesLoading } = useQuery({
    queryKey: ['public-platform-currencies'],
    queryFn: async () => {
      const { data } = await publicClient.get(`${API_ROOT}/public/currencies`);
      return data as { base_currency: string; currencies: PlatformCurrency[] };
    },
    staleTime: 10 * 60 * 1000,
  });

  // Detect currency from IP
  const { data: detected, isLoading: detectLoading } = useQuery<DetectedCurrency>({
    queryKey: ['public-detect-currency'],
    queryFn: async () => {
      const { data } = await publicClient.get(`${API_ROOT}/public/detect-currency`);
      return data;
    },
    staleTime: 30 * 60 * 1000, // IP doesn't change often
    retry: false,
  });

  const currencies = currencyData?.currencies || [];

  // Determine which currency is active
  const selectedCode = manualCode
    || detected?.currency_code
    || currencyData?.base_currency
    || 'USD';

  const selectedCurrency = useMemo(
    () => currencies.find((c) => c.currency_code === selectedCode) || null,
    [currencies, selectedCode],
  );

  const rate = selectedCurrency
    ? Number(selectedCurrency.exchange_rate_to_base)
    : 1;

  const convertPrice = useCallback(
    (usdAmount: number | string): number => {
      const n = typeof usdAmount === 'string' ? parseFloat(usdAmount) : usdAmount;
      if (isNaN(n)) return 0;
      return n * rate;
    },
    [rate],
  );

  const decimals = selectedCurrency?.decimal_places ?? 2;

  const formatPrice = useCallback(
    (usdAmount: number | string): string => {
      const converted = convertPrice(usdAmount);
      const sym = selectedCurrency?.symbol || '$';
      const pos = selectedCurrency?.symbol_position || 'prefix';
      const formatted = converted.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });
      return pos === 'suffix' ? `${formatted} ${sym}` : `${sym}${formatted}`;
    },
    [convertPrice, selectedCurrency, decimals],
  );

  return {
    currencies,
    selectedCode,
    selectedCurrency,
    setCurrency: setManualCode,
    convertPrice,
    formatPrice,
    symbol: selectedCurrency?.symbol || '$',
    flagEmoji: selectedCurrency?.flag_emoji || detected?.flag_emoji || '',
    isLoading: currenciesLoading || detectLoading,
    detectedCountry: detected?.detected_country || null,
  };
}
