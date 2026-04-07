import logging
from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from core.models import AuditBaseModel

logger = logging.getLogger('dtsg')


class QAConfiguration(AuditBaseModel):
    """Configure when QA inspections are required"""
    
    INSPECTION_TRIGGERS = [
        ('GRN_Created', 'On GRN Creation'),
        ('Production_Started', 'On Production Start'),
        ('Production_Completed', 'On Production Completion'),
        ('Sales_Dispatch', 'On Sales Dispatch'),
        ('Manual', 'Manual Trigger Only'),
    ]
    
    INSPECTION_TYPES = [
        ('Incoming', 'Incoming Inspection'),
        ('In-Process', 'In-Process Inspection'),
        ('Final', 'Final Inspection'),
        ('Pre-Dispatch', 'Pre-Dispatch Inspection'),
    ]
    
    name = models.CharField(max_length=100)
    trigger_event = models.CharField(max_length=30, choices=INSPECTION_TRIGGERS)
    inspection_type = models.CharField(max_length=20, choices=INSPECTION_TYPES)
    is_required = models.BooleanField(default=True)
    auto_create = models.BooleanField(default=True)
    
    item_category = models.ForeignKey('inventory.ItemCategory', on_delete=models.SET_NULL, null=True, blank=True)
    product_type = models.ForeignKey('inventory.ProductType', on_delete=models.SET_NULL, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'QA Configuration'
        verbose_name_plural = 'QA Configurations'
    
    def __str__(self):
        return f"{self.name} ({self.get_trigger_event_display()})"


class QualityInspection(AuditBaseModel):
    INSPECTION_TYPE_CHOICES = [
        ('Incoming', 'Incoming (Received Goods)'),
        ('In-Process', 'In-Process (During Production)'),
        ('Final', 'Final (Before Delivery)'),
    ]
    
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Passed', 'Passed'),
        ('Failed', 'Failed'),
    ]
    
    inspection_number = models.CharField(max_length=50, unique=True)
    inspection_type = models.CharField(max_length=20, choices=INSPECTION_TYPE_CHOICES)
    
    reference_type = models.CharField(max_length=50, blank=True)
    reference_number = models.CharField(max_length=50, blank=True)
    
    inspection_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    inspector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    # ── GL Account Override ────────────────────────────────────────────────────
    # When set, quality posting uses this account for QC expense instead of the
    # global DEFAULT_GL_ACCOUNTS['QC_EXPENSE'] fallback.
    qc_expense_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quality_inspections_as_qc_expense',
        help_text="Override QC Expense account. Falls back to DEFAULT_GL_ACCOUNTS['QC_EXPENSE'].",
    )

    goods_received_note = models.ForeignKey(
        'procurement.GoodsReceivedNote', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='quality_inspections'
    )
    production_order = models.ForeignKey(
        'production.ProductionOrder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='quality_inspections'
    )
    item = models.ForeignKey(
        'inventory.Item', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='quality_inspections'
    )
    
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['inspection_type']),
            models.Index(fields=['inspection_date']),
            models.Index(fields=['inspector']),
        ]
        permissions = [
            ('approve_qualityinspection', 'Can approve quality inspections'),
        ]

    def save(self, *args, **kwargs):
        # Auto-generate inspection number
        if not self.inspection_number:
            last = QualityInspection.objects.order_by('-id').values_list('id', flat=True).first()
            next_num = (last or 0) + 1
            self.inspection_number = f"QI-{next_num:06d}"

        is_new = self.pk is None
        old_status = None
        if not is_new:
            try:
                old_status = QualityInspection.objects.only('status').get(pk=self.pk).status
            except QualityInspection.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # When inspection fails, auto-create an Approval request for disposition review
        if old_status != 'Failed' and self.status == 'Failed':
            self._create_disposition_approval()
            # QUAL-H1: Auto NCR Creation when inspection fails
            self._create_ncr_from_failure()
            # QUAL-H2: GRN Hold on Inspection Fail
            self._put_grn_on_hold()
            # QUAL-H3: Production Hold on Inspection Fail
            self._put_production_on_hold()

    def _create_disposition_approval(self):
        """Create an Approval request when inspection fails, requiring management review."""
        from workflow.models import Approval
        ct = ContentType.objects.get_for_model(self)

        # Don't create duplicate approvals
        if Approval.objects.filter(content_type=ct, object_id=self.pk, status__in=['Draft', 'Pending']).exists():
            return

        Approval.objects.create(
            content_type=ct,
            object_id=self.pk,
            title=f"Failed QC Inspection: {self.inspection_number}",
            description=(
                f"Quality inspection {self.inspection_number} ({self.get_inspection_type_display()}) "
                f"has FAILED. Disposition review required."
            ),
            status='Pending',
            requested_by=self.inspector,
        )
        logger.info(f"Approval request created for failed inspection {self.inspection_number}")

    def _create_ncr_from_failure(self):
        """QUAL-H1: Auto-create NCR when inspection fails."""
        try:
            failed_items = self.lines.filter(result='Fail').count()
            if failed_items == 0:
                return
            
            # Check if NCR already exists for this inspection
            if NonConformance.objects.filter(related_inspection=self).exists():
                return
            
            ncr_number = f"NCR-{self.inspection_number}"
            
            ncr = NonConformance.objects.create(
                ncr_number=ncr_number,
                title=f"Quality Non-Conformance from Inspection {self.inspection_number}",
                description=(
                    f"Inspection {self.inspection_number} ({self.get_inspection_type_display()}) "
                    f"failed with {failed_items} item(s) failing quality checks."
                ),
                severity='Major',
                status='Open',
                related_inspection=self,
                source_type=self.reference_type or 'Inspection',
                source_id=self.pk,
            )
            
            # Update NCR severity based on inspection type
            if self.inspection_type == 'Incoming':
                ncr.severity = 'Critical'
                ncr.save()
            
            logger.info(f"Auto-created NCR {ncr_number} for failed inspection {self.inspection_number}")
        except Exception as e:
            logger.error(f"Failed to auto-create NCR for inspection {self.inspection_number}: {e}")

    def _put_grn_on_hold(self):
        """QUAL-H2: Put GRN on hold when inspection fails."""
        if not self.goods_received_note:
            return
        
        try:
            grn = self.goods_received_note
            if hasattr(grn, 'status') and grn.status == 'Received':
                grn.status = 'On Hold'
                grn.save(update_fields=['status'], _allow_status_change=True)
                logger.info(f"GRN {grn.grn_number} put on hold due to failed inspection {self.inspection_number}")
        except Exception as e:
            logger.error(f"Failed to put GRN on hold for inspection {self.inspection_number}: {e}")

    def _put_production_on_hold(self):
        """QUAL-H3: Put Production Order on hold when inspection fails."""
        if not self.production_order:
            return
        
        try:
            from production.models import ProductionOrder
            production = self.production_order
            
            if hasattr(production, 'status') and production.status == 'In Progress':
                production.status = 'On Hold'
                production.save(update_fields=['status'])
                logger.info(f"Production Order {production.order_number} put on hold due to failed inspection {self.inspection_number}")
        except Exception as e:
            logger.error(f"Failed to put production on hold for inspection {self.inspection_number}: {e}")

    def __str__(self):
        return f"{self.inspection_number} - {self.inspection_type}"


class InspectionLine(AuditBaseModel):
    inspection = models.ForeignKey(QualityInspection, on_delete=models.CASCADE, related_name='lines')
    
    parameter = models.CharField(max_length=200)
    specification = models.TextField(blank=True)
    
    RESULT_CHOICES = [
        ('Pass', 'Pass'),
        ('Fail', 'Fail'),
        ('N/A', 'Not Applicable'),
    ]
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    
    measurement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.inspection.inspection_number} - {self.parameter}"


class NonConformance(AuditBaseModel):
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Under Investigation', 'Under Investigation'),
        ('Corrective Action', 'Corrective Action'),
        ('Closed', 'Closed'),
        ('Rejected', 'Rejected'),
    ]
    
    SEVERITY_CHOICES = [
        ('Critical', 'Critical'),
        ('Major', 'Major'),
        ('Minor', 'Minor'),
    ]
    
    ncr_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Open')
    
    related_inspection = models.ForeignKey(QualityInspection, on_delete=models.SET_NULL, null=True, blank=True, related_name='ncrs')
    
    source_type = models.CharField(max_length=50, blank=True, help_text="Procurement, Production, Sales, Inventory")
    source_id = models.PositiveIntegerField(null=True, blank=True, help_text="ID of source document")
    
    root_cause = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    preventive_action = models.TextField(blank=True)
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_ncrs')
    closed_date = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['severity']),
            models.Index(fields=['assigned_to']),
        ]

    def __str__(self):
        return f"{self.ncr_number} - {self.title}"


class CustomerComplaint(AuditBaseModel):
    STATUS_CHOICES = [
        ('Received', 'Received'),
        ('Under Investigation', 'Under Investigation'),
        ('Action Taken', 'Action Taken'),
        ('Closed', 'Closed'),
    ]
    
    complaint_number = models.CharField(max_length=50, unique=True)
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    
    subject = models.CharField(max_length=200)
    description = models.TextField()
    
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Received')
    
    # INT-9: Replaced CharField with proper FK to SalesOrder.
    # Legacy CharField kept temporarily as related_sales_order_ref for data migration.
    related_sales_order_ref = models.CharField(max_length=50, blank=True, help_text="Legacy: text reference kept for backward compat")
    related_sales_order = models.ForeignKey(
        'sales.SalesOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='complaints',
    )
    related_ncr = models.ForeignKey(NonConformance, on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints')
    
    resolution = models.TextField(blank=True)
    resolution_date = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.complaint_number} - {self.subject}"


class QualityChecklist(AuditBaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    checklist_type = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class QualityChecklistLine(AuditBaseModel):
    checklist = models.ForeignKey(QualityChecklist, on_delete=models.CASCADE, related_name='lines')
    
    sequence = models.PositiveIntegerField()
    parameter = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    is_critical = models.BooleanField(default=False)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"{self.checklist.name} - {self.sequence}. {self.parameter}"


class CalibrationRecord(AuditBaseModel):
    EQUIPMENT_TYPE_CHOICES = [
        ('Measuring', 'Measuring Equipment'),
        ('Testing', 'Testing Equipment'),
        ('Production', 'Production Equipment'),
    ]
    
    equipment_name = models.CharField(max_length=200)
    equipment_code = models.CharField(max_length=50, unique=True)
    equipment_type = models.CharField(max_length=20, choices=EQUIPMENT_TYPE_CHOICES)
    
    manufacturer = models.CharField(max_length=100, blank=True)
    model_number = models.CharField(max_length=50, blank=True)
    serial_number = models.CharField(max_length=50, blank=True)
    
    last_calibration_date = models.DateField(null=True, blank=True)
    next_calibration_date = models.DateField(null=True, blank=True)
    
    calibration_interval_months = models.PositiveIntegerField(default=12)
    
    STATUS_CHOICES = [
        ('Calibrated', 'Calibrated'),
        ('Due', 'Due'),
        ('Overdue', 'Overdue'),
        ('Out of Service', 'Out of Service'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Calibrated')
    
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.equipment_code} - {self.equipment_name}"


class SupplierQuality(AuditBaseModel):
    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.CASCADE, related_name='quality_records')
    
    evaluation_date = models.DateField()
    
    quality_score = models.DecimalField(max_digits=5, decimal_places=2, help_text="0-100")
    delivery_score = models.DecimalField(max_digits=5, decimal_places=2, help_text="0-100")
    overall_score = models.DecimalField(max_digits=5, decimal_places=2)
    
    RATING_CHOICES = [
        ('Excellent', 'Excellent'),
        ('Good', 'Good'),
        ('Average', 'Average'),
        ('Poor', 'Poor'),
    ]
    rating = models.CharField(max_length=20, choices=RATING_CHOICES)
    
    comments = models.TextField(blank=True)
    next_evaluation_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.vendor.name} - {self.rating}"
