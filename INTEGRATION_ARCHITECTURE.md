# DTSG ERP Integration Architecture

## Document Purpose
Enterprise integration strategy for DTSG ERP with major ERP systems and third-party applications.

---

## TASK 1: CURRENT INTEGRATION READINESS ASSESSMENT

### 1.1 Current API Structure

**Root URL pattern**: `/api/v1/<module>/` with backward compat at `/api/<module>/`

| Module | Prefix | Endpoints (ViewSets) | Pattern |
|--------|--------|---------------------|---------|
| **Accounting** | `/api/v1/accounting/` | 95+ routes: accounts, journals, vendor-invoices, payments, customer-invoices, receipts, fixed-assets, gl-balances, bank-accounts, tax-*, cost-centers, fiscal-periods, reports/* | DRF Router |
| **Budget** | `/api/v1/budget/` | unified-budget, encumbrances, variances, amendments | DRF Router |
| **Procurement** | `/api/v1/procurement/` | vendors, requests, orders, grns, invoice-matching, credit-notes, debit-notes, purchase-returns | DRF Router |
| **Inventory** | `/api/v1/inventory/` | warehouses, items, stocks, batches, movements, reconciliations, serial-numbers, expiry-alerts | DRF Router |
| **Sales** | `/api/v1/sales/` | customers, leads, opportunities, quotations, orders, delivery-notes, analytics | DRF Router |
| **HRM** | `/api/v1/hrm/` | employees, departments, positions, leave, attendance, payroll, performance, training, compliance, exit | DRF Router |
| **Production** | `/api/v1/production/` | work-centers, bills-of-materials, production-orders, material-issues, job-cards, routings | DRF Router |
| **Quality** | `/api/v1/quality/` | inspections, non-conformances, complaints, checklists, calibrations, supplier-quality | DRF Router |
| **Service** | `/api/v1/service/` | assets, technicians, tickets, schedules, work-orders, citizen-requests, metrics | DRF Router |
| **Workflow** | `/api/v1/workflow/` | approval-groups, approval-templates, approvals, definitions, instances, delegations | DRF Router |
| **Core** | `/api/v1/core/` | users, auth/*, menu, modules, health | DRF Router + FBV |
| **Tenants** | `/api/v1/tenants/` | tenants, modules, plans, subscriptions, payments, user-roles, roles, settings | DRF Router + FBV |
| **SuperAdmin** | `/api/v1/superadmin/` | tenants, plans, payments, users, api-keys, webhooks, support-tickets, announcements, invoices, usage, languages, currencies, smtp | FBV |

**API versioning**: `ALLOWED_VERSIONS = ['v1', 'v2']` configured but only v1 in use. v2 namespace is available for integration APIs.

### 1.2 Existing Webhook Infrastructure

**Models** (in `superadmin/models.py`):
- `WebhookConfig`: tenant-scoped, with `subscribed_events` (JSONField), `secret_key`, `timeout_seconds`, `retry_count`
- `WebhookDelivery`: delivery log with `payload`, `status`, `status_code`, `response_body`, `duration_ms`, `retry_attempt`

**Current webhook events** (outbound only):
```
tenant.created, tenant.updated, tenant.suspended
subscription.created, subscription.renewed, subscription.cancelled
payment.success, payment.failed
user.created, user.login
```

**Delivery mechanism**: Synchronous HTTP POST in `webhook_test` view with HMAC-SHA256 signature (`X-Webhook-Signature` header), SSRF protection (validates public IP). No async delivery via Celery yet.

**Gaps**:
- No business-object events (invoice.created, po.approved, payment.posted, etc.)
- No inbound webhook receiver
- No retry queue (currently only test delivery, no production dispatch)
- No Celery task for async delivery

### 1.3 Current API Authentication

- **Token Auth**: `ExpiringTokenAuthentication` in `core/authentication.py` -- tokens in public schema, 24h expiry, session revocation support
- **JWT**: `rest_framework_simplejwt` configured with 15-min access / 24h refresh tokens, rotate+blacklist
- **API Keys**: `TenantAPIKey` model in superadmin -- per-tenant, with `api_key` (64-char), `api_secret` (128-char), `allowed_ips`, `rate_limit`, `expires_at`
- **RBAC**: `RBACPermission` with tenant-scoped role hierarchy (admin > senior_manager > manager > user > viewer) plus module-level CRUD+approve+post via `Role` model
- **Public Schema Backend**: All auth queries run against public schema regardless of active tenant

**Gaps**:
- No OAuth2 provider (for third-party apps to get tokens)
- API keys exist but no middleware to authenticate requests via API key (only Token/JWT auth classes configured)
- No scoped API tokens (all-or-nothing access)

### 1.4 Data Model Compatibility

**Chart of Accounts**: 8-digit account codes (`DEFAULT_GL_ACCOUNTS`), hierarchical with `parent` FK, standard types (Asset/Liability/Equity/Income/Expense). Compatible with SAP/Dynamics mapping.

**Multi-dimensional accounting**: Fund, Function, Program, Geo, MDA -- maps well to SAP cost elements and Dynamics financial dimensions.

**Customer/Vendor**: `Customer` (sales module) and `Vendor` (procurement module) are separate models -- standard ERP pattern, maps to SAP Business Partner or Dynamics accounts.

**Invoice structure**: `VendorInvoice`, `CustomerInvoice` with line items -- standard pattern compatible with UBL/PEPPOL.

**Currency**: Multi-currency with `Currency` model, exchange rates, revaluation -- maps to SAP currency types and Dynamics exchange rate framework.

**Fiscal periods**: `FiscalPeriod`, `FiscalYear` with open/close/lock semantics -- standard ERP pattern.

### 1.5 Current Import/Export Capabilities

- **No dedicated import/export module exists** -- no CSV/Excel/bank statement import functionality found in codebase
- **No bank statement parsing** (MT940, CAMT.053, OFX)
- **No data export endpoints** (PDF/Excel report generation)
- **Celery configured** but only 2 periodic tasks (session/token cleanup)

---

## TASK 2: INTEGRATION PLAN BY TIER

### Tier 1: Major ERPs

#### SAP S/4HANA / ECC
| Data Flow | DTSG Entity | SAP Entity | Protocol | Direction |
|-----------|-------------|------------|----------|-----------|
| Chart of Accounts | `Account` | GL Account Master (SKA1/SKAT) | OData / RFC | Bidirectional |
| Cost Centers | `CostCenter` | Cost Center (CSKS/CSKT) | OData | Bidirectional |
| Vendors | `Vendor` | Business Partner (BUT000) | OData / IDoc | Bidirectional |
| Customers | `Customer` | Business Partner (BUT000) | OData / IDoc | Bidirectional |
| Purchase Orders | `PurchaseOrder` | PO (EKKO/EKPO) | OData / IDoc | Bidirectional |
| Invoices | `VendorInvoice` / `CustomerInvoice` | FI Document (BKPF/BSEG) | OData / IDoc | Bidirectional |
| Journals | `JournalHeader` / `JournalLine` | FI Posting (BKPF/BSEG) | OData / BAPI | DTSG -> SAP |
| Inventory | `Item` / `StockMovement` | Material Master (MARA) / Movement (MSEG) | OData / IDoc | Bidirectional |
| Employees | `Employee` | HR Master (PA0001) | OData | SAP -> DTSG |

**Technical approach**: Use SAP OData V4 APIs for S/4HANA, RFC/BAPI for ECC via PyRFC. IDocs for batch master data sync.

#### Microsoft Dynamics 365
| Data Flow | DTSG Entity | Dynamics Entity | Protocol |
|-----------|-------------|----------------|----------|
| Accounts | `Account` | `ledgerChartOfAccounts` | Dataverse / Business Central API |
| Customers | `Customer` | `customers` | Business Central API |
| Vendors | `Vendor` | `vendors` | Business Central API |
| Purchase Orders | `PurchaseOrder` | `purchaseOrders` | Business Central API |
| Sales Orders | `SalesOrder` | `salesOrders` | Business Central API |
| Invoices | `CustomerInvoice` | `salesInvoices` | Business Central API |
| Journals | `JournalHeader` | `generalJournalEntries` | Business Central API |
| Items | `Item` | `items` | Business Central API |

**Technical approach**: OAuth2 via Azure AD, REST API with OData query syntax. Use Dataverse Web API for D365 F&O, Business Central API for BC.

#### Oracle NetSuite
| Data Flow | DTSG Entity | NetSuite Record | Protocol |
|-----------|-------------|----------------|----------|
| Accounts | `Account` | Account | SuiteTalk REST |
| Customers | `Customer` | Customer | SuiteTalk REST |
| Vendors | `Vendor` | Vendor | SuiteTalk REST |
| Invoices | `CustomerInvoice` | Invoice | SuiteTalk REST |
| Purchase Orders | `PurchaseOrder` | PurchaseOrder | SuiteTalk REST |
| Journal Entries | `JournalHeader` | JournalEntry | SuiteTalk REST |

**Technical approach**: Token-based auth (TBA), REST API with SuiteQL for complex queries.

#### Sage Intacct / Sage 300
| Data Flow | Protocol |
|-----------|----------|
| GL Accounts, AP/AR, Journals | Sage Intacct Web Services (XML) |
| Vendors, Customers, Items | Sage 300 Web API (REST) |

### Tier 2: Common Business Apps

#### Payment Gateways
| Provider | Integration Type | Use Case |
|----------|-----------------|----------|
| **Stripe** | REST API + Webhooks | Subscription billing, payment collection |
| **PayStack** | REST API + Webhooks | Nigerian payment processing (NGN focus) |
| **Flutterwave** | REST API + Webhooks | Pan-African payment processing |

#### Banking
| Standard | Format | Use Case |
|----------|--------|----------|
| **MT940** (SWIFT) | Fixed-width text | Bank statement import for reconciliation |
| **CAMT.053** (ISO 20022) | XML | Modern bank statement import |
| **OFX** | XML | Alternative bank statement format |
| **Open Banking** | REST API | Real-time balance/transaction feeds |

#### Tax Compliance
| System | Integration |
|--------|-------------|
| **FIRS (Nigeria)** | TIN validation, e-filing API |
| **VAT** | VAT return generation, MTD (UK), e-invoicing |
| **WHT** | Withholding tax certificate generation |

#### E-commerce
| Platform | Protocol | Data Flow |
|----------|----------|-----------|
| **Shopify** | REST + Webhooks | Orders -> Sales Orders, Products -> Items |
| **WooCommerce** | REST + Webhooks | Orders -> Sales Orders, Products -> Items |

#### CRM
| Platform | Protocol | Data Flow |
|----------|----------|-----------|
| **Salesforce** | REST + Bulk API | Accounts <-> Customers, Opportunities <-> Quotations |
| **HubSpot** | REST + Webhooks | Contacts <-> Customers, Deals <-> Opportunities |

### Tier 3: Infrastructure

| Category | Provider | Protocol |
|----------|----------|----------|
| **Email** | SendGrid / Mailgun | REST API + SMTP |
| **Storage** | AWS S3 / Azure Blob | SDK |
| **Reporting** | Power BI / Tableau | Embedded API, Direct SQL |
| **SSO** | Azure AD / Okta / LDAP | SAML 2.0 / OIDC / LDAP |

---

## TASK 3: INTEGRATION FRAMEWORK DESIGN

### 3.1 New Django App: `integrations/`

#### Directory Structure
```
integrations/
    __init__.py
    apps.py
    admin.py
    urls.py

    # Core Models
    models/
        __init__.py
        registry.py          # IntegrationProvider, TenantIntegration
        credentials.py       # CredentialVault, OAuthToken
        webhooks.py          # WebhookEndpoint, InboundWebhookLog
        sync.py              # SyncJob, SyncLog, SyncMapping
        data_mapping.py      # FieldMapping, DataTransformRule
        errors.py            # IntegrationError, RetryQueue

    # Serializers
    serializers/
        __init__.py
        registry.py
        credentials.py
        webhooks.py
        sync.py
        mapping.py

    # Views
    views/
        __init__.py
        registry.py          # IntegrationProvider CRUD, tenant activation
        webhooks_inbound.py   # Inbound webhook receiver
        webhooks_outbound.py  # Outbound webhook management
        sync.py               # Sync job management
        mapping.py             # Field mapping configuration
        api_gateway.py         # OAuth2 provider, API key auth

    # Connectors (one per integration target)
    connectors/
        __init__.py
        base.py               # BaseConnector abstract class
        sap/
            __init__.py
            connector.py      # SAPConnector
            mapping.py        # SAP field mappings
            auth.py           # SAP OAuth/Basic auth
        dynamics/
            __init__.py
            connector.py
            mapping.py
            auth.py
        netsuite/
            __init__.py
            connector.py
            mapping.py
            auth.py
        stripe/
            __init__.py
            connector.py
            webhooks.py       # Stripe webhook handler
        paystack/
            __init__.py
            connector.py
            webhooks.py
        flutterwave/
            __init__.py
            connector.py
            webhooks.py
        shopify/
            __init__.py
            connector.py
            webhooks.py
        woocommerce/
            __init__.py
            connector.py
            webhooks.py
        salesforce/
            __init__.py
            connector.py
            mapping.py
        hubspot/
            __init__.py
            connector.py
        banking/
            __init__.py
            mt940_parser.py
            camt053_parser.py
            ofx_parser.py
            reconciler.py

    # Celery Tasks
    tasks/
        __init__.py
        webhook_dispatch.py   # Async outbound webhook delivery
        sync_engine.py        # Scheduled sync tasks
        retry.py              # Retry failed operations

    # Data Formats
    formats/
        __init__.py
        chart_of_accounts.py  # CoA interchange format
        invoice.py            # Invoice interchange format
        journal_entry.py      # JE interchange format
        master_data.py        # Customer/Vendor interchange

    # Utilities
    utils/
        __init__.py
        encryption.py         # Fernet encryption for credentials
        rate_limiter.py       # Per-integration rate limiting
        signature.py          # Webhook signature verification
        transform.py          # Data transformation helpers

    migrations/
        __init__.py
```

### 3.2 Django Models

#### `integrations/models/registry.py`

```python
from django.db import models
from django.contrib.auth.models import User
from core.models import AuditBaseModel
from tenants.models import Client


class IntegrationProvider(models.Model):
    """Registry of available integration providers (global, not tenant-scoped)."""

    CATEGORY_CHOICES = [
        ('erp', 'ERP System'),
        ('payment', 'Payment Gateway'),
        ('banking', 'Banking'),
        ('ecommerce', 'E-Commerce'),
        ('crm', 'CRM'),
        ('tax', 'Tax Compliance'),
        ('email', 'Email Service'),
        ('storage', 'Cloud Storage'),
        ('reporting', 'Reporting/BI'),
        ('auth', 'Authentication/SSO'),
        ('payroll', 'Payroll'),
        ('custom', 'Custom'),
    ]

    AUTH_TYPE_CHOICES = [
        ('api_key', 'API Key'),
        ('oauth2', 'OAuth 2.0'),
        ('basic', 'Basic Auth'),
        ('token', 'Bearer Token'),
        ('certificate', 'Client Certificate'),
        ('saml', 'SAML'),
        ('custom', 'Custom'),
    ]

    code = models.CharField(max_length=50, unique=True, db_index=True)  # e.g. 'sap_s4hana', 'stripe', 'paystack'
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    auth_type = models.CharField(max_length=20, choices=AUTH_TYPE_CHOICES)

    # Configuration schema (JSON Schema defining required config fields)
    config_schema = models.JSONField(default=dict, help_text='JSON Schema for provider configuration')

    # Capabilities
    supports_inbound_webhook = models.BooleanField(default=False)
    supports_outbound_webhook = models.BooleanField(default=False)
    supports_real_time_sync = models.BooleanField(default=False)
    supports_batch_sync = models.BooleanField(default=False)
    supports_polling = models.BooleanField(default=False)

    # Available data types for sync
    supported_entities = models.JSONField(
        default=list,
        help_text='List of entity types: ["accounts", "invoices", "customers", "vendors", ...]'
    )

    # Metadata
    icon_url = models.URLField(blank=True)
    documentation_url = models.URLField(blank=True)
    base_url = models.URLField(blank=True, help_text='Default API base URL')
    api_version = models.CharField(max_length=20, blank=True)

    is_active = models.BooleanField(default=True)
    is_beta = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class TenantIntegration(AuditBaseModel):
    """Active integration instance for a specific tenant."""

    STATUS_CHOICES = [
        ('configured', 'Configured'),
        ('testing', 'Testing'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('error', 'Error'),
        ('disabled', 'Disabled'),
    ]

    SYNC_DIRECTION_CHOICES = [
        ('inbound', 'Inbound (External -> DTSG)'),
        ('outbound', 'Outbound (DTSG -> External)'),
        ('bidirectional', 'Bidirectional'),
    ]

    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='integrations')
    provider = models.ForeignKey(IntegrationProvider, on_delete=models.PROTECT, related_name='tenant_integrations')

    name = models.CharField(max_length=100, help_text='Friendly name for this integration instance')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='configured')
    sync_direction = models.CharField(max_length=20, choices=SYNC_DIRECTION_CHOICES, default='bidirectional')

    # Provider-specific configuration (validated against provider.config_schema)
    config = models.JSONField(default=dict, help_text='Provider-specific configuration')

    # Sync settings
    sync_enabled = models.BooleanField(default=False)
    sync_interval_minutes = models.PositiveIntegerField(default=60)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=20, blank=True)
    last_error = models.TextField(blank=True)

    # Rate limiting
    rate_limit_per_minute = models.PositiveIntegerField(default=60)
    rate_limit_per_hour = models.PositiveIntegerField(default=1000)

    # Entity mapping
    enabled_entities = models.JSONField(
        default=list,
        help_text='Entities enabled for sync: ["accounts", "invoices", ...]'
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['tenant', 'provider', 'name']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.provider.name} ({self.status})"
```

#### `integrations/models/credentials.py`

```python
from django.db import models
from django.conf import settings
from tenants.models import Client
from cryptography.fernet import Fernet
import json
import base64
import os


def _get_encryption_key():
    """Derive Fernet key from Django SECRET_KEY."""
    key_bytes = settings.SECRET_KEY.encode()[:32].ljust(32, b'\0')
    return base64.urlsafe_b64encode(key_bytes)


class CredentialVault(models.Model):
    """Encrypted credential storage for integration connections.

    All sensitive values (API keys, secrets, passwords, tokens) are
    encrypted at rest using Fernet symmetric encryption derived from
    Django's SECRET_KEY.
    """

    CREDENTIAL_TYPE_CHOICES = [
        ('api_key', 'API Key'),
        ('oauth2', 'OAuth 2.0 Credentials'),
        ('basic', 'Basic Auth'),
        ('token', 'Bearer Token'),
        ('certificate', 'Client Certificate'),
        ('custom', 'Custom Credentials'),
    ]

    integration = models.OneToOneField(
        'TenantIntegration', on_delete=models.CASCADE, related_name='credentials'
    )
    credential_type = models.CharField(max_length=20, choices=CREDENTIAL_TYPE_CHOICES)

    # Encrypted storage -- all sensitive data stored as encrypted JSON
    _encrypted_data = models.BinaryField(db_column='encrypted_data')

    # OAuth2-specific fields (non-sensitive metadata)
    oauth2_token_url = models.URLField(blank=True)
    oauth2_authorize_url = models.URLField(blank=True)
    oauth2_scope = models.CharField(max_length=500, blank=True)
    oauth2_token_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Credential Vault'

    def set_credentials(self, data: dict):
        """Encrypt and store credential data."""
        f = Fernet(_get_encryption_key())
        self._encrypted_data = f.encrypt(json.dumps(data).encode())

    def get_credentials(self) -> dict:
        """Decrypt and return credential data."""
        f = Fernet(_get_encryption_key())
        return json.loads(f.decrypt(bytes(self._encrypted_data)).decode())

    def __str__(self):
        return f"Credentials for {self.integration}"


class OAuthToken(models.Model):
    """Stores OAuth2 access/refresh tokens for active integrations."""

    credential = models.OneToOneField(CredentialVault, on_delete=models.CASCADE, related_name='oauth_token')

    _encrypted_access_token = models.BinaryField(db_column='encrypted_access_token')
    _encrypted_refresh_token = models.BinaryField(db_column='encrypted_refresh_token', null=True, blank=True)

    token_type = models.CharField(max_length=20, default='Bearer')
    scope = models.CharField(max_length=500, blank=True)
    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_access_token(self, token: str):
        f = Fernet(_get_encryption_key())
        self._encrypted_access_token = f.encrypt(token.encode())

    def get_access_token(self) -> str:
        f = Fernet(_get_encryption_key())
        return f.decrypt(bytes(self._encrypted_access_token)).decode()

    def set_refresh_token(self, token: str):
        f = Fernet(_get_encryption_key())
        self._encrypted_refresh_token = f.encrypt(token.encode())

    def get_refresh_token(self) -> str:
        if not self._encrypted_refresh_token:
            return ''
        f = Fernet(_get_encryption_key())
        return f.decrypt(bytes(self._encrypted_refresh_token)).decode()

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"OAuth token for {self.credential.integration}"
```

#### `integrations/models/webhooks.py`

```python
from django.db import models
from django.contrib.auth.models import User
from tenants.models import Client
import secrets


class WebhookEndpoint(models.Model):
    """Inbound webhook receiver endpoint per integration.

    Each active integration gets a unique webhook URL:
    /api/v2/integrations/webhooks/inbound/<uuid>/
    """

    integration = models.ForeignKey(
        'TenantIntegration', on_delete=models.CASCADE, related_name='webhook_endpoints'
    )

    # Unique endpoint identifier (used in URL)
    endpoint_id = models.UUIDField(unique=True, editable=False)

    # Verification
    secret_key = models.CharField(max_length=128)
    signature_header = models.CharField(
        max_length=50, default='X-Webhook-Signature',
        help_text='Header name containing the signature'
    )
    signature_algorithm = models.CharField(
        max_length=20, default='hmac-sha256',
        choices=[
            ('hmac-sha256', 'HMAC-SHA256'),
            ('hmac-sha1', 'HMAC-SHA1'),
            ('none', 'No Verification'),
        ]
    )

    # Subscribed events from external system
    subscribed_events = models.JSONField(default=list)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        import uuid
        if not self.endpoint_id:
            self.endpoint_id = uuid.uuid4()
        if not self.secret_key:
            self.secret_key = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Webhook endpoint {self.endpoint_id} for {self.integration}"


class InboundWebhookLog(models.Model):
    """Log of received inbound webhooks."""

    STATUS_CHOICES = [
        ('received', 'Received'),
        ('verified', 'Verified'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
        ('rejected', 'Rejected'),
    ]

    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='logs')

    event_type = models.CharField(max_length=100)
    headers = models.JSONField(default=dict)
    payload = models.JSONField(default=dict)
    raw_body = models.TextField(blank=True)

    source_ip = models.GenericIPAddressField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')
    processing_result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['endpoint', '-received_at']),
            models.Index(fields=['event_type', '-received_at']),
        ]

    def __str__(self):
        return f"{self.event_type} -> {self.endpoint.integration} ({self.status})"


class OutboundWebhookEvent(models.Model):
    """Extended outbound webhook events beyond the superadmin set.

    These are business-object events dispatched to external systems.
    """

    BUSINESS_EVENT_CHOICES = [
        # Accounting
        ('invoice.created', 'Invoice Created'),
        ('invoice.posted', 'Invoice Posted'),
        ('invoice.paid', 'Invoice Paid'),
        ('invoice.cancelled', 'Invoice Cancelled'),
        ('journal.posted', 'Journal Entry Posted'),
        ('journal.reversed', 'Journal Entry Reversed'),
        ('payment.created', 'Payment Created'),
        ('payment.posted', 'Payment Posted'),
        ('receipt.created', 'Receipt Created'),
        ('receipt.posted', 'Receipt Posted'),
        # Procurement
        ('purchase_order.created', 'Purchase Order Created'),
        ('purchase_order.approved', 'Purchase Order Approved'),
        ('purchase_order.cancelled', 'Purchase Order Cancelled'),
        ('grn.created', 'GRN Created'),
        ('grn.posted', 'GRN Posted'),
        # Sales
        ('sales_order.created', 'Sales Order Created'),
        ('sales_order.confirmed', 'Sales Order Confirmed'),
        ('sales_order.cancelled', 'Sales Order Cancelled'),
        ('delivery_note.created', 'Delivery Note Created'),
        ('quotation.sent', 'Quotation Sent'),
        # Inventory
        ('stock.adjusted', 'Stock Adjusted'),
        ('stock.transferred', 'Stock Transferred'),
        ('reorder.triggered', 'Reorder Alert Triggered'),
        ('item.created', 'Item Created'),
        ('item.updated', 'Item Updated'),
        # HRM
        ('employee.created', 'Employee Created'),
        ('employee.terminated', 'Employee Terminated'),
        ('payroll.completed', 'Payroll Run Completed'),
        ('leave.approved', 'Leave Approved'),
        # Workflow
        ('approval.pending', 'Approval Pending'),
        ('approval.approved', 'Approval Approved'),
        ('approval.rejected', 'Approval Rejected'),
    ]

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    module = models.CharField(max_length=30)
    payload_schema = models.JSONField(default=dict, help_text='JSON Schema for event payload')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['module', 'code']

    def __str__(self):
        return f"{self.code} - {self.name}"
```

#### `integrations/models/sync.py`

```python
from django.db import models
from django.contrib.auth.models import User
from tenants.models import Client


class SyncJob(models.Model):
    """Scheduled or on-demand sync job configuration."""

    SYNC_TYPE_CHOICES = [
        ('full', 'Full Sync'),
        ('incremental', 'Incremental Sync'),
        ('delta', 'Delta Sync (Change Detection)'),
    ]

    FREQUENCY_CHOICES = [
        ('realtime', 'Real-time (Webhook)'),
        ('5min', 'Every 5 Minutes'),
        ('15min', 'Every 15 Minutes'),
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('manual', 'Manual Only'),
    ]

    DIRECTION_CHOICES = [
        ('inbound', 'External -> DTSG'),
        ('outbound', 'DTSG -> External'),
    ]

    integration = models.ForeignKey(
        'TenantIntegration', on_delete=models.CASCADE, related_name='sync_jobs'
    )

    name = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50)  # e.g. 'accounts', 'invoices', 'customers'
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPE_CHOICES, default='incremental')
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='hourly')

    # Scheduling
    is_enabled = models.BooleanField(default=True)
    cron_expression = models.CharField(max_length=100, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    # Filters
    sync_filter = models.JSONField(
        default=dict, blank=True,
        help_text='Filter criteria: {"date_from": "2024-01-01", "status": "posted"}'
    )

    # State tracking for incremental sync
    last_sync_cursor = models.JSONField(
        default=dict, blank=True,
        help_text='Cursor for incremental sync: {"last_modified": "2024-01-01T00:00:00Z", "last_id": 123}'
    )

    # Statistics
    total_records_synced = models.BigIntegerField(default=0)
    total_errors = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.entity_type} - {self.direction})"


class SyncLog(models.Model):
    """Log of individual sync execution runs."""

    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('completed_with_errors', 'Completed with Errors'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    sync_job = models.ForeignKey(SyncJob, on_delete=models.CASCADE, related_name='logs')

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='running')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    records_processed = models.PositiveIntegerField(default=0)
    records_created = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    records_skipped = models.PositiveIntegerField(default=0)
    records_failed = models.PositiveIntegerField(default=0)

    error_details = models.JSONField(default=list, blank=True)

    # The cursor state after this run (for incremental)
    sync_cursor_snapshot = models.JSONField(default=dict, blank=True)

    triggered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['sync_job', '-started_at']),
        ]

    def __str__(self):
        return f"{self.sync_job.name} run at {self.started_at} ({self.status})"
```

#### `integrations/models/data_mapping.py`

```python
from django.db import models


class FieldMapping(models.Model):
    """Configurable field mapping between DTSG and external systems.

    Example: DTSG Account.code -> SAP GL_ACCOUNT, with optional transformation.
    """

    TRANSFORM_CHOICES = [
        ('none', 'No Transformation'),
        ('uppercase', 'To Uppercase'),
        ('lowercase', 'To Lowercase'),
        ('pad_left', 'Pad Left (Zeros)'),
        ('pad_right', 'Pad Right'),
        ('truncate', 'Truncate'),
        ('lookup', 'Lookup Table'),
        ('format_date', 'Format Date'),
        ('format_number', 'Format Number'),
        ('custom', 'Custom Expression'),
    ]

    integration = models.ForeignKey(
        'TenantIntegration', on_delete=models.CASCADE, related_name='field_mappings'
    )

    entity_type = models.CharField(max_length=50)  # e.g. 'account', 'invoice', 'customer'

    dtsg_field = models.CharField(max_length=100, help_text='DTSG model field path: "code", "customer.name"')
    external_field = models.CharField(max_length=100, help_text='External system field: "GL_ACCOUNT", "AccountNumber"')

    direction = models.CharField(max_length=20, choices=[
        ('inbound', 'External -> DTSG'),
        ('outbound', 'DTSG -> External'),
        ('bidirectional', 'Both Directions'),
    ], default='bidirectional')

    transform = models.CharField(max_length=20, choices=TRANSFORM_CHOICES, default='none')
    transform_params = models.JSONField(
        default=dict, blank=True,
        help_text='Parameters for transformation: {"length": 10, "pad_char": "0"}'
    )

    is_required = models.BooleanField(default=False)
    default_value = models.CharField(max_length=200, blank=True)

    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['entity_type', 'sort_order']
        unique_together = ['integration', 'entity_type', 'dtsg_field', 'external_field']

    def __str__(self):
        return f"{self.dtsg_field} <-> {self.external_field} ({self.entity_type})"


class ValueMapping(models.Model):
    """Lookup table for mapping discrete values between systems.

    Example: DTSG account_type 'Asset' -> SAP 'BSX'
    """

    field_mapping = models.ForeignKey(
        FieldMapping, on_delete=models.CASCADE, related_name='value_mappings'
    )

    dtsg_value = models.CharField(max_length=200)
    external_value = models.CharField(max_length=200)

    class Meta:
        unique_together = ['field_mapping', 'dtsg_value']

    def __str__(self):
        return f"{self.dtsg_value} <-> {self.external_value}"


class DataTransformRule(models.Model):
    """Complex data transformation rules for entity mapping."""

    integration = models.ForeignKey(
        'TenantIntegration', on_delete=models.CASCADE, related_name='transform_rules'
    )

    name = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50)

    # Python-safe expression for transformation
    # e.g. "'{fund_code}-{function_code}-{account_code}'"
    expression = models.TextField(help_text='Transformation expression')

    # Input/output field definitions
    input_fields = models.JSONField(default=list)
    output_field = models.CharField(max_length=100)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['entity_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.entity_type})"
```

#### `integrations/models/errors.py`

```python
from django.db import models


class IntegrationError(models.Model):
    """Persistent error log for integration failures."""

    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]

    integration = models.ForeignKey(
        'TenantIntegration', on_delete=models.CASCADE, related_name='errors'
    )

    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='error')
    error_code = models.CharField(max_length=50, blank=True)
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)

    # Context
    entity_type = models.CharField(max_length=50, blank=True)
    entity_id = models.CharField(max_length=100, blank=True)
    operation = models.CharField(max_length=50, blank=True)  # 'sync', 'webhook', 'api_call'

    # Resolution
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['integration', 'is_resolved', '-occurred_at']),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.message[:80]}"


class RetryQueue(models.Model):
    """Queue for retrying failed operations with exponential backoff."""

    STATUS_CHOICES = [
        ('pending', 'Pending Retry'),
        ('retrying', 'Retrying'),
        ('succeeded', 'Succeeded'),
        ('exhausted', 'Retries Exhausted'),
        ('cancelled', 'Cancelled'),
    ]

    integration = models.ForeignKey(
        'TenantIntegration', on_delete=models.CASCADE, related_name='retry_queue'
    )

    operation_type = models.CharField(max_length=50)  # 'webhook_delivery', 'sync', 'api_call'
    operation_data = models.JSONField(default=dict)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    max_retries = models.PositiveIntegerField(default=5)
    retry_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField()

    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_retry_at']
        indexes = [
            models.Index(fields=['status', 'next_retry_at']),
        ]

    def calculate_next_retry(self):
        """Exponential backoff: 1min, 2min, 4min, 8min, 16min."""
        from django.utils import timezone
        from datetime import timedelta
        delay = timedelta(minutes=2 ** self.retry_count)
        self.next_retry_at = timezone.now() + delay

    def __str__(self):
        return f"Retry {self.operation_type} (attempt {self.retry_count}/{self.max_retries})"
```

### 3.3 Base Connector Abstract Class

#### `integrations/connectors/base.py`

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger('dtsg.integrations')


@dataclass
class SyncResult:
    """Result of a sync operation."""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: List[Dict] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def total_processed(self):
        return self.created + self.updated + self.skipped + self.failed


class BaseConnector(ABC):
    """Abstract base class for all integration connectors.

    Every connector must implement:
    - authenticate(): Establish connection
    - test_connection(): Verify connectivity
    - get_entity() / list_entities(): Read from external system
    - push_entity(): Write to external system
    - handle_webhook(): Process inbound webhook
    """

    def __init__(self, integration):
        """
        Args:
            integration: TenantIntegration model instance
        """
        self.integration = integration
        self.config = integration.config
        self.credentials = None
        self._session = None

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the external system. Return True on success."""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test the connection. Return {'success': bool, 'message': str}."""
        pass

    @abstractmethod
    def get_entity(self, entity_type: str, entity_id: str) -> Optional[Dict]:
        """Fetch a single entity from the external system."""
        pass

    @abstractmethod
    def list_entities(self, entity_type: str, filters: Dict = None,
                      cursor: Dict = None) -> tuple:
        """Fetch a list of entities. Returns (records, next_cursor)."""
        pass

    @abstractmethod
    def push_entity(self, entity_type: str, data: Dict) -> Dict:
        """Push a single entity to the external system.
        Returns {'id': external_id, 'status': 'created'|'updated'}."""
        pass

    def handle_webhook(self, event_type: str, payload: Dict) -> Dict:
        """Process an inbound webhook event. Override in subclass.
        Returns {'status': 'processed', 'records_affected': N}."""
        raise NotImplementedError(f"Webhook handling not implemented for {self.__class__.__name__}")

    def map_inbound(self, entity_type: str, external_data: Dict) -> Dict:
        """Map external data to DTSG format using configured field mappings."""
        from integrations.models.data_mapping import FieldMapping
        mappings = FieldMapping.objects.filter(
            integration=self.integration,
            entity_type=entity_type,
            direction__in=['inbound', 'bidirectional'],
        ).order_by('sort_order')

        result = {}
        for m in mappings:
            value = external_data.get(m.external_field, m.default_value)
            if value and m.transform != 'none':
                value = self._apply_transform(m, value)
            if value or m.is_required:
                result[m.dtsg_field] = value
        return result

    def map_outbound(self, entity_type: str, dtsg_data: Dict) -> Dict:
        """Map DTSG data to external format using configured field mappings."""
        from integrations.models.data_mapping import FieldMapping
        mappings = FieldMapping.objects.filter(
            integration=self.integration,
            entity_type=entity_type,
            direction__in=['outbound', 'bidirectional'],
        ).order_by('sort_order')

        result = {}
        for m in mappings:
            value = dtsg_data.get(m.dtsg_field, m.default_value)
            if value and m.transform != 'none':
                value = self._apply_transform(m, value)
            if value or m.is_required:
                result[m.external_field] = value
        return result

    def _apply_transform(self, mapping, value):
        """Apply transformation to a field value."""
        t = mapping.transform
        params = mapping.transform_params or {}

        if t == 'uppercase':
            return str(value).upper()
        elif t == 'lowercase':
            return str(value).lower()
        elif t == 'pad_left':
            return str(value).zfill(params.get('length', 10))
        elif t == 'truncate':
            return str(value)[:params.get('length', 50)]
        elif t == 'lookup':
            from integrations.models.data_mapping import ValueMapping
            vm = ValueMapping.objects.filter(
                field_mapping=mapping, dtsg_value=str(value)
            ).first()
            return vm.external_value if vm else value
        return value

    def close(self):
        """Clean up connection resources."""
        self._session = None
```

### 3.4 URL Patterns

#### `integrations/urls.py`

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    registry, webhooks_inbound, webhooks_outbound,
    sync, mapping, api_gateway
)

router = DefaultRouter()
router.register(r'providers', registry.IntegrationProviderViewSet, basename='integration-provider')
router.register(r'connections', registry.TenantIntegrationViewSet, basename='tenant-integration')
router.register(r'sync-jobs', sync.SyncJobViewSet, basename='sync-job')
router.register(r'sync-logs', sync.SyncLogViewSet, basename='sync-log')
router.register(r'field-mappings', mapping.FieldMappingViewSet, basename='field-mapping')
router.register(r'errors', registry.IntegrationErrorViewSet, basename='integration-error')

urlpatterns = [
    # Standard CRUD via router
    path('', include(router.urls)),

    # Inbound webhooks (no auth required -- verified by signature)
    path('webhooks/inbound/<uuid:endpoint_id>/',
         webhooks_inbound.receive_webhook, name='inbound-webhook'),

    # Outbound webhook management
    path('webhooks/outbound/events/',
         webhooks_outbound.list_events, name='outbound-events'),
    path('webhooks/outbound/subscriptions/',
         webhooks_outbound.list_subscriptions, name='outbound-subscriptions'),

    # Connection testing
    path('connections/<int:pk>/test/',
         registry.test_connection, name='test-connection'),
    path('connections/<int:pk>/sync/',
         sync.trigger_sync, name='trigger-sync'),

    # OAuth2 callbacks
    path('oauth2/callback/<int:integration_id>/',
         api_gateway.oauth2_callback, name='oauth2-callback'),

    # Banking import
    path('banking/import-statement/',
         webhooks_inbound.import_bank_statement, name='import-bank-statement'),
]
```

**Registration in root urls.py** -- add to `v1_patterns` or create v2:

```python
# In dtsg_erp/urls.py, add to v1_patterns:
path('integrations/', include('integrations.urls')),
```

### 3.5 Standard Data Interchange Formats

#### `integrations/formats/chart_of_accounts.py`

```python
"""Standard interchange format for Chart of Accounts.

Maps between DTSG Account model and external ERP account structures.
Supports SAP GL Account, Dynamics 365 ledgerAccount, NetSuite Account.
"""

# DTSG -> Standard -> External
STANDARD_ACCOUNT_SCHEMA = {
    "account_code": "",          # DTSG: Account.code | SAP: SAKNR | D365: MainAccountId
    "account_name": "",          # DTSG: Account.name | SAP: TXT50 | D365: Name
    "account_type": "",          # Asset/Liability/Equity/Income/Expense
    "parent_code": "",           # Hierarchical parent
    "is_active": True,
    "currency_code": "",         # ISO 4217
    "is_reconciliation": False,
    "reconciliation_type": "",

    # Dimensional mapping
    "cost_center_code": "",      # DTSG: CostCenter.code | SAP: KOSTL
    "profit_center_code": "",    # DTSG: ProfitCenter.code | SAP: PRCTR
    "fund_code": "",             # DTSG: Fund.code (gov't accounting)
    "function_code": "",         # DTSG: Function.code
    "program_code": "",          # DTSG: Program.code
}

SAP_MAPPING = {
    "account_code": "SAKNR",
    "account_name": "TXT50",
    "account_type": "XBILK",      # Balance sheet indicator -> derive type
    "is_active": "XLOEV",         # Deletion flag (inverted)
    "cost_center_code": "KOSTL",
    "profit_center_code": "PRCTR",
}

DYNAMICS_365_MAPPING = {
    "account_code": "MainAccountId",
    "account_name": "Name",
    "account_type": "MainAccountCategory",
    "is_active": "IsSuspended",  # Inverted
}

NETSUITE_MAPPING = {
    "account_code": "acctNumber",
    "account_name": "acctName",
    "account_type": "acctType",
    "is_active": "isInactive",  # Inverted
    "parent_code": "parent",
}
```

#### `integrations/formats/invoice.py`

```python
"""Standard interchange format for Invoices.

Supports both Vendor (AP) and Customer (AR) invoices.
Maps to SAP FI Documents, Dynamics Sales/Purchase Invoices, UBL format.
"""

STANDARD_INVOICE_SCHEMA = {
    "invoice_number": "",
    "invoice_type": "",          # 'customer' | 'vendor'
    "invoice_date": "",          # ISO 8601
    "due_date": "",
    "currency_code": "",         # ISO 4217
    "exchange_rate": 1.0,

    # Parties
    "vendor_code": "",           # For AP invoices
    "customer_code": "",         # For AR invoices
    "party_name": "",
    "party_tax_id": "",

    # Amounts
    "subtotal": 0,
    "tax_amount": 0,
    "discount_amount": 0,
    "total_amount": 0,

    # References
    "purchase_order_number": "",
    "delivery_note_number": "",
    "external_reference": "",

    # Status
    "status": "",                # Draft/Posted/Paid/Cancelled
    "payment_status": "",        # Unpaid/Partial/Paid

    # Line items
    "lines": [
        {
            "line_number": 0,
            "item_code": "",
            "description": "",
            "quantity": 0,
            "unit_price": 0,
            "discount_percent": 0,
            "tax_code": "",
            "tax_rate": 0,
            "tax_amount": 0,
            "line_total": 0,
            "account_code": "",      # GL account
            "cost_center_code": "",
        }
    ],

    # Dimensional coding (government accounting)
    "fund_code": "",
    "function_code": "",
    "program_code": "",
}
```

### 3.6 Celery Tasks

#### `integrations/tasks/webhook_dispatch.py`

```python
from celery import shared_task
from django.utils import timezone
import hashlib
import hmac
import json
import logging
import requests
import time

logger = logging.getLogger('dtsg.integrations')


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    autoretry_for=(requests.ConnectionError, requests.Timeout),
    retry_backoff=True,
    retry_backoff_max=900,
)
def dispatch_webhook(self, webhook_config_id, event, payload):
    """Async webhook delivery with exponential backoff retry.

    Called by signal handlers when business events occur.
    """
    from superadmin.models import WebhookConfig, WebhookDelivery

    try:
        wh = WebhookConfig.objects.get(pk=webhook_config_id, is_active=True)
    except WebhookConfig.DoesNotExist:
        logger.warning(f"Webhook config {webhook_config_id} not found or inactive")
        return

    if event not in wh.subscribed_events:
        return

    body = json.dumps(payload)
    signature = hmac.new(
        wh.secret_key.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    delivery = WebhookDelivery.objects.create(
        webhook=wh,
        event=event,
        payload=payload,
        status='Pending',
        retry_attempt=self.request.retries,
    )

    start = time.time()
    try:
        resp = requests.post(
            wh.webhook_url,
            data=body,
            headers={
                'Content-Type': 'application/json',
                'X-Webhook-Signature': f"sha256={signature}",
                'X-Webhook-Event': event,
                'X-Webhook-Delivery': str(delivery.id),
            },
            timeout=wh.timeout_seconds,
        )
        duration = int((time.time() - start) * 1000)

        delivery.status = 'Success' if resp.status_code < 400 else 'Failed'
        delivery.status_code = resp.status_code
        delivery.response_body = resp.text[:2000]
        delivery.duration_ms = duration
        delivery.delivered_at = timezone.now()
        delivery.save()

        wh.last_triggered_at = timezone.now()
        wh.last_status_code = resp.status_code
        wh.save(update_fields=['last_triggered_at', 'last_status_code'])

        if resp.status_code >= 400:
            raise requests.HTTPError(f"HTTP {resp.status_code}")

    except Exception as e:
        duration = int((time.time() - start) * 1000)
        delivery.status = 'Failed'
        delivery.error_message = str(e)[:500]
        delivery.duration_ms = duration
        delivery.save()
        raise


@shared_task
def dispatch_business_event(tenant_id, event_code, payload):
    """Dispatch a business event to all subscribed webhooks for a tenant.

    Usage in views/signals:
        dispatch_business_event.delay(
            tenant_id=request.tenant.id,
            event_code='invoice.posted',
            payload={'invoice_id': inv.id, 'invoice_number': inv.number, ...}
        )
    """
    from superadmin.models import WebhookConfig

    webhooks = WebhookConfig.objects.filter(
        tenant_id=tenant_id,
        is_active=True,
    )

    for wh in webhooks:
        if event_code in wh.subscribed_events:
            dispatch_webhook.delay(wh.id, event_code, payload)
```

#### `integrations/tasks/sync_engine.py`

```python
from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger('dtsg.integrations')


@shared_task
def run_scheduled_syncs():
    """Celery Beat task: find and execute all due sync jobs.

    Add to CELERY_BEAT_SCHEDULE:
    'run-integration-syncs': {
        'task': 'integrations.tasks.sync_engine.run_scheduled_syncs',
        'schedule': 300,  # Every 5 minutes
    }
    """
    from integrations.models.sync import SyncJob

    due_jobs = SyncJob.objects.filter(
        is_enabled=True,
        integration__is_active=True,
        integration__status='active',
        next_run_at__lte=timezone.now(),
    ).select_related('integration', 'integration__provider')

    for job in due_jobs:
        execute_sync_job.delay(job.id)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def execute_sync_job(self, sync_job_id, triggered_by_id=None):
    """Execute a single sync job."""
    from integrations.models.sync import SyncJob, SyncLog
    from integrations.connectors import get_connector
    from django_tenants.utils import schema_context

    try:
        job = SyncJob.objects.select_related(
            'integration', 'integration__provider', 'integration__tenant'
        ).get(pk=sync_job_id)
    except SyncJob.DoesNotExist:
        return

    log = SyncLog.objects.create(
        sync_job=job,
        status='running',
        triggered_by_id=triggered_by_id,
    )

    try:
        connector = get_connector(job.integration)
        connector.authenticate()

        tenant = job.integration.tenant
        with schema_context(tenant.schema_name):
            if job.direction == 'inbound':
                result = _sync_inbound(connector, job)
            else:
                result = _sync_outbound(connector, job)

        log.records_created = result.created
        log.records_updated = result.updated
        log.records_skipped = result.skipped
        log.records_failed = result.failed
        log.error_details = result.errors
        log.status = 'completed' if result.failed == 0 else 'completed_with_errors'
        log.sync_cursor_snapshot = job.last_sync_cursor

        # Update job scheduling
        job.last_run_at = timezone.now()
        job.last_sync_cursor = result.errors  # Would be cursor in real impl
        _schedule_next_run(job)
        job.save()

    except Exception as e:
        log.status = 'failed'
        log.error_details = [{'error': str(e)}]
        logger.exception(f"Sync job {sync_job_id} failed: {e}")

    log.completed_at = timezone.now()
    log.save()

    # Update integration stats
    job.total_records_synced += log.records_created + log.records_updated
    job.total_errors += log.records_failed
    job.save(update_fields=['total_records_synced', 'total_errors'])


def _schedule_next_run(job):
    """Calculate next run time based on frequency."""
    from datetime import timedelta

    freq_map = {
        '5min': timedelta(minutes=5),
        '15min': timedelta(minutes=15),
        'hourly': timedelta(hours=1),
        'daily': timedelta(days=1),
        'weekly': timedelta(weeks=1),
    }
    delta = freq_map.get(job.frequency)
    if delta:
        job.next_run_at = timezone.now() + delta
    else:
        job.next_run_at = None  # Manual or realtime


def _sync_inbound(connector, job):
    """Pull data from external system into DTSG."""
    from integrations.connectors.base import SyncResult
    result = SyncResult()

    records, next_cursor = connector.list_entities(
        entity_type=job.entity_type,
        filters=job.sync_filter,
        cursor=job.last_sync_cursor,
    )

    for record in records:
        try:
            dtsg_data = connector.map_inbound(job.entity_type, record)
            # Entity-specific creation/update logic would go here
            result.created += 1
        except Exception as e:
            result.failed += 1
            result.errors.append({
                'record_id': record.get('id', 'unknown'),
                'error': str(e),
            })

    if next_cursor:
        job.last_sync_cursor = next_cursor

    return result


def _sync_outbound(connector, job):
    """Push data from DTSG to external system."""
    from integrations.connectors.base import SyncResult
    result = SyncResult()
    # Implementation would query DTSG models and push to external
    return result
```

### 3.7 API Gateway Additions

#### OAuth2 Provider (for external apps connecting TO DTSG)

```python
# integrations/views/api_gateway.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([AllowAny])
def oauth2_callback(request, integration_id):
    """Handle OAuth2 authorization code callback from external systems.

    Flow:
    1. User initiates connection in DTSG UI
    2. DTSG redirects to external system's authorize URL
    3. User approves access
    4. External system redirects back here with auth code
    5. We exchange code for access/refresh tokens
    6. Tokens stored encrypted in CredentialVault
    """
    from integrations.models.registry import TenantIntegration
    from integrations.models.credentials import CredentialVault, OAuthToken

    code = request.query_params.get('code')
    state = request.query_params.get('state')
    error = request.query_params.get('error')

    if error:
        return Response({'error': error}, status=400)

    try:
        integration = TenantIntegration.objects.get(pk=integration_id)
    except TenantIntegration.DoesNotExist:
        return Response({'error': 'Integration not found'}, status=404)

    # Exchange code for tokens (implementation depends on provider)
    from integrations.connectors import get_connector
    connector = get_connector(integration)
    tokens = connector.exchange_auth_code(code)

    # Store tokens
    vault = integration.credentials
    oauth_token, _ = OAuthToken.objects.update_or_create(
        credential=vault,
        defaults={
            'token_type': tokens.get('token_type', 'Bearer'),
            'scope': tokens.get('scope', ''),
            'expires_at': tokens['expires_at'],
        }
    )
    oauth_token.set_access_token(tokens['access_token'])
    if tokens.get('refresh_token'):
        oauth_token.set_refresh_token(tokens['refresh_token'])
    oauth_token.save()

    integration.status = 'active'
    integration.save(update_fields=['status'])

    # Redirect back to frontend
    from django.conf import settings
    return Response({'status': 'connected', 'redirect': f"{settings.FRONTEND_URL}/integrations/{integration_id}"})
```

#### API Key Authentication Middleware

```python
# integrations/authentication.py

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone


class IntegrationAPIKeyAuthentication(BaseAuthentication):
    """Authenticate requests using tenant API keys.

    Usage: Include header `X-API-Key: <key>` and `X-API-Secret: <secret>`

    Add to REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] or
    use per-view: authentication_classes = [IntegrationAPIKeyAuthentication]
    """

    def authenticate(self, request):
        api_key = request.META.get('HTTP_X_API_KEY')
        api_secret = request.META.get('HTTP_X_API_SECRET')

        if not api_key:
            return None  # Let other auth methods try

        from superadmin.models import TenantAPIKey
        from django_tenants.utils import schema_context

        with schema_context('public'):
            try:
                key_obj = TenantAPIKey.objects.select_related('tenant').get(
                    api_key=api_key,
                    is_active=True,
                )
            except TenantAPIKey.DoesNotExist:
                raise AuthenticationFailed('Invalid API key.')

        # Check expiry
        if key_obj.expires_at and key_obj.expires_at < timezone.now():
            raise AuthenticationFailed('API key has expired.')

        # Check secret
        if api_secret and key_obj.api_secret != api_secret:
            raise AuthenticationFailed('Invalid API secret.')

        # Check IP allowlist
        if key_obj.allowed_ips:
            client_ip = request.META.get('REMOTE_ADDR', '')
            allowed = [ip.strip() for ip in key_obj.allowed_ips.split(',')]
            if client_ip not in allowed:
                raise AuthenticationFailed('IP not allowed.')

        # Update last used
        key_obj.last_used_at = timezone.now()
        key_obj.save(update_fields=['last_used_at'])

        # Set tenant context
        request.META['HTTP_X_TENANT_DOMAIN'] = key_obj.tenant.domains.first().domain

        # Return the API key creator as the authenticated user
        return (key_obj.created_by, key_obj)
```

### 3.8 Sync Patterns Summary

| Pattern | Trigger | Latency | Use Case |
|---------|---------|---------|----------|
| **Real-time** | Webhook event | < 5 sec | Payment notifications, stock updates, order creation |
| **Near-real-time** | Polling (Celery Beat) | 5-15 min | Invoice sync, customer updates, price changes |
| **Batch** | Scheduled ETL | Daily/hourly | GL posting, payroll sync, CoA sync, bank statement import |
| **Request-response** | On-demand API call | Immediate | Balance inquiry, credit check, tax rate lookup |

---

## TASK 4: IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Weeks 1-4)

**Goal**: Integration Hub app, API Gateway, Webhook Framework

**Files to create**:

| File | Purpose |
|------|---------|
| `integrations/__init__.py` | App init |
| `integrations/apps.py` | Django app config, register in TENANT_APPS |
| `integrations/admin.py` | Admin registration for all models |
| `integrations/models/__init__.py` | Import all models |
| `integrations/models/registry.py` | IntegrationProvider, TenantIntegration |
| `integrations/models/credentials.py` | CredentialVault, OAuthToken |
| `integrations/models/webhooks.py` | WebhookEndpoint, InboundWebhookLog, OutboundWebhookEvent |
| `integrations/models/sync.py` | SyncJob, SyncLog |
| `integrations/models/data_mapping.py` | FieldMapping, ValueMapping, DataTransformRule |
| `integrations/models/errors.py` | IntegrationError, RetryQueue |
| `integrations/serializers/*.py` | DRF serializers for all models |
| `integrations/views/registry.py` | Provider list, integration CRUD, test connection |
| `integrations/views/webhooks_inbound.py` | Universal webhook receiver |
| `integrations/views/webhooks_outbound.py` | Event subscription management |
| `integrations/views/sync.py` | Sync job CRUD, manual trigger |
| `integrations/views/mapping.py` | Field mapping CRUD |
| `integrations/views/api_gateway.py` | OAuth2 callback, token management |
| `integrations/urls.py` | URL routing |
| `integrations/connectors/__init__.py` | Connector registry, get_connector() |
| `integrations/connectors/base.py` | BaseConnector ABC |
| `integrations/tasks/__init__.py` | Task registration |
| `integrations/tasks/webhook_dispatch.py` | Async webhook delivery |
| `integrations/tasks/sync_engine.py` | Scheduled sync engine |
| `integrations/tasks/retry.py` | Retry queue processor |
| `integrations/utils/encryption.py` | Fernet helpers |
| `integrations/utils/rate_limiter.py` | Per-integration rate limiter |
| `integrations/utils/signature.py` | Webhook signature verification |
| `integrations/authentication.py` | API Key auth class |
| `integrations/formats/*.py` | Standard interchange formats |

**Models to add**: ~12 new models (all listed above)

**Endpoints to build**:
- `GET/POST /api/v1/integrations/providers/` -- list/create providers
- `GET/POST /api/v1/integrations/connections/` -- list/create tenant integrations
- `GET/PUT/DELETE /api/v1/integrations/connections/<id>/` -- manage integration
- `POST /api/v1/integrations/connections/<id>/test/` -- test connection
- `POST /api/v1/integrations/webhooks/inbound/<uuid>/` -- receive webhook
- `GET/POST /api/v1/integrations/sync-jobs/` -- sync job CRUD
- `POST /api/v1/integrations/connections/<id>/sync/` -- trigger sync
- `GET/POST /api/v1/integrations/field-mappings/` -- mapping CRUD
- `GET /api/v1/integrations/errors/` -- error log

**Settings changes** (`dtsg_erp/settings.py`):
- Add `'integrations'` to `TENANT_APPS`
- Add `IntegrationAPIKeyAuthentication` to `DEFAULT_AUTHENTICATION_CLASSES`
- Add Celery Beat schedule for `run_scheduled_syncs`
- Add `'cryptography'` to requirements.txt

**Root URL change** (`dtsg_erp/urls.py`):
- Add `path('integrations/', include('integrations.urls'))` to `v1_patterns`

---

### Phase 2: Payment Gateway Integration (Weeks 5-8)

**Goal**: Stripe, PayStack, Flutterwave connectors for subscription billing and tenant payment collection

**Files to create**:

| File | Purpose |
|------|---------|
| `integrations/connectors/stripe/__init__.py` | |
| `integrations/connectors/stripe/connector.py` | StripeConnector: create charges, subscriptions, refunds |
| `integrations/connectors/stripe/webhooks.py` | Handle charge.succeeded, invoice.paid, etc. |
| `integrations/connectors/paystack/__init__.py` | |
| `integrations/connectors/paystack/connector.py` | PayStackConnector: initialize transaction, verify |
| `integrations/connectors/paystack/webhooks.py` | Handle charge.success, transfer.success |
| `integrations/connectors/flutterwave/__init__.py` | |
| `integrations/connectors/flutterwave/connector.py` | FlutterwaveConnector |
| `integrations/connectors/flutterwave/webhooks.py` | Handle payment events |

**Database seeds**: Create IntegrationProvider records for Stripe, PayStack, Flutterwave with correct config_schema

**Endpoints**:
- Inbound webhooks already handled by Phase 1 universal receiver
- `POST /api/v1/integrations/payments/initialize/` -- start payment flow
- `POST /api/v1/integrations/payments/verify/` -- verify payment

---

### Phase 3: Banking Integration (Weeks 9-12)

**Goal**: Bank statement import (MT940, CAMT.053), reconciliation automation

**Files to create**:

| File | Purpose |
|------|---------|
| `integrations/connectors/banking/__init__.py` | |
| `integrations/connectors/banking/mt940_parser.py` | Parse MT940 SWIFT bank statements |
| `integrations/connectors/banking/camt053_parser.py` | Parse ISO 20022 CAMT.053 XML |
| `integrations/connectors/banking/ofx_parser.py` | Parse OFX/QFX bank statements |
| `integrations/connectors/banking/reconciler.py` | Auto-match bank transactions to DTSG payments/receipts |
| `integrations/views/banking.py` | File upload, parse, review, reconcile endpoints |

**Endpoints**:
- `POST /api/v1/integrations/banking/import-statement/` -- upload bank statement file
- `GET /api/v1/integrations/banking/parsed-transactions/` -- review parsed transactions
- `POST /api/v1/integrations/banking/reconcile/` -- run auto-reconciliation
- `POST /api/v1/integrations/banking/match/` -- manual match

**Dependencies**: `mt940` (PyPI package for MT940), `lxml` (for CAMT.053 XML)

---

### Phase 4: SAP / Dynamics Connectors (Weeks 13-20)

**Goal**: Bidirectional sync with SAP S/4HANA and Microsoft Dynamics 365

**Files to create**:

| File | Purpose |
|------|---------|
| `integrations/connectors/sap/__init__.py` | |
| `integrations/connectors/sap/connector.py` | SAPConnector: OData client for S/4HANA |
| `integrations/connectors/sap/mapping.py` | SAP-specific field mappings (SAKNR, BUKRS, etc.) |
| `integrations/connectors/sap/auth.py` | SAP OAuth2 / Basic auth / X.509 cert |
| `integrations/connectors/sap/idoc.py` | IDoc message parsing/generation |
| `integrations/connectors/dynamics/__init__.py` | |
| `integrations/connectors/dynamics/connector.py` | DynamicsConnector: Business Central / F&O API |
| `integrations/connectors/dynamics/mapping.py` | Dynamics field mappings |
| `integrations/connectors/dynamics/auth.py` | Azure AD OAuth2 flow |
| `integrations/connectors/netsuite/__init__.py` | |
| `integrations/connectors/netsuite/connector.py` | NetSuiteConnector: SuiteTalk REST |
| `integrations/connectors/netsuite/mapping.py` | NetSuite field mappings |
| `integrations/connectors/netsuite/auth.py` | Token-Based Auth (TBA) |

**Entity sync implementations**:
- Chart of Accounts (bidirectional)
- Customer/Vendor master data (bidirectional)
- Purchase Orders (DTSG -> SAP/Dynamics)
- Invoices (bidirectional)
- Journal Entries (DTSG -> SAP/Dynamics)
- Inventory items and stock levels (bidirectional)

**Dependencies**: `requests-oauthlib` (OAuth2), `msal` (Microsoft auth), `zeep` (SOAP for legacy SAP)

---

### Phase 5: E-commerce / CRM Integration (Weeks 21-26)

**Goal**: Shopify, WooCommerce, Salesforce, HubSpot connectors

**Files to create**:

| File | Purpose |
|------|---------|
| `integrations/connectors/shopify/connector.py` | ShopifyConnector: orders, products, customers |
| `integrations/connectors/shopify/webhooks.py` | Handle orders/create, products/update |
| `integrations/connectors/woocommerce/connector.py` | WooCommerceConnector |
| `integrations/connectors/woocommerce/webhooks.py` | Handle woocommerce_created_order, etc. |
| `integrations/connectors/salesforce/connector.py` | SalesforceConnector: Accounts, Opportunities, Contacts |
| `integrations/connectors/salesforce/mapping.py` | SOQL queries, field mapping |
| `integrations/connectors/hubspot/connector.py` | HubSpotConnector: Contacts, Deals, Companies |

**Data flows**:
- Shopify/WooCommerce Order -> DTSG Sales Order -> Customer Invoice
- Shopify/WooCommerce Product -> DTSG Inventory Item
- Salesforce Account <-> DTSG Customer
- Salesforce Opportunity <-> DTSG Quotation/Sales Order
- HubSpot Contact <-> DTSG Customer/Lead

**Dependencies**: `shopifyapi`, `woocommerce` (PyPI), `simple-salesforce`

---

## APPENDIX A: settings.py Changes Summary

```python
# Add to TENANT_APPS (in dtsg_erp/settings.py):
TENANT_APPS = [
    ...
    'integrations',
]

# Add API Key auth to REST_FRAMEWORK:
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'core.authentication.ExpiringTokenAuthentication',
        'integrations.authentication.IntegrationAPIKeyAuthentication',
    ],
    ...
}

# Add Celery Beat tasks:
CELERY_BEAT_SCHEDULE = {
    ...
    'run-integration-syncs': {
        'task': 'integrations.tasks.sync_engine.run_scheduled_syncs',
        'schedule': 300,  # 5 minutes
    },
    'process-retry-queue': {
        'task': 'integrations.tasks.retry.process_retry_queue',
        'schedule': 60,  # 1 minute
    },
}

# Encryption key for credential vault:
INTEGRATION_ENCRYPTION_KEY = os.getenv('INTEGRATION_ENCRYPTION_KEY', '')
```

## APPENDIX B: requirements.txt Additions

```
# Phase 1: Foundation
cryptography>=42.0       # Fernet encryption for credential vault

# Phase 2: Payment Gateways
stripe>=8.0              # Stripe Python SDK
# paystackapi            # PayStack (or use requests directly)

# Phase 3: Banking
mt940>=4.0               # MT940 bank statement parser
lxml>=5.0                # XML parsing for CAMT.053

# Phase 4: ERP Connectors
requests-oauthlib>=1.3   # OAuth2 for SAP/Dynamics
msal>=1.28               # Microsoft Authentication Library
# pyrfc                  # SAP RFC (optional, requires SAP NW RFC SDK)

# Phase 5: E-commerce/CRM
simple-salesforce>=1.12  # Salesforce API
# shopify-python-api     # Shopify Admin API
```

## APPENDIX C: Migration Dependencies

The `integrations` app depends on:
- `tenants` (for `Client` FK)
- `superadmin` (for extending `WebhookConfig` events)
- `core` (for `AuditBaseModel`)

Migration order:
1. `integrations.0001_initial` -- all integration models
2. Data migration to seed `IntegrationProvider` records
3. Data migration to seed `OutboundWebhookEvent` records
