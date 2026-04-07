from django.db import models
from django.utils import timezone
from core.models import AuditBaseModel

class ServiceAsset(AuditBaseModel):
    name = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100, unique=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    inventory_serial = models.ForeignKey('inventory.ItemSerialNumber', on_delete=models.SET_NULL, null=True, blank=True, help_text="Linked inventory serial number")

    def __str__(self):
        return f"{self.name} ({self.serial_number})"

class Technician(AuditBaseModel):
    """Technician/Resource tracking"""
    name = models.CharField(max_length=200)
    employee_code = models.CharField(max_length=50, unique=True)
    employee = models.ForeignKey(
        'hrm.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='technician_profile'
    )
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    specialization = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    # Availability tracking
    is_available = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['is_available']),
        ]

    @property
    def active_tickets(self):
        return self.assigned_tickets.filter(status__in=['Open', 'In Progress']).count()

    def __str__(self):
        return f"{self.name} - {self.employee_code}"

class ServiceTicket(AuditBaseModel):
    TICKET_STATUS = [
        ('Open', 'Open'),
        ('In Progress', 'In Progress'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]
    PRIORITY = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]

    ticket_number = models.CharField(max_length=50, unique=True)
    subject = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=TICKET_STATUS, default='Open')
    priority = models.CharField(max_length=20, choices=PRIORITY, default='Medium')
    
    asset = models.ForeignKey(ServiceAsset, on_delete=models.SET_NULL, null=True, blank=True)
    technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')

    due_date = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)

    # ── GL Account Overrides ───────────────────────────────────────────────────
    # Per-ticket GL account selection.  Falls back to DEFAULT_GL_ACCOUNTS when
    # null so that existing tickets and the general service configuration remain
    # unaffected.
    service_revenue_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='service_tickets_as_revenue',
        help_text="Override Service Revenue account. Falls back to DEFAULT_GL_ACCOUNTS['SERVICE_REVENUE'].",
    )
    service_expense_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='service_tickets_as_expense',
        help_text="Override Service Expense account. Falls back to DEFAULT_GL_ACCOUNTS['SERVICE_EXPENSE'].",
    )

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['technician']),
        ]

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            last = ServiceTicket.objects.order_by('-id').values_list('id', flat=True).first()
            next_num = (last or 0) + 1
            self.ticket_number = f"TKT-{next_num:06d}"
        if self.status == 'Resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()
        if self.technician and self.status == 'In Progress' and not self.started_at:
            self.started_at = timezone.now()
        super().save(*args, **kwargs)

        # Auto-check SLA on status transitions
        if self.status in ('In Progress', 'Resolved', 'Closed'):
            try:
                sla = self.sla
                if self.status == 'In Progress' and not sla.first_response_at:
                    sla.first_response_at = timezone.now()
                sla.check_sla()
            except SLATracking.DoesNotExist:
                pass

    def __str__(self):
        return f"[{self.ticket_number}] {self.subject}"

class SLATracking(models.Model):
    ticket = models.OneToOneField(ServiceTicket, related_name='sla', on_delete=models.CASCADE)
    response_time_limit = models.IntegerField(help_text="In minutes")
    resolution_time_limit = models.IntegerField(help_text="In minutes")
    
    first_response_at = models.DateTimeField(null=True, blank=True)
    is_response_met = models.BooleanField(default=False)
    is_resolution_met = models.BooleanField(default=False)

    def check_sla(self):
        ticket = self.ticket

        # Check response SLA
        if self.first_response_at and ticket.created_at:
            response_minutes = (self.first_response_at - ticket.created_at).total_seconds() / 60
            self.is_response_met = response_minutes <= self.response_time_limit

        # Check resolution SLA
        if ticket.resolved_at and ticket.created_at:
            resolution_minutes = (ticket.resolved_at - ticket.created_at).total_seconds() / 60
            self.is_resolution_met = resolution_minutes <= self.resolution_time_limit

        self.save()

    def __str__(self):
        return f"SLA {self.ticket}"

class WorkOrder(AuditBaseModel):
    """Work order for task assignment with cost tracking."""
    WORK_ORDER_STATUS = [
        ('Pending', 'Pending'),
        ('Assigned', 'Assigned'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    
    PRIORITY = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Urgent', 'Urgent'),
    ]

    work_order_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=WORK_ORDER_STATUS, default='Pending')
    priority = models.CharField(max_length=20, choices=PRIORITY, default='Medium')
    
    asset = models.ForeignKey(ServiceAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_orders')
    technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_orders')
    
    scheduled_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    
    labor_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    parts_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    notes = models.TextField(blank=True)

    # ── GL Account Overrides ───────────────────────────────────────────────────
    service_revenue_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_orders_as_revenue',
        help_text="Override Service Revenue account. Falls back to DEFAULT_GL_ACCOUNTS['SERVICE_REVENUE'].",
    )
    service_expense_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_orders_as_expense',
        help_text="Override Service Expense account. Falls back to DEFAULT_GL_ACCOUNTS['SERVICE_EXPENSE'].",
    )

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['technician']),
        ]

    def save(self, *args, **kwargs):
        if not self.work_order_number:
            last = WorkOrder.objects.order_by('-id').values_list('id', flat=True).first()
            next_num = (last or 0) + 1
            self.work_order_number = f"WO-{next_num:06d}"
        self.total_cost = self.labor_cost + self.parts_cost
        if self.status == 'Completed' and not self.completed_date:
            from django.utils import timezone
            self.completed_date = timezone.now().date()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.work_order_number}] {self.title}"


class WorkOrderMaterial(models.Model):
    """Materials/parts used in a work order."""
    work_order = models.ForeignKey(WorkOrder, related_name='materials', on_delete=models.CASCADE)
    item = models.ForeignKey('inventory.Item', on_delete=models.SET_NULL, null=True, blank=True, help_text="Linked inventory item for stock tracking")
    item_description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    
    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.item_description} x{self.quantity}"


class CitizenRequest(AuditBaseModel):
    """Public-facing citizen portal requests."""
    REQUEST_STATUS = [
        ('Submitted', 'Submitted'),
        ('Acknowledged', 'Acknowledged'),
        ('In Progress', 'In Progress'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]
    
    request_number = models.CharField(max_length=50, unique=True)
    citizen_name = models.CharField(max_length=200)
    citizen_email = models.EmailField()
    citizen_phone = models.CharField(max_length=20, blank=True)
    citizen_address = models.TextField(blank=True)
    
    category = models.CharField(max_length=100)
    subject = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=REQUEST_STATUS, default='Submitted')
    
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    
    related_ticket = models.ForeignKey(ServiceTicket, on_delete=models.SET_NULL, null=True, blank=True, related_name='citizen_requests')

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['category']),
        ]

    def save(self, *args, **kwargs):
        if not self.request_number:
            from django.utils.crypto import get_random_string
            self.request_number = f"CR-{get_random_string(8, allowed_chars='0123456789')}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.request_number}] {self.subject}"


class ServiceMetric(models.Model):
    """Service metrics and KPIs."""
    PERIOD_CHOICES = [
        ('Daily', 'Daily'),
        ('Weekly', 'Weekly'),
        ('Monthly', 'Monthly'),
        ('Quarterly', 'Quarterly'),
        ('Yearly', 'Yearly'),
    ]
    
    name = models.CharField(max_length=100)
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()

    class Meta:
        indexes = [
            models.Index(fields=['period']),
            models.Index(fields=['period_start']),
        ]

    total_tickets = models.IntegerField(default=0)
    open_tickets = models.IntegerField(default=0)
    resolved_tickets = models.IntegerField(default=0)
    closed_tickets = models.IntegerField(default=0)
    
    avg_response_time = models.DecimalField(max_digits=10, decimal_places=2, help_text="In minutes")
    avg_resolution_time = models.DecimalField(max_digits=10, decimal_places=2, help_text="In minutes")
    
    sla_response_met = models.IntegerField(default=0)
    sla_response_total = models.IntegerField(default=0)
    sla_resolution_met = models.IntegerField(default=0)
    sla_resolution_total = models.IntegerField(default=0)
    
    total_work_orders = models.IntegerField(default=0)
    completed_work_orders = models.IntegerField(default=0)
    total_labor_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    @property
    def response_sla_percentage(self):
        if self.sla_response_total > 0:
            return round((self.sla_response_met / self.sla_response_total) * 100, 2)
        return 0
    
    @property
    def resolution_sla_percentage(self):
        if self.sla_resolution_total > 0:
            return round((self.sla_resolution_met / self.sla_resolution_total) * 100, 2)
        return 0
    
    def __str__(self):
        return f"{self.name} ({self.period})"


class MaintenanceSchedule(AuditBaseModel):
    """Recurring maintenance schedule for assets."""
    FREQUENCY_CHOICES = [
        ('Daily', 'Daily'),
        ('Weekly', 'Weekly'),
        ('Monthly', 'Monthly'),
        ('Quarterly', 'Quarterly'),
        ('Yearly', 'Yearly'),
    ]
    
    asset = models.ForeignKey(ServiceAsset, related_name='schedules', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    next_run_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['frequency']),
        ]

    def __str__(self):
        return f"{self.title} ({self.frequency}) - {self.asset.name}"
    
    def generate_ticket(self):
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta
        
        ticket = ServiceTicket.objects.create(
            ticket_number=f"M-{self.id}-{self.next_run_date.strftime('%Y%m%d')}",
            subject=f"Maintenance: {self.title}",
            description=self.description,
            asset=self.asset,
            priority='Medium',
            due_date=timezone.now() + timedelta(days=7),
            status='Open'
        )
        
        if self.frequency == 'Daily':
            self.next_run_date += timedelta(days=1)
        elif self.frequency == 'Weekly':
            self.next_run_date += timedelta(weeks=1)
        elif self.frequency == 'Monthly':
            self.next_run_date += relativedelta(months=1)
        elif self.frequency == 'Quarterly':
            self.next_run_date += relativedelta(months=3)
        elif self.frequency == 'Yearly':
            self.next_run_date += relativedelta(years=1)
            
        self.save()
        return ticket
