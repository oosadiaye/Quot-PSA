import apiClient from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PlanFeature {
  category: string;
  name: string;
  included: boolean;
  limit?: string;
}

export interface SubscriptionPlan {
  id: number;
  name: string;
  plan_type: string;
  description: string;
  price: string;
  billing_cycle: string;
  max_users: number;
  max_storage_gb: number;
  allowed_modules: string[];
  features: PlanFeature[];
  is_featured: boolean;
  trial_days: number;
  tenant_count?: number;
  active_tenants?: number;
  trial_tenants?: number;
}

export interface Tenant {
  id: number;
  name: string;
  schema_name: string;
  created_on: string;
  status: string;
  plan?: string;
  end_date?: string;
  domains?: string[];
}

export interface DashboardStats {
  total_tenants: number;
  active_subscriptions: number;
  trial_subscriptions: number;
  suspended: number;
  expired_subscriptions: number;
  cancelled_subscriptions: number;
  total_revenue: string;
  recent_signups: { name: string; created_on: string }[];
}

export interface TenantModule {
  id: number | null;
  module_name: string;
  module_title: string;
  description: string;
  is_active: boolean;
  configured: boolean;
}

export interface SystemHealth {
  database: string;
  disk_usage: number;
  memory_usage: number;
  active_connections: number;
  tenants: { total: number; active: number; trial: number; suspended: number };
  timestamp: string;
}

export interface AuditLog {
  id: number;
  timestamp: string;
  user_id: number;
  username?: string;
  action_type: string;
  module: string;
  object_repr: string;
  changes: any;
  ip_address: string;
  tenant_id: number | null;
  tenant_name: string;
}

export interface CrossTenantUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  date_joined: string;
  last_login: string | null;
  tenant_id: number;
  tenant_name: string;
  tenants?: { tenant_id: number; tenant_name: string; role: string; is_active: boolean }[];
}

export interface PaginatedResponse<T> {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  results: T[];
}

export interface ImpersonateResponse {
  token: string;
  tenant_domain: string;
  user?: { id: number; username: string; email: string };
  tenant_name: string;
  session_id: number;
}

export interface ImpersonationLog {
  id: number;
  superadmin: string;
  target_user: string;
  target_tenant: string;
  started_at: string;
  ended_at: string | null;
  ip_address: string;
  is_active: boolean;
}

export interface ExpiringTrial {
  tenant_id: number;
  tenant_name: string;
  plan: string | null;
  end_date: string;
  days_remaining: number;
}

// Phase 1: Referrer & Commission
export interface Referrer {
  id: number;
  referrer_code: string;
  referrer_type: string;
  company_name: string;
  contact_name: string;
  email: string;
  phone: string;
  address: string;
  commission_rate: string;
  commission_type: string;
  bank_name: string;
  bank_account: string;
  payment_schedule: string;
  is_active: boolean;
  created_at: string;
  total_referrals?: number;
  total_commission?: string;
  pending_commission?: string;
}

export interface Referral {
  id: number;
  referrer_id: number;
  referrer_name: string;
  referrer_code: string;
  tenant_id: number;
  tenant_name: string;
  status: string;
  source: string;
  utm_campaign: string;
  utm_medium: string;
  referred_at: string;
  converted_at: string | null;
}

export interface Commission {
  id: number;
  referrer_id: number;
  referrer_name: string;
  tenant_id: number;
  tenant_name: string;
  referral_id: number;
  sale_amount: string;
  sale_date: string;
  commission_rate: string;
  commission_type: string;
  commission_amount: string;
  status: string;
  payment_date: string | null;
  invoice_number: string;
  notes: string;
  created_at: string;
}

export interface CommissionPayout {
  id: number;
  referrer_id: number;
  referrer_name: string;
  period_start: string;
  period_end: string;
  total_commissions: string;
  commissions_count: number;
  status: string;
  payout_date: string | null;
  payout_reference: string;
  payment_method: string;
  notes: string;
  created_at: string;
}

// Phase 2: Support
export interface SupportTicket {
  id: number;
  ticket_number: string;
  subject: string;
  description: string;
  category: string;
  priority: string;
  status: string;
  requester_name: string;
  requester_email: string;
  requester_tenant_id: number | null;
  requester_tenant_name: string | null;
  assigned_to_id: number | null;
  assigned_to_name: string | null;
  resolution: string;
  resolved_at: string | null;
  resolved_by_name: string | null;
  created_at: string;
  updated_at: string;
  comments?: TicketComment[];
  attachments?: TicketAttachment[];
}

export interface TicketComment {
  id: number;
  author_id: number;
  author_name: string;
  content: string;
  is_internal: boolean;
  created_at: string;
}

export interface TicketAttachment {
  id: number;
  file_name: string;
  file_size: number;
  uploaded_by: string;
  uploaded_at: string;
  file_url: string | null;
}

// Phase 3: Language & Currency
export interface LanguageConfig {
  id: number;
  language_code: string;
  language_name: string;
  native_name: string;
  flag_emoji: string;
  is_active: boolean;
  is_default: boolean;
  is_rtl: boolean;
  date_format: string;
  time_format: string;
  sort_order: number;
}

export interface CurrencyConfig {
  id: number;
  currency_code: string;
  currency_name: string;
  symbol: string;
  is_active: boolean;
  is_default: boolean;
  decimal_places: number;
  decimal_separator: string;
  thousand_separator: string;
  symbol_position: string;
  exchange_rate_to_base: string;
  last_updated: string | null;
  auto_update: boolean;
  country_codes: string[];
  flag_emoji: string;
}

export interface TenantLanguageSetting {
  id: number;
  tenant_id: number;
  tenant_name: string;
  language_id: number;
  language_name: string;
  language_code: string;
  allow_user_override: boolean;
}

export interface TenantCurrencySetting {
  id: number;
  tenant_id: number;
  tenant_name: string;
  currency_id: number;
  currency_code: string;
  currency_name: string;
  allow_user_override: boolean;
}

// Phase 4: SMTP
export interface TenantSMTPConfig {
  id: number;
  tenant_id: number;
  tenant_name: string;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_from_email: string;
  smtp_from_name: string;
  reply_to_email: string;
  is_active: boolean;
  is_verified: boolean;
  verified_at: string | null;
  test_sent_at: string | null;
  test_status: string;
  created_at: string;
}

// Phase 5: API Keys & Webhooks
export interface APIKey {
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

export interface WebhookConfig {
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

export interface WebhookDelivery {
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

// Phase 6: Announcements
export interface Announcement {
  id: number;
  title: string;
  content: string;
  content_html: string;
  priority: string;
  target: string;
  target_plan_ids: number[];
  target_tenant_ids: number[];
  show_on_login: boolean;
  show_on_dashboard: boolean;
  starts_at: string;
  ends_at: string | null;
  is_published: boolean;
  created_by_name: string | null;
  created_at: string;
}

export interface TenantNotification {
  id: number;
  tenant_id: number;
  tenant_name: string;
  announcement_id: number | null;
  notification_type: string;
  title: string;
  message: string;
  is_read: boolean;
  read_at: string | null;
  action_url: string;
  created_at: string;
}

// Phase 7: Usage & Billing
export interface TenantUsage {
  id: number;
  tenant_id: number;
  tenant_name: string;
  billing_period_start: string;
  billing_period_end: string;
  users_count: number;
  storage_mb: number;
  api_calls: number;
  transactions_count: number;
  overage_users: number;
  overage_storage_mb: number;
  overage_api_calls: number;
  base_cost: string;
  overage_cost: string;
  total_cost: string;
  is_billed: boolean;
  created_at: string;
}

export interface Invoice {
  id: number;
  invoice_number: string;
  tenant_id: number;
  tenant_name: string;
  period_start: string;
  period_end: string;
  subscription_amount: string;
  usage_amount: string;
  tax_amount: string;
  discount_amount: string;
  total_amount: string;
  status: string;
  paid_at: string | null;
  payment_method: string;
  payment_reference: string;
  issue_date: string;
  due_date: string;
  notes: string;
  created_at: string;
}

export interface BillingAnalytics {
  monthly_revenue: { month: string; total: string; count: number }[];
  summary: {
    total_invoiced: string;
    total_paid: string;
    total_pending: string;
    total_overdue: string;
    total_commissions_paid: string;
    pending_commissions: string;
  };
}

export interface SaaSStats {
  referrers: { total: number; active: number };
  referrals: { total: number; active: number; pending: number };
  commissions: { total_paid: string; total_pending: string };
  support: { open: number; in_progress: number; resolved: number };
  announcements: { total: number; published: number };
  invoices: { total: number; paid: number; pending: number; overdue: number };
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const superadminApi = {
  // Dashboard
  getStats: () => apiClient.get<DashboardStats>('/superadmin/dashboard/stats'),

  // System Health
  getSystemHealth: () => apiClient.get<SystemHealth>('/superadmin/system/health'),

  // Subscription Plans
  getPlans: () => apiClient.get<SubscriptionPlan[]>('/superadmin/plans'),
  getPlanComparison: () => apiClient.get<SubscriptionPlan[]>('/superadmin/plans/comparison'),
  createPlan: (data: Partial<SubscriptionPlan>) => apiClient.post('/superadmin/plans', data),
  updatePlan: (id: number, data: Partial<SubscriptionPlan>) => apiClient.put(`/superadmin/plans/${id}`, data),
  deletePlan: (id: number) => apiClient.delete(`/superadmin/plans/${id}`),

  // Trials
  getExpiringTrials: (days?: number) =>
    apiClient.get<ExpiringTrial[]>('/superadmin/trials/expiring', { params: { days: days || 7 } }),

  // Tenants
  getTenants: () => apiClient.get<Tenant[]>('/superadmin/tenants'),
  getTenant: (id: number) => apiClient.get(`/superadmin/tenants/${id}`),
  createTenant: (data: { organization_name: string }) => apiClient.post('/superadmin/tenants', data),
  updateTenant: (id: number, data: { name: string }) => apiClient.put(`/superadmin/tenants/${id}`, data),
  deleteTenant: (id: number) => apiClient.delete(`/superadmin/tenants/${id}`),
  changeTenantPlan: (tenantId: number, planId: number) =>
    apiClient.post(`/superadmin/tenants/${tenantId}/change-plan`, { plan_id: planId }),
  suspendTenant: (id: number) => apiClient.post(`/superadmin/tenants/${id}`, { action: 'suspend' }),
  activateTenant: (id: number) => apiClient.post(`/superadmin/tenants/${id}`, { action: 'activate' }),
  extendTenant: (id: number, days: number) =>
    apiClient.post(`/superadmin/tenants/${id}`, { action: 'extend', days }),
  resetTenantPassword: (id: number) =>
    apiClient.post(`/superadmin/tenants/${id}`, { action: 'reset_password' }),

  // Tenant Modules
  getTenantModules: (tenantId: number) =>
    apiClient.get<TenantModule[]>(`/superadmin/tenants/${tenantId}/modules`),
  updateTenantModules: (tenantId: number, modules: { module_name: string; is_active: boolean }[]) =>
    apiClient.post(`/superadmin/tenants/${tenantId}/modules`, { modules }),

  // Payments
  getPayments: (page?: number, pageSize?: number) =>
    apiClient.get<PaginatedResponse<any>>('/superadmin/payments', { params: { page, page_size: pageSize } }),
  approvePayment: (id: number, notes?: string) =>
    apiClient.post(`/superadmin/payments/${id}/approve`, { action: 'approve', notes }),
  rejectPayment: (id: number, notes?: string) =>
    apiClient.post(`/superadmin/payments/${id}/approve`, { action: 'reject', notes }),

  // Public tenant signup
  tenantSignup: (data: { organization_name: string; admin_email: string; admin_username: string; plan_type?: string }) =>
    apiClient.post('/superadmin/tenant/signup', data),

  // Global Module Management
  getGlobalModules: () => apiClient.get('/superadmin/modules/global'),
  toggleGlobalModule: (moduleName: string, isEnabled: boolean) =>
    apiClient.post('/superadmin/modules/global', { module_name: moduleName, is_enabled: isEnabled }),

  // User Management
  getUsers: (page?: number, pageSize?: number, search?: string) =>
    apiClient.get<PaginatedResponse<CrossTenantUser>>('/superadmin/users', {
      params: { page, page_size: pageSize, search },
    }),
  updateUser: (userId: number, data: { is_active?: boolean }) =>
    apiClient.patch(`/superadmin/users/${userId}`, data),

  // Audit Logs
  getAuditLogs: (params?: { tenant_id?: number; action_type?: string; start_date?: string; end_date?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<AuditLog>>('/superadmin/audit-logs', { params }),

  // Settings
  getSettings: () => apiClient.get('/superadmin/settings'),
  saveSettings: (data: any) => apiClient.put('/superadmin/settings', data),
  testSmtp: (toEmail: string) => apiClient.post('/superadmin/settings/test-smtp', { to_email: toEmail }),

  // Impersonation
  impersonateUser: (userId: number, tenantId: number) =>
    apiClient.post<ImpersonateResponse>('/superadmin/impersonate', { user_id: userId, tenant_id: tenantId }),
  stopImpersonation: (sessionId: number) =>
    apiClient.post<{ status: string }>('/superadmin/impersonate/stop', { session_id: sessionId }),
  getImpersonationLogs: (page?: number) =>
    apiClient.get<PaginatedResponse<ImpersonationLog>>('/superadmin/impersonate/logs', { params: { page } }),

  // ---- Phase 1: Referrer & Commission ----
  getReferrers: (params?: { page?: number; page_size?: number; search?: string; is_active?: string }) =>
    apiClient.get<PaginatedResponse<Referrer>>('/superadmin/referrers', { params }),
  getReferrer: (id: number) => apiClient.get<Referrer>(`/superadmin/referrers/${id}`),
  createReferrer: (data: Partial<Referrer>) => apiClient.post('/superadmin/referrers', data),
  updateReferrer: (id: number, data: Partial<Referrer>) => apiClient.put(`/superadmin/referrers/${id}`, data),
  deleteReferrer: (id: number) => apiClient.delete(`/superadmin/referrers/${id}`),

  getReferrals: (params?: { page?: number; page_size?: number; referrer_id?: number; status?: string }) =>
    apiClient.get<PaginatedResponse<Referral>>('/superadmin/referrals', { params }),
  createReferral: (data: { referrer_id: number; tenant_id: number; source?: string }) =>
    apiClient.post('/superadmin/referrals', data),

  getCommissions: (params?: { page?: number; page_size?: number; referrer_id?: number; status?: string }) =>
    apiClient.get<PaginatedResponse<Commission>>('/superadmin/commissions', { params }),
  createCommission: (data: Partial<Commission>) => apiClient.post('/superadmin/commissions', data),
  getCommission: (id: number) => apiClient.get<Commission>(`/superadmin/commissions/${id}`),
  updateCommission: (id: number, data: { action?: string; status?: string; notes?: string }) =>
    apiClient.put(`/superadmin/commissions/${id}`, data),

  getPayouts: (params?: { page?: number; page_size?: number; referrer_id?: number; status?: string }) =>
    apiClient.get<PaginatedResponse<CommissionPayout>>('/superadmin/commission-payouts', { params }),
  createPayout: (data: { referrer_id: number; period_start: string; period_end: string; notes?: string }) =>
    apiClient.post('/superadmin/commission-payouts', data),
  updatePayout: (id: number, data: { action: string; payout_reference?: string; payment_method?: string; notes?: string }) =>
    apiClient.put(`/superadmin/commission-payouts/${id}`, data),

  // ---- Phase 2: Support Tickets ----
  getSupportTickets: (params?: { page?: number; page_size?: number; status?: string; priority?: string; category?: string; search?: string }) =>
    apiClient.get<PaginatedResponse<SupportTicket>>('/superadmin/support-tickets', { params }),
  getSupportTicket: (id: number) => apiClient.get<SupportTicket>(`/superadmin/support-tickets/${id}`),
  createSupportTicket: (data: Partial<SupportTicket>) => apiClient.post('/superadmin/support-tickets', data),
  updateSupportTicket: (id: number, data: Partial<SupportTicket>) =>
    apiClient.put(`/superadmin/support-tickets/${id}`, data),
  deleteSupportTicket: (id: number) => apiClient.delete(`/superadmin/support-tickets/${id}`),
  addTicketComment: (ticketId: number, data: { content: string; is_internal?: boolean }) =>
    apiClient.post(`/superadmin/support-tickets/${ticketId}/comments`, data),
  uploadTicketAttachment: (ticketId: number, formData: FormData) =>
    apiClient.post(`/superadmin/support-tickets/${ticketId}/attachments`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  assignTicket: (ticketId: number, assignedToId: number | null) =>
    apiClient.post(`/superadmin/support-tickets/${ticketId}/assign`, { assigned_to_id: assignedToId }),

  // ---- Phase 3: Language & Currency ----
  getLanguages: () => apiClient.get<LanguageConfig[]>('/superadmin/languages'),
  getLanguage: (id: number) => apiClient.get<LanguageConfig>(`/superadmin/languages/${id}`),
  createLanguage: (data: Partial<LanguageConfig>) => apiClient.post('/superadmin/languages', data),
  updateLanguage: (id: number, data: Partial<LanguageConfig>) => apiClient.put(`/superadmin/languages/${id}`, data),
  deleteLanguage: (id: number) => apiClient.delete(`/superadmin/languages/${id}`),

  getCurrencies: () => apiClient.get<CurrencyConfig[]>('/superadmin/currencies'),
  getCurrency: (id: number) => apiClient.get<CurrencyConfig>(`/superadmin/currencies/${id}`),
  createCurrency: (data: Partial<CurrencyConfig>) => apiClient.post('/superadmin/currencies', data),
  updateCurrency: (id: number, data: Partial<CurrencyConfig>) => apiClient.put(`/superadmin/currencies/${id}`, data),
  deleteCurrency: (id: number) => apiClient.delete(`/superadmin/currencies/${id}`),

  getTenantLanguages: () => apiClient.get<TenantLanguageSetting[]>('/superadmin/tenant-languages'),
  setTenantLanguage: (data: { tenant_id: number; language_id: number; allow_user_override?: boolean }) =>
    apiClient.post('/superadmin/tenant-languages', data),

  getTenantCurrencies: () => apiClient.get<TenantCurrencySetting[]>('/superadmin/tenant-currencies'),
  setTenantCurrency: (data: { tenant_id: number; currency_id: number; allow_user_override?: boolean }) =>
    apiClient.post('/superadmin/tenant-currencies', data),

  // ---- Phase 4: Tenant SMTP ----
  getTenantSMTP: () => apiClient.get<TenantSMTPConfig[]>('/superadmin/tenant-smtp'),
  getTenantSMTPDetail: (id: number) => apiClient.get<TenantSMTPConfig>(`/superadmin/tenant-smtp/${id}`),
  createTenantSMTP: (data: Partial<TenantSMTPConfig>) => apiClient.post('/superadmin/tenant-smtp', data),
  updateTenantSMTP: (id: number, data: Partial<TenantSMTPConfig>) => apiClient.put(`/superadmin/tenant-smtp/${id}`, data),
  deleteTenantSMTP: (id: number) => apiClient.delete(`/superadmin/tenant-smtp/${id}`),
  testTenantSMTP: (id: number) => apiClient.post(`/superadmin/tenant-smtp/${id}/test`),

  // ---- Phase 5: API Keys & Webhooks ----
  getAPIKeys: (tenantId?: number) =>
    apiClient.get<APIKey[]>('/superadmin/api-keys', { params: tenantId ? { tenant_id: tenantId } : {} }),
  getAPIKey: (id: number) => apiClient.get<APIKey>(`/superadmin/api-keys/${id}`),
  createAPIKey: (data: { tenant_id: number; key_name: string; key_type?: string; allowed_ips?: string; rate_limit?: number; expires_at?: string }) =>
    apiClient.post<{ id: number; api_key: string; api_secret: string }>('/superadmin/api-keys', data),
  updateAPIKey: (id: number, data: Partial<APIKey> & { regenerate?: boolean }) =>
    apiClient.put(`/superadmin/api-keys/${id}`, data),
  deleteAPIKey: (id: number) => apiClient.delete(`/superadmin/api-keys/${id}`),

  getWebhooks: (tenantId?: number) =>
    apiClient.get<WebhookConfig[]>('/superadmin/webhooks', { params: tenantId ? { tenant_id: tenantId } : {} }),
  getWebhook: (id: number) => apiClient.get<WebhookConfig>(`/superadmin/webhooks/${id}`),
  createWebhook: (data: { tenant_id: number; webhook_name: string; webhook_url: string; subscribed_events?: string[]; timeout_seconds?: number; retry_count?: number }) =>
    apiClient.post<{ id: number; secret_key: string }>('/superadmin/webhooks', data),
  updateWebhook: (id: number, data: Partial<WebhookConfig>) => apiClient.put(`/superadmin/webhooks/${id}`, data),
  deleteWebhook: (id: number) => apiClient.delete(`/superadmin/webhooks/${id}`),
  testWebhook: (id: number) => apiClient.post(`/superadmin/webhooks/${id}/test`),
  getWebhookDeliveries: (webhookId: number, page?: number) =>
    apiClient.get<PaginatedResponse<WebhookDelivery>>(`/superadmin/webhooks/${webhookId}/deliveries`, { params: { page } }),

  // ---- Phase 6: Announcements & Notifications ----
  getAnnouncements: (params?: { is_published?: string }) =>
    apiClient.get<Announcement[]>('/superadmin/announcements', { params }),
  getAnnouncement: (id: number) => apiClient.get<Announcement>(`/superadmin/announcements/${id}`),
  createAnnouncement: (data: Partial<Announcement>) => apiClient.post('/superadmin/announcements', data),
  updateAnnouncement: (id: number, data: Partial<Announcement>) => apiClient.put(`/superadmin/announcements/${id}`, data),
  deleteAnnouncement: (id: number) => apiClient.delete(`/superadmin/announcements/${id}`),
  publishAnnouncement: (id: number) => apiClient.post(`/superadmin/announcements/${id}/publish`),

  getNotifications: (params?: { tenant_id?: number; is_read?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<TenantNotification>>('/superadmin/notifications', { params }),

  // ---- Phase 7: Usage & Billing ----
  getTenantUsage: (params?: { tenant_id?: number; is_billed?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<TenantUsage>>('/superadmin/usage', { params }),
  createTenantUsage: (data: { tenant_id: number; billing_period_start: string; billing_period_end: string; [key: string]: any }) =>
    apiClient.post('/superadmin/usage', data),

  getInvoices: (params?: { tenant_id?: number; status?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<Invoice>>('/superadmin/invoices', { params }),
  getInvoice: (id: number) => apiClient.get<Invoice>(`/superadmin/invoices/${id}`),
  createInvoice: (data: Partial<Invoice>) => apiClient.post('/superadmin/invoices', data),
  updateInvoice: (id: number, data: Partial<Invoice>) => apiClient.put(`/superadmin/invoices/${id}`, data),
  deleteInvoice: (id: number) => apiClient.delete(`/superadmin/invoices/${id}`),

  getBillingAnalytics: () => apiClient.get<BillingAnalytics>('/superadmin/billing/analytics'),

  // SaaS Dashboard Stats
  getSaaSStats: () => apiClient.get<SaaSStats>('/superadmin/saas-stats'),

  // ---- Module Pricing (per-module SaaS pricing) ----
  getModulePricing: () => apiClient.get('/superadmin/module-pricing'),
  createModulePricing: (data: any) => apiClient.post('/superadmin/module-pricing', data),
  updateModulePricing: (id: number, data: any) => apiClient.put(`/superadmin/module-pricing/${id}`, data),
  deleteModulePricing: (id: number) => apiClient.delete(`/superadmin/module-pricing/${id}`),
};
