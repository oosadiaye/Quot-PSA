from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, FileExtensionValidator
from core.models import AuditBaseModel, ImmutableModelMixin, StatusTransitionMixin, quantize_currency
from accounting.models import Fund, Function, Program, Geo, Account, MDA, BudgetEncumbrance, WithholdingTax, TaxCode
from accounting.budget_logic import check_budget_availability, get_active_budget
from decimal import Decimal
from datetime import date


# Cap the computed variance percentage at the LEGACY NUMERIC(5,2)
# maximum (999.99) so the value saves cleanly on every tenant — those
# still on the narrow column AND those already migrated to (10,2).
# The exact percentage above 999.99 doesn't matter operationally:
# anything above the configured threshold (typically 5 %) trips the
# Variance gate and payment_hold flag, so capping preserves the
# "wildly out of tolerance" semantics without requiring every tenant
# to migrate before they can post over-threshold invoices.
_VARIANCE_PCT_CAP = Decimal('999.99')


def _cap_variance_pct(value):
    """Clip a computed variance % to the column's maximum representable
    value so save() never fails with numeric-field-overflow on tenants
    still running the legacy NUMERIC(5,2) column.

    Without this cap, a partial-receipt invoice (real variance > 999.99%)
    would propagate Decimal('1226.07') to the ORM and the database would
    reject the INSERT/UPDATE — blocking verification entirely. Capping
    preserves "this is wildly out of tolerance" semantics while letting
    the row save and the Variance status / payment_hold flag fire.
    """
    if value is None:
        return Decimal('0')
    if value > _VARIANCE_PCT_CAP:
        return _VARIANCE_PCT_CAP
    if value < -_VARIANCE_PCT_CAP:
        return -_VARIANCE_PCT_CAP
    return value


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
    is_active = models.BooleanField(default=False, help_text='Activated only after registration payment is confirmed')

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

    # ── Government Vendor Registration (Annual Validity) ─────────
    registration_number = models.CharField(
        max_length=50, blank=True, default='',
        help_text='BPP/State registration certificate number',
    )
    registration_fiscal_year = models.ForeignKey(
        'accounting.FiscalYear', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='registered_vendors',
        help_text='Fiscal year this registration is valid for',
    )
    registration_date = models.DateField(
        null=True, blank=True,
        help_text='Date vendor was registered/renewed',
    )
    expiry_date = models.DateField(
        null=True, blank=True,
        help_text='Registration expiry date (typically end of fiscal year)',
    )

    # Banking details
    bank_name = models.CharField(max_length=100, blank=True, default='')
    bank_account_number = models.CharField(max_length=20, blank=True, default='')
    bank_sort_code = models.CharField(max_length=10, blank=True, default='')

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['expiry_date']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def is_registration_valid(self) -> bool:
        """Check if vendor registration is valid for the current date."""
        from datetime import date
        if not self.expiry_date:
            return self.is_active  # No expiry set = use is_active flag
        return self.is_active and self.expiry_date >= date.today()

    @property
    def registration_status(self) -> str:
        """Return human-readable registration status."""
        from datetime import date
        if not self.is_active and not self.registration_date:
            return 'PENDING_ACTIVATION'
        if not self.is_active:
            return 'BLOCKED'
        if not self.expiry_date:
            return 'NO_EXPIRY'
        if self.expiry_date >= date.today():
            return 'ACTIVE'
        return 'EXPIRED'


class VendorRenewalInvoice(AuditBaseModel):
    """
    Invoice generated for vendor registration or renewal.

    Flow:
    1. Government generates invoice with fee amount + TSA bank details
    2. Vendor pays to the specified TSA bank account
    3. Vendor submits payment receipt
    4. Government confirms payment → GL entry: DR TSA Bank, CR Revenue
    5. Vendor activated (new) or renewed (existing)
    """
    STATUS_CHOICES = [
        ('GENERATED', 'Invoice Generated'),
        ('SENT', 'Sent to Vendor'),
        ('PAID', 'Payment Confirmed'),
        ('CANCELLED', 'Cancelled'),
    ]
    TYPE_CHOICES = [
        ('REGISTRATION', 'Initial Registration'),
        ('RENEWAL', 'Annual Renewal'),
    ]

    invoice_type = models.CharField(max_length=15, choices=TYPE_CHOICES, default='RENEWAL')
    invoice_number = models.CharField(max_length=30, unique=True, db_index=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='renewal_invoices')
    fiscal_year = models.ForeignKey(
        'accounting.FiscalYear', on_delete=models.PROTECT,
        related_name='renewal_invoices',
        help_text='Fiscal year the vendor is renewing for',
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tsa_account = models.ForeignKey(
        'accounting.TreasuryAccount', on_delete=models.PROTECT,
        related_name='renewal_invoices',
        help_text='TSA bank account where vendor should pay',
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='GENERATED')
    invoice_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(
        max_length=50, blank=True, default='',
        help_text='Vendor payment receipt/teller number',
    )
    payment_date = models.DateField(null=True, blank=True)
    journal = models.ForeignKey(
        'accounting.JournalHeader', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='renewal_invoices',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-invoice_date']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['fiscal_year', 'status']),
        ]

    def __str__(self):
        return f"RNW-{self.invoice_number} — {self.vendor.name} — NGN {self.amount:,.2f}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            from accounting.models.gl import TransactionSequence
            self.invoice_number = TransactionSequence.get_next('vendor_renewal', 'RNW-')
        super().save(*args, **kwargs)


class PurchaseRequest(StatusTransitionMixin, AuditBaseModel):
    """Initial request for purchase."""
    ALLOWED_TRANSITIONS = {
        'Draft': ['Pending', 'Approved'],
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

    def _generate_po_number(self):
        """Generate a sequential PO number for the current year: PO-YYYY-NNNNN.

        Mirrors the PR auto-numbering: locks the highest-numbered PO for the
        current year with select_for_update() so concurrent inserts queue
        instead of producing duplicates.
        """
        import datetime
        from django.db import transaction
        year = datetime.date.today().year
        prefix = f'PO-{year}-'
        with transaction.atomic():
            last = (
                PurchaseOrder.objects
                .select_for_update()
                .filter(po_number__startswith=prefix)
                .order_by('-po_number')
                .first()
            )
            if last and last.po_number:
                try:
                    last_seq = int(last.po_number.split('-')[-1])
                except (ValueError, IndexError):
                    last_seq = PurchaseOrder.objects.filter(
                        po_number__startswith=prefix
                    ).count()
            else:
                last_seq = 0
            return f'{prefix}{last_seq + 1:05d}'

    def save(self, *args, **kwargs):
        if not self.po_number:
            self.po_number = self._generate_po_number()

        self.clean()
        self.validate_status_transition()
        is_new = self.pk is None
        old_status = None

        # Calculate tax — only safe after the row exists, since `subtotal`
        # iterates `self.lines.all()` (a reverse relation that requires a PK).
        # On the initial INSERT the serializer creates the lines AFTER this
        # save, so a follow-up save triggered by the serializer (or by a
        # subsequent status transition) will recompute the correct tax.
        if self.pk:
            self.calculate_tax()

        if not is_new:
            old_inst = PurchaseOrder.objects.get(pk=self.pk)
            old_status = old_inst.status

        # Budget encumbrance transitions also require lines, so they only
        # make sense on UPDATE (when self.pk exists). On insert, status is
        # 'Draft' anyway — encumbrance kicks in later when status moves
        # to Approved/Posted.
        if self.pk and self.status in ['Approved', 'Posted'] and old_status not in ['Approved', 'Posted']:
            # ── Warrant ceiling check (PSA Authority to Incur Expenditure) ──
            # Block the Approved transition if the PO would push committed +
            # expended beyond what has been warranted/released. This is the
            # quarterly cash-release ceiling — distinct from the annual
            # appropriation ceiling already validated by
            # process_budget_encumbrance().
            self._check_warrant_ceiling()
            self.process_budget_encumbrance()
            # ── Register Appropriation commitment (ProcurementBudgetLink) ──
            # This is what populates the "Committed" column on the Budget
            # Execution Report. Booking it on Approved (not only Posted)
            # aligns with IPSAS — the MDA has a legal obligation the moment
            # the PO is approved, so the appropriation should be encumbered
            # immediately, not deferred to GL journal entry time.
            try:
                from accounting.services.procurement_commitments import create_commitment_for_po
                create_commitment_for_po(self)
            except Exception as exc:  # Don't block the save on commitment failure
                import logging
                logging.getLogger(__name__).warning(
                    "Commitment link failed for PO %s: %s", self.po_number, exc,
                )

        # Refresh commitment when an already-Approved/Posted PO is saved
        # (e.g. header edit or price change before any GRN exists).
        if self.pk and self.status in ['Approved', 'Posted'] and old_status in ['Approved', 'Posted']:
            try:
                from accounting.services.procurement_commitments import create_commitment_for_po
                create_commitment_for_po(self)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Commitment refresh failed for PO %s: %s", self.po_number, exc,
                )

        if self.pk and old_status in ['Approved', 'Posted'] and self.status in ['Rejected', 'Closed']:
            self.cancel_budget_encumbrance()
            # Release the appropriation commitment when the PO is cancelled.
            try:
                from accounting.services.procurement_commitments import cancel_commitment_for_po
                cancel_commitment_for_po(self)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Cancel commitment failed for PO %s: %s", self.po_number, exc,
                )

        super().save(*args, **kwargs)

    def _check_warrant_ceiling(self):
        """Validate the PO total against the released-warrant ceiling.

        Called from save() at the Draft → Approved transition. Raises
        ``ValidationError`` if the PO would exceed the cumulative warrants
        released against the matching Appropriation. The error bubbles
        up through DRF as a 400 with a structured message that the
        frontend turns into a red error banner.

        Aggregates by economic account so a multi-line PO that spans
        several economic codes is checked per-appropriation.
        """
        from accounting.budget_logic import (
            check_warrant_availability,
            is_warrant_pre_payment_enforced,
        )
        from collections import defaultdict
        from decimal import Decimal as _D

        # Pre-payment warrant enforcement is opt-in via
        # ``WARRANT_ENFORCEMENT_STAGE``. Default build runs the check
        # only at payment time, so PO commitment posts without
        # warrant interrogation.
        if not is_warrant_pre_payment_enforced():
            return

        # Group line totals by their economic account so each
        # appropriation's warrant balance is checked independently.
        account_totals: dict = defaultdict(lambda: _D('0'))
        for line in self.lines.all():
            if line.account:
                account_totals[line.account] += (line.quantity * line.unit_price)

        # Tax rolls into the first line's account (mirrors how tax is
        # encumbered today). If you eventually split tax across lines,
        # update this loop to match.
        if self.tax_amount and account_totals:
            first_acct = next(iter(account_totals))
            account_totals[first_acct] += self.tax_amount

        for account, amount in account_totals.items():
            allowed, message, _info = check_warrant_availability(
                dimensions={'mda': self.mda, 'fund': self.fund},
                account=account,
                amount=amount,
                exclude_po=self,  # don't double-count this PO if it's a re-approval
            )
            if not allowed:
                # Plain-string ValidationError — serializer renders it as
                # {"non_field_errors": ["..."]} which the frontend's red
                # banner picks up directly.
                raise ValidationError(message)

    def process_budget_encumbrance(self):
        """
        Groups lines by (account, mda, fund, function, program, geo), runs
        dual-engine budget validation, and creates BudgetEncumbrance records.

        Engine 1 — Legacy Budget table (backward-compat):
          Creates a BudgetEncumbrance row when an active Budget row exists.
          Tenants that have migrated fully to Appropriations won't have one,
          so the encumbrance is skipped — but the Appropriation check below
          still fires.

        Engine 2 — Modern Appropriation / BudgetCheckRule policy:
          Evaluates the tenant's configured check_policy against the
          Appropriation register, identical to the gate used by PR approval
          and AP Invoice posting. Hard blocks collected across all lines are
          raised as a single ValidationError at the end so the user sees
          every failing line in one response.
        """
        from accounting.budget_logic import get_active_budget
        from accounting.services.budget_check_rules import (
            check_policy, find_matching_appropriation,
        )
        import logging as _logging
        _log = _logging.getLogger('dtsg')

        budget_totals: dict = {}
        for line in self.lines.all():
            key = (line.account, self.mda, self.fund, self.function, self.program, self.geo)
            amount = line.unit_price * line.quantity
            budget_totals[key] = budget_totals.get(key, Decimal('0.00')) + amount

        hard_block_messages: list[str] = []

        for (account, mda, fund, function, program, geo), total_amount in budget_totals.items():
            # ── Engine 1: legacy Budget encumbrance ──────────────────────────
            budget = get_active_budget(
                dimensions={
                    'mda': mda, 'fund': fund,
                    'function': function, 'program': program, 'geo': geo,
                },
                account=account,
                date=self.order_date,
            )
            if budget is not None:
                BudgetEncumbrance.objects.update_or_create(
                    budget=budget,
                    reference_type='PO',
                    reference_id=self.pk,
                    defaults={
                        'encumbrance_date': self.order_date,
                        'amount': total_amount,
                        'status': 'ACTIVE',
                        'description': f"Encumbrance for PO {self.po_number}",
                    },
                )
            else:
                _log.warning(
                    "PO %s: no active legacy Budget for account %s — "
                    "encumbrance skipped; Appropriation check still applies.",
                    getattr(self, 'po_number', '?'),
                    getattr(account, 'code', account),
                )

            # ── Engine 2: modern Appropriation / policy check ─────────────
            fiscal_year = self.order_date.year if self.order_date else None
            appropriation = find_matching_appropriation(
                mda=mda, fund=fund, account=account,
                fiscal_year=fiscal_year,
            )
            result = check_policy(
                account_code=account.code if account else '',
                appropriation=appropriation,
                requested_amount=total_amount,
                transaction_label='purchase order',
                account_name=getattr(account, 'name', '') if account else '',
            )
            if result.blocked:
                mda_code = mda.code if mda else 'N/A'
                fund_code = fund.code if fund else 'N/A'
                acct_code = account.code if account else 'N/A'
                hard_block_messages.append(
                    f"[{mda_code}/{acct_code}/{fund_code}] {result.reason}"
                )

        if hard_block_messages:
            raise ValidationError(
                'Cannot approve PO: ' + '; '.join(hard_block_messages)
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
        constraints = [
            # Business rule: a Purchase Requisition can have at most ONE
            # active Purchase Order. "Active" means any status except
            # Rejected — so if a PO gets rejected the PR is free to be
            # converted again (with a fresh PO), but you cannot raise
            # two simultaneous POs against the same PR. Previously the
            # system silently allowed duplicate conversions.
            models.UniqueConstraint(
                fields=['purchase_request'],
                condition=models.Q(purchase_request__isnull=False) & ~models.Q(status='Rejected'),
                name='uniq_active_po_per_purchase_request',
            ),
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

    def _refresh_po_commitment(self):
        """Refresh the parent PO's appropriation commitment after a line change."""
        if self.po_id and self.po.status in ('Approved', 'Posted'):
            try:
                from accounting.services.procurement_commitments import create_commitment_for_po
                create_commitment_for_po(self.po)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Commitment refresh failed after line change on PO %s: %s",
                    self.po.po_number, exc,
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._refresh_po_commitment()

    def delete(self, *args, **kwargs):
        po = self.po  # capture before deletion removes the FK
        super().delete(*args, **kwargs)
        if po.status in ('Approved', 'Posted'):
            try:
                from accounting.services.procurement_commitments import create_commitment_for_po
                create_commitment_for_po(po)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Commitment refresh failed after line deletion on PO %s: %s",
                    po.po_number, exc,
                )

class GoodsReceivedNote(StatusTransitionMixin, AuditBaseModel):
    """Confirms receipt of goods/services."""
    ALLOWED_TRANSITIONS = {
        # PSA simple path (no Receiving Officer gating):  Draft → Posted
        # Approval-gated path:                            Draft → On Hold → Posted
        # Legacy receiving-bay path (still supported):    Draft → Received → Posted
        # In Public Sector Accounting the receipt and the posting are a single
        # operational step ("post the GRN" = "confirm goods received and book
        # the GL entry"), so we allow Draft → Posted directly.
        'Draft':     ['Received', 'On Hold', 'Posted', 'Cancelled'],
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
        help_text=(
            "Receiving warehouse for this GRN. Auto-resolved from the MDA "
            "via inventory.services.get_default_warehouse_for_mda() — not "
            "exposed in the UI."
        ),
    )
    mda = models.ForeignKey(
        MDA, on_delete=models.PROTECT,
        null=True, blank=True,  # nullable for migration; tightened in stage-3 migration
        related_name='goods_received_notes',
        help_text=(
            "The MDA receiving the goods/services. Must match "
            "purchase_order.mda — enforced in clean(). Auto-populated from "
            "the PO on first save."
        ),
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

    def clean(self):
        """Enforce MDA consistency with the originating Purchase Order.

        A GRN must always receive goods against the same MDA that raised the
        PO — otherwise the P2P audit trail breaks and one ministry could
        "receive" goods charged to another ministry's budget. Auto-population
        in ``save()`` handles the happy path; this guard catches direct
        API/shell attempts to override the MDA.
        """
        super().clean()
        if self.mda_id and self.purchase_order_id:
            po_mda_id = self.purchase_order.mda_id
            if po_mda_id and self.mda_id != po_mda_id:
                raise ValidationError({
                    'mda': (
                        f"GRN MDA must match the Purchase Order's MDA "
                        f"(PO {self.purchase_order.po_number} is assigned "
                        f"to MDA id={po_mda_id}, got id={self.mda_id})."
                    )
                })

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

        # Auto-populate MDA from the originating PO when missing. The UI no
        # longer asks the user to pick a warehouse — MDA is the public-sector
        # accountable custodian and is copied straight from the PO. Running
        # before validate_status_transition() so clean() sees a consistent
        # MDA during ModelForm / serializer validation.
        if not self.mda_id and self.purchase_order_id:
            self.mda_id = self.purchase_order.mda_id

        # Auto-resolve the default Warehouse for this MDA so inventory
        # tracking (ItemStock / StockMovement / ItemBatch) keeps working
        # without changing the inventory schema. Idempotent per MDA.
        if not self.warehouse_id and self.mda_id:
            from inventory.services import get_default_warehouse_for_mda
            self.warehouse = get_default_warehouse_for_mda(self.mda)

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

                # Receiving warehouse is auto-resolved from self.mda in the
                # early save() block above, so it is always populated by the
                # time we get here. The "first active warehouse" fallback
                # was removed because it could route Ministry-of-Health goods
                # into the Ministry-of-Education stores.
                from inventory.models import StockMovement
                receiving_warehouse = self.warehouse
                if not receiving_warehouse:
                    raise ValidationError(
                        "GRN has no resolved warehouse — MDA missing or "
                        "get_default_warehouse_for_mda() failed."
                    )

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
                    # Posted -> Closed is a legitimate PO lifecycle
                    # transition; ``ImmutableModelMixin.save`` otherwise
                    # rejects any edit to a Posted row with
                    # "Cannot modify a posted transaction". Flag the
                    # save explicitly so the guard lets the status
                    # move through while still refusing unrelated
                    # edits elsewhere.
                    po.save(_allow_status_change=True)

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

                # Commitment status progression: ACTIVE → INVOICED
                # Goods are now physically received but unpaid. INVOICED
                # still counts toward Appropriation.total_committed
                # (which sums status IN ('ACTIVE', 'INVOICED')) so the
                # budget encumbrance is preserved until the PV pays.
                try:
                    from accounting.services.procurement_commitments import (
                        mark_commitment_invoiced_for_po,
                    )
                    mark_commitment_invoiced_for_po(po)
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "GRN %s: commitment INVOICED flip failed (non-fatal): %s",
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
            # Validate that total received across all GRNs does not exceed PO qty.
            # Race-safe: re-read the PO line under select_for_update so two
            # concurrent GRN line saves can't both pass the over-receipt
            # check against the same stale ``quantity_received`` value.
            # Locking is best-effort outside of an atomic block (Django
            # raises ``TransactionManagementError`` if no transaction is
            # active) — the model save() is typically wrapped in atomic()
            # by the caller (post_grn / serializer save), but if not we
            # fall back to a plain reload.
            from django.db import transaction as _txn
            try:
                po_line_locked = (
                    type(self.po_line).objects
                    .select_for_update()
                    .get(pk=self.po_line_id)
                )
            except _txn.TransactionManagementError:
                po_line_locked = type(self.po_line).objects.get(pk=self.po_line_id)
            already_received = po_line_locked.quantity_received or Decimal('0')
            # Exclude self if updating an existing line
            if self.pk:
                existing = GoodsReceivedNoteLine.objects.filter(pk=self.pk).first()
                if existing:
                    already_received -= existing.quantity_received
            remaining = po_line_locked.quantity - already_received
            if self.quantity_received > remaining:
                raise ValidationError(
                    f"Cannot receive {self.quantity_received}. "
                    f"PO line qty: {po_line_locked.quantity}, "
                    f"already received: {already_received}, "
                    f"remaining: {remaining}."
                )

            total_after = already_received + self.quantity_received
            if total_after < po_line_locked.quantity:
                self.received_quantity_status = 'Partial'
            else:
                self.received_quantity_status = 'Full'
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.quantity_received * self.po_line.unit_price

    def __str__(self):
        return f"GRN Line: {self.po_line}"

class DownPaymentRequest(StatusTransitionMixin, AuditBaseModel):
    """Down payment / advance payment request raised when a PO is created.
    Finance reviews and processes it into an actual Payment.

    State machine (enforced via ``StatusTransitionMixin``):
      Pending → Approved | Rejected
      Approved → Processed | Rejected
      Processed (terminal)
      Rejected (terminal)
    """

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
    ALLOWED_TRANSITIONS = {
        'Pending':   ['Approved', 'Rejected'],
        'Approved':  ['Processed', 'Rejected'],
        'Processed': [],   # terminal
        'Rejected':  [],   # terminal
    }

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
      Draft → Matched        (calculate_match: variance ≤ threshold)
      Draft → Variance       (calculate_match: variance > threshold)
      Pending_Review → Approved / Rejected
      Matched → Pending_Review (submit after manual match)
      Matched → Variance / Rejected
      Variance → Rejected / Matched
    """
    ALLOWED_TRANSITIONS = {
        # ``Variance`` is reachable from Draft because ``calculate_match``
        # (called from save()) computes the status based on variance %.
        # A freshly-created matching with above-threshold variance is
        # legitimately Variance from inception — without enumerating
        # this path, every over-threshold post fails with
        # "Invalid status transition from 'Draft' to 'Variance'".
        'Draft':          ['Pending_Review', 'Matched', 'Variance', 'Rejected'],
        'Pending_Review': ['Approved', 'Rejected'],
        'Matched':        ['Pending_Review', 'Variance', 'Rejected', 'Approved'],
        'Variance':       ['Matched', 'Rejected'],
        'Approved':       [],
        'Rejected':       [],
    }
    # System-allocated tracking number for the verification record itself.
    # Distinct from ``invoice_reference`` (the vendor's number on their
    # paperwork): this is the in-house IV-YYYY-NNNNN identifier that
    # users quote when emailing/calling about the verification — every
    # downstream document (VendorInvoice, PaymentVoucher, JournalEntry)
    # also surfaces this so a single audit trail crosses subsystems.
    # Allocated automatically in save() via TransactionSequence; existing
    # rows get backfilled by migration 0047.
    verification_number = models.CharField(
        max_length=30, db_index=True, blank=True, default='',
        help_text='In-house tracking number, e.g. IV-2026-00001.',
    )

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

    # Tax code (VAT / input tax) and withholding tax selections.
    # When set these FKs drive automatic VAT / WHT computation at post-to-GL
    # time via the VendorInvoiceLine the matching provisions.
    tax_code = models.ForeignKey(
        'accounting.TaxCode', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invoice_matchings',
        help_text='VAT / input-tax code to apply to invoice subtotal.',
    )
    withholding_tax = models.ForeignKey(
        'accounting.WithholdingTax', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invoice_matchings',
        help_text='Withholding tax code to apply to invoice subtotal.',
    )
    wht_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Computed WHT amount = subtotal × withholding_tax.rate.',
    )
    # Transaction-level WHT exemption override — analogous to SAP BP's
    # per-document "exempt from withholding" flag. When set, WHT is NOT
    # computed even if the vendor master carries a default WHT code.
    # Separate from Vendor.wht_exempt (which is a permanent master-data
    # exemption); this one is episodic (e.g. contract-by-contract).
    wht_exempt = models.BooleanField(
        default=False,
        help_text='Exempt this transaction from withholding tax, overriding the vendor default.',
    )
    wht_exempt_reason = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Audit reason for the transaction-level WHT exemption.',
    )

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
    # Widened from (5,2) → (10,2) so over-threshold variances don't
    # overflow Postgres NUMERIC(5,2). The legacy precision capped the
    # field at 999.99% — but a partial GRN (e.g. ₦81k received vs
    # ₦1.075M invoiced) yields a real variance of ~1226%, which is
    # mathematically valid and must persist on the matching record so
    # the variance gate / payment hold can act on it. (10,2) gives
    # headroom up to 99,999,999.99% — safely beyond any sane data.
    variance_percentage = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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

        # Tax-neutral comparison amount. GRN value is computed as
        # qty × unit_price with no tax (the warehouse never books
        # VAT), so comparing the gross invoice (which INCLUDES VAT)
        # against the GRN fires a false variance equal to the tax
        # rate on every VAT-bearing invoice. ``compare_amount``
        # strips the VAT for the GRN comparison; the gross
        # ``invoice_amount`` is still used in the PO comparison
        # (PO contracts include VAT) and in the variance_amount
        # reported to operators (so the on-screen Naira diff
        # reflects what they actually billed).
        invoice_tax = self.invoice_tax_amount or 0
        compare_amount = (
            self.invoice_subtotal
            if (invoice_tax > 0 and self.invoice_subtotal)
            else self.invoice_amount
        )

        if self.invoice_amount == self.po_amount == grn_amount:
            self.match_type = 'Full'
            self.status = 'Matched'
            self.variance_amount = 0
            self.variance_percentage = 0
        elif compare_amount == grn_amount:
            if self.po_fully_received:
                self.match_type = 'Full'
                self.status = 'Matched'
                self.variance_amount = self.invoice_amount - self.po_amount
            else:
                self.match_type = 'Partial'
                self.status = 'Pending_Review'
                self.variance_amount = self.invoice_amount - self.po_amount
            if self.po_amount and self.po_amount > 0:
                self.variance_percentage = _cap_variance_pct(
                    quantize_currency((abs(self.variance_amount) / self.po_amount) * 100)
                )
        else:
            self.match_type = 'Partial'
            # Variance Naira amount stays gross (operator-facing,
            # matches the on-screen invoice they typed). Variance
            # percentage uses the tax-neutral ``compare_amount`` so
            # the gate doesn't false-trip on the VAT delta.
            self.variance_amount = quantize_currency(self.invoice_amount - (grn_amount or self.po_amount))
            pct_numerator = abs(compare_amount - (grn_amount or self.po_amount))
            pct_base = grn_amount or self.po_amount
            if pct_base and pct_base > 0:
                self.variance_percentage = _cap_variance_pct(
                    quantize_currency((pct_numerator / pct_base) * 100)
                )

            if self.variance_percentage <= variance_threshold:
                self.status = 'Matched'
                self.payment_hold = False
            else:
                self.status = 'Variance'
                self.payment_hold = True

    def save(self, *args, **kwargs):
        # Allocate the system-tracking number on first save so every new
        # verification gets a stable identifier the user can quote. Same
        # pattern as JournalHeader.document_number (TransactionSequence-
        # backed). Wrapped in try/except — sequence allocation must
        # never block the save (blank verification_number is tolerated
        # by the field default; UI falls back to ``IV-{id}``).
        if not self.pk and not self.verification_number:
            try:
                from accounting.models.gl import TransactionSequence
                self.verification_number = TransactionSequence.get_next(
                    'invoice_verification', 'IV-',
                )
            except Exception:  # noqa: BLE001
                pass
        # WARN-3 FIX: enforce valid transitions (StatusTransitionMixin.validate_status_transition
        # must be called explicitly; it is not automatic).
        self.validate_status_transition()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['verification_number']),
        ]

    def __str__(self):
        return f"{self.verification_number or f'IV-{self.pk or 0}'} — {self.invoice_reference}"


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


# =============================================================================
# BPP DUE PROCESS COMPLIANCE
# =============================================================================

class ProcurementThreshold(models.Model):
    """
    BPP Procurement thresholds — determines approval authority level.
    Values per the Public Procurement Act 2007 and State Procurement Laws.

    When a PO amount is being approved, the system checks against these thresholds
    to route to the correct authority and determine if a No Objection Certificate is required.
    """
    CATEGORY_CHOICES = [
        ('GOODS_SERVICES', 'Goods & Services'),
        ('WORKS',          'Works / Construction'),
        ('CONSULTANCY',    'Consultancy Services'),
    ]
    AUTHORITY_CHOICES = [
        ('ACCOUNTING_OFFICER', 'Accounting Officer'),
        ('PTB',                'Parastatal Tenders Board (PTB)'),
        ('MTB',                'Ministerial Tenders Board (MTB)'),
        ('EXCO',               'State Executive Council'),
        ('BPP',                'Bureau of Public Procurement'),
    ]

    category        = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    authority_level = models.CharField(max_length=25, choices=AUTHORITY_CHOICES)
    min_amount      = models.DecimalField(max_digits=20, decimal_places=2)
    max_amount      = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text="Null = unlimited (highest tier)",
    )
    requires_bpp_no = models.BooleanField(
        default=False,
        help_text="Requires No Objection Certificate from BPP",
    )
    fiscal_year     = models.ForeignKey(
        'accounting.FiscalYear', on_delete=models.PROTECT,
        null=True, blank=True,
        help_text="Null = applies to all fiscal years",
    )
    is_active       = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'min_amount']
        verbose_name = 'BPP Procurement Threshold'
        verbose_name_plural = 'BPP Procurement Thresholds'

    def __str__(self):
        max_display = f"NGN {self.max_amount:,.2f}" if self.max_amount else "Unlimited"
        return f"{self.category} | {self.authority_level} | NGN {self.min_amount:,.2f} - {max_display}"

    @classmethod
    def get_authority_level(cls, amount: Decimal, category: str) -> dict:
        """
        Returns the appropriate approval authority for a given procurement amount.
        Returns dict with authority_level, requires_bpp_no, threshold_id.
        """
        threshold = cls.objects.filter(
            category=category,
            min_amount__lte=amount,
            is_active=True,
        ).filter(
            models.Q(max_amount__gte=amount) | models.Q(max_amount__isnull=True),
        ).order_by('-min_amount').first()

        if threshold:
            return {
                'authority_level': threshold.authority_level,
                'requires_bpp_no': threshold.requires_bpp_no,
                'threshold_id': threshold.pk,
            }
        # Default to highest authority if no threshold matches
        return {
            'authority_level': 'EXCO',
            'requires_bpp_no': True,
            'threshold_id': None,
        }


class CertificateOfNoObjection(AuditBaseModel):
    """
    BPP No Objection Certificate (NOC) — required for procurements above threshold.
    Purchase Order CANNOT be issued without a valid NOC above the BPP threshold.
    Section 16 of the Public Procurement Act 2007.
    """
    purchase_order     = models.OneToOneField(
        'procurement.PurchaseOrder', on_delete=models.PROTECT,
        related_name='no_objection',
    )
    certificate_number = models.CharField(max_length=50, unique=True)
    issued_date        = models.DateField()
    expiry_date        = models.DateField()
    authority_level    = models.CharField(max_length=25)
    issuing_officer    = models.CharField(max_length=200)
    is_valid           = models.BooleanField(default=True)
    amount_covered     = models.DecimalField(max_digits=20, decimal_places=2)
    scope_description  = models.TextField()
    conditions         = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Certificate of No Objection'
        verbose_name_plural = 'Certificates of No Objection'

    def __str__(self):
        return f"NOC {self.certificate_number} - PO {self.purchase_order}"

    def save(self, *args, **kwargs):
        """Auto-invalidate expired certificates on every save."""
        from django.utils import timezone
        if self.expiry_date and self.expiry_date < timezone.now().date():
            self.is_valid = False
        super().save(*args, **kwargs)


class ProcurementBudgetLink(models.Model):
    """
    Links a Purchase Order to its appropriation — enforces budget availability.
    Created automatically when PO is approved.

    This is the commitment (encumbrance) record that reduces the available
    appropriation balance when a PO is approved.
    """
    purchase_order   = models.OneToOneField(
        'procurement.PurchaseOrder', on_delete=models.PROTECT,
        related_name='budget_link',
    )
    appropriation    = models.ForeignKey(
        'budget.Appropriation', on_delete=models.PROTECT,
        related_name='commitments',
    )
    committed_amount = models.DecimalField(max_digits=20, decimal_places=2)
    ncoa_code        = models.ForeignKey(
        'accounting.NCoACode', on_delete=models.PROTECT,
        related_name='procurement_commitments',
    )
    committed_at     = models.DateTimeField(auto_now_add=True)
    status           = models.CharField(
        max_length=20, default='ACTIVE',
        choices=[
            ('ACTIVE',    'Active Commitment'),
            ('INVOICED',  'Partially/Fully Invoiced'),
            ('CLOSED',    'Closed'),
            ('CANCELLED', 'Cancelled'),
        ],
    )

    class Meta:
        verbose_name = 'Procurement Budget Link'
        verbose_name_plural = 'Procurement Budget Links'
        indexes = [
            models.Index(fields=['appropriation', 'status'], name='cmt_appr_status_idx'),
        ]

    def __str__(self):
        return f"PO {self.purchase_order} -> APP {self.appropriation.pk}"
