# DTSG ERP SaaS SuperAdmin Dashboard Enhancement Plan
## Comprehensive Feature Implementation Plan

---

## EXECUTIVE SUMMARY

The current SuperAdmin dashboard has basic functionality for:
- Tenant management
- Plan management
- User management
- Basic settings
- Audit logs
- System health monitoring

**Missing Critical SaaS Features:**
- Referrer & Commission tracking
- Support ticket system
- Multi-language configuration
- Multi-currency configuration
- Tenant-level SMTP
- API key management
- Webhooks
- Announcements
- Revenue analytics
- Usage metering/billing

---

## PHASE 1: REFERRER & COMMISSION SYSTEM

### 1.1 Backend Models

```python
# superadmin/models.py - Add Referrer System

class Referrer(models.Model):
    """Represents a referrer/affiliate partner"""
    TYPE_CHOICES = [
        ('Partner', 'Business Partner'),
        ('Affiliate', 'Affiliate Marketer'),
        ('Employee', 'Employee'),
        ('Reseller', 'Reseller'),
    ]
    
    referrer_code = models.CharField(max_length=50, unique=True)
    referrer_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    
    # Business Info
    company_name = models.CharField(max_length=200, blank=True)
    contact_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # Commission Settings
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    commission_type = models.CharField(max_length=20, choices=[
        ('Percentage', 'Percentage of Sale'),
        ('Fixed', 'Fixed Amount per Sale'),
    ], default='Percentage')
    
    # Payment Info
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    payment_schedule = models.CharField(max_length=20, choices=[
        ('Monthly', 'Monthly'),
        ('Quarterly', 'Quarterly'),
        ('OnDemand', 'On Demand'),
    ], default='Monthly')
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.contact_name} ({self.referrer_code})"


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
    tenant = models.ForeignKey('tenants.Client', on_delete=models.CASCADE, related_name='referral_info')
    referred_at = models.DateTimeField(auto_now_add=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    # Tracking
    source = models.CharField(max_length=100, blank=True)  # e.g., 'website', 'email', 'campaign'
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=50, blank=True)
    
    class Meta:
        unique_together = ['referrer', 'tenant']
        ordering = ['-referred_at']


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
    
    # Sale Details
    tenant = models.ForeignKey('tenants.Client', on_delete=models.CASCADE, related_name='commissions')
    subscription = models.ForeignKey('superadmin.Subscription', on_delete=models.CASCADE, null=True, blank=True)
    sale_amount = models.DecimalField(max_digits=15, decimal_places=2)
    sale_date = models.DateField()
    
    # Commission Calculation
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    commission_type = models.CharField(max_length=20)
    commission_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Payment Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=50, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-sale_date']
    
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
    
    total_commissions = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    payout_date = models.DateField(null=True, blank=True)
    payout_reference = models.CharField(max_length=100, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-period_end']
```

---

## PHASE 2: SUPPORT TICKET SYSTEM

### 2.1 Support Models

```python
# superadmin/models.py - Add Support System

class SupportTicket(models.Model):
    """Global support tickets (not tenant-specific)"""
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
    
    # Requester (can be tenant admin or superadmin)
    requester_name = models.CharField(max_length=100)
    requester_email = models.EmailField()
    requester_tenant = models.ForeignKey('tenants.Client', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Assignment
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    
    # Resolution
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_tickets')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.ticket_number:
            self.ticket_number = f"SUPPORT-{timezone.now().strftime('%Y%m%d')}-{self.pk or 'NEW'}"
        super().save(*args, **kwargs)


class TicketComment(models.Model):
    """Comments on support tickets"""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    is_internal = models.BooleanField(default=False)  # Internal notes not visible to requester
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']


class TicketAttachment(models.Model):
    """Attachments for support tickets"""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='support/attachments/')
    file_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
```

---

## PHASE 3: MULTI-LANGUAGE & MULTI-CURRENCY

### 3.1 Configuration Models

```python
# superadmin/models.py - Add Language & Currency

class LanguageConfig(models.Model):
    """Supported languages for the platform"""
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('fr', 'French'),
        ('es', 'Spanish'),
        ('de', 'German'),
        ('ar', 'Arabic'),
        ('pt', 'Portuguese'),
        ('zh', 'Chinese'),
        ('ja', 'Japanese'),
    ]
    
    language_code = models.CharField(max_length=10, unique=True)
    language_name = models.CharField(max_length=50)
    native_name = models.CharField(max_length=50)  # E.g., "Français"
    
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    is_rtl = models.BooleanField(default=False)  # Right-to-left languages
    
    # Display
    flag_emoji = models.CharField(max_length=10)  # E.g., 🇺🇸
    date_format = models.CharField(max_length=30, default='YYYY-MM-DD')
    time_format = models.CharField(max_length=30, default='HH:mm')
    
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['sort_order', 'language_name']
    
    def __str__(self):
        return f"{self.flag_emoji} {self.language_name}"


class CurrencyConfig(models.Model):
    """Supported currencies for the platform"""
    CURRENCY_CHOICES = [
        ('NGN', 'Nigerian Naira'),
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('JPY', 'Japanese Yen'),
        ('CNY', 'Chinese Yuan'),
        ('KES', 'Kenyan Shilling'),
        ('ZAR', 'South African Rand'),
        ('GHS', 'Ghanaian Cedi'),
    ]
    
    currency_code = models.CharField(max_length=3, unique=True)
    currency_name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=5)
    
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    
    # Formatting
    decimal_places = models.PositiveIntegerField(default=2)
    decimal_separator = models.CharField(max_length=1, default='.')
    thousand_separator = models.CharField(max_length=1, default=',')
    symbol_position = models.CharField(max_length=10, choices=[
        ('prefix', 'Before Amount'),
        ('suffix', 'After Amount'),
    ], default='prefix')
    
    # Exchange Rates
    exchange_rate_to_base = models.DecimalField(max_digits=20, decimal_places=6, default=1.0)
    last_updated = models.DateTimeField(null=True, blank=True)
    auto_update = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['currency_code']
    
    def __str__(self):
        return f"{self.symbol} {self.currency_code}"


class TenantLanguageSetting(models.Model):
    """Per-tenant language configuration"""
    tenant = models.OneToOneField('tenants.Client', on_delete=models.CASCADE, related_name='language_setting')
    language = models.ForeignKey(LanguageConfig, on_delete=models.PROTECT)
    allow_user_override = models.BooleanField(default=True)


class TenantCurrencySetting(models.Model):
    """Per-tenant currency configuration"""
    tenant = models.OneToOneField('tenants.Client', on_delete=models.CASCADE, related_name='currency_setting')
    currency = models.ForeignKey(CurrencyConfig, on_delete=models.PROTECT)
    allow_user_override = models.BooleanField(default=False)
```

---

## PHASE 4: SMTP CONFIGURATION (Global & Tenant)

### 4.1 Tenant SMTP Models

```python
# superadmin/models.py - Add Tenant SMTP

class TenantSMTPConfig(models.Model):
    """Per-tenant SMTP configuration for sending emails"""
    tenant = models.OneToOneField('tenants.Client', on_delete=models.CASCADE, related_name='smtp_config')
    
    # SMTP Settings
    smtp_host = models.CharField(max_length=255)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=255)
    smtp_password = models.CharField(max_length=255)  # Should be encrypted
    
    # Security
    smtp_use_tls = models.BooleanField(default=True)
    smtp_use_ssl = models.BooleanField(default=False)
    
    # From Address
    smtp_from_email = models.EmailField()
    smtp_from_name = models.CharField(max_length=100)
    reply_to_email = models.EmailField(blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Testing
    test_sent_at = models.DateTimeField(null=True, blank=True)
    test_status = models.CharField(max_length=20, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Tenant SMTP Configuration'
        verbose_name_plural = 'Tenant SMTP Configurations'
    
    def __str__(self):
        return f"{self.tenant.name} - {self.smtp_host}"
    
    def test_connection(self):
        """Test SMTP connection"""
        try:
            import smtplib
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            if self.smtp_use_tls:
                server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.quit()
            self.is_verified = True
            self.test_status = 'Success'
            self.test_sent_at = timezone.now()
            return True
        except Exception as e:
            self.is_verified = False
            self.test_status = str(e)
            return False
```

---

## PHASE 5: API KEY & WEBHOOK MANAGEMENT

### 5.1 API & Webhook Models

```python
# superadmin/models.py - Add API & Webhooks

class TenantAPIKey(models.Model):
    """API keys for tenant API access"""
    KEY_TYPE_CHOICES = [
        ('Production', 'Production'),
        ('Sandbox', 'Sandbox'),
    ]
    
    tenant = models.ForeignKey('tenants.Client', on_delete=models.CASCADE, related_name='api_keys')
    key_name = models.CharField(max_length=100)
    key_type = models.CharField(max_length=20, choices=KEY_TYPE_CHOICES, default='Production')
    
    api_key = models.CharField(max_length=64, unique=True)
    api_secret = models.CharField(max_length=128)  # Should be encrypted
    
    # Restrictions
    allowed_ips = models.TextField(blank=True)  # Comma-separated IPs
    rate_limit = models.PositiveIntegerField(default=1000)  # Requests per hour
    
    # Status
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.tenant.name} - {self.key_name} ({self.key_type})"
    
    @classmethod
    def generate_key(cls):
        import secrets
        return secrets.token_urlsafe(32)


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
    
    tenant = models.ForeignKey('tenants.Client', on_delete=models.CASCADE, related_name='webhooks')
    webhook_name = models.CharField(max_length=100)
    webhook_url = models.URLField()
    secret_key = models.CharField(max_length=128)
    
    # Events to subscribe
    subscribed_events = models.JSONField(default=list)  # List of EVENT_CHOICES
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Delivery
    timeout_seconds = models.PositiveIntegerField(default=30)
    retry_count = models.PositiveIntegerField(default=3)
    
    # Logging
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    last_status_code = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.tenant.name} - {self.webhook_name}"


class WebhookDelivery(models.Model):
    """Log of webhook deliveries"""
    webhook = models.ForeignKey(WebhookConfig, on_delete=models.CASCADE, related_name='deliveries')
    event = models.CharField(max_length=50)
    payload = models.JSONField()
    
    # Delivery Status
    status = models.CharField(max_length=20)  # Pending, Success, Failed
    status_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    # Timing
    attempted_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    
    retry_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-attempted_at']
```

---

## PHASE 6: ANNOUNCEMENTS & NOTIFICATIONS

### 6.1 Announcement Models

```python
# superadmin/models.py - Add Announcements

class Announcement(models.Model):
    """System-wide announcements to tenants"""
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Normal', 'Normal'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]
    TARGET_CHOICES = [
        ('All', 'All Tenants'),
        ('Plan', 'Specific Plans'),
        ('Tenant', 'Specific Tenants'),
    ]
    
    title = models.CharField(max_length=200)
    content = models.TextField()
    content_html = models.TextField(blank=True)  # Rich text
    
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Normal')
    target = models.CharField(max_length=20, choices=TARGET_CHOICES, default='All')
    
    # Targeting
    target_plans = models.ManyToManyField('SubscriptionPlan', blank=True, related_name='announcements')
    target_tenants = models.ManyToManyField('tenants.Client', blank=True, related_name='announcements')
    
    # Display
    show_on_login = models.BooleanField(default=True)
    show_on_dashboard = models.BooleanField(default=True)
    
    # Timing
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    
    # Status
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
        ('Announcement', 'Announcement'),
        ('Alert', 'Alert'),
        ('Reminder', 'Reminder'),
        ('Invoice', 'Invoice'),
    ]
    
    tenant = models.ForeignKey('tenants.Client', on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Delivery
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Actions
    action_url = models.CharField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
```

---

## PHASE 7: USAGE METERING & BILLING ANALYTICS

### 7.1 Usage Models

```python
# superadmin/models.py - Add Usage

class TenantUsage(models.Model):
    """Track tenant resource usage for billing"""
    tenant = models.ForeignKey('tenants.Client', on_delete=models.CASCADE, related_name='usage_records')
    billing_period_start = models.DateField()
    billing_period_end = models.DateField()
    
    # Usage Metrics
    users_count = models.PositiveIntegerField(default=0)
    storage_mb = models.BigIntegerField(default=0)  # Megabytes
    api_calls = models.BigIntegerField(default=0)
    transactions_count = models.BigIntegerField(default=0)
    
    # Overages
    overage_users = models.PositiveIntegerField(default=0)
    overage_storage_mb = models.BigIntegerField(default=0)
    overage_api_calls = models.BigIntegerField(default=0)
    
    # Calculated Costs
    base_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    overage_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    is_billed = models.BooleanField(default=False)
    invoice = models.ForeignKey('Invoice', on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['tenant', 'billing_period_start']
        ordering = ['-billing_period_start']


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
    tenant = models.ForeignKey('tenants.Client', on_delete=models.CASCADE, related_name='invoices')
    
    # Period
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Amounts
    subscription_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    usage_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Payment
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    
    # Dates
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-issue_date']
    
    def __str__(self):
        return f"{self.invoice_number} - {self.tenant.name}"
```

---

## IMPLEMENTATION SEQUENCE

### Week 1-2: Referrer & Commission System
- [ ] Add Referrer, Referral, Commission, CommissionPayout models
- [ ] Create API endpoints for referrer management
- [ ] Build frontend Referrer management page
- [ ] Build Commission tracking page
- [ ] Build Payout processing page

### Week 3: Support Ticket System
- [ ] Add SupportTicket, TicketComment, TicketAttachment models
- [ ] Create ticket CRUD API endpoints
- [ ] Build Support dashboard page
- [ ] Add ticket assignment workflow
- [ ] Build ticket detail view with comments

### Week 4: Language & Currency Configuration
- [ ] Add LanguageConfig, CurrencyConfig models
- [ ] Add tenant-level language/currency settings
- [ ] Build configuration UI
- [ ] Update tenant creation wizard

### Week 5: SMTP Configuration
- [ ] Add TenantSMTPConfig model
- [ ] Create SMTP test functionality
- [ ] Build tenant SMTP configuration UI
- [ ] Integrate email sending

### Week 6: API Keys & Webhooks
- [ ] Add TenantAPIKey, WebhookConfig, WebhookDelivery models
- [ ] Create API key generation/management
- [ ] Build webhook configuration UI
- [ ] Implement webhook delivery system

### Week 7: Announcements & Notifications
- [ ] Add Announcement, TenantNotification models
- [ ] Create announcement creation UI
- [ ] Build notification center
- [ ] Add in-app notification display

### Week 8: Usage & Billing Analytics
- [ ] Add TenantUsage, Invoice models
- [ ] Create usage tracking service
- [ ] Build billing analytics dashboard
- [ ] Invoice generation system

---

## VERIFICATION CHECKLIST

### Before each feature:
- [ ] Models load correctly
- [ ] Migrations created and applied
- [ ] API endpoints functional
- [ ] Frontend builds without errors

### Phase completion:
- [ ] All API endpoints tested
- [ ] UI components functional
- [ ] No existing features broken
- [ ] Documentation updated

---

## EXISTING FILES TO PRESERVE

Must NOT modify:
- `superadmin/models.py` - Only extend with new models
- `superadmin/views.py` - Add new views, don't modify existing
- `superadmin/urls.py` - Add new URLs only
- `frontend/src/pages/superadmin/*` - Extend only
- `frontend/src/pages/superadmin/tabs/*` - Add new tabs only

---

## SUCCESS METRICS

- All new models load without errors
- All API endpoints return valid responses
- Frontend builds without errors
- No regression in existing functionality
- All new features are feature-flag controllable