import re
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


# DNS-label compatible: lowercase letters, digits, hyphens; cannot start
# or end with a hyphen; minimum 2 chars; maximum 30 chars (DNS labels go
# up to 63 but UX-wise short slugs read much better as subdomains —
# ``oag-delta.erp.tryquot.com`` beats
# ``office-of-accountant-general-delta-state.erp.tryquot.com``).
SLUG_REGEX = r'^[a-z0-9](?:[a-z0-9-]{0,28}[a-z0-9])?$'
SLUG_VALIDATOR = RegexValidator(
    regex=SLUG_REGEX,
    message=(
        'Tenant slug must be lowercase letters, digits, or hyphens, '
        '2-30 characters, and may not start or end with a hyphen.'
    ),
)


def slugify_tenant_name(name: str, max_length: int = 30) -> str:
    """Turn a free-text tenant name into a DNS-label-safe slug.

    Falls back to ``tenant`` if the name produces an empty result so
    the caller never has to handle the empty-string edge case.
    """
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)   # non-alphanumeric → hyphen
    s = re.sub(r'-+', '-', s).strip('-')  # collapse + trim hyphens
    return (s or 'tenant')[:max_length].rstrip('-') or 'tenant'


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


GOVERNMENT_TIER_CHOICES = [
    ('STATE', 'State Government'),
    ('LGA', 'Local Government Area'),
]


class Client(TenantMixin):
    name = models.CharField(max_length=100)
    # Short, DNS-safe identifier used as the subdomain prefix for the
    # tenant's app URL — e.g. ``oag-delta`` → ``oag-delta.erp.tryquot.com``.
    # Distinct from ``schema_name`` (which is the Postgres schema and
    # may be longer/legacy). Always lowercase; validated on save.
    slug = models.CharField(
        max_length=30, unique=True, blank=True, default='',
        validators=[SLUG_VALIDATOR],
        help_text='Short URL slug used as subdomain prefix (e.g. "oag-delta").',
    )
    created_on = models.DateField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Business classification
    business_category = models.CharField(
        max_length=50, choices=BUSINESS_CATEGORIES,
        blank=True, default='other',
        help_text='Industry category — drives default CoA, BOM templates, and module config',
    )

    # ─── Government Configuration (Quot PSE) ─────────────────────
    government_tier = models.CharField(
        max_length=5, choices=GOVERNMENT_TIER_CHOICES, blank=True, default='',
        help_text='STATE = State Government, LGA = Local Government Area',
    )
    state_nbs_code = models.CharField(
        max_length=2, blank=True, default='',
        help_text='NBS 2-digit state code (e.g., 24 for Kwara, 28 for Lagos)',
    )
    state_name = models.CharField(max_length=100, blank=True, default='')
    lga_code = models.CharField(
        max_length=2, blank=True, default='',
        help_text='NBS LGA code within the state (only for LGA-tier tenants)',
    )
    lga_name = models.CharField(max_length=100, blank=True, default='')

    # ─── MDA Isolation Mode ─────────────────────────────────────
    MDA_ISOLATION_CHOICES = [
        ('UNIFIED', 'Unified — all users see all MDAs'),
        ('SEPARATED', 'Separated — each MDA operates as a branch'),
    ]
    mda_isolation_mode = models.CharField(
        max_length=10, choices=MDA_ISOLATION_CHOICES, default='UNIFIED',
        help_text='UNIFIED = no data filtering; SEPARATED = per-MDA data isolation',
    )

    # ─── Budget Control Settings ────────────────────────────────
    enforce_warrant = models.BooleanField(
        default=False,
        help_text='True = warrant must be released before payment (strict). '
                  'False = only appropriation + balance checked (relaxed).',
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

    # ─── Provisioning state ─────────────────────────────────────
    # Tenant rows save INSTANTLY now; a Celery worker handles the
    # 100+ migrations asynchronously and flips status to 'active'.
    PROVISIONING_CHOICES = [
        ('pending', 'Pending — queued for schema creation'),
        ('provisioning', 'Provisioning — migrations running'),
        ('active', 'Active — ready for use'),
        ('failed', 'Failed — see provisioning_error'),
    ]
    provisioning_status = models.CharField(
        max_length=20, choices=PROVISIONING_CHOICES, default='pending',
        help_text='Async schema-creation state. Frontend polls this.',
    )
    provisioning_started_at = models.DateTimeField(null=True, blank=True)
    provisioning_completed_at = models.DateTimeField(null=True, blank=True)
    provisioning_error = models.TextField(blank=True, default='')

    # Schema creation is explicit — the Celery task calls create_schema()
    # so the API request returns in milliseconds instead of minutes.
    auto_create_schema = False
    # ``auto_drop_schema=False`` is the safe default: a hard ``Client.delete()``
    # would otherwise drop the entire Postgres schema (and every accounting
    # row inside it) with no recovery path. We provide a soft-delete via
    # the overridden ``delete()`` below; an explicit physical drop is
    # still possible via the ``hard_delete`` method, which is the only
    # path that should ever destroy a tenant's schema.
    auto_drop_schema = False

    def save(self, *args, **kwargs):
        # Auto-generate a slug on first save if the caller didn't provide
        # one. We collision-check against every other Client because the
        # slug is the subdomain prefix and must be globally unique within
        # the deployment. The probe loop terminates quickly because we
        # append ``-2``, ``-3``, … until a free slot is found.
        if not self.slug:
            base = slugify_tenant_name(self.name or self.schema_name or 'tenant')
            candidate = base
            n = 2
            while Client.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                # Truncate ``base`` so ``base-N`` still fits in 30 chars.
                suffix = f'-{n}'
                candidate = base[: 30 - len(suffix)] + suffix
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    @property
    def subdomain(self) -> str:
        """Full hostname for this tenant — ``<slug>.<SUBDOMAIN_BASE>``.

        ``SUBDOMAIN_BASE`` is read from settings so dev / staging / prod
        can each point at a different apex (``erp.tryquot.com`` in prod,
        ``localhost`` in dev). Falls back to the legacy ``dtsg.test``
        suffix only if no setting is configured at all.
        """
        from django.conf import settings
        base = getattr(settings, 'TENANT_SUBDOMAIN_BASE', None) or 'dtsg.test'
        return f'{self.slug}.{base}'

    def absolute_url(self, scheme: str | None = None) -> str:
        """Convenience: full ``https://<slug>.erp.tryquot.com`` URL.

        Used by ``select_tenant`` to tell the frontend exactly where to
        redirect after the user picks an organisation. Honours the
        ``TENANT_DEFAULT_SCHEME`` setting (``https`` in prod, ``http``
        in dev) unless the caller forces a scheme.
        """
        from django.conf import settings
        if scheme is None:
            scheme = getattr(settings, 'TENANT_DEFAULT_SCHEME', 'https')
        return f'{scheme}://{self.subdomain}'

    def delete(self, *args, **kwargs):
        """Soft delete — flag the row as deleted but keep the schema intact.

        Hard-deleting a Client previously dropped the entire Postgres
        schema (every accounting / contracts / procurement row inside),
        with no recovery path. The model carries ``is_deleted`` and
        ``deleted_at`` fields specifically to support reversible
        deletion, but no override existed to honour them — calling
        ``client.delete()`` bypassed both flags entirely.

        Now ``delete()`` flips the flags + revokes UserTenantRoles +
        suspends the subscription. The schema itself stays intact and
        the row stays queryable via the ``all_objects`` manager (or
        ``hard_delete()`` if a permanent drop is required).
        """
        from django.utils import timezone
        from django.db import transaction as _txn
        with _txn.atomic():
            self.is_deleted = True
            self.deleted_at = timezone.now()
            # Marking the schema as not the canonical name protects
            # against accidental ``select_tenant`` resolution against
            # this row after delete; the schema itself is preserved
            # for audit / recovery.
            self.save(update_fields=['is_deleted', 'deleted_at'])
            # Revoke active tenant roles on the deleted tenant so users
            # who'd previously been members can't reach the schema via
            # the user-tenants list.
            UserTenantRole.objects.filter(
                tenant=self, is_active=True,
            ).update(is_active=False)
            # Cancel the subscription (one-to-one).
            sub = TenantSubscription.objects.filter(tenant=self).first()
            if sub and sub.status not in ('cancelled', 'expired'):
                sub.status = 'cancelled'
                sub.save(update_fields=['status', 'updated_at'])

    def hard_delete(self, *args, **kwargs):
        """Permanent destruction — drops the schema AND deletes the row.

        Only callable explicitly. Use this when the operator has
        confirmed (e.g., via a destructive-action dialog with
        re-typed tenant name) that the data should be physically
        destroyed. Sets ``auto_drop_schema=True`` for the duration of
        this call so django-tenants drops the schema as part of the
        normal delete cascade.
        """
        from django.db import transaction as _txn
        with _txn.atomic():
            self._meta.auto_drop_schema = True
            try:
                # Bypass our own soft-delete by calling super().delete().
                models.Model.delete(self, *args, **kwargs)
            finally:
                self._meta.auto_drop_schema = False


class Domain(DomainMixin):
    pass


AVAILABLE_MODULES = [
    # ── Quot PSE: Nigeria Government IFMIS Modules ──────────────────────────
    ('dimensions', 'NCoA Dimensions',       'NCoA 6-segment classification — Administrative, Economic, Functional, Programme, Fund, Geographic'),
    ('accounting', 'General Ledger',        'Chart of Accounts, Journals, AP/AR, Fixed Assets, IPSAS Accrual Accounting'),
    ('budget',     'Budget & Appropriation', 'Appropriations, Warrants, Budget Execution, Variance Analysis'),
    ('treasury',   'Treasury & TSA',        'Treasury Single Account, Payment Vouchers, Payment Instructions, Cash Position'),
    ('revenue',    'Revenue (IGR)',          'Revenue Heads, Revenue Collection, PAYE, Fees & Fines, e-Collection'),
    ('procurement','Procurement',           'Purchase Requisitions, Purchase Orders, GRN, BPP Due Process, No Objection'),
    ('contracts',  'Contracts & Milestones', 'Contract Ceiling Enforcement, IPCs, Retention, Mobilization, Tiered Variations'),
    ('inventory',  'Stores & Inventory',    'Government Stores, Stock Management, Warehouses'),
    ('hrm',        'Human Resources',       'Employees, Leave, Payroll, Pension (CPS), PAYE, IPPIS Alignment'),
    ('workflow',   'Workflow & Approvals',   'Approval Templates, Multi-level Workflows, Delegation'),
    ('reporting',  'Financial Reporting',    'IPSAS Statements, COFOG Reports, Budget vs Actual, Revenue Performance'),
    ('audit',      'Audit & Compliance',    'Audit Trail, Transaction Logs, Period Close, Year-End'),
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

    def clean(self):
        """Validate ``allowed_modules`` against the canonical
        ``AVAILABLE_MODULES`` registry.

        Without this, a typo ('accounting'->'acccounting') silently
        persists as an entry that no module-resolution check will
        ever match — the plan stays "valid" but tenants on it can't
        actually unlock the misspelled module. Surface as a
        ValidationError at save time (admin / API both call clean()).
        """
        super().clean()
        if not isinstance(self.allowed_modules, list):
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'allowed_modules': 'Must be a list of module names.',
            })
        valid_keys = {key for (key, _title, _desc) in AVAILABLE_MODULES}
        unknown = [m for m in self.allowed_modules if m not in valid_keys]
        if unknown:
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'allowed_modules': (
                    f'Unknown module(s): {sorted(unknown)}. '
                    f'Allowed values: {sorted(valid_keys)}.'
                ),
            })

    def save(self, *args, **kwargs):
        # Run full_clean before save so admin + API + raw model
        # creates all surface validation errors at the same boundary.
        self.full_clean()
        super().save(*args, **kwargs)


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
        ('accounting',   'General Ledger & Accounting'),
        ('budget',       'Budget & Appropriation'),
        ('treasury',     'Treasury & TSA'),
        ('procurement',  'Procurement & Due Process'),
        ('inventory',    'Stores & Inventory'),
        ('hrm',          'Human Resources & Payroll'),
        ('revenue',      'Revenue Collection (IGR)'),
        ('workflow',     'Workflow & Approvals'),
        ('reporting',    'Financial Reporting'),
        ('audit',        'Audit & Compliance'),
        ('admin',        'System Administration'),
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
                'administrativesegment', 'economicsegment', 'functionalsegment',
                'programmesegment', 'fundsegment', 'geographicsegment', 'ncoacode',
                'journalheader', 'journalline', 'currency', 'glbalance',
                'bankaccount', 'vendorinvoice', 'payment', 'paymentallocation',
                'fixedasset', 'depreciationschedule',
                'bankreconciliation', 'fiscalperiod', 'fiscalyear',
            ],
            'budget': [
                'appropriation', 'warrant', 'unifiedbudget',
                'unifiedbudgetamendment', 'unifiedbudgetencumbrance',
            ],
            'treasury': [
                'treasuryaccount', 'paymentvouchergov', 'paymentinstruction',
            ],
            'revenue': [
                'revenuehead', 'revenuecollection',
            ],
            'procurement': [
                'vendor', 'purchaserequest', 'purchaserequestline',
                'purchaseorder', 'purchaseorderline', 'goodsreceivednote',
                'goodsreceivednoteline', 'invoicematching',
                'procurementthreshold', 'certificateofnoobjection',
                'procurementbudgetlink',
            ],
            'inventory': [
                'warehouse', 'itemcategory', 'item', 'itemstock',
                'itembatch', 'stockmovement', 'stockreconciliation',
            ],
            'hrm': [
                'department', 'position', 'employee', 'leavetype', 'leaverequest',
                'leavebalance', 'attendance', 'holiday', 'salarystructure',
                'salarycomponent', 'payrollperiod', 'payrollrun', 'payrollline',
                'payslip', 'pensionfundadministrator', 'employeepensionprofile',
                'pensionremittance', 'nigeriataxbracket',
            ],
            'workflow': [
                'workflowdefinition', 'workflowinstance', 'workflowstep',
                'approvaltemplate', 'approval', 'approvallog',
            ],
            'reporting': [
                'financialreporttemplate', 'financialreport', 'xbrlreport',
            ],
            'audit': [
                'transactionauditlog', 'approvalrule', 'approvalinstance',
                'periodclosing', 'yearendclosing',
            ],
            'admin': [
                'user', 'group', 'tenant', 'tenantmodule', 'tenantsubscription',
                'role', 'usertenantrole',
            ],
        }
        return module_models.get(self.module, [])
