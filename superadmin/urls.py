from django.urls import path
from . import views

urlpatterns = [
    # Public tenant signup
    path('tenant/signup', views.tenant_signup, name='tenant_signup'),

    # Dashboard
    path('dashboard/stats', views.dashboard_stats, name='dashboard_stats'),

    # Subscription Plans
    path('plans', views.subscription_plans, name='subscription_plans'),
    path('plans/comparison', views.plan_comparison, name='plan_comparison'),
    path('plans/<int:plan_id>', views.subscription_plan_detail, name='subscription_plan_detail'),

    # Trials
    path('trials/expiring', views.expiring_trials, name='expiring_trials'),

    # Tenants
    path('tenants', views.tenant_list, name='tenant_list'),
    path('tenants/<int:tenant_id>', views.tenant_detail, name='tenant_detail'),
    path('tenants/<int:tenant_id>/change-plan', views.tenant_change_plan, name='tenant_change_plan'),
    path('tenants/<int:tenant_id>/modules', views.tenant_modules, name='tenant_modules'),

    # Payments
    path('payments', views.payment_list, name='payment_list'),
    path('payments/<int:payment_id>/approve', views.payment_approve, name='payment_approve'),

    # Global Module Management
    path('modules/global', views.global_module_toggle, name='global_module_toggle'),

    # User Management
    path('users', views.user_list, name='user_list'),
    path('users/bulk-delete', views.bulk_delete_users, name='bulk_delete_users'),
    path('users/<int:user_id>', views.user_detail, name='user_detail'),

    # Audit Logs
    path('audit-logs', views.audit_logs, name='audit_logs'),

    # System Health
    path('system/health', views.system_health, name='system_health'),

    # Platform Settings
    path('settings', views.platform_settings, name='platform_settings'),
    path('settings/test-smtp', views.test_smtp, name='test_smtp'),

    # Impersonation
    path('impersonate', views.impersonate_user, name='impersonate_user'),
    path('impersonate/stop', views.stop_impersonation, name='stop_impersonation'),
    path('impersonate/logs', views.impersonation_logs, name='impersonation_logs'),

    # Phase 1: Referrer & Commission
    path('referrers', views.referrer_list_create, name='referrer_list'),
    path('referrers/<int:pk>', views.referrer_detail, name='referrer_detail'),
    path('referrals', views.referral_list_create, name='referral_list'),
    path('commissions', views.commission_list_create, name='commission_list'),
    path('commissions/<int:pk>', views.commission_detail, name='commission_detail'),
    path('commission-payouts', views.commission_payout_list_create, name='commission_payout_list'),
    path('commission-payouts/<int:pk>', views.commission_payout_detail, name='commission_payout_detail'),

    # Phase 2: Support Tickets
    path('support-tickets', views.support_ticket_list_create, name='support_ticket_list'),
    path('support-tickets/<int:pk>', views.support_ticket_detail, name='support_ticket_detail'),
    path('support-tickets/<int:pk>/comments', views.ticket_comment_create, name='ticket_comment_create'),
    path('support-tickets/<int:pk>/attachments', views.ticket_attachment_upload, name='ticket_attachment_upload'),
    path('support-tickets/<int:pk>/assign', views.ticket_assign, name='ticket_assign'),

    # Phase 3: Language & Currency Config
    path('languages', views.language_config_list, name='language_config_list'),
    path('languages/<int:pk>', views.language_config_detail, name='language_config_detail'),
    path('currencies', views.currency_config_list, name='currency_config_list'),
    path('currencies/<int:pk>', views.currency_config_detail, name='currency_config_detail'),
    path('tenant-languages', views.tenant_language_setting_list, name='tenant_language_setting_list'),
    path('tenant-currencies', views.tenant_currency_setting_list, name='tenant_currency_setting_list'),

    # Phase 4: Tenant SMTP
    path('tenant-smtp', views.tenant_smtp_list, name='tenant_smtp_list'),
    path('tenant-smtp/<int:pk>', views.tenant_smtp_detail, name='tenant_smtp_detail'),
    path('tenant-smtp/<int:pk>/test', views.test_smtp_connection, name='test_smtp_connection'),

    # Phase 5: API Keys & Webhooks
    path('api-keys', views.api_key_list, name='api_key_list'),
    path('api-keys/<int:pk>', views.api_key_detail, name='api_key_detail'),
    path('webhooks', views.webhook_list, name='webhook_list'),
    path('webhooks/<int:pk>', views.webhook_detail, name='webhook_detail'),
    path('webhooks/<int:pk>/test', views.webhook_test, name='webhook_test'),
    path('webhooks/<int:pk>/regenerate-secret', views.webhook_regenerate_secret, name='webhook_regenerate_secret'),
    path('webhooks/<int:pk>/deliveries', views.webhook_deliveries, name='webhook_deliveries'),

    # Phase 6: Announcements & Notifications
    path('announcements', views.announcement_list, name='announcement_list'),
    path('announcements/<int:pk>', views.announcement_detail, name='announcement_detail'),
    path('announcements/<int:pk>/publish', views.announcement_publish, name='announcement_publish'),
    path('notifications', views.notification_list, name='notification_list'),

    # Phase 7: Usage & Billing
    path('usage', views.tenant_usage_list, name='tenant_usage_list'),
    path('invoices', views.invoice_list_create, name='invoice_list'),
    path('invoices/<int:pk>', views.invoice_detail, name='invoice_detail'),
    path('billing/analytics', views.billing_analytics, name='billing_analytics'),

    # SaaS Dashboard
    path('saas-stats', views.saas_dashboard_stats, name='saas_dashboard_stats'),

    # Module Pricing (public + superadmin)
    path('module-pricing', views.module_pricing_list, name='module_pricing_list'),
    path('module-pricing/<int:pk>', views.module_pricing_detail, name='module_pricing_detail'),
    path('public/platform-info', views.public_platform_info, name='public_platform_info'),
    path('public/currencies', views.public_currencies, name='public_currencies'),
    path('public/detect-currency', views.public_detect_currency, name='public_detect_currency'),
    path('public/plans', views.public_subscription_plans, name='public_subscription_plans'),
    path('public/modules', views.public_module_pricing, name='public_module_pricing'),
    path('public/modules/<str:module_name>', views.public_module_pricing_detail, name='public_module_pricing_detail'),

    # Email Templates
    path('email-templates', views.email_template_list, name='email_template_list'),
    path('email-templates/<int:pk>', views.email_template_detail, name='email_template_detail'),
    path('email-templates/<int:pk>/preview', views.email_template_preview, name='email_template_preview'),
    path('email-templates/<int:pk>/send-test', views.email_template_send_test, name='email_template_send_test'),
]
