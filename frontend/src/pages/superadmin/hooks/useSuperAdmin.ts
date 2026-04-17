import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { superadminApi } from '../../../api/superadmin';
import apiClient from '../../../api/client';
import type {
  SubscriptionPlan, Tenant, DashboardStats, AuditLog, SystemHealth,
  CrossTenantUser, ImpersonateResponse, Referrer, Referral, Commission, CommissionPayout,
  Announcement,
} from '../../../api/superadmin';

const STALE_TIME = 2 * 60 * 1000;

// ============================================================================
// DASHBOARD STATS
// ============================================================================

export const useDashboardStats = () =>
  useQuery<DashboardStats>({
    queryKey: ['superadmin-stats'],
    queryFn: async () => {
      const { data } = await superadminApi.getStats();
      return data;
    },
    staleTime: STALE_TIME,
  });

// ============================================================================
// TENANTS
// ============================================================================

export const useTenants = () =>
  useQuery<Tenant[]>({
    queryKey: ['superadmin-tenants'],
    queryFn: async () => {
      const { data } = await superadminApi.getTenants();
      return data || [];
    },
    staleTime: STALE_TIME,
  });

export const useCreateTenant = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { organization_name: string }) => {
      const { data } = await superadminApi.createTenant(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-tenants'] });
      qc.invalidateQueries({ queryKey: ['superadmin-stats'] });
    },
  });
};

export const useTenantAction = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ tenantId, action, data }: { tenantId: number; action: string; data?: any }) => {
      if (action === 'change_plan') {
        const res = await superadminApi.changeTenantPlan(tenantId, data.planId);
        return res.data;
      } else if (action === 'extend') {
        const res = await superadminApi.extendTenant(tenantId, data.days);
        return res.data;
      } else if (action === 'suspend') {
        const res = await superadminApi.suspendTenant(tenantId);
        return res.data;
      } else if (action === 'activate') {
        const res = await superadminApi.activateTenant(tenantId);
        return res.data;
      } else if (action === 'update') {
        const res = await superadminApi.updateTenant(tenantId, data);
        return res.data;
      } else if (action === 'reset_password') {
        const res = await superadminApi.resetTenantPassword(tenantId);
        return res.data;
      } else if (action === 'delete') {
        const res = await superadminApi.deleteTenant(tenantId);
        return res.data;
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-tenants'] });
      qc.invalidateQueries({ queryKey: ['superadmin-stats'] });
    },
  });
};

// ============================================================================
// USERS
// ============================================================================

export const useUsers = () =>
  useQuery<CrossTenantUser[]>({
    queryKey: ['superadmin-users'],
    queryFn: async () => {
      const { data } = await superadminApi.getUsers();
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
    staleTime: STALE_TIME,
  });

export const useSaveUser = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id?: number; data: any }) => {
      if (id) {
        const res = await apiClient.patch(`/superadmin/users/${id}`, data);
        return res.data;
      }
      const res = await apiClient.post('/superadmin/users/', data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-users'] });
    },
  });
};

export const useToggleUserStatus = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, isActive }: { userId: number; isActive: boolean; tenantId?: number }) => {
      const { data } = await superadminApi.updateUser(userId, { is_active: isActive });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-users'] });
    },
  });
};

export const useBulkDeleteUsers = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ids: number[]) => {
      const { data } = await apiClient.post('/superadmin/users/bulk-delete', { ids });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-users'] });
    },
  });
};

// ============================================================================
// PLANS
// ============================================================================

export const usePlans = () =>
  useQuery<SubscriptionPlan[]>({
    queryKey: ['superadmin-plans'],
    queryFn: async () => {
      const { data } = await superadminApi.getPlans();
      return data || [];
    },
    staleTime: STALE_TIME,
    refetchOnWindowFocus: false,
  });

export const useCreatePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<SubscriptionPlan>) => {
      const { data } = await superadminApi.createPlan(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-plans'] });
    },
  });
};

export const useUpdatePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<SubscriptionPlan> }) => {
      const res = await superadminApi.updatePlan(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-plans'] });
    },
  });
};

export const useDeletePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await superadminApi.deletePlan(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-plans'] });
    },
  });
};

// ============================================================================
// PAYMENTS
// ============================================================================

export const usePayments = () =>
  useQuery({
    queryKey: ['superadmin-payments'],
    queryFn: async () => {
      const { data } = await superadminApi.getPayments();
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
    staleTime: STALE_TIME,
  });

export const useApprovePayment = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action, notes }: { id: number; action: 'approve' | 'reject'; notes?: string }) => {
      if (action === 'approve') {
        const res = await superadminApi.approvePayment(id, notes);
        return res.data;
      }
      const res = await superadminApi.rejectPayment(id, notes);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-payments'] });
    },
  });
};

// ============================================================================
// GLOBAL MODULES
// ============================================================================

export interface GlobalModule {
  module_name: string;
  module_title: string;
  description: string;
  is_globally_enabled: boolean;
  active_tenants: number;
  total_configured: number;
  total_tenants: number;
}

export const useGlobalModules = () =>
  useQuery<GlobalModule[]>({
    queryKey: ['global-modules'],
    queryFn: async () => {
      const { data } = await superadminApi.getGlobalModules();
      return data || [];
    },
    staleTime: STALE_TIME,
  });

export const useToggleGlobalModule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ moduleName, isEnabled }: { moduleName: string; isEnabled: boolean }) => {
      const { data } = await superadminApi.toggleGlobalModule(moduleName, isEnabled);
      return data;
    },
    onSuccess: () => {
      // Refresh the global overview table
      qc.invalidateQueries({ queryKey: ['global-modules'] });
      // Immediately propagate to the current session's sidebar / route guards
      qc.invalidateQueries({ queryKey: ['tenantModules'] });
    },
  });
};

// ============================================================================
// TENANT MODULES
// ============================================================================

export interface TenantModuleItem {
  id: number | null;
  module_name: string;
  module_title: string;
  description: string;
  is_active: boolean;
  configured: boolean;
}

export const useTenantModules = (tenantId: number | null) =>
  useQuery<TenantModuleItem[]>({
    queryKey: ['tenant-modules', tenantId],
    queryFn: async () => {
      if (!tenantId) return [];
      const { data } = await superadminApi.getTenantModules(tenantId);
      return Array.isArray(data) ? data : (data as any)?.modules || [];
    },
    enabled: !!tenantId,
    staleTime: STALE_TIME,
  });

export const useToggleTenantModule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ tenantId, modules }: { tenantId: number; modules: Record<string, boolean> }) => {
      // Convert {module_name: boolean} map to [{module_name, is_active}] array
      const modulesArray = Object.entries(modules).map(([module_name, is_active]) => ({
        module_name,
        is_active,
      }));
      const { data } = await superadminApi.updateTenantModules(tenantId, modulesArray);
      return data;
    },
    onSuccess: (_data, variables) => {
      // Refresh the per-tenant table in the drawer
      qc.invalidateQueries({ queryKey: ['tenant-modules', variables.tenantId] });
      // Refresh the global overview stats row
      qc.invalidateQueries({ queryKey: ['global-modules'] });
      // Immediately propagate to the current session's sidebar / route guards
      qc.invalidateQueries({ queryKey: ['tenantModules'] });
    },
  });
};

// ============================================================================
// AUDIT LOGS
// ============================================================================

export const useAuditLogs = (params?: { tenant_id?: number; action_type?: string; limit?: number }) =>
  useQuery<AuditLog[]>({
    queryKey: ['superadmin-audit-logs', params],
    queryFn: async () => {
      const { data } = await superadminApi.getAuditLogs({ ...params, page_size: params?.limit || 100 });
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
    staleTime: STALE_TIME,
  });

// ============================================================================
// SYSTEM HEALTH
// ============================================================================

export const useSystemHealth = () =>
  useQuery<SystemHealth>({
    queryKey: ['superadmin-system-health'],
    queryFn: async () => {
      const { data } = await superadminApi.getSystemHealth();
      return data;
    },
    staleTime: 30 * 1000, // 30s — refresh more often
  });

// ============================================================================
// SUPERADMIN SETTINGS
// ============================================================================

export interface SuperAdminSettings {
  organization_name: string;
  default_timezone: string;
  default_currency: string;
  maintenance_mode: boolean;
  session_timeout_minutes: number;
  require_special_chars: boolean;
  require_uppercase: boolean;
  min_password_length: number;
  two_factor_enabled: boolean;
  rate_limit_per_hour: number;
  token_expiry_days: number;
  max_login_attempts: number;
  // SMTP
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_from_email: string;
  smtp_from_name: string;
  support_email: string;
  smtp_enabled: boolean;
}

export const useSuperAdminSettings = () =>
  useQuery<SuperAdminSettings>({
    queryKey: ['superadmin-settings'],
    queryFn: async () => {
      const { data } = await superadminApi.getSettings();
      return data;
    },
    staleTime: STALE_TIME,
  });

export const useSaveSuperAdminSettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<SuperAdminSettings>) => {
      const { data } = await superadminApi.saveSettings(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-settings'] });
    },
  });
};

export const useTestSmtp = () => {
  return useMutation({
    mutationFn: async (toEmail: string) => {
      const { data } = await superadminApi.testSmtp(toEmail);
      return data;
    },
  });
};

// ============================================================================
// IMPERSONATION
// ============================================================================

export const useImpersonateUser = () => {
  return useMutation<ImpersonateResponse, Error, { userId: number; tenantId: number }>({
    mutationFn: async ({ userId, tenantId }) => {
      const { data } = await superadminApi.impersonateUser(userId, tenantId);
      return data;
    },
  });
};

export const useImpersonationLogs = () =>
  useQuery({
    queryKey: ['impersonation-logs'],
    queryFn: async () => {
      const { data } = await superadminApi.getImpersonationLogs();
      return data;
    },
    staleTime: STALE_TIME,
  });

// ============================================================================
// PLAN COMPARISON & TRIALS
// ============================================================================

export const usePlanComparison = () =>
  useQuery({
    queryKey: ['plan-comparison'],
    queryFn: async () => {
      const { data } = await superadminApi.getPlanComparison();
      return data || [];
    },
    staleTime: STALE_TIME,
    refetchOnWindowFocus: false,
  });

export const useExpiringTrials = (days: number = 7) =>
  useQuery({
    queryKey: ['expiring-trials', days],
    queryFn: async () => {
      const { data } = await superadminApi.getExpiringTrials(days);
      return data || [];
    },
    staleTime: STALE_TIME,
    refetchOnWindowFocus: false,
  });

// ============================================================================
// WEBHOOKS
// ============================================================================

export interface WebhookConfigItem {
  id: number;
  tenant_id: number;
  tenant_name: string;
  webhook_name: string;
  webhook_url: string;
  subscribed_events: string[];
  is_active: boolean;
  timeout_seconds: number;
  retry_count: number;
  last_triggered_at: string | null;
  last_status_code: number | null;
  created_at: string;
  created_by_name: string | null;
}

export interface WebhookDeliveryItem {
  id: number;
  event: string;
  status: string;
  status_code: number | null;
  error_message: string;
  duration_ms: number | null;
  attempted_at: string;
  delivered_at: string | null;
  retry_attempt: number;
}

export const useWebhooks = (tenantId?: number) =>
  useQuery<WebhookConfigItem[]>({
    queryKey: ['superadmin-webhooks', tenantId],
    queryFn: async () => {
      const { data } = await superadminApi.getWebhooks(tenantId);
      return Array.isArray(data) ? data : [];
    },
    staleTime: STALE_TIME,
  });

export const useCreateWebhook = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      tenant_id: number;
      webhook_name: string;
      webhook_url: string;
      subscribed_events?: string[];
      timeout_seconds?: number;
      retry_count?: number;
    }) => {
      const { data } = await superadminApi.createWebhook(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-webhooks'] });
    },
  });
};

export const useUpdateWebhook = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<WebhookConfigItem> }) => {
      const res = await superadminApi.updateWebhook(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-webhooks'] });
    },
  });
};

export const useDeleteWebhook = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await superadminApi.deleteWebhook(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-webhooks'] });
    },
  });
};

export const useTestWebhook = () => {
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await superadminApi.testWebhook(id);
      return data;
    },
  });
};

export const useWebhookDeliveries = (webhookId: number | null, page?: number) =>
  useQuery<{ results: WebhookDeliveryItem[]; count?: number; total_pages?: number }>({
    queryKey: ['webhook-deliveries', webhookId, page],
    queryFn: async () => {
      if (!webhookId) return { results: [] };
      const { data } = await superadminApi.getWebhookDeliveries(webhookId, page);
      return data as any;
    },
    enabled: !!webhookId,
    staleTime: 30 * 1000,
  });

// ============================================================================
// API KEYS
// ============================================================================

export interface APIKeyItem {
  id: number;
  tenant_id: number;
  tenant_name: string;
  key_name: string;
  key_type: string;
  api_key: string;
  allowed_ips: string;
  rate_limit: number;
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
  created_by_name: string | null;
}

export const useAPIKeys = (tenantId?: number) =>
  useQuery<APIKeyItem[]>({
    queryKey: ['superadmin-api-keys', tenantId],
    queryFn: async () => {
      const { data } = await superadminApi.getAPIKeys(tenantId);
      return Array.isArray(data) ? data : [];
    },
    staleTime: STALE_TIME,
  });

export const useCreateAPIKey = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      tenant_id: number;
      key_name: string;
      key_type?: string;
      allowed_ips?: string;
      rate_limit?: number;
      expires_at?: string;
    }) => {
      const { data } = await superadminApi.createAPIKey(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-api-keys'] });
    },
  });
};

export const useUpdateAPIKey = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<APIKeyItem> & { regenerate?: boolean } }) => {
      const res = await superadminApi.updateAPIKey(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-api-keys'] });
    },
  });
};

export const useDeleteAPIKey = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await superadminApi.deleteAPIKey(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-api-keys'] });
    },
  });
};

// ============================================================================
// REFERRERS
// ============================================================================

export const useReferrers = (params?: { search?: string; is_active?: string }) =>
  useQuery<Referrer[]>({
    queryKey: ['superadmin-referrers', params],
    queryFn: async () => {
      const { data } = await superadminApi.getReferrers({ page: 1, page_size: 200, ...params });
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
    staleTime: STALE_TIME,
  });

export const useCreateReferrer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<Referrer>) => {
      const { data } = await superadminApi.createReferrer(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-referrers'] });
      qc.invalidateQueries({ queryKey: ['superadmin-stats'] });
    },
  });
};

export const useUpdateReferrer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<Referrer> }) => {
      const res = await superadminApi.updateReferrer(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-referrers'] });
    },
  });
};

export const useDeleteReferrer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await superadminApi.deleteReferrer(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-referrers'] });
      qc.invalidateQueries({ queryKey: ['superadmin-stats'] });
    },
  });
};

// ============================================================================
// REFERRALS
// ============================================================================

export const useReferrals = (params?: { referrer_id?: number; status?: string }) =>
  useQuery<Referral[]>({
    queryKey: ['superadmin-referrals', params],
    queryFn: async () => {
      const { data } = await superadminApi.getReferrals({ page: 1, page_size: 200, ...params });
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
    staleTime: STALE_TIME,
  });

export const useCreateReferral = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { referrer_id: number; tenant_id: number; source?: string }) => {
      const { data } = await superadminApi.createReferral(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-referrals'] });
      qc.invalidateQueries({ queryKey: ['superadmin-referrers'] });
    },
  });
};

// ============================================================================
// COMMISSIONS
// ============================================================================

export const useCommissions = (params?: { referrer_id?: number; status?: string }) =>
  useQuery<Commission[]>({
    queryKey: ['superadmin-commissions', params],
    queryFn: async () => {
      const { data } = await superadminApi.getCommissions({ page: 1, page_size: 200, ...params });
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
    staleTime: STALE_TIME,
  });

export const useUpdateCommission = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: { action?: string; status?: string; notes?: string } }) => {
      const res = await superadminApi.updateCommission(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-commissions'] });
      qc.invalidateQueries({ queryKey: ['superadmin-referrers'] });
    },
  });
};

// ============================================================================
// COMMISSION PAYOUTS
// ============================================================================

export const usePayouts = (params?: { referrer_id?: number; status?: string }) =>
  useQuery<CommissionPayout[]>({
    queryKey: ['superadmin-payouts', params],
    queryFn: async () => {
      const { data } = await superadminApi.getPayouts({ page: 1, page_size: 200, ...params });
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
    staleTime: STALE_TIME,
  });

export const useCreatePayout = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { referrer_id: number; period_start: string; period_end: string; notes?: string }) => {
      const { data } = await superadminApi.createPayout(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-payouts'] });
      qc.invalidateQueries({ queryKey: ['superadmin-commissions'] });
    },
  });
};

export const useUpdatePayout = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: { action: string; payout_reference?: string; payment_method?: string; notes?: string } }) => {
      const res = await superadminApi.updatePayout(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-payouts'] });
      qc.invalidateQueries({ queryKey: ['superadmin-commissions'] });
      qc.invalidateQueries({ queryKey: ['superadmin-referrers'] });
    },
  });
};

// ============================================================================
// ANNOUNCEMENTS
// ============================================================================

export const useAnnouncements = () =>
  useQuery<Announcement[]>({
    queryKey: ['superadmin-announcements'],
    queryFn: async () => {
      const { data } = await superadminApi.getAnnouncements();
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
    staleTime: STALE_TIME,
  });

export const useCreateAnnouncement = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<Announcement>) => {
      const { data } = await superadminApi.createAnnouncement(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-announcements'] });
    },
  });
};

export const useUpdateAnnouncement = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<Announcement> }) => {
      const res = await superadminApi.updateAnnouncement(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-announcements'] });
    },
  });
};

export const useDeleteAnnouncement = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await superadminApi.deleteAnnouncement(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-announcements'] });
    },
  });
};

export const usePublishAnnouncement = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await superadminApi.publishAnnouncement(id);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-announcements'] });
    },
  });
};

// ============================================================================
// BILLING & INVOICES  (Issues #14 / #15 — replaces raw useQuery in BillingTab)
// ============================================================================

import type { Invoice, TenantUsage, BillingAnalytics } from '../../../api/superadmin';

export interface PaginatedResult<T> {
  results: T[];
  count?: number;
  total_pages?: number;
}

export const useInvoices = (params?: {
  tenant_id?: number;
  status?: string;
  page?: number;
  page_size?: number;
}) =>
  useQuery<PaginatedResult<Invoice>>({
    queryKey: ['superadmin-invoices', params],
    queryFn: async () => {
      const { data } = await superadminApi.getInvoices(params);
      // data is PaginatedResponse<Invoice> — normalise to a consistent shape
      if (Array.isArray(data)) return { results: data };
      return data as PaginatedResult<Invoice>;
    },
    staleTime: STALE_TIME,
  });

export const useCreateInvoice = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<Invoice>) => {
      const { data } = await superadminApi.createInvoice(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-invoices'] });
    },
  });
};

export const useUpdateInvoice = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<Invoice> }) => {
      const res = await superadminApi.updateInvoice(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-invoices'] });
    },
  });
};

export const useTenantUsageRecords = (params?: {
  tenant_id?: number;
  is_billed?: string;
  page?: number;
}) =>
  useQuery<PaginatedResult<TenantUsage>>({
    queryKey: ['superadmin-usage', params],
    queryFn: async () => {
      const { data } = await superadminApi.getTenantUsage(params);
      if (Array.isArray(data)) return { results: data };
      return data as PaginatedResult<TenantUsage>;
    },
    staleTime: STALE_TIME,
  });

export const useBillingAnalytics = () =>
  useQuery<BillingAnalytics>({
    queryKey: ['superadmin-billing-analytics'],
    queryFn: async () => {
      const { data } = await superadminApi.getBillingAnalytics();
      return data;
    },
    staleTime: STALE_TIME,
  });

// ============================================================================
// MODULE PRICING (per-module SaaS pricing)
// ============================================================================

export interface ModulePricingRecord {
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
  is_active: boolean;
  is_popular: boolean;
  sort_order: number;
}

export const useModulePricingAdmin = () =>
  useQuery<ModulePricingRecord[]>({
    queryKey: ['superadmin-module-pricing'],
    queryFn: async () => {
      const { data } = await superadminApi.getModulePricing();
      return Array.isArray(data) ? data : [];
    },
    staleTime: STALE_TIME,
  });

export const useCreateModulePricing = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<ModulePricingRecord>) => {
      const { data } = await superadminApi.createModulePricing(payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-module-pricing'] });
    },
  });
};

export const useUpdateModulePricing = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<ModulePricingRecord> }) => {
      const res = await superadminApi.updateModulePricing(id, data);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-module-pricing'] });
    },
  });
};

export const useDeleteModulePricing = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await superadminApi.deleteModulePricing(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin-module-pricing'] });
    },
  });
};
