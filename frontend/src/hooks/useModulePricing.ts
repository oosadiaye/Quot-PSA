import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const API_ROOT = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/superadmin`;

export interface ModulePricingItem {
  id: number;
  module_name: string;
  title: string;
  tagline: string;
  description: string;
  icon: string;
  price_monthly: string;
  price_yearly: string;
  features: string[];
  highlights: string[];
  is_popular: boolean;
  sort_order: number;
}

const publicClient = axios.create();

export const useModulePricing = () =>
  useQuery<ModulePricingItem[]>({
    queryKey: ['public-module-pricing'],
    queryFn: async () => {
      const { data } = await publicClient.get(`${API_ROOT}/public/modules`);
      return Array.isArray(data) ? data : [];
    },
    staleTime: 5 * 60 * 1000,
  });

export const useModulePricingDetail = (moduleName: string) =>
  useQuery<ModulePricingItem>({
    queryKey: ['public-module-pricing', moduleName],
    queryFn: async () => {
      const { data } = await publicClient.get(`${API_ROOT}/public/modules/${moduleName}`);
      return data;
    },
    enabled: !!moduleName,
    staleTime: 5 * 60 * 1000,
  });
