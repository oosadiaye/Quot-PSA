"""
Integration Models
==================
Supports connecting DTSG ERP to external ERP systems (SAP, Dynamics 365,
Sage) and arbitrary 3rd-party platforms (Shopify, Stripe, custom webhooks).

Architecture
------------
IntegrationConfig    — one row per connected external system per tenant
FieldMapping         — column-level transform rules between DTSG and remote
WebhookEndpoint      — outbound webhook subscriptions (DTSG -> external)
WebhookInboundLog    — received webhook events (external -> DTSG)
SyncLog              — record-level sync history with retry state
"""

import hashlib
import hmac
import secrets
import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


# -- Choices -------------------------------------------------------------------

class SystemType(models.TextChoices):
    SAP_ECC = 'sap_ecc', 'SAP ECC'
    SAP_S4HANA = 'sap_s4hana', 'SAP S/4HANA (OData)'
    SAP_BC = 'sap_bc', 'SAP Business Central / B1'
    DYNAMICS_365_BC = 'dynamics_365_bc', 'Microsoft Dynamics 365 BC'
    DYNAMICS_365_FO = 'dynamics_365_fo', 'Microsoft Dynamics 365 F&O'
    DYNAMICS_AX = 'dynamics_ax', 'Microsoft Dynamics AX'
    SAGE_INTACCT = 'sage_intacct', 'Sage Intacct'
    SAGE_200 = 'sage_200', 'Sage 200'
    SAGE_50 = 'sage_50', 'Sage 50'
    SAGE_X3 = 'sage_x3', 'Sage X3'
    QUICKBOOKS = 'quickbooks', 'QuickBooks Online'
    XERO = 'xero', 'Xero'
    NETSUITE = 'netsuite', 'Oracle NetSuite'
    SHOPIFY = 'shopify', 'Shopify'
    WOOCOMMERCE = 'woocommerce', 'WooCommerce'
    STRIPE = 'stripe', 'Stripe'
    PAYSTACK = 'paystack', 'Paystack'
    FLUTTERWAVE = 'flutterwave', 'Flutterwave'
    SALESFORCE = 'salesforce', 'Salesforce CRM'
    HUBSPOT = 'hubspot', 'HubSpot CRM'
    CUSTOM = 'custom', 'Custom / Generic REST'
    CUSTOM_SOAP = 'custom_soap', 'Custom SOAP/XML'
    WEBHOOK_ONLY = 'webhook_only', 'Webhook Only'


class AuthMethod(models.TextChoices):
    NONE = 'none', 'No Auth'
    API_KEY = 'api_key', 'API Key Header'
    BASIC = 'basic', 'HTTP Basic Auth'
    BEARER = 'bearer', 'Bearer Token'
    OAUTH2_CC = 'oauth2_cc', 'OAuth 2.0 Client Credentials'
    OAUTH2_AUTH = 'oauth2_auth', 'OAuth 2.0 Authorization Code'
    SAP_COOKIE = 'sap_cookie', 'SAP CSRF Cookie'
    HMAC = 'hmac', 'HMAC Signature'


class SyncDirection(models.TextChoices):
    INBOUND = 'inbound', 'Inbound (Remote -> DTSG)'
    OUTBOUND = 'outbound', 'Outbound (DTSG -> Remote)'
    BIDIRECTIONAL = 'bidirectional', 'Bidirectional'


class SyncStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    SUCCESS = 'success', 'Success'
    PARTIAL = 'partial', 'Partial Success'
    FAILED = 'failed', 'Failed'
    SKIPPED = 'skipped', 'Skipped (no change)'
    RETRY = 'retry', 'Queued for Retry'


class ModuleCode(models.TextChoices):
    ACCOUNTING = 'accounting', 'Accounting / GL'
    AP = 'ap', 'Accounts Payable'
    AR = 'ar', 'Accounts Receivable'
    ASSETS = 'assets', 'Fixed Assets'
    BUDGET = 'budget', 'Budget'
    INVENTORY = 'inventory', 'Inventory'
    PROCUREMENT = 'procurement', 'Procurement / P2P'
    SALES = 'sales', 'Sales / O2C'
    HRM = 'hrm', 'HRM / Payroll'
    PRODUCTION = 'production', 'Production / MFG'
    QUALITY = 'quality', 'Quality'
    SERVICE = 'service', 'Service / Maintenance'
    CUSTOMERS = 'customers', 'Customers / CRM'
    VENDORS = 'vendors', 'Vendors / Suppliers'
    ITEMS = 'items', 'Items / Products'
    ALL = 'all', 'All Modules'


class EventType(models.TextChoices):
    SALES_ORDER_CREATED = 'sales_order.created', 'Sales Order Created'
    SALES_ORDER_UPDATED = 'sales_order.updated', 'Sales Order Updated'
    SALES_ORDER_CONFIRMED = 'sales_order.confirmed', 'Sales Order Confirmed'
    DELIVERY_POSTED = 'delivery.posted', 'Delivery Note Posted'
    CUSTOMER_INVOICE_CREATED = 'customer_invoice.created', 'Customer Invoice Created'
    CUSTOMER_PAYMENT_RECEIVED = 'customer_payment.received', 'Customer Payment Received'
    SALES_RETURN_CREATED = 'sales_return.created', 'Sales Return Created'
    PURCHASE_ORDER_CREATED = 'purchase_order.created', 'Purchase Order Created'
    PURCHASE_ORDER_APPROVED = 'purchase_order.approved', 'Purchase Order Approved'
    GRN_POSTED = 'grn.posted', 'GRN Posted'
    VENDOR_INVOICE_CREATED = 'vendor_invoice.created', 'Vendor Invoice Created'
    VENDOR_PAYMENT_MADE = 'vendor_payment.made', 'Vendor Payment Made'
    STOCK_MOVEMENT_CREATED = 'stock_movement.created', 'Stock Movement Created'
    STOCK_LEVEL_LOW = 'stock.low', 'Stock Below Reorder Point'
    ITEM_CREATED = 'item.created', 'Item Created'
    ITEM_UPDATED = 'item.updated', 'Item Updated'
    JOURNAL_POSTED = 'journal.posted', 'Journal Entry Posted'
    PAYMENT_POSTED = 'payment.posted', 'Payment Posted'
    PERIOD_CLOSED = 'period.closed', 'Period Closed'
    YEAR_END_CLOSED = 'year_end.closed', 'Year-End Closed'
    EMPLOYEE_CREATED = 'employee.created', 'Employee Created'
    EMPLOYEE_UPDATED = 'employee.updated', 'Employee Updated'
    PAYROLL_POSTED = 'payroll.posted', 'Payroll Run Posted'
    PRODUCTION_ORDER_CREATED = 'production_order.created', 'Production Order Created'
    PRODUCTION_ORDER_COMPLETED = 'production_order.completed', 'Production Order Completed'
    CUSTOM = 'custom', 'Custom Event'


TRANSFORM_CHOICES = [
    ('none', 'None'),
    ('upper', 'Uppercase'),
    ('lower', 'Lowercase'),
    ('zero_pad_10', 'Zero-pad to 10 chars (SAP GL account)'),
    ('date_iso', 'Date -> ISO-8601'),
    ('date_sap', 'Date -> SAP YYYYMMDD'),
    ('amount_abs', 'Amount -> absolute value'),
    ('debit_credit_sign', 'Negate for debit/credit sign convention'),
    ('boolean_x', 'Boolean -> X/empty (SAP)'),
]


# -- Main Config ---------------------------------------------------------------

class IntegrationConfig(models.Model):
    """
    One record per connected external system per tenant.
    Stores credentials (encrypted at environment level), sync schedule, and
    enabled modules.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, help_text='Human label, e.g. "SAP Production"')
    system_type = models.CharField(max_length=40, choices=SystemType.choices)
    is_active = models.BooleanField(default=True)

    base_url = models.URLField(blank=True, help_text='e.g. https://mycompany.s4hana.cloud/sap/opu/odata/')
    auth_method = models.CharField(max_length=20, choices=AuthMethod.choices, default=AuthMethod.BEARER)
    credentials = models.JSONField(
        default=dict, blank=True,
        help_text=(
            'Auth credentials as JSON. Keys by auth_method: '
            'bearer={"token":""}, basic={"username":"","password":""}, '
            'api_key={"header_name":"X-Api-Key","key":""}, '
            'oauth2_cc={"client_id":"","client_secret":"","token_url":""}, '
            'sap_cookie={"username":"","password":"","csrf_url":""}'
        ),
    )
    token_cache = models.JSONField(default=dict, blank=True)

    direction = models.CharField(max_length=20, choices=SyncDirection.choices, default=SyncDirection.BIDIRECTIONAL)
    enabled_modules = models.JSONField(default=list, help_text='List of ModuleCode values. Empty = all.')
    sync_interval_minutes = models.PositiveIntegerField(default=60, help_text='0 = manual only')
    last_sync_at = models.DateTimeField(null=True, blank=True)
    next_sync_at = models.DateTimeField(null=True, blank=True)

    webhook_secret = models.CharField(max_length=128, blank=True)

    # SAP
    sap_client = models.CharField(max_length=10, blank=True)
    sap_system_id = models.CharField(max_length=10, blank=True)
    # Dynamics
    dynamics_tenant_id = models.CharField(max_length=80, blank=True)
    dynamics_environment = models.CharField(max_length=80, blank=True)
    # Sage
    sage_company_id = models.CharField(max_length=80, blank=True)

    max_retries = models.PositiveSmallIntegerField(default=3)
    retry_backoff_seconds = models.PositiveIntegerField(default=60)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Integration Config'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.get_system_type_display()})'

    def generate_webhook_secret(self):
        self.webhook_secret = secrets.token_hex(32)
        self.save(update_fields=['webhook_secret'])
        return self.webhook_secret

    def verify_hmac_signature(self, payload: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return False
        expected = hmac.new(
            self.webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        # Strip 'sha256=' prefix exactly (not lstrip which strips individual chars)
        normalised = signature[7:] if signature.startswith('sha256=') else signature
        return hmac.compare_digest(expected, normalised)


# -- Field Mapping -------------------------------------------------------------

class FieldMapping(models.Model):
    """
    Maps DTSG field names to remote system field names per module.
    Supports renames and a fixed set of safe value transforms.
    """
    config = models.ForeignKey(IntegrationConfig, on_delete=models.CASCADE, related_name='field_mappings')
    module = models.CharField(max_length=30, choices=ModuleCode.choices)
    dtsg_field = models.CharField(max_length=120, help_text='Python dot-path in DTSG, e.g. "account.code"')
    remote_field = models.CharField(max_length=120)
    transform = models.CharField(max_length=40, choices=TRANSFORM_CHOICES, default='none')
    default_value = models.CharField(max_length=255, blank=True)
    is_required_remote = models.BooleanField(default=False)
    direction = models.CharField(max_length=20, choices=SyncDirection.choices, default=SyncDirection.BIDIRECTIONAL)

    class Meta:
        unique_together = [('config', 'module', 'dtsg_field', 'direction')]
        ordering = ['module', 'dtsg_field']

    def __str__(self):
        return f'{self.config.name}: {self.module} {self.dtsg_field} <-> {self.remote_field}'

    def apply(self, value):
        """Apply the configured transform to a value."""
        import decimal
        if value is None:
            return self.default_value or None
        t = self.transform
        if t == 'upper':
            return str(value).upper()
        if t == 'lower':
            return str(value).lower()
        if t == 'zero_pad_10':
            return str(value).zfill(10)
        if t == 'date_sap':
            if hasattr(value, 'strftime'):
                return value.strftime('%Y%m%d')
            return str(value).replace('-', '')
        if t == 'date_iso':
            if hasattr(value, 'isoformat'):
                return value.isoformat()
        if t == 'boolean_x':
            return 'X' if value else ''
        if t == 'amount_abs':
            return abs(decimal.Decimal(str(value)))
        if t == 'debit_credit_sign':
            return -decimal.Decimal(str(value))
        return value


# -- Outbound Webhook Endpoints ------------------------------------------------

class WebhookEndpoint(models.Model):
    """Subscription: POST DTSG events to an external URL."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey(
        IntegrationConfig, on_delete=models.CASCADE,
        related_name='webhook_endpoints', null=True, blank=True,
    )
    name = models.CharField(max_length=120)
    target_url = models.URLField()
    events = models.JSONField(default=list, help_text='EventType list. Empty = all.')
    modules = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    secret = models.CharField(max_length=128, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    max_retries = models.PositiveSmallIntegerField(default=3)
    timeout_seconds = models.PositiveSmallIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Webhook Endpoint'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} -> {self.target_url}'

    def generate_secret(self):
        self.secret = secrets.token_hex(32)
        self.save(update_fields=['secret'])
        return self.secret

    def sign_payload(self, payload: bytes) -> str:
        if not self.secret:
            return ''
        return 'sha256=' + hmac.new(
            self.secret.encode(), payload, hashlib.sha256
        ).hexdigest()


# -- Webhook Delivery Log ------------------------------------------------------

class WebhookDelivery(models.Model):
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')
    event_type = models.CharField(max_length=80)
    payload = models.JSONField()
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Webhook Delivery'


# -- Inbound Webhook Log -------------------------------------------------------

class WebhookInboundLog(models.Model):
    config = models.ForeignKey(
        IntegrationConfig, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inbound_logs',
    )
    source_system = models.CharField(max_length=40, choices=SystemType.choices, blank=True)
    event_type = models.CharField(max_length=120, blank=True)
    headers = models.JSONField(default=dict)
    raw_payload = models.TextField()
    parsed_payload = models.JSONField(null=True, blank=True)
    signature_valid = models.BooleanField(null=True, blank=True)
    processing_status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    processing_notes = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']
        verbose_name = 'Inbound Webhook Log'


# -- Sync Log ------------------------------------------------------------------

class SyncLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey(IntegrationConfig, on_delete=models.CASCADE, related_name='sync_logs')
    module = models.CharField(max_length=30, choices=ModuleCode.choices)
    direction = models.CharField(max_length=20, choices=SyncDirection.choices)
    triggered_by = models.CharField(
        max_length=30,
        choices=[('scheduled', 'Scheduled'), ('manual', 'Manual'), ('webhook', 'Webhook Trigger')],
        default='manual',
    )
    status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    records_total = models.PositiveIntegerField(default=0)
    records_created = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    records_skipped = models.PositiveIntegerField(default=0)
    records_failed = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Sync Log'

    def __str__(self):
        return f'{self.config.name} | {self.module} | {self.status} | {self.started_at:%Y-%m-%d %H:%M}'

    @property
    def duration_seconds(self):
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class SyncLogItem(models.Model):
    sync_log = models.ForeignKey(SyncLog, on_delete=models.CASCADE, related_name='items')
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    remote_id = models.CharField(max_length=120, blank=True)
    action = models.CharField(
        max_length=20,
        choices=[('create', 'Create'), ('update', 'Update'), ('delete', 'Delete'), ('read', 'Read')],
    )
    status = models.CharField(max_length=20, choices=SyncStatus.choices)
    error_detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
