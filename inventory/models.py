from django.db import models
from django.utils import timezone
from core.models import AuditBaseModel, ImmutableModelMixin
from django.contrib.auth.models import User
from accounting.models import Account
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class Item(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)



    sku = models.CharField(unique=True, max_length=50)

    name = models.CharField(max_length=200)

    description = models.TextField()

    unit_of_measure = models.CharField(max_length=20)

    total_quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    total_value = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])


    expense_account = models.ForeignKey(Account, models.PROTECT, blank=True, null=True)

    inventory_account = models.ForeignKey(Account, models.PROTECT, related_name='item_inventory_account_set', blank=True, null=True)


    barcode = models.CharField(max_length=50)

    is_active = models.BooleanField()

    max_stock = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    min_stock = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    reorder_point = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    reorder_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    selling_price = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal('0'))

    standard_price = models.DecimalField(
        max_digits=19, decimal_places=4, default=Decimal('0'),
        help_text='User-defined reference cost set at product creation. Used as cost price for Standard valuation and as an initial baseline for other methods.'
    )

    cost_price = models.DecimalField(
        max_digits=19, decimal_places=4, default=Decimal('0'),
        help_text='Current computed cost price. Updated after each GRN based on the valuation method.'
    )

    shelf_life_days = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Expected shelf life in days. Used to auto-suggest expiry date on batch receipt.'
    )

    valuation_method = models.CharField(max_length=10, choices=[
        ('FIFO', 'FIFO'),
        ('WA', 'Weighted Average'),
        ('LIFO', 'LIFO'),
        ('STD', 'Standard Cost'),
    ], default='WA')

    @property
    def stock_level(self):
        """Current total available stock across all warehouses."""
        return self.total_quantity

    @property
    def needs_reorder(self):
        """True if total stock has fallen to or below the reorder point."""
        return self.total_quantity <= self.reorder_point

    @property
    def average_cost(self):
        from django.db.models import Sum, Avg
        if self.total_quantity and self.total_quantity > 0:
            return (self.total_value / self.total_quantity).quantize(Decimal('0.0001'))
        movements = StockMovement.objects.filter(
            item=self,
            movement_type='IN'
        ).aggregate(
            total_cost=Sum(models.F('quantity') * models.F('unit_price')),
            total_qty=Sum('quantity')
        )
        if movements['total_qty'] and movements['total_qty'] > 0:
            return (movements['total_cost'] / movements['total_qty']).quantize(Decimal('0.0001'))
        return Decimal('0')

    def recalculate_stock_values(self):
        from django.db.models import Sum

        result = ItemStock.objects.filter(item=self).aggregate(
            total_qty=Sum('quantity'),
        )
        self.total_quantity = result['total_qty'] or Decimal('0')

        if self.valuation_method == 'STD':
            # Standard Cost: value is always quantity × standard_price; cost_price never changes
            self.total_value = self.total_quantity * self.standard_price
            self.cost_price = self.standard_price
        elif self.valuation_method == 'WA':
            # Weighted Average: (total in value - total out value)
            in_val = StockMovement.objects.filter(
                item=self, movement_type__in=['IN', 'ADJ']
            ).aggregate(
                v=Sum(models.F('quantity') * models.F('unit_price'))
            )['v'] or Decimal('0')
            out_val = StockMovement.objects.filter(
                item=self, movement_type='OUT'
            ).aggregate(
                v=Sum(models.F('quantity') * models.F('unit_price'))
            )['v'] or Decimal('0')
            self.total_value = in_val - out_val
            self.cost_price = (
                (self.total_value / self.total_quantity).quantize(Decimal('0.0001'))
                if self.total_quantity > 0 else self.standard_price
            )
        else:
            # FIFO / LIFO: layer-based valuation
            self.total_value = self._layer_valuation()
            self.cost_price = (
                (self.total_value / self.total_quantity).quantize(Decimal('0.0001'))
                if self.total_quantity > 0 else self.standard_price
            )

        self.save(update_fields=['total_quantity', 'total_value', 'cost_price'])
        return self

    def _layer_valuation(self):
        """Value remaining stock using FIFO or LIFO cost layers.

        Builds an ordered list of IN cost layers, then "consumes" them
        against cumulative OUT quantity in the appropriate order.
        """
        layers = list(
            StockMovement.objects.filter(item=self, movement_type='IN')
            .order_by('created_at')
            .values_list('quantity', 'unit_price')
        )

        total_out = StockMovement.objects.filter(
            item=self, movement_type='OUT'
        ).aggregate(q=Sum('quantity'))['q'] or Decimal('0')

        if self.valuation_method == 'LIFO':
            # LIFO: consume latest layers first, remaining value is oldest layers
            layers = list(reversed(layers))

        # Consume layers by total OUT qty
        remaining_out = total_out
        for i, (qty, _price) in enumerate(layers):
            if remaining_out <= 0:
                break
            consume = min(qty, remaining_out)
            layers[i] = (qty - consume, _price)
            remaining_out -= consume

        # Sum remaining layer values
        return sum(
            qty * price for qty, price in layers if qty > 0
        )

    category = models.ForeignKey('ItemCategory', models.PROTECT, blank=True, null=True)

    product_category = models.ForeignKey('ProductCategory', models.PROTECT, blank=True, null=True)

    product_type = models.ForeignKey('ProductType', models.PROTECT, blank=True, null=True)

    preferred_vendor = models.ForeignKey(
        'procurement.Vendor',
        models.SET_NULL,
        null=True, blank=True,
        related_name='preferred_items',
        help_text='Default vendor used when automatically generating Purchase Orders from reorder alerts.',
    )

    # Production BOM link removed — Quot PSE is public sector (no manufacturing)

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'

    def __str__(self):
        return f"{self.sku} - {self.name}"

    def clean(self):
        super().clean()
        if not self.inventory_account and not self.product_type:
            raise ValidationError("Either inventory_account or product_type must be set")









class ItemBatch(models.Model):

    id = models.BigAutoField(primary_key=True)

    batch_number = models.CharField(max_length=50)

    receipt_date = models.DateField()

    expiry_date = models.DateField(blank=True, null=True)

    quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    remaining_quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    reference_number = models.CharField(max_length=100)

    item = models.ForeignKey(Item, models.PROTECT)

    warehouse = models.ForeignKey('Warehouse', models.PROTECT)

    class Meta:
        verbose_name = 'Product Batch'
        verbose_name_plural = 'Product Batches'
        unique_together = (('item', 'batch_number'),)







class ItemCategory(models.Model):

    id = models.BigAutoField(primary_key=True)

    name = models.CharField(max_length=100)

    parent = models.ForeignKey('self', models.PROTECT, blank=True, null=True)

    class Meta:
        verbose_name = 'Product Category'
        verbose_name_plural = 'Product Categories'

    def __str__(self):
        return self.name










class ItemStock(models.Model):

    id = models.BigAutoField(primary_key=True)

    quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    reserved_quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity

    item = models.ForeignKey(Item, models.PROTECT)

    warehouse = models.ForeignKey('Warehouse', models.PROTECT)

    def reserve(self, quantity, reference_type, reference_id):
        """O2C-M2: Reserve stock for an order."""
        available = self.available_quantity
        if available < quantity:
            raise ValueError(f"Insufficient stock. Available: {available}, Requested: {quantity}")
        
        self.reserved_quantity += quantity
        self.save(update_fields=['reserved_quantity'])
        
        StockReservation.objects.create(
            item_stock=self,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            status='Reserved'
        )
        
        return True

    def release_reservation(self, quantity, reference_type, reference_id):
        """O2C-M2: Release reserved stock."""
        reservations = StockReservation.objects.filter(
            item_stock=self,
            reference_type=reference_type,
            reference_id=reference_id,
            status='Reserved'
        )
        
        released = Decimal('0')
        for res in reservations:
            if released >= quantity:
                break
            to_release = min(res.quantity, quantity - released)
            res.quantity -= to_release
            released += to_release
            if res.quantity <= 0:
                res.status = 'Released'
                res.save()
            else:
                res.save()
        
        self.reserved_quantity -= released
        self.save(update_fields=['reserved_quantity'])
        return released

    class Meta:
        verbose_name = 'Product Stock'
        verbose_name_plural = 'Product Stock'


class StockReservation(models.Model):
    """O2C-M2: Track stock reservations for orders."""
    STATUS_CHOICES = [
        ('Reserved', 'Reserved'),
        ('Allocated', 'Allocated'),
        ('Released', 'Released'),
        ('Fulfilled', 'Fulfilled'),
    ]
    
    item_stock = models.ForeignKey(ItemStock, on_delete=models.CASCADE, related_name='reservations')
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    reference_type = models.CharField(max_length=50)
    reference_id = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Reserved')
    reserved_at = models.DateTimeField(auto_now_add=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['reference_type', 'reference_id']),
        ]
    
    def __str__(self):
        return f"Reservation {self.reference_type}:{self.reference_id} - {self.quantity}"




    unique_together = (('item', 'warehouse'),)







class ProductCategory(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)



    name = models.CharField(max_length=100)


    parent = models.ForeignKey('self', models.PROTECT, blank=True, null=True)


    product_type = models.ForeignKey('ProductType', models.PROTECT)






    unique_together = (('name', 'product_type'),)







class ProductType(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)



    name = models.CharField(unique=True, max_length=50)

    description = models.TextField(blank=True, default='')

    clearing_account = models.ForeignKey(Account, models.PROTECT, related_name='producttype_clearing_account_set', blank=True, null=True)

    expense_account = models.ForeignKey(Account, models.PROTECT, related_name='producttype_expense_account_set', blank=True, null=True)

    inventory_account = models.ForeignKey(Account, models.PROTECT, related_name='producttype_inventory_account_set', blank=True, null=True)

    revenue_account = models.ForeignKey(Account, models.PROTECT, related_name='producttype_revenue_account_set', blank=True, null=True)

    goods_in_transit_account = models.ForeignKey(
        Account, models.PROTECT,
        related_name='producttype_git_account_set',
        blank=True, null=True,
        help_text='Clearing GL account used as intermediary during inter-warehouse stock transfers. '
                  'DR on dispatch, CR on receive. Balance = goods currently in transit.'
    )













class ReorderAlert(models.Model):

    id = models.BigAutoField(primary_key=True)

    current_stock = models.DecimalField(max_digits=15, decimal_places=4)

    reorder_point = models.DecimalField(max_digits=15, decimal_places=4)

    suggested_quantity = models.DecimalField(max_digits=15, decimal_places=4)

    is_sent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    item = models.ForeignKey(Item, models.PROTECT)

    warehouse = models.ForeignKey('Warehouse', models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'warehouse'],
                condition=models.Q(is_sent=False),
                name='unique_pending_reorder_alert',
            ),
        ]











class InventorySettings(models.Model):
    """
    Per-tenant inventory configuration singleton.

    Always retrieved via ``InventorySettings.load()`` — never construct directly.
    Row with pk=1 is auto-created on first access.
    """
    auto_po_enabled = models.BooleanField(
        default=False,
        help_text=(
            'When enabled, a Draft Purchase Order is automatically created the moment '
            'stock falls at or below an item\'s reorder point.'
        ),
    )
    auto_po_draft_only = models.BooleanField(
        default=True,
        help_text=(
            'Auto-generated POs are always created as Draft (require human review '
            'before submission). Strongly recommended to keep this on.'
        ),
    )

    class Meta:
        verbose_name = 'Inventory Settings'
        verbose_name_plural = 'Inventory Settings'

    def __str__(self):
        return 'Inventory Settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class StockMovement(AuditBaseModel):
    MOVEMENT_TYPE_CHOICES = [
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
        ('ADJ', 'Adjustment'),
        ('TRF', 'Transfer'),
    ]

    id = models.BigAutoField(primary_key=True)

    movement_type = models.CharField(max_length=3, choices=MOVEMENT_TYPE_CHOICES)

    quantity = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal('0'))])

    unit_price = models.DecimalField(max_digits=19, decimal_places=4, validators=[MinValueValidator(Decimal('0'))])

    reference_number = models.CharField(max_length=100)

    remarks = models.TextField()

    item = models.ForeignKey(Item, models.PROTECT)

    warehouse = models.ForeignKey('Warehouse', models.PROTECT)

    cost_method = models.CharField(max_length=10)

    to_warehouse = models.ForeignKey('Warehouse', models.PROTECT, related_name='stockmovement_to_warehouse_set', blank=True, null=True)

    batch = models.ForeignKey(ItemBatch, models.PROTECT, blank=True, null=True)

    TRANSFER_STATUS_CHOICES = [
        ('In Transit', 'In Transit'),
        ('Received',   'Received'),
    ]

    transfer_status = models.CharField(
        max_length=20, choices=TRANSFER_STATUS_CHOICES,
        blank=True, default='',
        help_text='Lifecycle stage for TRF-type movements only. '
                  'In Transit = dispatched (Warehouse A debited, GIT credited). '
                  'Received = Warehouse B has posted GRN (Inventory B debited, GIT cleared).'
    )

    gl_posted = models.BooleanField(default=False)
    journal_entry = models.ForeignKey(
        'accounting.JournalHeader', models.SET_NULL,
        blank=True, null=True,
        related_name='stock_movements'
    )
    receive_journal_entry = models.ForeignKey(
        'accounting.JournalHeader', models.SET_NULL,
        blank=True, null=True,
        related_name='stock_transfer_receipts',
        help_text='Journal entry created when Warehouse B receives the transfer (Step 2).'
    )

    def clean(self):
        super().clean()
        if self.movement_type in ('OUT', 'TRF') and self.warehouse_id:
            stock = ItemStock.objects.filter(
                item=self.item, warehouse=self.warehouse
            ).first()
            available = stock.available_quantity if stock else Decimal('0')
            if self.quantity > available:
                raise ValidationError(
                    f"Insufficient stock. Available: {available}, Requested: {self.quantity}"
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)








    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name='positive_movement_quantity'),
        ]


class StockReconciliation(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    TYPE_CHOICES = [
        ('Full', 'Full Count'),
        ('Partial', 'Partial Count'),
        ('Cycle', 'Cycle Count'),
        ('Spot', 'Spot Check'),
    ]

    id = models.BigAutoField(primary_key=True)

    reconciliation_number = models.CharField(unique=True, max_length=50)

    reconciliation_type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    reconciliation_date = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    notes = models.TextField(blank=True, default='')



    warehouse = models.ForeignKey('Warehouse', models.PROTECT)












class StockReconciliationLine(models.Model):

    id = models.BigAutoField(primary_key=True)

    system_quantity = models.DecimalField(max_digits=15, decimal_places=4)

    physical_quantity = models.DecimalField(max_digits=15, decimal_places=4)

    variance_quantity = models.DecimalField(max_digits=15, decimal_places=4)

    variance_value = models.DecimalField(max_digits=19, decimal_places=4)

    reason = models.TextField(blank=True, default='')

    is_adjusted = models.BooleanField(default=False)

    item = models.ForeignKey(Item, models.PROTECT)

    reconciliation = models.ForeignKey(StockReconciliation, models.PROTECT, related_name='lines')

    class Meta:
        # Enforce one line per item per reconciliation at the DB level.
        # This makes get_or_create truly race-condition-safe: a concurrent
        # duplicate INSERT will raise IntegrityError, which Django catches and
        # handles by returning the existing row.
        unique_together = [('reconciliation', 'item')]

    def save(self, avg_cost=None, *args, **kwargs):
        # Auto-calculate variance
        self.variance_quantity = self.physical_quantity - self.system_quantity
        if avg_cost is None:
            avg_cost = self.item.average_cost
        self.variance_value = self.variance_quantity * avg_cost
        super().save(*args, **kwargs)












class Warehouse(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)



    name = models.CharField(max_length=100)

    location = models.CharField(max_length=255)

    is_active = models.BooleanField()



    is_central = models.BooleanField()












class ItemSerialNumber(AuditBaseModel):
    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('Allocated', 'Allocated'),
        ('Sold', 'Sold'),
        ('Returned', 'Returned'),
        ('Defective', 'Defective'),
        ('Scrapped', 'Scrapped'),
    ]

    id = models.BigAutoField(primary_key=True)
    serial_number = models.CharField(max_length=100, unique=True)
    item = models.ForeignKey(Item, models.PROTECT, related_name='serial_numbers')
    batch = models.ForeignKey(ItemBatch, models.PROTECT, blank=True, null=True, related_name='serial_numbers')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Available')
    warehouse = models.ForeignKey(Warehouse, models.PROTECT)
    purchase_date = models.DateField(blank=True, null=True)
    purchase_price = models.DecimalField(max_digits=19, decimal_places=4, blank=True, null=True)
    sale_date = models.DateField(blank=True, null=True)
    # Sales FK removed — Quot PSE is public sector (no sales orders)
    issue_reference = models.CharField(max_length=100, blank=True, default='',
        help_text="Issue/distribution reference number")
    warranty_start = models.DateField(blank=True, null=True)
    warranty_end = models.DateField(blank=True, null=True)
    current_location = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Product Serial Number'
        verbose_name_plural = 'Product Serial Numbers'

    @property
    def is_under_warranty(self):
        if self.warranty_end:
            return self.warranty_end >= timezone.now().date()
        return False

    def __str__(self):
        return self.serial_number

class BatchExpiryAlert(AuditBaseModel):
    id = models.BigAutoField(primary_key=True)
    item = models.ForeignKey(Item, models.PROTECT)
    batch = models.ForeignKey(ItemBatch, models.PROTECT, related_name='expiry_alerts')
    warehouse = models.ForeignKey(Warehouse, models.PROTECT, blank=True, null=True)
    expiry_date = models.DateField()
    alert_date = models.DateField(auto_now_add=True)
    is_sent = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)

    @property
    def remaining_quantity(self):
        return self.batch.remaining_quantity

    @property
    def warehouse_name(self):
        if self.warehouse:
            return self.warehouse.name
        return self.batch.warehouse.name

    def __str__(self):
        return f"Alert: {self.item} - {self.batch}"


class Reservation(AuditBaseModel):
    """Inventory reservation for sales order lines"""
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Fulfilled', 'Fulfilled'),
        ('Partially_Fulfilled', 'Partially Fulfilled'),
        ('Cancelled', 'Cancelled'),
    ]

    # Government context: reservations linked to procurement/requisition, not sales
    requisition_reference = models.CharField(max_length=100, blank=True, default='',
        help_text="Purchase requisition or issue reference")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='reservations')
    warehouse = models.ForeignKey('Warehouse', on_delete=models.PROTECT, related_name='reservations')
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    fulfilled_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    reserved_date = models.DateField(auto_now_add=True)
    expires_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-reserved_date']

    @property
    def remaining_quantity(self):
        return self.quantity - self.fulfilled_quantity

    def __str__(self):
        return f"Reservation {self.id} - {self.item.name} ({self.quantity})"


class UnitOfMeasure(models.Model):
    """Standardised unit of measure — referenced by Item.unit_of_measure."""
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"
