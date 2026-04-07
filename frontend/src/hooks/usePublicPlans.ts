import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const API_ROOT = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/superadmin`;

export interface PublicPlan {
  id: number;
  name: string;
  plan_type: string;
  description: string;
  price: string;
  billing_cycle: string;
  max_users: number;
  max_storage_gb: number;
  allowed_modules: string[];
  module_names: string[];
  features: { category: string; name: string; included: boolean; limit?: string }[];
  is_featured: boolean;
  trial_days: number;
}

const publicClient = axios.create();

export const usePublicPlans = () =>
  useQuery<PublicPlan[]>({
    queryKey: ['public-subscription-plans'],
    queryFn: async () => {
      const { data } = await publicClient.get(`${API_ROOT}/public/plans`);
      return Array.isArray(data) ? data : [];
    },
    staleTime: 5 * 60 * 1000,
  });
