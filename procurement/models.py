from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, FileExtensionValidator
from core.models import AuditBaseModel, ImmutableModelMixin, StatusTransitionMixin, quantize_currency
from accounting.models import Fund, Function, Program, Geo, Account, MDA, BudgetEncumbrance, Budget, WithholdingTax, TaxCode
from accounting.budget_logic import check_budget_availability, get_active_budget
from decimal import Decimal
from datetime import date


class PurchaseType(models.Model):
    """Product types for procurement - links to inventory ProductType (deprecated - use inventory.ProductType)"""
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = 'Purchase Types (Legacy)'
    
    def __str__(self):
        return self.name

class VendorCategory(models.Model):
    """Vendor category (e.g. Local, Foreign) linked to AP reconciliation account."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    reconciliation_account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        limit_choices_to={'reconciliation_type': 'accounts_payable'},
        related_name='vendor_categories',
        help_text='AP reconciliation account from Chart of Accounts',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'Vendor Categories'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Vendor(AuditBaseModel):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    category = models.ForeignKey(
        VendorCategory, on_delete=models.PROTECT,
        related_name='vendors',
        null=True, blank=True,
    )
    tax_id = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    
    # AP balance — outstanding amount owed to vendor (updated atomically at PO/payment posting)
    balance = models.DecimalField(max_digits=19, decimal_places=2, default=0)

    # Performance scoring
    total_orders = models.IntegerField(default=0)
    on_time_deliveries = models.IntegerField(default=0)
    quality_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_purchase_value = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    
    # Vendor rating
    @property
    def performance_rating(self):
        if self.total_orders == 0:
            return 0
        delivery_rate = (self.on_time_deliveries / self.total_orders) * 100
        return (delivery_rate * 0.5) + (float(self.quality_score or 0) * 0.5)
    
    @property
    def on_time_delivery_rate(self):
        if self.total_orders == 0:
            return 0
        return (self.on_time_deliveries / self.total_orders) * 100

    withholding_tax_code = models.ForeignKey(
        WithholdingTax, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendors',
        help_text='Default WHT code applied to this vendor on transactions',
    )
    wht_exempt = models.BooleanField(default=False, help_text='Exempt this vendor from withholding tax')

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

class PurchaseRequest(StatusTransitionMixin, AuditBaseModel):
    """Initial request for purchase."""
    ALLOWED_TRANSITIONS = {
        'Draft': ['Pending'],
        'Pending': ['Approved', 'Rejected'],
        'Approved': [],
        'Rejected': ['Draft'],
    }
    request_number = models.CharField(max_length=50, unique=True, blank=True)
    description = models.TextField()
    requested_date = models.DateField(auto_now_add=True)
    
    # Requester info
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_requests'
    )
    
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Urgent', 'Urgent'),
    ]
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')

    # Dimensions
    mda = models.ForeignKey(MDA, on_delete=models.PROTECT, null=True, blank=True)
    fund = models.ForeignKey(Fund, on_delete=models.PROTECT)
    function = models.ForeignKey(Function, on_delete=models.PROTECT)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    geo = models.ForeignKey(Geo, on_delete=models.PROTECT)
    cost_center = models.ForeignKey(
        'accounting.CostCenter', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_requests'
    )

    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    def _generate_pr_number(self):
        """Generate a sequential PR number for the current year: PR-YYYY-NNNNN.

        FIX #13: The previous count-based approach had a race condition — two
        concurrent inserts could both read the same count before either committed.
        We now lock the *last* PR row with select_for_update() and derive the
        next sequence from its number, preventing concurrent generation of
        duplicate PR numbers.
        """
        import datetime
        from django.db import transaction
        year = datetime.date.today().year
        prefix = f'PR-{year}-'
        with transaction.atomic():
            # Lock the highest existing PR for this year so concurrent inserts
            # queue behind this transaction rather than reading stale counts.
            last = (
                PurchaseRequest.objects
                .select_for_update()
                .filter(request_number__startswith=prefix)
                .order_by('-request_number')
                .first()
            )
            if last and last.request_number:
                try:
                    last_seq = int(last.request_number.split('-')[-1])
                except (ValueError, IndexError):
                    last_seq = PurchaseRequest.objects.filter(
                        request_number__startswith=prefix
                    ).count()
            else:
                last_seq = 0
            return f'{prefix}{last_seq + 1:05d}'

    def save(self, *args, **kwargs):
        if not self.request_number:
            self.request_number = self._generate_pr_number()

        self.validate_status_transition()
        is_new = self.pk is None
        old_status = None
        if not is_new:
            try:
                old_inst = PurchaseRequest.objects.get(pk=self.pk)
                old_status = old_inst.status
            except PurchaseRequest.DoesNotExist:
                pass

        # Validate budget on approval
        if self.status == 'Approved' and old_status != 'Approved':
            self.validate_budget()

        super().save(*args, **kwargs)

    def validate_budget(self):
        """Checks if budget exists for the lines in this PR."""
        budget_totals = {}
        for line in self.lines.all():
            key = (line.account, self.mda, self.fund, self.function, self.program, self.geo)
            amount = line.estimated_unit_price * line.quantity
            budget_totals[key] = budget_totals.get(key, Decimal('0.00')) + amount

        for (account, mda, fund, function, program, geo), total_amount in budget_totals.items():
            allowed, message = check_budget_availability(
                dimensions={
                    'mda': mda,
                    'fund': fund,
                    'function': function,
                    'program': program,
                    'geo': geo
                },
                account=account,
                amount=total_amount,
                date=self.requested_date or date.today(),
                transaction_type='PR',
                transaction_id=self.pk or 0
            )
            
            if not allowed:
                raise ValidationError(f"Budget Check Failed for {account.code}: {message}")

    class Meta:
        indexes = [
            models.Index(fields=['status']),
        ]
        permissions = [
            ('approve_purchaserequest', 'Can approve purchase requests'),
        ]

    def __str__(self):
        return self.request_number

class PurchaseRequestLine(models.Model):
    request = models.ForeignKey(PurchaseRequest, related_name='lines', on_delete=models.CASCADE)
    item_description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    estimated_unit_price = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])

    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True,
        help_text='GL account derived from the item product type. Left blank on PR; resolved at PO/GRN stage.'
    )
    asset = models.ForeignKey(
        'accounting.FixedAsset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_request_lines'
    )

    # Optional link to inventory
    item = models.ForeignKey(
        'inventory.Item', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_request_lines'
    )
    product_type = models.ForeignKey(
        'inventory.ProductType', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_request_lines'
    )
    product_category = models.ForeignKey(
        'inventory.ProductCategory', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_request_lines'
    )

    @property
    def total_estimated_price(self):
        return self.quantity * self.estimated_unit_price

    def __str__(self):
        return f"PR Line: {self.item_description}"

class PurchaseOrder(StatusTransitionMixin, AuditBaseModel, ImmutableModelMixin):
    """Binding purchase agreement."""
    ALLOWED_TRANSITIONS = {
        'Draft': ['Pending', 'Approved'],
        'Pending': ['Approved', 'Rejected'],
        'Approved': ['Posted', 'Rejected', 'Closed'],
        'Posted': ['Closed'],
        'Rejected': ['Draft'],
        'Closed': [],
    }
    po_number = models.CharField(max_length=50, unique=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    purchase_request = models.ForeignKey(PurchaseRequest, on_delete=models.SET_NULL, null=True, blank=True)
    order_date = models.DateField()
    expected_delivery_date = models.DateField(null=True, blank=True)
    
    # Delivery info
    delivery_address = models.TextField(blank=True)
    delivery_contact = models.CharField(max_length=100, blank=True)
    
    # Payment terms
    PAYMENT_TERMS = [
        ('Immediate', 'Immediate'),
        ('Net_15', 'Net 15'),
        ('Net_30', 'Net 30'),
        ('Net_45', 'Net 45'),
        ('Net_60', 'Net 60'),
        ('Due_on_Receipt', 'Due on Receipt'),
    ]
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS, default='Net_30')
    
    # Tax
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_code = models.ForeignKey(
        TaxCode, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_orders',
    )
    wht_exempt = models.BooleanField(default=False, help_text='Exempt this transaction from withholding tax')
    
    # Additional fields
    notes = models.TextField(blank=True)
    terms_and_conditions = models.TextField(blank=True)
    
    # Dimensions
    mda = models.ForeignKey(MDA, on_delete=models.PROTECT, null=True, blank=True)
    fund = models.ForeignKey(Fund, on_delete=models.PROTECT)
    function = models.ForeignKey(Function, on_delete=models.PROTECT)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    geo = models.ForeignKey(Geo, on_delete=models.PROTECT)

    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Posted', 'Posted'),
        ('Rejected', 'Rejected'),
        ('Closed', 'Closed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    @property
    def subtotal(self):
        return sum(line.total_price for line in self.lines.all())
    
    @property
    def total_amount(self):
        return self.subtotal + self.tax_amount
    
    def calculate_tax(self):
        """Calculate tax amount based on subtotal and tax rate"""
        self.tax_amount = quantize_currency(self.subtotal * (self.tax_rate / 100))
        return self.tax_amount

    def clean(self):
        super().clean()
        # 7.1: Vendor must be active
        if self.vendor and not self.vendor.is_active:
            raise ValidationError(f"Vendor '{self.vendor.name}' is inactive. Cannot create PO for inactive vendor.")
        # 7.3: Expected delivery must be on or after order date
        if self.expected_delivery_date and self.order_date:
            if self.expected_delivery_date < self.order_date:
                raise ValidationError("Expected delivery date cannot be before order date.")

    def save(self, *args, **kwargs):
        self.clean()
        self.validate_status_transition()
        is_new = self.pk is None
        old_status = None

        # Calculate tax before saving
        self.calculate_tax()

        if not is_new:
            old_inst = PurchaseOrder.objects.get(pk=self.pk)
            old_status = old_inst.status

        # Transition to Approved or Posted triggers budget check and encumbrance
        if self.status in ['Approved', 'Posted'] and old_status not in ['Approved', 'Posted']:
            self.process_budget_encumbrance()
            
        # Transition from Approved/Posted to Cancelled/Rejected/Closed
        if old_status in ['Approved', 'Posted'] and self.status in ['Rejected', 'Closed']:
            self.cancel_budget_encumbrance()

        super().save(*args, **kwargs)

    def process_budget_encumbrance(self):
        """
        Groups lines by budget (Account + Dimensions) and checks availability.
        Creates BudgetEncumbrance records.
        """
        budget_totals = {}
        for line in self.lines.all():
            key = (line.account, self.mda, self.fund, self.function, self.program, self.geo)
            amount = line.unit_price * line.quantity
            budget_totals[key] = budget_totals.get(key, Decimal('0.00')) + amount

        for (account, mda, fund, function, program, geo), total_amount in budget_totals.items():
            allowed, message = check_budget_availability(
                dimensions={
                    'mda': mda,
                    'fund': fund,
                    'function': function,
                    'program': program,
                    'geo': geo
                },
                account=account,
                amount=total_amount,
                date=self.order_date,
                transaction_type='PO',
                transaction_id=self.pk
            )
            
            if not allowed:
                raise ValidationError(f"Budget Check Failed for {account.code}: {message}")
            
            # Find the budget object (needed for encumbrance)
            from accounting.budget_logic import get_active_budget
            budget = get_active_budget(
                dimensions={
                    'mda': mda,
                    'fund': fund,
                    'function': function,
                    'program': program,
                    'geo': geo
                },
                account=account,
                date=self.order_date
            )

            # FIX #15: Guard against None budget — if no active budget was found
            # for this dimension combination, skip encumbrance creation to avoid
            # an IntegrityError on the NOT NULL budget FK.
            if budget is None:
                import logging as _logging
                _logging.getLogger('dtsg').warning(
                    f"PO {getattr(self, 'po_number', '?')}: no active budget found "
                    f"for account {getattr(account, 'code', account)} — encumbrance skipped."
                )
                continue

            # Create or update encumbrance
            BudgetEncumbrance.objects.update_or_create(
                budget=budget,
                reference_type='PO',
                reference_id=self.pk,
                defaults={
                    'encumbrance_date': self.order_date,
                    'amount': total_amount,
                    'status': 'ACTIVE',
                    'description': f"Encumbrance for PO {self.po_number}"
                }
            )

    def cancel_budget_encumbrance(self):
        """Cancels all active encumbrances for this PO"""
        BudgetEncumbrance.objects.filter(
            reference_type='PO',
            reference_id=self.pk,
            status='ACTIVE'
        ).update(status='CANCELLED')

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['vendor']),
        ]
        permissions = [
            ('approve_purchaseorder', 'Can approve purchase orders'),
        ]

    def __str__(self):
        return self.po_number

class PurchaseOrderLine(models.Model):
    po = models.ForeignKey(PurchaseOrder, related_name='lines', on_delete=models.CASCADE)
    item_description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    unit_price = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    
    # Optional link to inventory Item
    item = models.ForeignKey(
        'inventory.Item', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_order_lines'
    )
    
    # Product type and category from inventory
    product_type = models.ForeignKey(
        'inventory.ProductType', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_order_lines'
    )
    product_category = models.ForeignKey(
        'inventory.ProductCategory', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_order_lines'
    )

    # Optional link to fixed asset being procured
    asset = models.ForeignKey(
        'accounting.FixedAsset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_order_lines'
    )

    @property
    def total_price(self):
        return self.quantity * self.unit_price
        
    @property
    def pending_quantity(self):
        return self.quantity - self.quantity_received
        
    @property
    def is_fully_received(self):
        return self.quantity_received >= self.quantity
        
    @property
    def received_amount(self):
        return self.quantity_received * self.unit_price

    def __str__(self):
        return f"PO Line: {self.item_description}"

class GoodsReceivedNote(StatusTransitionMixin, AuditBaseModel):
    """Confirms receipt of goods/services."""
    ALLOWED_TRANSITIONS = {
        # Normal path (approval disabled):     Draft → Received → Posted
        # Approval-gated path:                 Draft → On Hold → Received → Posted
        'Draft':     ['Received', 'On Hold'],
        'Received':  ['On Hold', 'Posted', 'Cancelled'],
        'On Hold':   ['Received', 'Posted', 'Cancelled'],
        'Posted':    [],
        'Cancelled': [],
    }
    grn_number = models.CharField(max_length=50, unique=True, blank=True)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT)
    received_date = models.DateField()
    received_by = models.CharField(max_length=100)
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT,
        null=True, blank=True,
        help_text="Receiving warehouse for this GRN"
    )

    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Received', 'Received'),
        ('On Hold', 'On Hold'),
        ('Posted', 'Posted'),
        ('Cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['purchase_order']),
        ]

    def __str__(self):
        return self.grn_number

    def _generate_grn_number(self):
        """Generate a sequential GRN number for the current year: GRN-YYYY-NNNNN.

        Uses the same lock-last-row approach as PR number generation to prevent
        concurrent inserts from generating duplicate numbers via a COUNT race.
        """
        import datetime
        from django.db import transaction
        year = datetime.date.today().year
        prefix = f'GRN-{year}-'
        with transaction.atomic():
            last = (
                GoodsReceivedNote.objects
                .select_for_update()
                .filter(grn_number__startswith=prefix)
                .order_by('-grn_number')
                .first()
            )
            if last and last.grn_number:
                try:
                    last_seq = int(last.grn_number.split('-')[-1])
                except (ValueError, IndexError):
                    last_seq = GoodsReceivedNote.objects.filter(
                        grn_number__startswith=prefix
                    ).count()
            else:
                last_seq = 0
            return f'{prefix}{last_seq + 1:05d}'

    def save(self, *args, **kwargs):
        from django.conf import settings
        from django.db import transaction

        if not self.grn_number:
            self.grn_number = self._generate_grn_number()

        self.validate_status_transition()
        is_new = self.pk is None
        old_status = None

        if not is_new:
            old_status = GoodsReceivedNote.objects.get(pk=self.pk).status

        # Only process GRN posting logic when transitioning to Posted
        should_process_posting = (old_status != 'Posted' and self.status == 'Posted')
        
        if should_process_posting:
            with transaction.atomic():
                # First save the GRN to get its PK
                super().save(*args, **kwargs)
                
                # Now process the posting
                proc_settings = getattr(settings, 'PROCUREMENT_SETTINGS', {})
                allow_partial = proc_settings.get('ALLOW_PARTIAL_RECEIVING', True)
                
                # Determine receiving warehouse
                from inventory.models import StockMovement, Warehouse
                receiving_warehouse = self.warehouse
                if not receiving_warehouse:
                    receiving_warehouse = Warehouse.objects.filter(is_active=True).first()
                if not receiving_warehouse:
                    raise ValidationError("No receiving warehouse specified and no active warehouse found.")

                for grn_line in self.lines.all():
                    po_line = PurchaseOrderLine.objects.select_for_update().get(pk=grn_line.po_line.pk)
                    po_line.quantity_received += grn_line.quantity_received
                    po_line.save()

                    if po_line.item and grn_line.quantity_received > 0:
                        from inventory.models import ItemStock, ItemBatch

                        # FIX #19: Create the ItemBatch FIRST (when batch_number is given)
                        # so the FK can be assigned to the StockMovement in the same INSERT.
                        # Previously batch was created after the movement, leaving batch=NULL.
                        batch_obj = None
                        if grn_line.batch_number:
                            batch_obj, _ = ItemBatch.objects.get_or_create(
                                batch_number=grn_line.batch_number,
                                item=po_line.item,
                                warehouse=receiving_warehouse,
                                defaults={
                                    'quantity': grn_line.quantity_received,
                                    'remaining_quantity': grn_line.quantity_received,
                                    'unit_cost': po_line.unit_price,
                                    'receipt_date': self.received_date,
                                    'expiry_date': grn_line.expiry_date,
                                    'reference_number': self.grn_number,
                                }
                            )

                        # DOUBLE-UPDATE FIX: Use instance pattern so we can set
                        # _skip_stock_update = True BEFORE the post_save signal fires.
                        # Without this, the signal increments stock first, then the
                        # explicit F() update below increments it a second time,
                        # resulting in 2× the received quantity being added.
                        grn_movement = StockMovement(
                            item=po_line.item,
                            warehouse=receiving_warehouse,
                            movement_type='IN',
                            quantity=grn_line.quantity_received,
                            unit_price=po_line.unit_price,
                            batch=batch_obj,   # ← properly linked to batch at creation
                            reference_number=self.grn_number,
                            remarks=f"GRN: {self.grn_number}"
                        )
                        grn_movement._skip_stock_update = True   # explicit update below is authoritative
                        grn_movement.save()

                        # Update ItemStock quantity atomically — single authoritative write
                        ItemStock.objects.update_or_create(
                            item=po_line.item,
                            warehouse=receiving_warehouse,
                            defaults={'quantity': Decimal('0')},
                        )
                        ItemStock.objects.filter(
                            item=po_line.item,
                            warehouse=receiving_warehouse,
                        ).update(quantity=models.F('quantity') + grn_line.quantity_received)

                        # Recalculate item-level totals after stock is updated
                        po_line.item.recalculate_stock_values()

                # GL journal creation is handled exclusively by TransactionPostingService
                # (called from the post_grn view action) to avoid duplicate journals.

                po = PurchaseOrder.objects.get(pk=self.purchase_order.pk)
                all_fully_received = all(
                    line.quantity_received >= line.quantity
                    for line in po.lines.all()
                )
                if all_fully_received:
                    po.status = 'Closed'
                    po.save()

                # 7.4: Auto-update vendor performance stats using atomic F() updates
                vendor = po.vendor
                total_orders_count = PurchaseOrder.objects.filter(
                    vendor=vendor, status__in=['Approved', 'Posted', 'Closed']
                ).count()
                on_time_count = vendor.on_time_deliveries
                if po.expected_delivery_date and self.received_date:
                    on_time_count = GoodsReceivedNote.objects.filter(
                        purchase_order__vendor=vendor,
                        status='Posted',
                        received_date__lte=models.F('purchase_order__expected_delivery_date'),
                    ).values('purchase_order').distinct().count()
                Vendor.objects.filter(pk=vendor.pk).update(
                    total_orders=total_orders_count,
                    on_time_deliveries=on_time_count,
                )

                # INT-10: Auto-create a draft VendorInvoice from the posted GRN.
                # The invoice stays in 'Draft' for AP review before approval/posting.
                try:
                    from accounting.models import VendorInvoice, VendorInvoiceLine
                    # Only create if no invoice already linked to this PO
                    existing = VendorInvoice.objects.filter(
                        purchase_order=po, status__in=['Draft', 'Approved']
                    ).exists()
                    if not existing:
                        subtotal = sum(
                            (gl.quantity_received * gl.po_line.unit_price)
                            for gl in self.lines.select_related('po_line').all()
                        )
                        vi = VendorInvoice.objects.create(
                            vendor=po.vendor,
                            purchase_order=po,
                            reference=f"GRN {self.grn_number}",
                            description=f"Auto-created from GRN {self.grn_number}",
                            invoice_date=self.received_date or date.today(),
                            due_date=po.payment_due_date if hasattr(po, 'payment_due_date') and po.payment_due_date else self.received_date or date.today(),
                            mda=getattr(po, 'mda', None),
                            fund=getattr(po, 'fund', None),
                            function=getattr(po, 'function', None),
                            program=getattr(po, 'program', None),
                            geo=getattr(po, 'geo', None),
                            subtotal=subtotal,
                            total_amount=subtotal,
                            status='Draft',
                        )
                        for grn_line in self.lines.select_related('po_line__item').all():
                            line_amount = grn_line.quantity_received * grn_line.po_line.unit_price
                            VendorInvoiceLine.objects.create(
                                invoice=vi,
                                account=grn_line.po_line.account if hasattr(grn_line.po_line, 'account') and grn_line.po_line.account else po.account,
                                description=f"{grn_line.po_line.item.name if grn_line.po_line.item else 'Item'} × {grn_line.quantity_received}",
                                amount=line_amount,
                            )
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "GRN %s: auto VendorInvoice creation failed (non-fatal): %s",
                        self.grn_number, exc,
                    )
        else:
            # Normal save path
            super().save(*args, **kwargs)

class GoodsReceivedNoteLine(models.Model):
    grn = models.ForeignKey(GoodsReceivedNote, related_name='lines', on_delete=models.CASCADE)
    po_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])

    # Batch / lot tracking captured at point of receipt
    batch_number = models.CharField(max_length=100, blank=True, default='',
        help_text='Batch or lot number from the supplier label.')
    expiry_date = models.DateField(null=True, blank=True,
        help_text='Expiry / best-before date from the supplier label.')

    received_quantity_status = models.CharField(max_length=20, choices=[
        ('Partial', 'Partial'),
        ('Full', 'Full'),
        ('Over', 'Over Receipt'),
    ], default='Partial')

    notes = models.TextField(blank=True)
    
    def save(self, *args, **kwargs):
        if self.po_line:
            # Validate that total received across all GRNs does not exceed PO qty
            already_received = self.po_line.quantity_received or Decimal('0')
            # Exclude self if updating an existing line
            if self.pk:
                existing = GoodsReceivedNoteLine.objects.filter(pk=self.pk).first()
                if existing:
                    already_received -= existing.quantity_received
            remaining = self.po_line.quantity - already_received
            if self.quantity_received > remaining:
                raise ValidationError(
                    f"Cannot receive {self.quantity_received}. "
                    f"PO line qty: {self.po_line.quantity}, "
                    f"already received: {already_received}, "
                    f"remaining: {remaining}."
                )

            total_after = already_received + self.quantity_received
            if total_after < self.po_line.quantity:
                self.received_quantity_status = 'Partial'
            else:
                self.received_quantity_status = 'Full'
        super().save(*args, **kwargs)
    
    @property
    def line_total(self):
        return self.quantity_received * self.po_line.unit_price

    def __str__(self):
        return f"GRN Line: {self.po_line}"

class DownPaymentRequest(AuditBaseModel):
    """Down payment / advance payment request raised when a PO is created.
    Finance reviews and processes it into an actual Payment."""

    CALC_TYPE_CHOICES = [
        ('percentage', 'Percentage of PO Total'),
        ('amount', 'Fixed Amount'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('Bank', 'Bank Transfer'),
        ('Cash', 'Cash'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending Review'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Processed', 'Processed'),
    ]

    request_number = models.CharField(max_length=50, unique=True, blank=True)
    purchase_order = models.OneToOneField(
        PurchaseOrder, on_delete=models.CASCADE, related_name='down_payment_request'
    )
    calc_type = models.CharField(max_length=20, choices=CALC_TYPE_CHOICES, default='percentage')
    calc_value = models.DecimalField(max_digits=10, decimal_places=4)
    requested_amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='Bank')
    bank_account = models.ForeignKey(
        'accounting.BankAccount', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='down_payment_requests'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    notes = models.TextField(blank=True, default='')
    # Set when Finance processes this request into an actual Payment
    payment = models.ForeignKey(
        'accounting.Payment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='down_payment_source'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.request_number} — {self.purchase_order.po_number}"

    def save(self, *args, **kwargs):
        if not self.request_number:
            import datetime
            from django.db import transaction as db_transaction
            year = datetime.date.today().year
            prefix = f'DPR-{year}-'
            with db_transaction.atomic():
                count = DownPaymentRequest.objects.select_for_update().filter(
                    request_number__startswith=prefix
                ).count()
                self.request_number = f'{prefix}{count + 1:05d}'
        super().save(*args, **kwargs)


class InvoiceMatching(StatusTransitionMixin, AuditBaseModel):
    """
    Three-way matching: PO vs GRN vs Invoice.

    WARN-3 FIX: now uses StatusTransitionMixin to enforce valid status transitions.
    Valid paths:
      Draft → Pending_Review (submit for approval)
      Draft → Matched        (calculate_match without approval)
      Pending_Review → Approved / Rejected
      Matched → Pending_Review (submit after manual match)
      Matched → Variance / Rejected
      Variance → Rejected / Matched
    """
    ALLOWED_TRANSITIONS = {
        'Draft':          ['Pending_Review', 'Matched', 'Rejected'],
        'Pending_Review': ['Approved', 'Rejected'],
        'Matched':        ['Pending_Review', 'Variance', 'Rejected', 'Approved'],
        'Variance':       ['Matched', 'Rejected'],
        'Approved':       [],
        'Rejected':       [],
    }
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, null=True, blank=True)
    goods_received_note = models.ForeignKey(GoodsReceivedNote, on_delete=models.PROTECT, null=True, blank=True)
    vendor_invoice = models.ForeignKey(
        'accounting.VendorInvoice',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoice_matchings',
        help_text='Link to the accounting VendorInvoice for payment processing'
    )
    
    invoice_reference = models.CharField(max_length=50)
    invoice_date = models.DateField()
    invoice_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Tax on invoice
    invoice_tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    invoice_subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    po_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    grn_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending_Review', 'Pending Review'),
        ('Matched', 'Matched'),
        ('Variance', 'Variance'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    MATCH_TYPE_CHOICES = [
        ('Full', 'Full Match'),
        ('Partial', 'Partial Match'),
        ('None', 'No Match'),
    ]
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, blank=True)
    
    variance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    variance_reason = models.TextField(blank=True)
    matched_date = models.DateField(null=True, blank=True)
    payment_hold = models.BooleanField(
        default=False,
        help_text='Automatically set when invoice variance exceeds threshold. Must be cleared before payment.',
    )

    # Down payment deduction — tracks how much of an existing advance/down payment
    # has been applied against this invoice. Net payable = invoice_amount - down_payment_applied.
    down_payment_applied = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Amount of down payment / advance deducted from this invoice.',
    )

    notes = models.TextField(blank=True)

    @property
    def net_payable(self):
        """Invoice amount less any applied down payment. This is what the vendor is actually owed."""
        return max(Decimal('0'), self.invoice_amount - self.down_payment_applied)

    def clean(self):
        super().clean()
        if not self.purchase_order and not self.goods_received_note:
            raise ValidationError("At least one of purchase_order or goods_received_note is required")

    @property
    def po_fully_received(self):
        """Check if all PO lines are fully received"""
        if not self.purchase_order:
            return False
        for line in self.purchase_order.lines.all():
            if line.quantity_received < line.quantity:
                return False
        return True
    
    @property
    def grn_fully_received(self):
        """Check if all GRN lines are fully received vs PO"""
        if not self.goods_received_note or not self.purchase_order:
            return False
        grn_lines = {line.po_line_id: line.quantity_received for line in self.goods_received_note.lines.all()}
        for po_line in self.purchase_order.lines.all():
            received = grn_lines.get(po_line.id, 0)
            if received < po_line.quantity:
                return False
        return True
    
    def calculate_match(self):
        """Calculate match between PO, GRN, and Invoice amounts with partial quantity support"""
        from django.conf import settings
        
        proc_settings = getattr(settings, 'PROCUREMENT_SETTINGS', {})
        variance_threshold = proc_settings.get('INVOICE_VARIANCE_THRESHOLD', 5.0)
        
        if self.purchase_order:
            self.po_amount = self.purchase_order.total_amount
        if self.goods_received_note:
            self.grn_amount = sum(line.line_total for line in self.goods_received_note.lines.all())
        
        if not self.po_amount or not self.grn_amount:
            self.match_type = 'None'
            self.status = 'Pending_Review'
            return
        
        po_received_amount = 0
        if self.purchase_order:
            for line in self.purchase_order.lines.all():
                po_received_amount += line.quantity_received * line.unit_price
        
        grn_amount = self.grn_amount or 0
        
        if self.invoice_amount == self.po_amount == grn_amount:
            self.match_type = 'Full'
            self.status = 'Matched'
            self.variance_amount = 0
            self.variance_percentage = 0
        elif self.invoice_amount == grn_amount:
            if self.po_fully_received:
                self.match_type = 'Full'
                self.status = 'Matched'
                self.variance_amount = self.invoice_amount - self.po_amount
            else:
                self.match_type = 'Partial'
                self.status = 'Pending_Review'
                self.variance_amount = self.invoice_amount - self.po_amount
            if self.po_amount and self.po_amount > 0:
                self.variance_percentage = quantize_currency((abs(self.variance_amount) / self.po_amount) * 100)
        else:
            self.match_type = 'Partial'
            self.variance_amount = quantize_currency(self.invoice_amount - (grn_amount or self.po_amount))
            if self.po_amount and self.po_amount > 0:
                self.variance_percentage = quantize_currency((abs(self.variance_amount) / self.po_amount) * 100)
            
            if self.variance_percentage <= variance_threshold:
                self.status = 'Matched'
                self.payment_hold = False
            else:
                self.status = 'Variance'
                self.payment_hold = True

    def save(self, *args, **kwargs):
        # WARN-3 FIX: enforce valid transitions (StatusTransitionMixin.validate_status_transition
        # must be called explicitly; it is not automatic).
        self.validate_status_transition()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Match {self.invoice_reference} for PO {self.purchase_order.po_number if self.purchase_order else 'N/A'}"


class VendorCreditNote(AuditBaseModel):
    """Vendor credit notes for returns and adjustments."""
    credit_note_number = models.CharField(max_length=50, unique=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True)
    goods_received_note = models.ForeignKey(GoodsReceivedNote, on_delete=models.SET_NULL, null=True, blank=True)
    
    credit_note_date = models.DateField()
    reason = models.TextField()
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Posted', 'Posted'),
        ('Void', 'Void'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['vendor']),
        ]

    def __str__(self):
        return f"Credit Note {self.credit_note_number} - {self.vendor.name}"


class VendorDebitNote(AuditBaseModel):
    """Vendor debit notes for additional charges."""
    debit_note_number = models.CharField(max_length=50, unique=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True)
    
    debit_note_date = models.DateField()
    reason = models.TextField()
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Posted', 'Posted'),
        ('Void', 'Void'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['vendor']),
        ]

    def __str__(self):
        return f"Debit Note {self.debit_note_number} - {self.vendor.name}"


class PurchaseReturn(StatusTransitionMixin, AuditBaseModel):
    """
    Track goods returned to vendors.

    Workflow: Draft → Pending (submit) → Approved → Completed / Cancelled
    Completion atomically: adjusts inventory stock (OUT), posts GL reversal, auto-creates
    a VendorCreditNote for the total return value.
    """
    ALLOWED_TRANSITIONS = {
        'Draft': ['Pending'],
        'Pending': ['Approved', 'Cancelled'],
        'Approved': ['Completed', 'Cancelled'],
        'Completed': [],
        'Cancelled': [],
    }
    return_number = models.CharField(max_length=50, unique=True, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT)
    goods_received_note = models.ForeignKey(GoodsReceivedNote, on_delete=models.SET_NULL, null=True, blank=True)
    credit_note = models.ForeignKey(VendorCreditNote, on_delete=models.SET_NULL, null=True, blank=True)

    return_date = models.DateField()
    reason = models.TextField()

    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    # ── Return number generation ──────────────────────────────────────────────
    def _generate_return_number(self):
        import datetime
        year = datetime.date.today().year
        prefix = f'RTN-{year}-'
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            count = PurchaseReturn.objects.select_for_update().filter(
                return_number__startswith=prefix
            ).count()
            return f'{prefix}{count + 1:05d}'

    def update_total(self):
        """Recalculate total_amount from line items and persist."""
        from django.db.models import Sum, ExpressionWrapper, F, DecimalField as DField
        total = self.lines.aggregate(
            total=Sum(
                ExpressionWrapper(F('quantity') * F('unit_price'), output_field=DField(max_digits=15, decimal_places=2))
            )
        )['total'] or Decimal('0')
        self.total_amount = total
        PurchaseReturn.objects.filter(pk=self.pk).update(total_amount=total)

    def save(self, *args, **kwargs):
        if not self.return_number:
            self.return_number = self._generate_return_number()
        self.validate_status_transition()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['vendor']),
            models.Index(fields=['purchase_order']),
        ]

    def __str__(self):
        return f"Return {self.return_number} - {self.vendor.name}"


class PurchaseReturnLine(models.Model):
    """
    A single line on a purchase return.

    Linked to the original PurchaseOrderLine via po_line FK for traceability and
    quantity validation (cannot return more than was received on the linked GRN line).
    """
    purchase_return = models.ForeignKey(PurchaseReturn, related_name='lines', on_delete=models.CASCADE)
    # Optional FK back to the originating PO line — enables qty-against-GRN validation
    po_line = models.ForeignKey(
        'PurchaseOrderLine',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='return_lines',
        help_text='Original PO line being returned. Used for quantity validation against the GRN.'
    )
    item = models.ForeignKey(
        'inventory.Item', on_delete=models.PROTECT,
        null=True, blank=True,  # optional: derived from po_line.item when available
    )
    # Text description preserved for display when item FK is not available
    item_description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_price = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    reason = models.TextField(blank=True)

    @property
    def total_amount(self):
        return self.quantity * self.unit_price

    @property
    def display_description(self):
        """Human-readable item label for display in tables and reports."""
        if self.item:
            return self.item.name
        if self.item_description:
            return self.item_description
        if self.po_line:
            return self.po_line.item_description
        return '—'

    def __str__(self):
        return f"{self.display_description} x {self.quantity}"


class VendorPerformanceMetrics(models.Model):
    """Track vendor performance metrics over time."""
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='performance_metrics')
    
    period_start = models.DateField()
    period_end = models.DateField()
    
    total_orders = models.IntegerField(default=0)
    total_order_value = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    
    on_time_deliveries = models.IntegerField(default=0)
    late_deliveries = models.IntegerField(default=0)
    early_deliveries = models.IntegerField(default=0)
    
    perfect_orders = models.IntegerField(default=0)
    defective_receipts = models.IntegerField(default=0)
    
    average_lead_time_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    quality_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    on_time_delivery_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    fulfillment_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['vendor', 'period_start', 'period_end']
        ordering = ['-period_end']
    
    def __str__(self):
        return f"{self.vendor.name} - {self.period_start} to {self.period_end}"


class VendorClassification(models.Model):
    """Vendor qualification/tier classification"""
    VENDOR_TIER_CHOICES = [
        ('New', 'New'),
        ('Qualified', 'Qualified'),
        ('Approved', 'Approved'),
        ('Preferred', 'Preferred'),
        ('Blocked', 'Blocked'),
    ]
    
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='classifications')
    tier = models.CharField(max_length=20, choices=VENDOR_TIER_CHOICES, default='New')
    qualification_date = models.DateField(null=True, blank=True)
    qualification_expiry = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendor_approvals')
    notes = models.TextField(blank=True, default='')
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-is_current', '-qualification_date']
    
    def __str__(self):
        return f"{self.vendor.name} - {self.tier}"


class VendorContract(AuditBaseModel):
    """Vendor contracts/agreements"""
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='contracts')
    contract_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    start_date = models.DateField()
    end_date = models.DateField()
    contract_value = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    auto_renew = models.BooleanField(default=False)
    renewal_terms_days = models.IntegerField(default=30)
    status = models.CharField(max_length=20, choices=[
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Expired', 'Expired'),
        ('Terminated', 'Terminated'),
    ], default='Draft')
    document = models.FileField(
        upload_to='vendor_contracts/',
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'xlsx', 'jpg', 'png'])],
        null=True, blank=True
    )
    
    class Meta:
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.contract_number} - {self.vendor.name}"


class InvoiceMatchingSettings(models.Model):
    """Configuration for invoice matching tolerance rules"""
    quantity_variance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=5.0)
    price_variance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)
    allow_partial_match = models.BooleanField(default=True)
    auto_escalate_unmatched = models.BooleanField(default=True)
    escalation_threshold_days = models.IntegerField(default=3)
    require_grn_for_payment = models.BooleanField(default=True)
    auto_approve_matched = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = 'Invoice Matching Settings'
        verbose_name_plural = 'Invoice Matching Settings'
    
    def __str__(self):
        return f"Tolerance: Qty={self.quantity_variance_percent}%, Price={self.price_variance_percent}%"
