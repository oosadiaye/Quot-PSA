import logging
from rest_framework import serializers

logger = logging.getLogger(__name__)
from .models import (
    Vendor, VendorCategory, PurchaseRequest, PurchaseRequestLine, PurchaseOrder, PurchaseOrderLine,
    GoodsReceivedNote, GoodsReceivedNoteLine, InvoiceMatching,
    VendorCreditNote, VendorDebitNote, PurchaseReturn, PurchaseReturnLine,
    DownPaymentRequest,
)
from accounting.models import MDA


class PositiveDecimalMixin:
    """Reusable validation for quantity and price fields."""

    def validate_quantity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_unit_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Unit price cannot be negative.")
        return value

class VendorCategorySerializer(serializers.ModelSerializer):
    reconciliation_account_name = serializers.CharField(
        source='reconciliation_account.name', read_only=True)
    reconciliation_account_code = serializers.CharField(
        source='reconciliation_account.code', read_only=True)
    vendor_count = serializers.IntegerField(source='_vendor_count', read_only=True, default=0)

    class Meta:
        model = VendorCategory
        fields = [
            'id', 'name', 'code', 'description',
            'reconciliation_account', 'reconciliation_account_name', 'reconciliation_account_code',
            'is_active', 'vendor_count',
        ]
        read_only_fields = ['id']


class VendorSerializer(serializers.ModelSerializer):
    performance_rating = serializers.ReadOnlyField()
    on_time_delivery_rate = serializers.ReadOnlyField()
    current_balance = serializers.DecimalField(max_digits=19, decimal_places=2, read_only=True, default=0)
    category_name = serializers.CharField(source='category.name', read_only=True)
    is_registration_valid = serializers.BooleanField(read_only=True)
    registration_status = serializers.CharField(read_only=True)
    fiscal_year_name = serializers.CharField(source='registration_fiscal_year.name', read_only=True, default='')

    class Meta:
        model = Vendor
        fields = [
            'id', 'name', 'code', 'category', 'category_name',
            'tax_id', 'address', 'email', 'phone',
            'is_active',
            'registration_number', 'registration_fiscal_year', 'fiscal_year_name',
            'registration_date', 'expiry_date',
            'is_registration_valid', 'registration_status',
            'bank_name', 'bank_account_number', 'bank_sort_code',
            'total_orders', 'on_time_deliveries', 'quality_score',
            'total_purchase_value', 'performance_rating', 'on_time_delivery_rate',
            'current_balance',
            'withholding_tax_code', 'wht_exempt',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by',
                            'is_registration_valid', 'registration_status', 'fiscal_year_name']

class PurchaseRequestLineSerializer(PositiveDecimalMixin, serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True, allow_null=True)
    account_name = serializers.CharField(source='account.name', read_only=True, allow_null=True)
    asset_name = serializers.CharField(source='asset.name', read_only=True, default='')
    item_name = serializers.CharField(source='item.name', read_only=True, allow_null=True)
    product_type_name = serializers.CharField(source='product_type.get_name_display', read_only=True, allow_null=True)
    product_category_name = serializers.CharField(source='product_category.name', read_only=True, allow_null=True)
    total_estimated_price = serializers.ReadOnlyField()

    class Meta:
        model = PurchaseRequestLine
        fields = [
            'id', 'item_description', 'quantity', 'estimated_unit_price',
            'account', 'account_code', 'account_name', 'asset', 'asset_name',
            'item', 'item_name', 'product_type', 'product_type_name',
            'product_category', 'product_category_name',
            'total_estimated_price',
        ]
        extra_kwargs = {
            'account': {'required': False, 'allow_null': True},
        }

    def validate_estimated_unit_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Estimated unit price cannot be negative.")
        return value

class PurchaseRequestSerializer(serializers.ModelSerializer):
    lines = PurchaseRequestLineSerializer(many=True)
    mda_name = serializers.ReadOnlyField(source='mda.name', allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounting.serializers import is_dimensions_enabled
        dims_enabled = is_dimensions_enabled(self.context)
        if dims_enabled:
            # Budget control pillars — MDA + Fund required
            for field in ['mda', 'fund']:
                if field in self.fields:
                    self.fields[field].required = True
                    self.fields[field].allow_null = False
            # Reporting dimensions — required for IPSAS reports
            for field in ['function', 'program', 'geo']:
                if field in self.fields:
                    self.fields[field].required = True
                    self.fields[field].allow_null = False
        else:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                if field in self.fields:
                    self.fields[field].required = False
                    self.fields[field].allow_null = True

    fund_name = serializers.ReadOnlyField(source='fund.name')
    function_name = serializers.ReadOnlyField(source='function.name')
    program_name = serializers.ReadOnlyField(source='program.name')
    geo_name = serializers.ReadOnlyField(source='geo.name')
    cost_center_name = serializers.CharField(source='cost_center.name', read_only=True, default='')
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True, allow_null=True)
    # Convert-to-PO guard — the UI uses these to hide the "Convert to PO"
    # button and show a "View PO" link once the PR has been converted.
    active_po_id = serializers.SerializerMethodField()
    active_po_number = serializers.SerializerMethodField()
    active_po_status = serializers.SerializerMethodField()

    def get_active_po_id(self, obj):
        po = self._active_po(obj)
        return po.id if po else None

    def get_active_po_number(self, obj):
        po = self._active_po(obj)
        return po.po_number if po else None

    def get_active_po_status(self, obj):
        po = self._active_po(obj)
        return po.status if po else None

    def _active_po(self, obj):
        """Return the single non-Rejected PO linked to this PR, if any.

        One-PO-per-PR is enforced by the DB constraint
        ``uniq_active_po_per_purchase_request`` so this will always be 0
        or 1 rows. Cached on the serializer instance per-obj to avoid
        re-querying inside the same render.
        """
        cache = getattr(self, '_active_po_cache', None)
        if cache is None:
            cache = self._active_po_cache = {}
        if obj.pk in cache:
            return cache[obj.pk]
        from procurement.models import PurchaseOrder
        po = (
            PurchaseOrder.objects
            .filter(purchase_request_id=obj.pk)
            .exclude(status='Rejected')
            .only('id', 'po_number', 'status')
            .first()
        )
        cache[obj.pk] = po
        return po

    class Meta:
        model = PurchaseRequest
        fields = [
            'id', 'request_number', 'description', 'requested_date', 'requested_by', 'requested_by_name',
            'priority', 'status', 'mda', 'mda_name', 'fund', 'fund_name', 'function', 'function_name',
            'program', 'program_name', 'geo', 'geo_name', 'cost_center', 'cost_center_name',
            'lines', 'created_at', 'updated_at',
            'active_po_id', 'active_po_number', 'active_po_status',
        ]
        read_only_fields = [
            'id', 'request_number', 'requested_date', 'created_at', 'updated_at',
            'active_po_id', 'active_po_number', 'active_po_status',
        ]

    def validate(self, data):
        # P2P-H5: PR Budget Period Date Validation
        # Ensure PR dates fall within budget period

        requested_date = data.get('requested_date')

        try:
            from accounting.models import BudgetPeriod

            if requested_date:
                period = BudgetPeriod.get_period_for_date(requested_date)
                if period:
                    if period.status in ['CLOSED', 'LOCKED']:
                        raise serializers.ValidationError({
                            'requested_date': f"Budget period for this date is {period.status}. Cannot create PR."
                        })
                elif BudgetPeriod.objects.exists():
                    raise serializers.ValidationError({
                        'requested_date': "No budget period configured for this date. Please configure fiscal periods."
                    })
        except ImportError:
            pass  # BudgetPeriod model not available

        return data

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        request = PurchaseRequest.objects.create(**validated_data)
        for line_data in lines_data:
            PurchaseRequestLine.objects.create(request=request, **line_data)
        return request

class PurchaseOrderLineSerializer(PositiveDecimalMixin, serializers.ModelSerializer):
    account_name = serializers.ReadOnlyField(source='account.name')
    total_price = serializers.ReadOnlyField()
    pending_quantity = serializers.ReadOnlyField()
    is_fully_received = serializers.ReadOnlyField()
    item_name = serializers.CharField(source='item.name', read_only=True, allow_null=True)
    item_shelf_life_days = serializers.IntegerField(source='item.shelf_life_days', read_only=True, allow_null=True)
    product_type_name = serializers.CharField(source='product_type.get_name_display', read_only=True, allow_null=True)
    product_category_name = serializers.CharField(source='product_category.name', read_only=True, allow_null=True)
    asset_name = serializers.CharField(source='asset.name', read_only=True, default='')

    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'item_description', 'quantity', 'quantity_received', 'pending_quantity',
            'unit_price', 'account', 'account_name', 'total_price', 'is_fully_received',
            'item', 'item_name', 'item_shelf_life_days',
            'product_type', 'product_type_name',
            'product_category', 'product_category_name',
            'asset', 'asset_name',
        ]

class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)
    vendor_name = serializers.ReadOnlyField(source='vendor.name')
    # Vendor-master defaults surfaced read-only so the Invoice Verification
    # form can pre-select the WHT code and honour a permanent exemption
    # without a second API call.
    vendor_wht_code = serializers.PrimaryKeyRelatedField(
        source='vendor.withholding_tax_code', read_only=True, allow_null=True,
    )
    vendor_wht_code_label = serializers.SerializerMethodField()
    vendor_wht_exempt = serializers.ReadOnlyField(source='vendor.wht_exempt')

    def get_vendor_wht_code_label(self, obj):
        wht = getattr(obj.vendor, 'withholding_tax_code', None) if obj.vendor else None
        if not wht:
            return ''
        return f"{wht.code} · {wht.name} ({wht.rate}%)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounting.serializers import is_dimensions_enabled
        dims_enabled = is_dimensions_enabled(self.context)
        if dims_enabled:
            for field in ['mda', 'fund']:
                if field in self.fields:
                    self.fields[field].required = True
                    self.fields[field].allow_null = False
            for field in ['function', 'program', 'geo']:
                if field in self.fields:
                    self.fields[field].required = True
                    self.fields[field].allow_null = False
        else:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                if field in self.fields:
                    self.fields[field].required = False
                    self.fields[field].allow_null = True

    mda_name = serializers.ReadOnlyField(source='mda.name', allow_null=True)
    mda_code = serializers.ReadOnlyField(source='mda.code', allow_null=True)
    fund_name = serializers.ReadOnlyField(source='fund.name')
    function_name = serializers.ReadOnlyField(source='function.name')
    program_name = serializers.ReadOnlyField(source='program.name')
    geo_name = serializers.ReadOnlyField(source='geo.name')
    subtotal = serializers.ReadOnlyField()
    total_amount = serializers.ReadOnlyField()
    # Computed lock indicator — true when at least one non-Cancelled GRN exists against this PO.
    # Used by the frontend to conditionally disable Edit / Cancel buttons.
    has_active_grns = serializers.SerializerMethodField()

    def get_has_active_grns(self, obj):
        return obj.goodsreceivednote_set.exclude(status='Cancelled').exists()

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'vendor', 'vendor_name',
            'vendor_wht_code', 'vendor_wht_code_label', 'vendor_wht_exempt',
            'purchase_request', 'order_date',
            'expected_delivery_date', 'delivery_address', 'delivery_contact', 'payment_terms',
            'tax_rate', 'tax_amount', 'subtotal', 'total_amount', 'notes', 'terms_and_conditions',
            'tax_code', 'wht_exempt',
            'status', 'mda', 'mda_name', 'mda_code',
            'fund', 'fund_name', 'function', 'function_name',
            'program', 'program_name', 'geo', 'geo_name', 'lines',
            'has_active_grns',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'po_number', 'has_active_grns', 'created_at', 'updated_at']

    def validate(self, data):
        # ── Vendor registration validity check ──────────────────
        vendor = data.get('vendor')
        if vendor and hasattr(vendor, 'is_registration_valid'):
            if not vendor.is_registration_valid:
                raise serializers.ValidationError({
                    'vendor': f"Vendor '{vendor.name}' registration has expired "
                              f"(expiry: {vendor.expiry_date}). "
                              f"Renew the vendor's registration before creating a Purchase Order."
                })

        order_date = data.get('order_date')
        expected_delivery_date = data.get('expected_delivery_date')
        if order_date and expected_delivery_date and expected_delivery_date < order_date:
            raise serializers.ValidationError({
                'expected_delivery_date': "Expected delivery date cannot be before order date."
            })

        # P2P-H2: Require Approved PR for PO
        purchase_request = data.get('purchase_request')
        if purchase_request and purchase_request.status != 'Approved':
            raise serializers.ValidationError({
                'purchase_request': f"Purchase Request must be in 'Approved' status. Current status: '{purchase_request.status}'"
            })

        # P2P-H6: PO vs PR Price Validation
        lines = data.get('lines', [])
        if lines and purchase_request:
            try:
                from .models import PurchaseRequestLine
                pr_lines = {pl.item_description: pl for pl in purchase_request.lines.all()}

                for idx, line in enumerate(lines):
                    unit_price = line.get('unit_price')
                    item_desc = line.get('item_description')
                    po_line = line.get('po_line')

                    if po_line and unit_price is not None and item_desc in pr_lines:
                        pr_line = pr_lines[item_desc]
                        if pr_line.estimated_unit_price and unit_price > pr_line.estimated_unit_price:
                            from decimal import Decimal
                            variance = unit_price - pr_line.estimated_unit_price
                            variance_pct = (variance / pr_line.estimated_unit_price * Decimal('100')).quantize(Decimal('0.01'))
                            raise serializers.ValidationError({
                                f'lines[{idx}]': f"PO price ({unit_price}) exceeds PR estimated price ({pr_line.estimated_unit_price}). Variance: {variance} ({variance_pct}%)"
                            })
            except ImportError as exc:
                logger.warning(
                    "procurement serializer: PurchaseRequest model unavailable; "
                    "skipping PO-vs-PR price variance check: %s", exc,
                )

        return data

    def create(self, validated_data):
        # PO header save runs first (PK is needed before lines can FK to it).
        # Lines are then created. Finally we save the PO again so its
        # `save()` recomputes tax_amount from the now-existing lines.
        lines_data = validated_data.pop('lines')
        order = PurchaseOrder.objects.create(**validated_data)
        for line_data in lines_data:
            PurchaseOrderLine.objects.create(po=order, **line_data)
        order.save()  # second save: now self.pk exists, calculate_tax() can iterate self.lines
        return order


class DownPaymentRequestSerializer(serializers.ModelSerializer):
    po_number = serializers.ReadOnlyField(source='purchase_order.po_number')
    vendor_name = serializers.ReadOnlyField(source='purchase_order.vendor.name')
    bank_account_name = serializers.ReadOnlyField(source='bank_account.name')
    payment_number = serializers.ReadOnlyField(source='payment.payment_number')
    # Exposes the unspent advance balance from the linked Payment record.
    # Used by the invoice verification form to show how much can still be deducted.
    advance_remaining = serializers.SerializerMethodField()

    def get_advance_remaining(self, obj):
        if obj.payment_id and obj.payment:
            return str(obj.payment.advance_remaining)
        return None

    class Meta:
        model = DownPaymentRequest
        fields = [
            'id', 'request_number', 'purchase_order', 'po_number', 'vendor_name',
            'calc_type', 'calc_value', 'requested_amount',
            'payment_method', 'bank_account', 'bank_account_name',
            'status', 'notes', 'payment', 'payment_number', 'advance_remaining',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = [
            'id', 'request_number', 'advance_remaining', 'created_at', 'updated_at', 'created_by', 'updated_by',
        ]


class GoodsReceivedNoteLineSerializer(serializers.ModelSerializer):
    # item_description was removed from GoodsReceivedNoteLine in migration 0005;
    # we derive it from the PO line for display purposes only.
    item_description = serializers.ReadOnlyField(source='po_line.item_description')
    # Alias kept for backwards compat — both names return the same value.
    po_line_item = serializers.ReadOnlyField(source='po_line.item_description')
    # unit_price lives on PurchaseOrderLine, not on the GRN line itself.
    unit_price = serializers.ReadOnlyField(source='po_line.unit_price')

    class Meta:
        model = GoodsReceivedNoteLine
        fields = [
            'id', 'po_line', 'po_line_item', 'item_description', 'unit_price',
            'quantity_received', 'batch_number', 'expiry_date',
        ]

    def validate_quantity_received(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Quantity received must be greater than zero.")
        return value

class GoodsReceivedNoteSerializer(serializers.ModelSerializer):
    lines = GoodsReceivedNoteLineSerializer(many=True)
    po_number = serializers.ReadOnlyField(source='purchase_order.po_number')

    # MDA is the new primary receiving dimension. Optional on input — when
    # missing, the model's save() hook copies it from the PO. Pass it
    # explicitly when you want defense-in-depth (the validate() block then
    # checks PO-vs-MDA consistency).
    mda = serializers.PrimaryKeyRelatedField(
        queryset=MDA.objects.all(),
        required=False, allow_null=True,
    )
    mda_name = serializers.ReadOnlyField(source='mda.name')
    mda_code = serializers.ReadOnlyField(source='mda.code')

    # Warehouse is auto-resolved from the MDA in the model's save() hook
    # (see inventory.services.get_default_warehouse_for_mda). The UI no
    # longer asks for it, but list/detail responses still surface it for
    # downstream inventory drilldowns.
    warehouse = serializers.PrimaryKeyRelatedField(read_only=True)
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')

    class Meta:
        model = GoodsReceivedNote
        fields = [
            'id', 'grn_number', 'purchase_order', 'po_number',
            'received_date', 'received_by',
            'mda', 'mda_name', 'mda_code',
            'warehouse', 'warehouse_name',
            'status', 'notes', 'lines',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = [
            'id', 'grn_number',
            'warehouse', 'warehouse_name',
            'created_at', 'updated_at', 'created_by', 'updated_by', 'status',
        ]

    def validate(self, data):
        received_date = data.get('received_date')
        purchase_order = data.get('purchase_order')
        if received_date and purchase_order and received_date < purchase_order.order_date:
            raise serializers.ValidationError({
                'received_date': "Received date cannot be before the purchase order date."
            })

        # Cross-field check: when both mda and purchase_order are supplied,
        # they must agree. The model's clean() repeats this check at the
        # ORM layer; doing it here surfaces a friendlier 400 to the API.
        mda = data.get('mda')
        if mda and purchase_order and purchase_order.mda_id and mda.pk != purchase_order.mda_id:
            raise serializers.ValidationError({
                'mda': (
                    f"GRN MDA ({mda.code}) must match the Purchase Order's "
                    f"MDA. PO {purchase_order.po_number} is assigned to "
                    f"a different MDA."
                )
            })
        return data

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        grn = GoodsReceivedNote.objects.create(**validated_data)
        for line_data in lines_data:
            # `item_description` was removed from GoodsReceivedNoteLine (migration 0005).
            # It is a ReadOnlyField derived from po_line, so it will never appear in
            # validated_data. Do NOT inject it into line_data — passing an unknown kwarg
            # to objects.create() raises TypeError.
            line_data.pop('item_description', None)  # defensive: strip if somehow present
            GoodsReceivedNoteLine.objects.create(grn=grn, **line_data)

        return grn

class InvoiceMatchingSerializer(serializers.ModelSerializer):
    po_number = serializers.ReadOnlyField(source='purchase_order.po_number')
    vendor_name = serializers.ReadOnlyField(source='purchase_order.vendor.name')
    grn_number = serializers.ReadOnlyField(source='goods_received_note.grn_number')
    # Derived: how much vendor is actually owed after deducting any applied down payment
    net_payable = serializers.ReadOnlyField()
    # Convenience: how much unspent advance is still available for this PO's DPR (if any)
    available_down_payment = serializers.SerializerMethodField()
    # Posted-state flags — let the UI hide "Post to GL" once the
    # auto-post fires on Approval (VendorInvoice goes to Posted and
    # its journal_entry is populated). Without these the button would
    # linger on the Approved screen even though the work is done.
    vendor_invoice_status = serializers.ReadOnlyField(source='vendor_invoice.status')
    journal_entry_id = serializers.SerializerMethodField()
    journal_reference = serializers.SerializerMethodField()
    # Lock affordance: PV link denormalised from the underlying vendor
    # invoice (matched by invoice_number convention used by
    # ``accounting.services.pv_factory``). Lets the verification list
    # hide its "Create PV" button when a PV already exists.
    payment_voucher_id = serializers.SerializerMethodField()
    payment_voucher_number = serializers.SerializerMethodField()
    payment_voucher_status = serializers.SerializerMethodField()

    def get_journal_entry_id(self, obj):
        return obj.vendor_invoice.journal_entry_id if obj.vendor_invoice_id else None

    def get_journal_reference(self, obj):
        if obj.vendor_invoice_id and obj.vendor_invoice.journal_entry_id:
            return obj.vendor_invoice.journal_entry.reference_number
        return None

    def _linked_pv(self, obj):
        # Matches the same lookup pattern the pv_factory uses.
        cached = getattr(obj, '_linked_pv_cache', None)
        if cached is not None:
            return cached if cached is not False else None
        invoice_number = (
            obj.vendor_invoice.invoice_number
            if obj.vendor_invoice_id else None
        )
        if not invoice_number:
            obj._linked_pv_cache = False
            return None
        from accounting.models.treasury import PaymentVoucherGov
        pv = (
            PaymentVoucherGov.objects
            .filter(invoice_number=invoice_number)
            .order_by('-id')
            .only('id', 'voucher_number', 'status')
            .first()
        )
        obj._linked_pv_cache = pv if pv is not None else False
        return pv

    def get_payment_voucher_id(self, obj):
        pv = self._linked_pv(obj)
        return pv.pk if pv else None

    def get_payment_voucher_number(self, obj):
        pv = self._linked_pv(obj)
        return pv.voucher_number if pv else None

    def get_payment_voucher_status(self, obj):
        pv = self._linked_pv(obj)
        return pv.status if pv else None

    def get_available_down_payment(self, obj):
        if not obj.purchase_order_id:
            return None
        try:
            from .models import DownPaymentRequest
            dpr = DownPaymentRequest.objects.filter(
                purchase_order_id=obj.purchase_order_id,
                status='Processed',
            ).select_related('payment').first()
            if dpr and dpr.payment:
                return str(dpr.payment.advance_remaining)
        except Exception as exc:
            logger.warning(
                "procurement serializer: could not fetch DownPaymentRequest "
                "for PO %s: %s", obj.purchase_order_id, exc,
            )
        return None

    class Meta:
        model = InvoiceMatching
        fields = [
            'id', 'verification_number',
            'purchase_order', 'po_number', 'vendor_name', 'goods_received_note', 'grn_number',
            'invoice_reference', 'invoice_date', 'invoice_amount', 'invoice_tax_amount', 'invoice_subtotal',
            'po_amount', 'grn_amount', 'match_type',
            'status', 'variance_amount', 'variance_percentage', 'variance_reason', 'matched_date',
            'payment_hold', 'down_payment_applied', 'net_payable', 'available_down_payment',
            'notes',
            # Tax codes — selected on the matching, drive VAT / WHT at post-to-GL
            'tax_code', 'withholding_tax', 'wht_amount',
            'wht_exempt', 'wht_exempt_reason',
            # Posted-state flags (read-only)
            'vendor_invoice', 'vendor_invoice_status', 'journal_entry_id', 'journal_reference',
            # PV-link denormalisation (lock affordance)
            'payment_voucher_id', 'payment_voucher_number', 'payment_voucher_status',
        ]
        read_only_fields = ['id', 'verification_number',
                            'po_amount', 'grn_amount', 'match_type', 'status', 'matched_date',
                            'net_payable', 'available_down_payment', 'wht_amount',
                            'vendor_invoice', 'vendor_invoice_status',
                            'journal_entry_id', 'journal_reference',
                            'payment_voucher_id', 'payment_voucher_number', 'payment_voucher_status']

    def validate_invoice_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Invoice amount must be greater than zero.")
        return value

    def validate_invoice_tax_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Invoice tax amount cannot be negative.")
        return value

    def validate(self, data):
        invoice_date = data.get('invoice_date')
        purchase_order = data.get('purchase_order')
        if invoice_date and purchase_order and invoice_date < purchase_order.order_date:
            raise serializers.ValidationError({
                'invoice_date': "Invoice date cannot be before the purchase order date."
            })
        return data

    def _recompute_tax_totals(self, instance):
        """Compute invoice_tax_amount from tax_code and wht_amount from
        withholding_tax, both against invoice_subtotal. Called after create()
        and update() so saved rows always carry consistent totals."""
        from decimal import Decimal as _D
        subtotal = instance.invoice_subtotal or _D('0')
        if instance.tax_code and instance.tax_code.rate:
            instance.invoice_tax_amount = (
                subtotal * _D(str(instance.tax_code.rate)) / _D('100')
            ).quantize(_D('0.01'))
        elif not instance.invoice_tax_amount:
            instance.invoice_tax_amount = _D('0')
        if instance.withholding_tax and instance.withholding_tax.rate:
            instance.wht_amount = (
                subtotal * _D(str(instance.withholding_tax.rate)) / _D('100')
            ).quantize(_D('0.01'))
        else:
            instance.wht_amount = _D('0')
        # Keep invoice_amount = subtotal + tax (vendor bills gross of VAT; WHT
        # is a deduction at payment, not a line on the invoice itself).
        if subtotal > 0 and instance.tax_code:
            instance.invoice_amount = subtotal + instance.invoice_tax_amount
        instance.save(update_fields=[
            'invoice_tax_amount', 'wht_amount', 'invoice_amount',
        ])
        return instance

    def create(self, validated_data):
        instance = super().create(validated_data)
        return self._recompute_tax_totals(instance)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        return self._recompute_tax_totals(instance)


class VendorCreditNoteSerializer(serializers.ModelSerializer):
    vendor_name = serializers.ReadOnlyField(source='vendor.name')
    po_number = serializers.ReadOnlyField(source='purchase_order.po_number', allow_null=True)
    grn_number = serializers.ReadOnlyField(source='goods_received_note.grn_number', allow_null=True)
    journal_entry_number = serializers.ReadOnlyField(source='journal_entry.reference_number', allow_null=True)

    class Meta:
        model = VendorCreditNote
        fields = [
            'id', 'credit_note_number', 'vendor', 'vendor_name', 'purchase_order', 'po_number',
            'goods_received_note', 'grn_number', 'credit_note_date', 'reason',
            'amount', 'tax_amount', 'total_amount', 'status',
            'journal_entry', 'journal_entry_number',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'credit_note_number', 'total_amount', 'status', 'journal_entry', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_tax_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Tax amount cannot be negative.")
        return value


class VendorDebitNoteSerializer(serializers.ModelSerializer):
    vendor_name = serializers.ReadOnlyField(source='vendor.name')
    po_number = serializers.ReadOnlyField(source='purchase_order.po_number', allow_null=True)
    journal_entry_number = serializers.ReadOnlyField(source='journal_entry.reference_number', allow_null=True)

    class Meta:
        model = VendorDebitNote
        fields = [
            'id', 'debit_note_number', 'vendor', 'vendor_name', 'purchase_order', 'po_number',
            'debit_note_date', 'reason', 'amount', 'tax_amount', 'total_amount', 'status',
            'journal_entry', 'journal_entry_number',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'debit_note_number', 'total_amount', 'status', 'journal_entry', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_tax_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Tax amount cannot be negative.")
        return value


class PurchaseReturnLineSerializer(PositiveDecimalMixin, serializers.ModelSerializer):
    item_name = serializers.SerializerMethodField()
    total_amount = serializers.ReadOnlyField()
    display_description = serializers.ReadOnlyField()

    def get_item_name(self, obj):
        return obj.display_description

    class Meta:
        model = PurchaseReturnLine
        fields = [
            'id', 'po_line', 'item', 'item_name', 'item_description',
            'quantity', 'unit_price', 'reason', 'total_amount', 'display_description',
        ]

    def validate_quantity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Return quantity must be greater than zero.")
        return value


class PurchaseReturnSerializer(serializers.ModelSerializer):
    # lines is writable on create; read-only on list/detail for performance
    lines = PurchaseReturnLineSerializer(many=True)
    vendor_name = serializers.ReadOnlyField(source='vendor.name')
    po_number = serializers.ReadOnlyField(source='purchase_order.po_number')
    grn_number = serializers.ReadOnlyField(source='goods_received_note.grn_number', allow_null=True)
    credit_note_number = serializers.ReadOnlyField(source='credit_note.credit_note_number', allow_null=True)

    class Meta:
        model = PurchaseReturn
        fields = [
            'id', 'return_number', 'vendor', 'vendor_name', 'purchase_order', 'po_number',
            'goods_received_note', 'grn_number', 'credit_note', 'credit_note_number',
            'return_date', 'reason', 'status', 'total_amount', 'notes', 'lines',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = [
            'id', 'return_number', 'vendor', 'total_amount', 'status',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]

    def validate(self, data):
        """
        Cross-field validation:
        1. At least one return line must be provided on creation.
        2. For lines with a po_line FK, the return quantity must not exceed the
           quantity received on the linked GRN line (if a GRN is selected).
        """
        lines = data.get('lines', [])
        if not lines:
            raise serializers.ValidationError({'lines': 'At least one return line is required.'})

        grn = data.get('goods_received_note')
        if grn:
            # Build a map: po_line_id → quantity_received from the selected GRN
            grn_received = {}
            for grn_line in grn.lines.select_related('po_line').all():
                grn_received[grn_line.po_line_id] = grn_line.quantity_received

            for idx, line in enumerate(lines):
                po_line = line.get('po_line')
                if po_line and po_line.id in grn_received:
                    max_qty = grn_received[po_line.id]
                    if line.get('quantity', 0) > max_qty:
                        raise serializers.ValidationError({
                            f'lines[{idx}]': (
                                f"Return quantity ({line['quantity']}) exceeds the quantity received "
                                f"({max_qty}) on the GRN for '{po_line.item_description}'."
                            )
                        })

        return data

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        po = validated_data['purchase_order']
        validated_data['vendor'] = po.vendor

        from django.db import transaction as db_tx
        with db_tx.atomic():
            purchase_return = PurchaseReturn.objects.create(**validated_data)
            for line_data in lines_data:
                # Derive item_description from po_line if not supplied
                po_line = line_data.get('po_line')
                if po_line and not line_data.get('item_description'):
                    line_data['item_description'] = po_line.item_description
                    if not line_data.get('item') and po_line.item:
                        line_data['item'] = po_line.item
                PurchaseReturnLine.objects.create(purchase_return=purchase_return, **line_data)

            # Compute total from the newly created lines
            purchase_return.update_total()

        return purchase_return


# ─── BPP Due Process Serializers (Quot PSE Phase 5) ──────────────────

from procurement.models import ProcurementThreshold, CertificateOfNoObjection, ProcurementBudgetLink


class ProcurementThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcurementThreshold
        fields = [
            'id', 'category', 'authority_level', 'min_amount', 'max_amount',
            'requires_bpp_no', 'fiscal_year', 'is_active',
        ]
        read_only_fields = ['id']


class CertificateOfNoObjectionSerializer(serializers.ModelSerializer):
    purchase_order_number = serializers.SerializerMethodField()

    class Meta:
        model = CertificateOfNoObjection
        fields = [
            'id', 'purchase_order', 'purchase_order_number',
            'certificate_number', 'issued_date', 'expiry_date',
            'authority_level', 'issuing_officer', 'is_valid',
            'amount_covered', 'scope_description', 'conditions',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_purchase_order_number(self, obj) -> str:
        return str(obj.purchase_order) if obj.purchase_order else ''


class ProcurementBudgetLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcurementBudgetLink
        fields = [
            'id', 'purchase_order', 'appropriation',
            'committed_amount', 'ncoa_code', 'committed_at', 'status',
        ]
        read_only_fields = ['id', 'committed_at']


class ThresholdCheckSerializer(serializers.Serializer):
    """Input for checking procurement approval authority level."""
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    category = serializers.ChoiceField(choices=['GOODS_SERVICES', 'WORKS', 'CONSULTANCY'])
