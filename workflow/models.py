from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from core.models import AuditBaseModel
from django.contrib.auth.models import User
from decimal import Decimal


class GlobalApprovalSettings(AuditBaseModel):
    """Global settings to enable/disable approvals per module"""
    
    MODULE_CHOICES = [
        # ── Procurement P2P chain ──────────────────────────────────────────────
        ('PurchaseRequest', 'Purchase Requests'),
        ('PurchaseOrder', 'Purchase Orders'),
        ('GoodsReceivedNote', 'Goods Received Notes'),
        ('InvoiceVerification', 'Invoice Verification (3-Way Match)'),
        ('PurchaseReturn', 'Purchase Returns'),
        # ── Government IFMIS workflows ────────────────────────────────────────
        ('PaymentVoucher', 'Payment Vouchers'),
        ('Appropriation', 'Budget Appropriations'),
        ('Warrant', 'Cash Release Warrants'),
        ('RevenueWriteOff', 'Revenue Write-Offs'),
        ('AssetDisposal', 'Asset Disposals'),
        ('Budget', 'Budgets'),
        ('JournalEntry', 'Journal Entries'),
        ('LeaveRequest', 'Leave Requests'),
        ('PayrollRun', 'Payroll Runs'),
    ]
    
    APPROVAL_MODE_CHOICES = [
        ('Disabled', 'Approvals Disabled - Auto-approve'),
        ('Optional', 'Optional - Can approve manually'),
        ('Required', 'Required - Must go through approval'),
        ('Strict', 'Strict - All require approval'),
    ]
    
    module = models.CharField(max_length=30, choices=MODULE_CHOICES, unique=True)
    approval_mode = models.CharField(max_length=20, choices=APPROVAL_MODE_CHOICES, default='Required')
    
    use_amount_threshold = models.BooleanField(default=False)
    low_amount_threshold = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('10000'))
    high_amount_threshold = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('100000'))
    
    auto_approve_below_threshold = models.BooleanField(default=True)
    send_notifications = models.BooleanField(default=True)
    notify_requester = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Approval Settings'
        verbose_name_plural = 'Approval Settings'
    
    @classmethod
    def get_mode(cls, module):
        settings = cls.objects.filter(module=module).first()
        if not settings:
            return 'Required'
        return settings.approval_mode
    
    @classmethod
    def is_enabled(cls, module):
        mode = cls.get_mode(module)
        return mode in ['Required', 'Strict']
    
    @classmethod
    def should_auto_approve(cls, module, amount):
        settings = cls.objects.filter(module=module).first()
        if not settings:
            return False
        if settings.auto_approve_below_threshold and amount:
            return amount < (settings.low_amount_threshold or 0)
        return False
    
    def __str__(self):
        return f"{self.module} - {self.approval_mode}"


class ApprovalGroup(AuditBaseModel):
    """Group of approvers for a specific approval level."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    members = models.ManyToManyField('auth.User', related_name='approval_groups')

    # MDA-scoped: null = global group, set = MDA-specific approver group
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE,
        null=True, blank=True, related_name='approval_groups',
        help_text='MDA-scoped group; null = global group',
    )

    # Approval limits
    min_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ApprovalTemplate(AuditBaseModel):
    """Template for approval workflows."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Target model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)

    # MDA-scoped: null = global template, set = MDA-specific approval chain
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE,
        null=True, blank=True, related_name='approval_templates',
        help_text='MDA-scoped template; null = global template',
    )

    # Approval sequence
    APPROVAL_TYPES = [
        ('Sequential', 'Sequential - One after another'),
        ('Parallel', 'Parallel - All at once'),
        ('Any', 'Any - One approval enough'),
    ]
    approval_type = models.CharField(max_length=20, choices=APPROVAL_TYPES, default='Sequential')

    # Steps
    steps = models.ManyToManyField(ApprovalGroup, through='ApprovalTemplateStep')

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.content_type})"


class ApprovalTemplateStep(models.Model):
    """Links approval groups to templates with sequence"""
    template = models.ForeignKey(ApprovalTemplate, on_delete=models.CASCADE)
    group = models.ForeignKey(ApprovalGroup, on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField()

    class Meta:
        ordering = ['sequence']
        unique_together = ['template', 'sequence']

    def __str__(self):
        return f"{self.template.name} - Step {self.sequence}: {self.group.name}"


class Approval(AuditBaseModel):
    """
    Centralized approval model for all documents across modules.
    Replaces the old WorkflowInstance for a more unified approach.
    """
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
    ]
    
    # Document reference
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Approval details
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    # Current approval level
    current_step = models.PositiveIntegerField(default=1)
    total_steps = models.PositiveIntegerField(default=1)
    
    # Requester
    requested_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='approval_requests')
    
    # Template used
    template = models.ForeignKey(ApprovalTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.status}"


class ApprovalStep(AuditBaseModel):
    """Individual approval step for an approval request"""
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    
    approval = models.ForeignKey(Approval, related_name='steps', on_delete=models.CASCADE)
    step_number = models.PositiveIntegerField()
    approver_group = models.ForeignKey(ApprovalGroup, on_delete=models.SET_NULL, null=True)
    approver = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='approvals_given')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    comment = models.TextField(blank=True)
    acted_at = models.DateTimeField(null=True, blank=True)
    
    due_date = models.DateTimeField(null=True, blank=True)
    sla_hours = models.PositiveIntegerField(
        default=24, help_text="SLA in hours for this step"
    )
    
    class Meta:
        ordering = ['step_number']
        unique_together = ['approval', 'step_number']
    
    def __str__(self):
        return f"Step {self.step_number} - {self.status}"
    
    @property
    def is_overdue(self):
        if self.status != 'Pending':
            return False
        if self.due_date:
            from django.utils import timezone
            return timezone.now() > self.due_date
        return False
    
    @property
    def sla_status(self):
        if self.is_overdue:
            return 'Overdue'
        if self.due_date:
            from django.utils import timezone
            remaining = (self.due_date - timezone.now()).total_seconds() / 3600
            if remaining < 4:
                return 'At Risk'
            return 'On Track'
        return 'No SLA'


class ApprovalSLAViolation(models.Model):
    """WF-M1: Track SLA violations for monitoring"""
    approval_step = models.OneToOneField(ApprovalStep, on_delete=models.CASCADE, related_name='sla_violation')
    expected_completion = models.DateTimeField()
    actual_completion = models.DateTimeField(null=True, blank=True)
    delay_hours = models.PositiveIntegerField(default=0)
    severity = models.CharField(max_length=20, choices=[
        ('Low', 'Low - < 24 hours'),
        ('Medium', 'Medium - 24-48 hours'),
        ('High', 'High - 48-72 hours'),
        ('Critical', 'Critical - > 72 hours'),
    ])
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"SLA Violation: {self.approval_step}"


class ApprovalLog(AuditBaseModel):
    """Audit trail for all approval actions"""
    ACTION_CHOICES = [
        ('Submit', 'Submit'),
        ('Approve', 'Approve'),
        ('Reject', 'Reject'),
        ('Cancel', 'Cancel'),
        ('Escalate', 'Escalate'),
    ]
    
    approval = models.ForeignKey(Approval, related_name='logs', on_delete=models.CASCADE)
    step = models.ForeignKey(ApprovalStep, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    comment = models.TextField(blank=True)
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.approval.title} - {self.action}"


class ApprovalDelegation(AuditBaseModel):
    """
    Allows an approver to delegate their approval authority to a substitute
    for a specified date range (e.g. vacation, leave).
    """
    delegator = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='delegations_given',
        help_text='The approver who is delegating their authority',
    )
    delegate = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='delegations_received',
        help_text='The substitute approver',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.delegator} → {self.delegate} ({self.start_date} to {self.end_date})"

    @classmethod
    def get_active_delegate(cls, user, on_date=None):
        """Return the active delegate for a given user on a given date, or None."""
        from django.utils import timezone
        if on_date is None:
            on_date = timezone.now().date()
        delegation = cls.objects.filter(
            delegator=user,
            is_active=True,
            start_date__lte=on_date,
            end_date__gte=on_date,
        ).select_related('delegate').first()
        return delegation.delegate if delegation else None


# Legacy models for backward compatibility
class WorkflowDefinition(AuditBaseModel):
    name = models.CharField(max_length=100)
    target_model = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.target_model})"

class WorkflowStep(models.Model):
    workflow = models.ForeignKey(WorkflowDefinition, related_name='steps', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    sequence = models.PositiveIntegerField()
    approver_role = models.CharField(max_length=100, help_text="Placeholder for Role/Group based approval")
    
    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"{self.workflow.name} - Step {self.sequence}: {self.name}"

class WorkflowInstance(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    
    workflow = models.ForeignKey(WorkflowDefinition, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    current_step = models.ForeignKey(WorkflowStep, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Generic Link to the document (e.g., PurchaseOrder #12)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        return f"Workflow for {self.content_object} - {self.status}"

class WorkflowLog(AuditBaseModel):
    instance = models.ForeignKey(WorkflowInstance, related_name='logs', on_delete=models.CASCADE)
    step = models.ForeignKey(WorkflowStep, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50) # e.g., 'Submit', 'Approve', 'Reject'
    comment = models.TextField(blank=True)
    user_display = models.CharField(max_length=255) # Simplified user tracking for vertical slice

    def __str__(self):
        return f"{self.instance} - {self.action} by {self.user_display}"
