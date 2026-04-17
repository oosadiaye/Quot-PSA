import secrets
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from tenants.models import Client, SubscriptionPlan

from superadmin.encryption import EncryptedCharField


class SuperAdminProfile(models.Model):
    """Extended profile for superadmin users"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='superadmin_profile')
    is_superadmin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='superadmin/avatars/', null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"SuperAdmin: {self.user.username}"


class SuperAdminSettings(models.Model):
    """Global platform settings (singleton, pk=1)"""
    organization_name = models.CharField(max_length=200, default='QUOT ERP')
    default_timezone = models.CharField(max_length=50, default='Africa/Lagos')
    default_currency = models.CharField(max_length=10, default='NGN')
    maintenance_mode = models.BooleanField(default=False)

    # Security
    session_timeout_minutes = models.PositiveIntegerField(default=60)
    require_special_chars = models.BooleanField(default=True)
    require_uppercase = models.BooleanField(default=True)
    min_password_length = models.PositiveIntegerField(default=8)
    two_factor_enabled = models.BooleanField(default=False)

    # API
    rate_limit_per_hour = models.PositiveIntegerField(default=1000)
    token_expiry_days = models.PositiveIntegerField(default=1)
    max_login_attempts = models.PositiveIntegerField(default=5)

    # Email/SMTP
    smtp_host = models.CharField(max_length=255, blank=True, default='')
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=255, blank=True, default='')
    # SEC: encrypted at rest via Fernet (superadmin/encryption.py).
    # Excluded from admin UI (SuperAdminSettingsAdmin.exclude).
    smtp_password = EncryptedCharField(blank=True, default='')
    smtp_use_tls = models.BooleanField(default=True)
    smtp_use_ssl = models.BooleanField(default=False)
    smtp_from_email = models.EmailField(blank=True, default='')
    smtp_from_name = models.CharField(max_length=100, blank=True, default='QUOT ERP')
    support_email = models.EmailField(blank=True, default='')
    smtp_enabled = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'SuperAdmin Settings'
        verbose_name_plural = 'SuperAdmin Settings'

    def __str__(self):
        return f"Platform Settings ({self.organization_name})"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ImpersonationLog(models.Model):
    """Audit trail for superadmin impersonation sessions."""
    superadmin = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='impersonation_sessions',
    )
    target_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='impersonated_sessions',
    )
    target_tenant = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='impersonation_logs',
    )
    token_key = models.CharField(max_length=40)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.superadmin.username} -> {self.target_user.username} @ {self.target_tenant.name}"


# =============================================================================
# SAAS ENHANCEMENT MODELS - PHASE 1: REFERRER & COMMISSION
# =============================================================================

class Referrer(models.Model):
    """Represents a referrer/affiliate partner"""
    TYPE_CHOICES = [
        ('Partner', 'Business Partner'),
        ('Affiliate', 'Affiliate Marketer'),
        ('Employee', 'Employee'),
        ('Reseller', 'Reseller'),
    ]
    
    referrer_code = models.CharField(max_length=50, unique=True)
    referrer_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='Partner')
    
    company_name = models.CharField(max_length=200, blank=True)
    contact_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    commission_type = models.CharField(max_length=20, choices=[
        ('Percentage', 'Percentage of Sale'),
        ('Fixed', 'Fixed Amount per Sale'),
    ], default='Percentage')
    
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    payment_schedule = models.CharField(max_length=20, choices=[
        ('Monthly', 'Monthly'),
        ('Quarterly', 'Quarterly'),
        ('OnDemand', 'On Demand'),
    ], default='Monthly')
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.contact_name} ({self.referrer_code})"
    
    def save(self, *args, **kwargs):
        if not self.referrer_code:
            self.referrer_code = f"REF-{secrets.token_urlsafe(8)[:8].upper()}"
        super().save(*args, **kwargs)


class Referral(models.Model):
    """Tracks referrals from referrers"""
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Trial', 'Trial Started'),
        ('Active', 'Active Subscription'),
        ('Cancelled', 'Cancelled'),
        ('Expired', 'Expired'),
    ]
    
    referrer = models.ForeignKey(Referrer, on_delete=models.CASCADE, related_name='referrals')
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='referral_info')
    referred_at = models.DateTimeField(auto_now_add=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    source = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=50, blank=True)
    
    class Meta:
        unique_together = ['referrer', 'tenant']
        ordering = ['-referred_at']
    
    def __str__(self):
        return f"{self.referrer.contact_name} -> {self.tenant.name}"


class Commission(models.Model):
    """Tracks commissions earned by referrers"""
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Paid', 'Paid'),
        ('Cancelled', 'Cancelled'),
    ]
    
    referrer = models.ForeignKey(Referrer, on_delete=models.CASCADE, related_name='commissions')
    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name='commissions')
    
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='commissions')
    subscription = models.ForeignKey(
        'tenants.TenantSubscription', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commissions',
    )
    sale_amount = models.DecimalField(max_digits=15, decimal_places=2)
    sale_date = models.DateField()
    
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    commission_type = models.CharField(max_length=20)
    commission_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=50, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-sale_date']
    
    def __str__(self):
        return f"{self.referrer.contact_name} - {self.commission_amount}"
    
    def calculate_commission(self):
        if self.commission_type == 'Percentage':
            self.commission_amount = self.sale_amount * (self.commission_rate / 100)
        else:
            self.commission_amount = self.commission_rate
        return self.commission_amount


class CommissionPayout(models.Model):
    """Batch payout to referrers"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Processing', 'Processing'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    ]

    referrer = models.ForeignKey(Referrer, on_delete=models.CASCADE, related_name='payouts')
    period_start = models.DateField()
    period_end = models.DateField()

    total_commissions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    commissions_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    payout_date = models.DateField(null=True, blank=True)
    payout_reference = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_end']

    def __str__(self):
        return f"Payout {self.referrer.contact_name} ({self.period_start} - {self.period_end})"


# =============================================================================
# PHASE 2: SUPPORT TICKET SYSTEM
# =============================================================================

class SupportTicket(models.Model):
    """Global support tickets"""
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('InProgress', 'In Progress'),
        ('WaitingCustomer', 'Waiting Customer'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]
    CATEGORY_CHOICES = [
        ('Technical', 'Technical Issue'),
        ('Billing', 'Billing'),
        ('Account', 'Account'),
        ('FeatureRequest', 'Feature Request'),
        ('DataIssue', 'Data Issue'),
        ('Integration', 'Integration'),
        ('Other', 'Other'),
    ]
    
    ticket_number = models.CharField(max_length=50, unique=True)
    subject = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    
    requester_name = models.CharField(max_length=100)
    requester_email = models.EmailField()
    requester_tenant = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_tickets')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.ticket_number:
            from django.db import IntegrityError
            for attempt in range(5):
                try:
                    last = SupportTicket.objects.order_by('-id').first()
                    next_num = (last.id + 1 + attempt) if last else (1 + attempt)
                    self.ticket_number = f"SUPPORT-{timezone.now().strftime('%Y%m%d')}-{next_num:05d}"
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    if attempt == 4:
                        raise
                    continue
        super().save(*args, **kwargs)


class TicketComment(models.Model):
    """Comments on support tickets"""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class TicketAttachment(models.Model):
    """Attachments for support tickets"""
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.csv', '.xlsx', '.xls', '.doc', '.docx', '.txt', '.zip'}

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='support/attachments/')
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """SEC: Model-level file size and extension validation as defense-in-depth."""
        import os
        super().clean()
        if self.file and hasattr(self.file, 'size') and self.file.size > self.MAX_FILE_SIZE:
            raise ValidationError(f"File too large. Maximum {self.MAX_FILE_SIZE // (1024*1024)}MB allowed.")
        if self.file_name:
            ext = os.path.splitext(self.file_name)[1].lower()
            if ext and ext not in self.ALLOWED_EXTENSIONS:
                raise ValidationError(f"File type {ext} not allowed.")

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file_name} on {self.ticket.ticket_number}"


# =============================================================================
# PHASE 3: MULTI-LANGUAGE & CURRENCY CONFIG
# =============================================================================

class LanguageConfig(models.Model):
    """Supported languages for the platform"""
    LANGUAGE_CHOICES = [
        ('en', 'English'), ('fr', 'French'), ('es', 'Spanish'),
        ('de', 'German'), ('ar', 'Arabic'), ('pt', 'Portuguese'),
        ('zh', 'Chinese'), ('ja', 'Japanese'),
    ]
    
    language_code = models.CharField(max_length=10, unique=True)
    language_name = models.CharField(max_length=50)
    native_name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    is_rtl = models.BooleanField(default=False)
    flag_emoji = models.CharField(max_length=10, default='🌐')
    date_format = models.CharField(max_length=30, default='YYYY-MM-DD')
    time_format = models.CharField(max_length=30, default='HH:mm')
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['sort_order', 'language_name']
    
    def __str__(self):
        return f"{self.flag_emoji} {self.language_name}"


class CurrencyConfig(models.Model):
    """Supported currencies for the platform"""
    currency_code = models.CharField(max_length=3, unique=True)
    currency_name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=5)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    decimal_places = models.PositiveIntegerField(default=2)
    decimal_separator = models.CharField(max_length=1, default='.')
    thousand_separator = models.CharField(max_length=1, default=',')
    symbol_position = models.CharField(max_length=10, choices=[
        ('prefix', 'Before Amount'),
        ('suffix', 'After Amount'),
    ], default='prefix')
    exchange_rate_to_base = models.DecimalField(max_digits=20, decimal_places=6, default=1.0)
    last_updated = models.DateTimeField(null=True, blank=True)
    auto_update = models.BooleanField(default=False)
    # ISO 3166-1 alpha-2 country codes for IP→currency auto-detection
    # Stored as JSON array, e.g. ["NG"] for Naira, ["KE"] for Shilling
    country_codes = models.JSONField(default=list, blank=True,
        help_text='List of ISO country codes mapped to this currency, e.g. ["NG","GH"]')
    flag_emoji = models.CharField(max_length=10, blank=True, default='',
        help_text='Flag emoji for display, e.g. 🇳🇬')

    class Meta:
        ordering = ['currency_code']

    def __str__(self):
        return f"{self.symbol} {self.currency_code}"


class TenantLanguageSetting(models.Model):
    """Per-tenant language configuration"""
    tenant = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='language_setting')
    language = models.ForeignKey(LanguageConfig, on_delete=models.PROTECT)
    allow_user_override = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.tenant.name} - {self.language.language_name}"


class TenantCurrencySetting(models.Model):
    """Per-tenant currency configuration"""
    tenant = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='currency_setting')
    currency = models.ForeignKey(CurrencyConfig, on_delete=models.PROTECT)
    allow_user_override = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.tenant.name} - {self.currency.currency_code}"


# =============================================================================
# PHASE 4: TENANT SMTP CONFIGURATION
# =============================================================================

class TenantSMTPConfig(models.Model):
    """Per-tenant SMTP configuration"""
    tenant = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='smtp_config')
    
    smtp_host = models.CharField(max_length=255)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=255)
    # SEC: encrypted at rest via Fernet (superadmin/encryption.py).
    # Excluded from admin UI (TenantSMTPConfigAdmin.exclude).
    smtp_password = EncryptedCharField()
    smtp_use_tls = models.BooleanField(default=True)
    smtp_use_ssl = models.BooleanField(default=False)
    smtp_from_email = models.EmailField()
    smtp_from_name = models.CharField(max_length=100)
    reply_to_email = models.EmailField(blank=True)
    
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    test_sent_at = models.DateTimeField(null=True, blank=True)
    test_status = models.CharField(max_length=20, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Tenant SMTP Configuration'
    
    def __str__(self):
        return f"{self.tenant.name} - {self.smtp_host}"


# =============================================================================
# PHASE 5: API KEYS & WEBHOOKS
# =============================================================================

class TenantAPIKey(models.Model):
    """API keys for tenant API access"""
    KEY_TYPE_CHOICES = [('Production', 'Production'), ('Sandbox', 'Sandbox')]

    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='api_keys')
    key_name = models.CharField(max_length=100)
    key_type = models.CharField(max_length=20, choices=KEY_TYPE_CHOICES, default='Production')
    api_key = models.CharField(max_length=64, unique=True)
    api_secret = models.CharField(max_length=128, blank=True)
    allowed_ips = models.TextField(blank=True)
    rate_limit = models.PositiveIntegerField(default=1000)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = secrets.token_urlsafe(32)
        if not self.api_secret:
            self.api_secret = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tenant.name} - {self.key_name} ({self.key_type})"


class WebhookConfig(models.Model):
    """Webhooks for tenant integrations"""
    EVENT_CHOICES = [
        ('tenant.created', 'Tenant Created'),
        ('tenant.updated', 'Tenant Updated'),
        ('tenant.suspended', 'Tenant Suspended'),
        ('subscription.created', 'Subscription Created'),
        ('subscription.renewed', 'Subscription Renewed'),
        ('subscription.cancelled', 'Subscription Cancelled'),
        ('payment.success', 'Payment Success'),
        ('payment.failed', 'Payment Failed'),
        ('user.created', 'User Created'),
        ('user.login', 'User Login'),
    ]

    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='webhooks')
    webhook_name = models.CharField(max_length=100)
    webhook_url = models.URLField()
    # Auto-generated on first save if not supplied — use webhook_regenerate_secret to rotate
    secret_key = models.CharField(max_length=128, blank=True)
    subscribed_events = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    timeout_seconds = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(60)])
    retry_count = models.PositiveIntegerField(default=3, validators=[MinValueValidator(1)])
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    last_status_code = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.secret_key:
            self.secret_key = secrets.token_urlsafe(64)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tenant.name} - {self.webhook_name}"


class WebhookDelivery(models.Model):
    """Log of webhook deliveries"""
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Success', 'Success'),
        ('Failed', 'Failed'),
    ]

    webhook = models.ForeignKey(WebhookConfig, on_delete=models.CASCADE, related_name='deliveries')
    event = models.CharField(max_length=50)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    status_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    retry_attempt = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-attempted_at']

    def __str__(self):
        return f"{self.webhook.webhook_name} - {self.event} ({self.status})"


# =============================================================================
# PHASE 6: ANNOUNCEMENTS & NOTIFICATIONS
# =============================================================================

class Announcement(models.Model):
    """System-wide announcements to tenants"""
    PRIORITY_CHOICES = [('Low', 'Low'), ('Normal', 'Normal'), ('High', 'High'), ('Critical', 'Critical')]
    TARGET_CHOICES = [('All', 'All Tenants'), ('Plan', 'Specific Plans'), ('Tenant', 'Specific Tenants')]

    title = models.CharField(max_length=200)
    content = models.TextField()
    content_html = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Normal')
    target = models.CharField(max_length=20, choices=TARGET_CHOICES, default='All')
    target_plans = models.ManyToManyField(SubscriptionPlan, blank=True, related_name='announcements')
    target_tenants = models.ManyToManyField(Client, blank=True, related_name='targeted_announcements')
    show_on_login = models.BooleanField(default=True)
    show_on_dashboard = models.BooleanField(default=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class TenantNotification(models.Model):
    """Per-tenant notification tracking"""
    NOTIFICATION_TYPE_CHOICES = [
        ('Announcement', 'Announcement'), ('Alert', 'Alert'),
        ('Reminder', 'Reminder'), ('Invoice', 'Invoice'),
    ]

    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='notifications')
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    action_url = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.title}"


# =============================================================================
# PHASE 7: USAGE METERING & BILLING
# =============================================================================

class TenantUsage(models.Model):
    """Track tenant resource usage for billing"""
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='usage_records')
    billing_period_start = models.DateField()
    billing_period_end = models.DateField()

    users_count = models.PositiveIntegerField(default=0)
    storage_mb = models.BigIntegerField(default=0)
    api_calls = models.BigIntegerField(default=0)
    transactions_count = models.BigIntegerField(default=0)

    overage_users = models.PositiveIntegerField(default=0)
    overage_storage_mb = models.BigIntegerField(default=0)
    overage_api_calls = models.BigIntegerField(default=0)

    base_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    overage_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    is_billed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['tenant', 'billing_period_start']
        ordering = ['-billing_period_start']

    def __str__(self):
        return f"{self.tenant.name} usage ({self.billing_period_start} - {self.billing_period_end})"


class Invoice(models.Model):
    """Platform invoices for tenant billing"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Overdue', 'Overdue'),
        ('Cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=50, unique=True)
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')

    period_start = models.DateField()
    period_end = models.DateField()

    subscription_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    usage_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)

    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f"{self.invoice_number} - {self.tenant.name}"

    def _recalc_total(self):
        """Centralised total calculation — called once before every save."""
        self.total_amount = (
            self.subscription_amount + self.usage_amount
            + self.tax_amount - self.discount_amount
        )

    def save(self, *args, **kwargs):
        self._recalc_total()
        if not self.invoice_number:
            from django.db import IntegrityError
            for attempt in range(5):
                try:
                    last = Invoice.objects.order_by('-id').first()
                    next_num = (last.id + 1 + attempt) if last else (1 + attempt)
                    self.invoice_number = f"INV-{timezone.now().strftime('%Y%m')}-{next_num:05d}"
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    if attempt == 4:
                        raise
                    continue
        super().save(*args, **kwargs)
