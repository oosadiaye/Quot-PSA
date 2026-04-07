from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


BUSINESS_CATEGORIES = [
    ('agriculture', 'Agriculture & Farming'),
    ('manufacturing', 'Manufacturing'),
    ('construction', 'Construction'),
    ('trading', 'Trading & Distribution'),
    ('healthcare', 'Healthcare'),
    ('education', 'Education'),
    ('technology', 'Technology / IT Services'),
    ('hospitality', 'Hospitality / Food & Beverage'),
    ('mining', 'Mining & Extractive Industries'),
    ('logistics', 'Transportation & Logistics'),
    ('real_estate', 'Real Estate & Property'),
    ('nonprofit', 'Non-Profit / NGO'),
    ('government', 'Government / Public Sector'),
    ('retail', 'Retail'),
    ('energy', 'Energy & Utilities'),
    ('other', 'General / Other'),
]


class Client(TenantMixin):
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Business classification
    business_category = models.CharField(
        max_length=50, choices=BUSINESS_CATEGORIES,
        blank=True, default='other',
        help_text='Industry category — drives default CoA, BOM templates, and module config',
    )

    # Branding & company info
    logo = models.ImageField(upload_to='tenant_logos/', null=True, blank=True)
    tagline = models.CharField(max_length=255, blank=True, default='')
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    postal_code = models.CharField(max_length=20, blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    website = models.URLField(blank=True, default='')

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

class Domain(DomainMixin):
    pass


AVAILABLE_MODULES = [
    ('dimensions', 'Dimensions', 'Fund, Function, Program, Geo, MDA - Multi-dimensional accounting'),
    ('accounting', 'Accounting', 'Chart of Accounts, Journals, AP/AR, Fixed Assets'),
    ('budget', 'Budget Management', 'Budget Allocations, Variance Analysis'),
    ('procurement', 'Procurement', 'Purchase Requests, Purchase Orders, Vendors'),
    ('inventory', 'Inventory', 'Items, Stock Management, Warehouses'),
    ('sales', 'Sales Management', 'CRM, Quotations, Sales Orders'),
    ('hrm', 'Human Resources', 'Employees, Leave, Payroll'),
    ('production', 'Production', 'BOM, Work Orders, Manufacturing'),
    ('quality', 'Quality Management', 'Inspections, NCR, Complaints'),
    ('service', 'Service Management', 'Tickets, Work Orders, Maintenance'),
    ('workflow', 'Workflow & Approvals', 'Approval Templates, Workflows'),
]


class TenantModule(models.Model):
    """
    DEPRECATED — legacy public-schema module config.

    This model lives in the public PostgreSQL schema and was the original
    storage for per-tenant module toggles. It has been superseded by
    ``core.TenantModule``, which lives in each tenant's own schema and
    requires no tenant FK.

    Keep this class until all data has been migrated (run the management
    command ``migrate_module_data``) and all code references have been
    updated. It will be removed in a future migration.
    """
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='modules')
    module_name = models.CharField(max_length=50)
    module_title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['tenant', 'module_name']
        ordering = ['module_title']

    def __str__(self):
        return f"{self.tenant.name} - {self.module_title}"


class SubscriptionPlan(models.Model):
    """Subscription plans for tenants"""
    BILLING_CYCLE_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    
    PLAN_TYPE_CHOICES = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('standard', 'Standard'),
        ('premium', 'Premium'),
        ('enterprise', 'Enterprise'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES, default='basic')
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, default='monthly')
    max_users = models.IntegerField(default=5)
    max_storage_gb = models.IntegerField(default=10)
    allowed_modules = models.JSONField(default=list)
    features = models.JSONField(default=list, blank=True, help_text='List of feature dicts: [{category, name, included, limit}]')
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    trial_days = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price', 'name']

    def __str__(self):
        return f"{self.name} - ${self.price}/{self.billing_cycle}"


class TenantSubscription(models.Model):
    """Tracks subscription status for each tenant"""
    STATUS_CHOICES = [
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    tenant = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    payment_method = models.CharField(max_length=50, blank=True)
    last_payment_date = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.status}"


class UserTenantRole(models.Model):
    """Maps users to tenants they can access, with a coarse-grained role.

    Lives in the public schema (tenants app is SHARED_APPS only)
    so it's the single source of truth for user-tenant access.

    The `groups` M2M holds Django Groups assigned to this user for this specific
    tenant, enabling tenant-scoped permissions (a user can be Senior Manager in
    Tenant A but Standard User in Tenant B).

    Dual-role architecture:
        This model provides **access-level** roles (admin > senior_manager >
        manager > user > viewer) that control coarse authorization — e.g.,
        whether a user can access a tenant at all and what UI sections they see.

        Fine-grained, **module-level** permissions are handled by the separate
        ``Role`` model, which grants per-module CRUD+approve+post flags.

        Typical flow:
        1. Middleware checks ``UserTenantRole`` to verify tenant access.
        2. Views check ``Role`` (via ``get_permissions()``) to enforce
           per-module actions (can_add, can_approve, etc.).
    """
    ROLE_CHOICES = [
        ('admin', 'Tenant Admin'),
        ('senior_manager', 'Senior Manager'),
        ('manager', 'Mid-Level Manager'),
        ('user', 'Standard User'),
        ('viewer', 'Read-Only Viewer'),
    ]

    ROLE_HIERARCHY = {
        'admin': 5,
        'senior_manager': 4,
        'manager': 3,
        'user': 2,
        'viewer': 1,
    }

    user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='tenant_roles'
    )
    tenant = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='user_roles'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    groups = models.ManyToManyField(
        'auth.Group', blank=True, related_name='tenant_roles',
        help_text='Django Groups assigned to this user for this tenant'
    )
    is_active = models.BooleanField(default=True)
    
    # Language preference for this tenant
    preferred_language = models.CharField(
        max_length=10,
        blank=True,
        default='',
        help_text='User preferred language for this tenant (e.g., en, fr, es)'
    )
    timezone = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='User timezone for this tenant'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'tenant']
        ordering = ['tenant__name']

    def __str__(self):
        return f"{self.user.username} → {self.tenant.name} ({self.role})"

    @property
    def role_level(self):
        return self.ROLE_HIERARCHY.get(self.role, 0)

    def has_min_role(self, min_role):
        """Check if this role meets or exceeds the minimum required role."""
        min_level = self.ROLE_HIERARCHY.get(min_role, 0)
        return self.role_level >= min_level

    def get_all_permissions(self):
        """Return all permission codenames from tenant-scoped groups."""
        perms = set()
        for group in self.groups.prefetch_related('permissions__content_type').all():
            for perm in group.permissions.all():
                perms.add(f"{perm.content_type.app_label}.{perm.codename}")
        return perms


def get_tenant_settings(tenant):
    """Return module_name → is_active dict for a tenant.

    Reads from the tenant's own PostgreSQL schema (core.TenantModule).
    Falls back to the legacy public-schema TenantModule if the per-tenant
    table has no rows yet (supports gradual migration).
    """
    from django_tenants.utils import schema_context
    from core.models import TenantModule as PerTenantModule

    with schema_context(tenant.schema_name):
        rows = list(PerTenantModule.objects.values('module_name', 'is_active'))

    if rows:
        return {r['module_name']: r['is_active'] for r in rows}

    # Legacy fallback: read from old public-schema table during migration
    return {m.module_name: m.is_active for m in tenant.modules.all()}


def is_module_enabled(tenant, module_name):
    """Check if a specific module is enabled for a tenant.

    Reads from the tenant's own PostgreSQL schema (core.TenantModule).
    """
    from django_tenants.utils import schema_context
    from core.models import TenantModule as PerTenantModule

    with schema_context(tenant.schema_name):
        return PerTenantModule.objects.filter(
            module_name=module_name, is_active=True
        ).exists()


def is_dimensions_enabled(tenant):
    """Check if dimensions module is enabled for a tenant."""
    return is_module_enabled(tenant, 'dimensions')


def get_enabled_dimensions(tenant):
    """Get list of enabled dimension names for a tenant.
    
    Returns list like ['fund', 'function', 'program', 'geo', 'mda'] if enabled,
    or empty list if dimensions module is disabled.
    """
    if not is_dimensions_enabled(tenant):
        return []
    return ['fund', 'function', 'program', 'geo', 'mda']


class ModulePricing(models.Model):
    """Per-module pricing for the SaaS subscription model.

    Superadmin sets a price for each ERP module. Tenants select which
    modules they want, and their monthly total is the sum of selected
    module prices. This replaces the old bundle-plan model where a
    fixed set of modules was tied to a single flat price.
    """
    module_name = models.CharField(
        max_length=50, unique=True,
        help_text='Must match a key from AVAILABLE_MODULES (e.g. "accounting")',
    )
    title = models.CharField(max_length=100)
    tagline = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50, blank=True, default='AppstoreOutlined',
        help_text='Ant Design icon name for the frontend',
    )
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    features = models.JSONField(
        default=list, blank=True,
        help_text='List of feature strings shown on the pricing card',
    )
    highlights = models.JSONField(
        default=list, blank=True,
        help_text='Key benefits shown on the detail page',
    )
    is_active = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False, help_text='Show a "Popular" badge')
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'title']

    def __str__(self):
        return f"{self.title} — ${self.price_monthly}/mo"


class TenantPayment(models.Model):
    """Payment records for tenant subscriptions via bank transfer"""
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('bank_deposit', 'Bank Deposit'),
        ('mobile_money', 'Mobile Money'),
        ('cheque', 'Cheque'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('processed', 'Processed'),
    ]
    
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='payments')
    subscription = models.ForeignKey(TenantSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    transaction_reference = models.CharField(max_length=100, unique=True)
    
    payment_date = models.DateField()
    receipt_document = models.FileField(upload_to='tenant_payments/receipts/', null=True, blank=True)
    receipt_filename = models.CharField(max_length=255, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_payments')
    approved_date = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-payment_date', '-created_at']
    
    def __str__(self):
        return f"{self.tenant.name} - {self.amount} ({self.status})"


class Role(models.Model):
    """
    DEPRECATED — legacy public-schema role model.

    This model lives in the public PostgreSQL schema and was the original
    storage for per-tenant module-based roles. It has been superseded by
    ``core.Role``, which lives in each tenant's own schema and requires no
    tenant FK.

    Keep this class until all data has been migrated (run the management
    command ``migrate_module_data``) and all code references have been
    updated. It will be removed in a future migration.

    Relationship to ``UserTenantRole``:
        ``UserTenantRole`` controls *whether* a user can access a tenant and
        at what hierarchy level (admin/manager/viewer).  ``Role`` controls
        *what actions* a user can perform within each ERP module
        (e.g., can_add invoices in Accounting, can_approve purchase orders
        in Procurement).  Both systems work together — access is checked
        first via ``UserTenantRole``, then module permissions via ``Role``.
    """
    
    MODULE_CHOICES = [
        ('accounting', 'Accounting'),
        ('sales', 'Sales'),
        ('procurement', 'Procurement'),
        ('inventory', 'Inventory'),
        ('hrm', 'Human Resources'),
        ('budget', 'Budget'),
        ('production', 'Production'),
        ('quality', 'Quality'),
        ('service', 'Service'),
        ('technical', 'Technical'),
        ('admin', 'Administration'),
    ]
    
    ROLE_TYPE_CHOICES = [
        ('manager', 'Manager'),
        ('officer', 'Officer'),
    ]

    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=False)
    module = models.CharField(max_length=20, choices=MODULE_CHOICES)
    role_type = models.CharField(max_length=20, choices=ROLE_TYPE_CHOICES)
    
    can_view = models.BooleanField(default=True)
    can_add = models.BooleanField(default=False)
    can_change = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_approve = models.BooleanField(default=False)
    can_post = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text='Default role for new users in this module')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['tenant', 'code']
        ordering = ['module', 'role_type', 'name']

    def __str__(self):
        return f"{self.tenant.name} - {self.name} ({self.module})"

    def get_permissions(self):
        """Return list of permission codenames based on role settings."""
        perms = []
        model_names = self._get_module_models()
        
        for model in model_names:
            if self.can_view:
                perms.append(f'view_{model}')
            if self.can_add:
                perms.append(f'add_{model}')
            if self.can_change:
                perms.append(f'change_{model}')
            if self.can_delete:
                perms.append(f'delete_{model}')
            if self.can_approve:
                perms.append(f'approve_{model}')
            if self.can_post:
                perms.append(f'post_{model}')
        
        return perms

    def _get_module_models(self):
        """Get list of model names for the module."""
        module_models = {
            'accounting': [
                'fund', 'function', 'program', 'geo', 'account', 'mda',
                'journalheader', 'journalline', 'journalreversal', 'currency', 'glbalance',
                'budgetperiod', 'budget', 'budgetencumbrance', 'budgettransfer',
                'bankaccount', 'vendorinvoice', 'payment', 'paymentallocation',
                'customerinvoice', 'receipt', 'receiptallocation',
                'fixedasset', 'depreciationschedule', 'costcenter',
                'bankreconciliation', 'taxregistration', 'taxexemption', 'taxreturn', 
                'withholdingtax', 'taxcode', 'profitcenter', 'fiscalperiod', 'fiscalyear',
            ],
            'sales': [
                'customer', 'lead', 'opportunity', 'quotation', 'quotationline',
                'salesorder', 'salesorderline', 'deliverynote', 'deliverynoteline',
            ],
            'procurement': [
                'purchasetype', 'vendor', 'purchaserequest', 'purchaserequestline',
                'purchaseorder', 'purchaseorderline', 'goodsreceivednote', 
                'goodsreceivednoteline', 'invoicematching', 'vendorcreditnote',
                'vendordebitnote', 'purchasereturn', 'purchasereturnline',
            ],
            'inventory': [
                'warehouse', 'producttype', 'productcategory', 'itemcategory',
                'item', 'itemstock', 'itembatch', 'stockmovement',
                'stockreconciliation', 'stockreconciliationline', 'reorderalert',
                'itemserialnumber', 'batchexpiryalert',
            ],
            'hrm': [
                'department', 'position', 'employee', 'leavetype', 'leaverequest',
                'leavebalance', 'attendance', 'holiday', 'jobpost', 'candidate',
                'interview', 'onboardingtask', 'onboardingprogress', 'salarystructure',
                'salarycomponent', 'payrollperiod', 'payrollrun', 'payrollline',
                'payslip', 'performancecycle', 'performancegoal', 'performancereview',
            ],
            'budget': [
                'budgetallocation', 'budgetline', 'budgetvariance',
            ],
            'production': [
                'workcenter', 'billofmaterials', 'bomline', 'productionorder',
                'materialissue', 'materialreceipt', 'jobcard', 'routing',
            ],
            'quality': [
                'qualityinspection', 'inspectionline', 'nonconformance',
                'customercomplaint', 'qualitychecklist', 'qualitychecklistline',
                'calibrationrecord', 'supplierquality',
            ],
            'service': [
                'serviceasset', 'technician', 'serviceticket', 'slatracking',
                'workorder', 'workordermaterial', 'citizenrequest', 'servicemetric',
                'maintenanceschedule',
            ],
            'technical': [
                'serviceasset', 'serviceticket', 'workorder', 'technician',
            ],
            'admin': [
                'user', 'group', 'tenant', 'tenantmodule', 'tenantsubscription',
                'role', 'usertenantrole',
            ],
        }
        return module_models.get(self.module, [])
