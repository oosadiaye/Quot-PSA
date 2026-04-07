from django.db import models
from django.contrib.auth.models import User
from core.models import AuditBaseModel
from decimal import Decimal


class WorkCenter(AuditBaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    description = models.TextField(blank=True)
    
    capacity_hours = models.DecimalField(max_digits=8, decimal_places=2, help_text="Available hours per day")
    efficiency = models.DecimalField(max_digits=5, decimal_places=2, default=100, help_text="Efficiency percentage")
    
    labor_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Labor cost per hour")
    overhead_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Overhead cost per hour")
    
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return self.name


class BillOfMaterials(AuditBaseModel):
    ITEM_TYPE_CHOICES = [
        ('Finished', 'Finished Product'),
        ('Semi-Finished', 'Semi-Finished Product'),
        ('Raw Material', 'Raw Material'),
    ]
    
    item_code = models.CharField(max_length=50, unique=True, db_index=True)
    item_name = models.CharField(max_length=200, db_index=True)
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES, db_index=True)

    # Optional FK to inventory Item — enables direct price/cost lookups
    # instead of fragile string matching on item_name
    inventory_item = models.ForeignKey(
        'inventory.Item', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='bom_set',
        help_text='Link to inventory Item for price lookups and stock integration',
    )

    unit = models.CharField(max_length=20)
    standard_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True, db_index=True)
    requires_quality_inspection = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.item_code} - {self.item_name}"

    @property
    def total_cost(self):
        """P2FG-M1: BOM Cost Rollup - Calculate total BOM cost from component costs."""
        total = Decimal('0.00')
        for line in self.lines.all():
            component_cost = line.component.standard_cost or Decimal('0.00')
            total += component_cost * line.total_quantity
        return total.quantize(Decimal('0.01'))

    def calculate_and_update_cost(self):
        """P2FG-M1: Calculate BOM cost and update standard_cost."""
        self.standard_cost = self.total_cost
        self.save(update_fields=['standard_cost'])
        return self.standard_cost

    @property
    def component_count(self):
        """Return number of components in BOM."""
        return self.lines.count()

    @property
    def has_circular_reference(self):
        """Check if BOM has circular reference to itself."""
        visited = set()
        
        def check_recursive(bom_id, chain):
            if bom_id in chain:
                return True
            if bom_id in visited:
                return False
            visited.add(bom_id)
            chain.add(bom_id)
            
            bom = BillOfMaterials.objects.filter(pk=bom_id).first()
            if bom:
                for line in bom.lines.all():
                    if check_recursive(line.component_id, chain.copy()):
                        return True
            return False
        
        return check_recursive(self.pk, set())


class BOMLine(AuditBaseModel):
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='lines')
    component = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='used_in_boms')
    
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    unit = models.CharField(max_length=20)
    
    scrap_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['bom', 'component']

    def __str__(self):
        return f"{self.bom.item_code} requires {self.quantity} {self.unit} of {self.component.item_code}"

    @property
    def total_quantity(self):
        scrap = self.scrap_percentage or 0
        return self.quantity * (1 + scrap / 100)


class ProductionOrder(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending Approval'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Scheduled', 'Scheduled'),
        ('In Progress', 'In Progress'),
        ('On Hold', 'On Hold'),
        ('Done', 'Done'),
        ('Cancelled', 'Cancelled'),
    ]
    
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='production_orders')
    
    quantity_planned = models.DecimalField(max_digits=12, decimal_places=4)
    quantity_produced = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft', db_index=True)
    
    work_center = models.ForeignKey(WorkCenter, on_delete=models.SET_NULL, null=True, blank=True)
    
    notes = models.TextField(blank=True)

    # ── GL Account Overrides ───────────────────────────────────────────────────
    # Allow per-order GL account selection.  Falls back to DEFAULT_GL_ACCOUNTS
    # when null so that existing orders are unaffected.
    wip_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_orders_as_wip',
        help_text="Override WIP Inventory account. Falls back to DEFAULT_GL_ACCOUNTS['WIP_INVENTORY'].",
    )
    finished_goods_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_orders_as_finished_goods',
        help_text="Override Finished Goods account. Falls back to DEFAULT_GL_ACCOUNTS['FINISHED_GOODS'].",
    )

    class Meta:
        permissions = [
            ('approve_productionorder', 'Can approve production orders'),
        ]
        indexes = [
            models.Index(fields=['status', 'start_date']),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.bom.item_name} ({self.quantity_planned})"


class MaterialIssue(AuditBaseModel):
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='material_issues')
    bom_line = models.ForeignKey(BOMLine, on_delete=models.CASCADE)
    
    quantity_issued = models.DecimalField(max_digits=12, decimal_places=4)
    issue_date = models.DateField(db_index=True)
    
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['production_order', 'issue_date']),
        ]

    def __str__(self):
        return f"Issue for {self.production_order.order_number}"


class MaterialReceipt(AuditBaseModel):
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='material_receipts')
    
    quantity_received = models.DecimalField(max_digits=12, decimal_places=4)
    receipt_date = models.DateField(db_index=True)
    
    is_scrap = models.BooleanField(default=False)
    scrap_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['production_order', 'receipt_date']),
        ]

    def __str__(self):
        return f"Receipt for {self.production_order.order_number}"


class JobCard(AuditBaseModel):
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='job_cards')
    work_center = models.ForeignKey(WorkCenter, on_delete=models.SET_NULL, null=True)
    operator = models.ForeignKey(
        'hrm.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='job_cards'
    )

    sequence = models.PositiveIntegerField()
    operation_name = models.CharField(max_length=100)
    
    time_planned = models.DecimalField(max_digits=8, decimal_places=2, help_text="Planned time in hours")
    time_actual = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text="Actual time in hours")
    
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Done', 'Done'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_index=True)
    
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['sequence']
        indexes = [
            models.Index(fields=['production_order', 'status']),
            models.Index(fields=['work_center', 'status']),
        ]

    def __str__(self):
        return f"{self.production_order.order_number} - {self.operation_name}"


class Routing(AuditBaseModel):
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='routings')
    sequence = models.PositiveIntegerField()
    operation_name = models.CharField(max_length=100)
    work_center = models.ForeignKey(WorkCenter, on_delete=models.SET_NULL, null=True)
    
    time_hours = models.DecimalField(max_digits=8, decimal_places=2)
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['sequence']
        unique_together = ['bom', 'sequence']

    def __str__(self):
        return f"{self.bom.item_code} - Step {self.sequence}: {self.operation_name}"
