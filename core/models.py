from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import json
from decimal import Decimal, ROUND_HALF_UP

CURRENCY_PRECISION = Decimal('0.01')
QUANTITY_PRECISION = Decimal('0.01')


def quantize_currency(value):
    """Round a Decimal to 2 decimal places using banker's rounding."""
    if value is None:
        return Decimal('0.00')
    return Decimal(str(value)).quantize(CURRENCY_PRECISION, rounding=ROUND_HALF_UP)


def quantize_quantity(value):
    """Round a Decimal to 2 decimal places for quantities."""
    if value is None:
        return Decimal('0.00')
    return Decimal(str(value)).quantize(QUANTITY_PRECISION, rounding=ROUND_HALF_UP)


class AuditBaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated"
    )

    class Meta:
        abstract = True


class ImmutableModelMixin(models.Model):
    """
    Prevents editing or deleting records that are marked as 'Posted'.

    INT-15 NOTE: STATUS_CHOICES defined here are the base set. Child models
    (e.g. VendorInvoice, Payment, CustomerInvoice) override status choices
    with their own domain-specific values. This is intentional — the mixin
    only guards the 'Posted' state; the full status lifecycle is owned by
    each concrete model.
    """
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Posted', 'Posted'),
        ('Reversed', 'Reversed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    def save(self, *args, **kwargs):
        allow = kwargs.pop('_allow_status_change', False)
        if self.pk:
            try:
                old = type(self).objects.get(pk=self.pk)
                if old.status == 'Posted' and not allow:
                    raise ValidationError("Cannot modify a posted transaction. Reverse it instead.")
            except type(self).DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == 'Posted':
            raise ValidationError("Cannot delete a 'Posted' transaction.")
        return super().delete(*args, **kwargs)

    class Meta:
        abstract = True


class StatusTransitionMixin(models.Model):
    """
    Enforces valid status transitions. Subclasses must define:
        ALLOWED_TRANSITIONS = {
            'Draft': ['Pending', 'Cancelled'],
            'Pending': ['Approved', 'Rejected'],
            ...
        }
    and have a `status` CharField.
    """
    ALLOWED_TRANSITIONS = {}  # Override in subclass

    def validate_status_transition(self):
        if not self.pk or not self.ALLOWED_TRANSITIONS:
            return
        try:
            old = self.__class__.objects.only('status').get(pk=self.pk)
        except self.__class__.DoesNotExist:
            return
        if old.status == self.status:
            return
        allowed = self.ALLOWED_TRANSITIONS.get(old.status, [])
        if self.status not in allowed:
            raise ValidationError(
                f"Invalid status transition from '{old.status}' to '{self.status}'. "
                f"Allowed transitions: {', '.join(allowed) if allowed else 'none (terminal state)'}."
            )

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """
    Comprehensive audit trail for all financial transactions and important actions.
    This provides a centralized audit log that tracks:
    - Document changes (create, update, delete)
    - Status transitions
    - User actions
    - Field-level changes
    - API calls
    """
    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
        ('POST', 'Posted to GL'),
        ('UNPOST', 'Unposted from GL'),
        ('APPROVE', 'Approved'),
        ('REJECT', 'Rejected'),
        ('CANCEL', 'Cancelled'),
        ('VOID', 'Voided'),
        ('CLOSE', 'Closed'),
        ('OPEN', 'Opened'),
        ('LOCK', 'Locked'),
        ('UNLOCK', 'Unlocked'),
        ('LOGIN', 'User Login'),
        ('LOGOUT', 'User Logout'),
        ('VIEW', 'Viewed'),
        ('EXPORT', 'Exported'),
        ('IMPORT', 'Imported'),
    ]
    
    # Who and when
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='core_audit_logs'
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # What action
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    
    # Which object
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Object identification
    object_repr = models.CharField(max_length=500, blank=True, default='')
    object_key = models.CharField(max_length=200, blank=True, default='', db_index=True)
    
    # Changes tracking (for updates)
    changes = models.JSONField(default=dict, blank=True)
    previous_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    
    # Status changes
    old_status = models.CharField(max_length=50, blank=True, default='')
    new_status = models.CharField(max_length=50, blank=True, default='')
    
    # Financial amounts
    amount = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True, default='')
    
    # Additional context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    tenant = models.CharField(max_length=50, blank=True, default='', db_index=True)
    session_id = models.CharField(max_length=100, blank=True, default='')
    
    # Notes
    description = models.TextField(blank=True, default='')
    reference = models.CharField(max_length=200, blank=True, default='')
    
    class Meta:
        db_table = 'core_audit_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['content_type', 'object_id', '-timestamp']),
            models.Index(fields=['tenant', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['object_key', '-timestamp']),
        ]
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        return f"{self.action} on {self.object_repr} by {self.user} at {self.timestamp}"

    @classmethod
    def log_create(cls, user, instance, **kwargs):
        """Log creation of a new object"""
        return cls._log_action(
            user=user,
            action='CREATE',
            instance=instance,
            new_values=cls._get_field_values(instance),
            **kwargs
        )

    @classmethod
    def log_update(cls, user, instance, old_values, new_values, **kwargs):
        """Log update to an existing object"""
        changes = {}
        for field in old_values:
            if field in new_values and old_values[field] != new_values[field]:
                changes[field] = {
                    'old': old_values[field],
                    'new': new_values[field]
                }
        
        return cls._log_action(
            user=user,
            action='UPDATE',
            instance=instance,
            previous_values=old_values,
            new_values=new_values,
            changes=changes,
            **kwargs
        )

    @classmethod
    def log_delete(cls, user, instance, **kwargs):
        """Log deletion of an object"""
        return cls._log_action(
            user=user,
            action='DELETE',
            instance=instance,
            previous_values=cls._get_field_values(instance),
            **kwargs
        )

    @classmethod
    def log_status_change(cls, user, instance, old_status, new_status, **kwargs):
        """Log status change"""
        return cls._log_action(
            user=user,
            action=cls._get_action_for_status(new_status),
            instance=instance,
            old_status=old_status,
            new_status=new_status,
            **kwargs
        )

    @classmethod
    def log_action(cls, user, action, instance=None, **kwargs):
        """Generic log action method"""
        return cls._log_action(user=user, action=action, instance=instance, **kwargs)

    @classmethod
    def _log_action(cls, user, action, instance=None, **kwargs):
        """Internal method to create audit log entry"""
        from django.db import connection
        
        # Get tenant from connection if available
        tenant = getattr(connection, 'tenant', None)
        tenant_name = getattr(tenant, 'name', '') if tenant else kwargs.get('tenant', '')
        
        log_entry = cls(
            user=user,
            action=action,
            content_type=kwargs.get('content_type'),
            object_id=kwargs.get('object_id'),
            object_repr=str(instance) if instance else kwargs.get('object_repr', ''),
            object_key=kwargs.get('object_key', ''),
            changes=kwargs.get('changes', {}),
            previous_values=kwargs.get('previous_values', {}),
            new_values=kwargs.get('new_values', {}),
            old_status=kwargs.get('old_status', ''),
            new_status=kwargs.get('new_status', ''),
            amount=kwargs.get('amount'),
            currency=kwargs.get('currency', ''),
            ip_address=kwargs.get('ip_address'),
            user_agent=kwargs.get('user_agent', ''),
            tenant=tenant_name,
            description=kwargs.get('description', ''),
            reference=kwargs.get('reference', ''),
        )
        
        if instance and not log_entry.content_type:
            log_entry.content_type = ContentType.objects.get_for_model(instance)
            pk = instance.pk
            if isinstance(pk, int):
                log_entry.object_id = pk
            else:
                # Store non-integer PKs in object_repr since object_id is PositiveIntegerField
                log_entry.object_repr = f"{log_entry.object_repr} [pk={pk}]"
            
        log_entry.save()
        return log_entry

    @staticmethod
    def _get_field_values(instance):
        """Extract relevant field values from an instance"""
        values = {}
        skip_fields = {'id', 'password', '_state', 'created_at', 'updated_at'}
        
        from datetime import date, datetime as dt
        for field in instance._meta.get_fields():
            if field.name in skip_fields:
                continue
            try:
                value = getattr(instance, field.name, None)
                if value is not None:
                    if isinstance(value, Decimal):
                        values[field.name] = str(value)
                    elif isinstance(value, (dt, date)):
                        values[field.name] = value.isoformat()
                    elif hasattr(value, '__dict__'):
                        # Skip complex objects
                        continue
                    else:
                        values[field.name] = value
            except (AttributeError, ValueError):
                pass
                
        return values

    @staticmethod
    def _get_action_for_status(status):
        """Map status to audit action"""
        status_actions = {
            'Posted': 'POST',
            'Approved': 'APPROVE',
            'Rejected': 'REJECT',
            'Cancelled': 'CANCEL',
            'Void': 'VOID',
            'Closed': 'CLOSE',
            'Open': 'OPEN',
            'Locked': 'LOCK',
            'Active': 'OPEN',
        }
        return status_actions.get(status, 'UPDATE')


def log_model_changes(sender, instance, created, **kwargs):
    """Signal handler to automatically log model changes"""
    from django.db import connection
    
    user = getattr(connection, 'user', None)
    
    # Skip logging for AuditLog itself to avoid infinite recursion,
    # and skip Django internal models (e.g. migration recorder) that
    # don't belong to our app modules.
    if isinstance(instance, AuditLog):
        return
    if sender.__module__.startswith('django.'):
        return
    
    if created:
        AuditLog.log_create(user, instance)
    else:
        # Log update with current field values.
        # Note: old_values require pre_save capture (see log_status_changes
        # for status-specific tracking).  Here we log the new state so the
        # audit trail records *what* changed, even without a diff.
        new_values = AuditLog._get_field_values(instance)
        AuditLog.log_update(user, instance, old_values={}, new_values=new_values)


def log_status_changes(sender, instance, **kwargs):
    """Signal handler to log status changes on ImmutableModelMixin models"""
    if not hasattr(instance, 'status'):
        return

    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                from django.db import connection
                user = getattr(connection, 'user', None)
                AuditLog.log_status_change(user, instance, old_instance.status, instance.status)
        except sender.DoesNotExist:
            pass


# ---------------------------------------------------------------------------
# Per-tenant schema models
# These live in TENANT_APPS (core) so each tenant gets their own isolated
# copy in their own PostgreSQL schema. No tenant FK needed — the schema
# context is the natural partition key.
# ---------------------------------------------------------------------------

class TenantModule(models.Model):
    """
    Per-tenant module / feature toggle.

    Lives in each tenant's own PostgreSQL schema (core is in TENANT_APPS).
    The schema context provides isolation — no tenant FK is required.
    Superadmin cross-tenant operations must switch schema via schema_context().
    """
    module_name = models.CharField(max_length=50, unique=True)
    module_title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['module_title']

    def __str__(self):
        return f"{self.module_title} ({'active' if self.is_active else 'inactive'})"


class TenantSetupProfile(models.Model):
    """
    Per-tenant setup/onboarding state and core company configuration.

    Created during tenant signup. The admin setup wizard reads and writes
    this singleton to track wizard progress and store company-level settings
    that drive dashboard, reports, and module defaults.
    """
    # Wizard progress
    setup_completed = models.BooleanField(default=False)
    current_step = models.PositiveIntegerField(default=0)
    completed_steps = models.JSONField(default=list, blank=True)

    # Company information (collected in wizard)
    company_name = models.CharField(max_length=200, blank=True, default='')
    company_email = models.EmailField(blank=True, default='')
    company_phone = models.CharField(max_length=30, blank=True, default='')
    company_address = models.TextField(blank=True, default='')
    company_city = models.CharField(max_length=100, blank=True, default='')
    company_state = models.CharField(max_length=100, blank=True, default='')
    company_country = models.CharField(max_length=100, blank=True, default='')
    company_website = models.URLField(blank=True, default='')
    tax_id = models.CharField(max_length=50, blank=True, default='', help_text='TIN / VAT / Tax ID')
    registration_number = models.CharField(max_length=100, blank=True, default='')

    # Fiscal & accounting
    fiscal_year_start = models.PositiveIntegerField(
        default=1, help_text='Month number (1=Jan, 4=Apr, 7=Jul, 10=Oct)',
    )
    default_currency = models.CharField(max_length=10, blank=True, default='USD')
    timezone = models.CharField(max_length=50, blank=True, default='UTC')

    # Business config
    business_category = models.CharField(max_length=50, blank=True, default='other')
    employee_count_range = models.CharField(
        max_length=30, blank=True, default='',
        help_text='e.g. 1-10, 11-50, 51-200, 201-500, 500+',
    )
    annual_revenue_range = models.CharField(max_length=50, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tenant Setup Profile'
        verbose_name_plural = 'Tenant Setup Profiles'

    def __str__(self):
        status = 'Complete' if self.setup_completed else f'Step {self.current_step}'
        return f"Setup ({status})"


class Role(models.Model):
    """
    Fine-grained, module-based permissions for a tenant's users.

    Lives in each tenant's own PostgreSQL schema (core is in TENANT_APPS).
    The schema context provides isolation — no tenant FK is required.
    Superadmin must switch to a tenant's schema_context() to manage their roles.
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

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    module = models.CharField(max_length=20, choices=MODULE_CHOICES)
    role_type = models.CharField(max_length=20, choices=ROLE_TYPE_CHOICES)

    can_view = models.BooleanField(default=True)
    can_add = models.BooleanField(default=False)
    can_change = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_approve = models.BooleanField(default=False)
    can_post = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text='Default role assigned to new users in this module',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['module', 'role_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.module})"

    def get_permissions(self):
        """Return list of permission codenames based on role settings."""
        perms = []
        for model in self._get_module_models():
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
        """Return the list of model codenames governed by this role's module."""
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


# =============================================================================
# AUTHENTICATION & SECURITY MODELS
# =============================================================================

class LoginAttempt(models.Model):
    """Tracks login attempts for account lockout and security auditing.

    Progressive lockout policy:
    - 3 failed attempts: 5 minutes lockout
    - 5 failed attempts: 15 minutes lockout
    - 10 failed attempts: 30 minutes lockout
    - 15+ failed attempts: 2 hours lockout
    
    Resets after successful login.
    """
    LOCKOUT_TIERS = [
        (3, 5),      # 3 failures = 5 min lockout
        (5, 15),     # 5 failures = 15 min lockout
        (10, 30),    # 10 failures = 30 min lockout
        (15, 120),   # 15 failures = 2 hour lockout
    ]
    LOCKOUT_WINDOW_HOURS = 24  # Track failures within 24-hour window

    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    attempted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    was_successful = models.BooleanField(default=False)

    class Meta:
        ordering = ['-attempted_at']
        indexes = [
            models.Index(fields=['username', '-attempted_at']),
            models.Index(fields=['ip_address', '-attempted_at']),
        ]

    def __str__(self):
        status = 'OK' if self.was_successful else 'FAIL'
        return f"{self.username} [{status}] {self.attempted_at}"

    @classmethod
    def _get_lockout_duration(cls, failure_count):
        """Get lockout duration based on failure count.
        
        Returns the duration for the highest threshold reached.
        """
        for threshold, duration in reversed(cls.LOCKOUT_TIERS):
            if failure_count >= threshold:
                return duration
        return 5  # Default minimum: 5 minutes for 3 failures

    @classmethod
    def _recent_failures(cls, username):
        """Return (count, last_failure) within the tracking window."""
        from django.utils import timezone
        window_start = timezone.now() - timezone.timedelta(hours=cls.LOCKOUT_WINDOW_HOURS)
        qs = cls.objects.filter(
            username=username,
            was_successful=False,
            attempted_at__gte=window_start,
        )
        count = qs.count()
        last = qs.order_by('-attempted_at').first() if count else None
        return count, last

    @classmethod
    def is_locked_out(cls, username):
        """Check if an account is currently locked due to excessive failures."""
        from django.utils import timezone
        count, last_failure = cls._recent_failures(username)
        if count < 3:  # Minimum threshold
            return False
        if last_failure:
            lockout_duration = cls._get_lockout_duration(count)
            lockout_until = last_failure.attempted_at + timezone.timedelta(
                minutes=lockout_duration
            )
            return timezone.now() < lockout_until
        return False

    @classmethod
    def remaining_lockout_seconds(cls, username):
        """Return seconds remaining on lockout, or 0 if not locked."""
        from django.utils import timezone
        count, last_failure = cls._recent_failures(username)
        if count < 3 or not last_failure:
            return 0
        lockout_duration = cls._get_lockout_duration(count)
        lockout_until = last_failure.attempted_at + timezone.timedelta(
            minutes=lockout_duration
        )
        remaining = (lockout_until - timezone.now()).total_seconds()
        return max(0, int(remaining))

    @classmethod
    def record_attempt(cls, username, ip_address='', user_agent='', success=False):
        return cls.objects.create(
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            was_successful=success,
        )

    @classmethod
    def clear_failures(cls, username):
        """Clear failure history after successful login."""
        from django.utils import timezone
        window_start = timezone.now() - timezone.timedelta(hours=cls.LOCKOUT_WINDOW_HOURS)
        cls.objects.filter(
            username=username,
            was_successful=False,
            attempted_at__gte=window_start,
        ).delete()


class PasswordHistory(models.Model):
    """Stores hashed passwords to prevent reuse of recent passwords."""
    HISTORY_DEPTH = 5  # Number of past passwords to check

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='password_history',
    )
    password_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} — {self.created_at:%Y-%m-%d %H:%M}"

    @classmethod
    def record_password(cls, user):
        """Save the user's current password hash to history."""
        cls.objects.create(user=user, password_hash=user.password)
        # Trim old entries beyond HISTORY_DEPTH
        old_ids = (
            cls.objects.filter(user=user)
            .order_by('-created_at')
            .values_list('pk', flat=True)[cls.HISTORY_DEPTH:]
        )
        cls.objects.filter(pk__in=list(old_ids)).delete()

    @classmethod
    def is_password_reused(cls, user, raw_password):
        """Check if raw_password matches any of the last N password hashes."""
        from django.contrib.auth.hashers import check_password
        recent = cls.objects.filter(user=user).order_by('-created_at')[:cls.HISTORY_DEPTH]
        for entry in recent:
            if check_password(raw_password, entry.password_hash):
                return True
        return False


class EmailVerification(models.Model):
    """Email verification tokens sent after registration."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='email_verification',
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Email Verification'

    def __str__(self):
        status = 'verified' if self.is_verified else 'pending'
        return f"{self.user.username} [{status}]"

    def save(self, *args, **kwargs):
        if not self.created_at:
            from django.utils import timezone as tz
            self.created_at = tz.now()
        super().save(*args, **kwargs)

    @classmethod
    def create_for_user(cls, user):
        """Create or refresh a verification token for a user."""
        import secrets
        from django.utils import timezone as tz
        token = secrets.token_urlsafe(48)
        obj, _ = cls.objects.update_or_create(
            user=user,
            defaults={
                'token': token,
                'is_verified': False,
                'verified_at': None,
                'created_at': tz.now(),
            },
        )
        return obj

    def verify(self):
        """Mark as verified."""
        from django.utils import timezone
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save(update_fields=['is_verified', 'verified_at'])

    @property
    def is_expired(self):
        """Tokens expire after 72 hours."""
        from django.utils import timezone
        return self.created_at < timezone.now() - timezone.timedelta(hours=72)


class UserSession(models.Model):
    """Tracks active auth tokens as sessions for management/revocation."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='sessions',
    )
    token_key = models.CharField(max_length=40, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['user', '-last_activity']),
        ]

    def __str__(self):
        return f"{self.user.username} — {self.ip_address} — {'active' if self.is_active else 'revoked'}"

    @classmethod
    def create_for_token(cls, user, token_key, ip_address='', user_agent=''):
        obj, created = cls.objects.update_or_create(
            token_key=token_key,
            defaults={
                'user': user,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'is_active': True,
            },
        )
        return obj

    @classmethod
    def revoke_all(cls, user, exclude_token_key=None):
        """Revoke all sessions for a user, optionally keeping one."""
        from rest_framework.authtoken.models import Token
        from django_tenants.utils import schema_context
        qs = cls.objects.filter(user=user, is_active=True)
        if exclude_token_key:
            qs = qs.exclude(token_key=exclude_token_key)
        token_keys = list(qs.values_list('token_key', flat=True))
        qs.update(is_active=False)
        # Delete corresponding auth tokens
        with schema_context('public'):
            Token.objects.filter(key__in=token_keys).delete()
