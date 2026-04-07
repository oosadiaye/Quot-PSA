from rest_framework import serializers
from .models import (
    Warehouse, ProductType, ProductCategory, ItemCategory, Item, ItemStock, ItemBatch,
    StockMovement, StockReconciliation, StockReconciliationLine, ReorderAlert,
    ItemSerialNumber, BatchExpiryAlert, InventorySettings
)

class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            'id', 'name', 'location', 'is_active', 'is_central',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class ProductTypeSerializer(serializers.ModelSerializer):
    # Human-readable display label for the type name.
    # source='name' is intentionally NOT used here — that would just return the
    # machine key ('non_stock').  We transform it to 'Non-Stock' instead.
    name_display = serializers.SerializerMethodField()
    description = serializers.CharField(allow_blank=True, required=False, default='')

    _NAME_LABELS = {
        'stock':     'Stock',
        'non_stock': 'Non-Stock',
        'service':   'Service',
        'spares':    'Spares',
    }

    def get_name_display(self, obj):
        return self._NAME_LABELS.get(obj.name, obj.name.replace('_', ' ').title())

    inventory_account_name = serializers.CharField(source='inventory_account.name', read_only=True, allow_null=True)
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True, allow_null=True)
    revenue_account_name = serializers.CharField(source='revenue_account.name', read_only=True, allow_null=True)
    clearing_account_name = serializers.CharField(source='clearing_account.name', read_only=True, allow_null=True)
    goods_in_transit_account_name = serializers.CharField(source='goods_in_transit_account.name', read_only=True, allow_null=True)

    # GL fields required per product type classification
    _REQUIRED_GL = {
        'stock':     ['inventory_account', 'expense_account', 'revenue_account', 'clearing_account'],
        'non_stock': ['expense_account', 'clearing_account'],
        'service':   ['revenue_account', 'clearing_account'],
        'spares':    ['inventory_account', 'expense_account', 'revenue_account', 'clearing_account'],
    }
    _ALL_GL = ['inventory_account', 'expense_account', 'revenue_account', 'clearing_account', 'goods_in_transit_account']

    class Meta:
        model = ProductType
        fields = [
            'id', 'name', 'name_display', 'description',
            'inventory_account', 'inventory_account_name',
            'expense_account', 'expense_account_name',
            'revenue_account', 'revenue_account_name',
            'clearing_account', 'clearing_account_name',
            'goods_in_transit_account', 'goods_in_transit_account_name',
            'created_at', 'updated_at'
        ]

    def validate(self, data):
        # On PATCH, name may not be in data — fall back to instance value
        name = data.get('name', getattr(self.instance, 'name', None))
        if not name:
            return data

        required = self._REQUIRED_GL.get(name, [])

        # Check required GL fields are provided
        errors = {}
        for field in required:
            value = data.get(field, getattr(self.instance, field, None) if self.instance else None)
            if value is None:
                label = field.replace('_', ' ').title()
                errors[field] = f'{label} is required for {name} type.'
        if errors:
            raise serializers.ValidationError(errors)

        # Null out GL fields that are not applicable for this type
        for field in self._ALL_GL:
            if field not in required:
                data[field] = None

        return data


class ProductCategorySerializer(serializers.ModelSerializer):
    product_type_name = serializers.CharField(source='product_type.name', read_only=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)
    
    class Meta:
        model = ProductCategory
        fields = [
            'id', 'name', 'product_type', 'product_type_name',
            'parent', 'parent_name', 'created_at', 'updated_at'
        ]


class ItemCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemCategory
        fields = ['id', 'name', 'parent']
        read_only_fields = ['id']

class ItemStockSerializer(serializers.ModelSerializer):
    item_name = serializers.ReadOnlyField(source='item.name')
    item_sku = serializers.ReadOnlyField(source='item.sku')
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')
    available_quantity = serializers.ReadOnlyField()
    cost_price = serializers.SerializerMethodField()
    selling_price = serializers.SerializerMethodField()
    qty_received = serializers.SerializerMethodField()
    qty_sold = serializers.SerializerMethodField()
    value_at_cost = serializers.SerializerMethodField()
    selling_value = serializers.SerializerMethodField()
    closing_stock = serializers.SerializerMethodField()

    class Meta:
        model = ItemStock
        fields = [
            'id', 'item', 'item_name', 'item_sku', 'warehouse', 'warehouse_name',
            'quantity', 'reserved_quantity', 'available_quantity',
            'cost_price', 'selling_price', 'qty_received', 'qty_sold',
            'value_at_cost', 'selling_value', 'closing_stock',
        ]

    def get_cost_price(self, obj):
        return float(obj.item.average_cost or 0)

    def get_selling_price(self, obj):
        return float(obj.item.selling_price or 0)

    def get_qty_received(self, obj):
        return float(getattr(obj, 'qty_received', 0) or 0)

    def get_qty_sold(self, obj):
        return float(getattr(obj, 'qty_sold', 0) or 0)

    def get_value_at_cost(self, obj):
        return float(obj.quantity * (obj.item.average_cost or 0))

    def get_selling_value(self, obj):
        qty_sold = float(getattr(obj, 'qty_sold', 0) or 0)
        return qty_sold * float(obj.item.selling_price or 0)

    def get_closing_stock(self, obj):
        return float(obj.quantity)

class ItemBatchSerializer(serializers.ModelSerializer):
    item_name = serializers.ReadOnlyField(source='item.name')
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')

    class Meta:
        model = ItemBatch
        fields = [
            'id', 'item', 'item_name', 'batch_number', 'receipt_date',
            'expiry_date', 'quantity', 'remaining_quantity', 'unit_cost',
            'warehouse', 'warehouse_name', 'reference_number',
        ]
        read_only_fields = ['id']

class BatchSplitSerializer(serializers.Serializer):
    split_quantity = serializers.DecimalField(max_digits=15, decimal_places=4)
    new_batch_number = serializers.CharField(max_length=50, required=False)

class BatchTransferSerializer(serializers.Serializer):
    to_warehouse = serializers.IntegerField()
    transfer_quantity = serializers.DecimalField(max_digits=15, decimal_places=4)

class ItemSerializer(serializers.ModelSerializer):
    average_cost = serializers.ReadOnlyField()
    stock_level = serializers.ReadOnlyField()
    needs_reorder = serializers.ReadOnlyField()
    category_name = serializers.ReadOnlyField(source='category.name')
    product_type_name = serializers.CharField(source='product_type.name', read_only=True)
    product_category_name = serializers.CharField(source='product_category.name', read_only=True, allow_null=True)
    inventory_account_name = serializers.CharField(source='inventory_account.name', read_only=True, allow_null=True)
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True, allow_null=True)
    preferred_vendor_name = serializers.CharField(source='preferred_vendor.name', read_only=True, allow_null=True)
    stocks = ItemStockSerializer(many=True, read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'sku', 'name', 'description',
            'product_type', 'product_type_name',
            'product_category', 'product_category_name',
            'category', 'category_name',  # Legacy field
            'unit_of_measure', 'valuation_method', 'total_quantity', 'total_value',
            'standard_price', 'cost_price', 'average_cost', 'selling_price', 'stock_level', 'reorder_point', 'reorder_quantity',
            'barcode', 'min_stock', 'max_stock', 'is_active', 'needs_reorder',
            'shelf_life_days',
            'inventory_account', 'inventory_account_name',
            'expense_account', 'expense_account_name',
            'preferred_vendor', 'preferred_vendor_name',
            'production_bom',
            'stocks', 'created_at', 'updated_at'
        ]

class StockMovementSerializer(serializers.ModelSerializer):
    item_name = serializers.ReadOnlyField(source='item.name')
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')
    batch_number = serializers.ReadOnlyField(source='batch.batch_number')
    to_warehouse_name = serializers.ReadOnlyField(source='to_warehouse.name')
    journal_entry_number = serializers.ReadOnlyField(source='journal_entry.reference_number', allow_null=True)
    receive_journal_number = serializers.ReadOnlyField(source='receive_journal_entry.reference_number', allow_null=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'item', 'item_name', 'warehouse', 'warehouse_name',
            'movement_type', 'quantity', 'unit_price', 'batch', 'batch_number',
            'to_warehouse', 'to_warehouse_name', 'reference_number', 'remarks',
            'cost_method', 'gl_posted', 'journal_entry', 'journal_entry_number',
            'transfer_status', 'receive_journal_entry', 'receive_journal_number',
            'created_at'
        ]
        read_only_fields = [
            'id', 'gl_posted', 'journal_entry', 'transfer_status',
            'receive_journal_entry', 'created_at'
        ]

class StockReconciliationLineSerializer(serializers.ModelSerializer):
    item_name = serializers.ReadOnlyField(source='item.name')

    class Meta:
        model = StockReconciliationLine
        fields = [
            'id', 'reconciliation', 'item', 'item_name', 'system_quantity',
            'physical_quantity', 'variance_quantity', 'variance_value',
            'reason', 'is_adjusted',
        ]
        read_only_fields = ['id']

class StockReconciliationSerializer(serializers.ModelSerializer):
    lines = StockReconciliationLineSerializer(many=True, read_only=True)
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')
    
    class Meta:
        model = StockReconciliation
        fields = [
            'id', 'reconciliation_number', 'reconciliation_type', 'warehouse',
            'warehouse_name', 'reconciliation_date', 'status', 'notes', 'lines',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'reconciliation_number', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def create(self, validated_data):
        from django.utils import timezone
        from django.utils.crypto import get_random_string
        validated_data['reconciliation_number'] = f"REC-{timezone.now().strftime('%Y%m%d')}-{get_random_string(6, '0123456789')}"
        return super().create(validated_data)

class ReorderAlertSerializer(serializers.ModelSerializer):
    item_name = serializers.ReadOnlyField(source='item.name')
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')

    class Meta:
        model = ReorderAlert
        fields = [
            'id', 'item', 'item_name', 'warehouse', 'warehouse_name',
            'current_stock', 'reorder_point', 'suggested_quantity',
            'is_sent', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ItemSerialNumberSerializer(serializers.ModelSerializer):
    item_name = serializers.ReadOnlyField(source='item.name')
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')
    is_under_warranty = serializers.ReadOnlyField()

    class Meta:
        model = ItemSerialNumber
        fields = [
            'id', 'item', 'item_name', 'serial_number', 'batch', 'status',
            'warehouse', 'warehouse_name', 'purchase_date', 'purchase_price',
            'sale_date', 'sales_order_line', 'warranty_start', 'warranty_end',
            'current_location', 'notes', 'is_under_warranty',
        ]
        read_only_fields = ['id']


class BatchExpiryAlertSerializer(serializers.ModelSerializer):
    item_name = serializers.ReadOnlyField(source='item.name')
    batch_number = serializers.ReadOnlyField(source='batch.batch_number')
    warehouse_name = serializers.ReadOnlyField()
    remaining_quantity = serializers.ReadOnlyField()

    class Meta:
        model = BatchExpiryAlert
        fields = [
            'id', 'item', 'item_name', 'batch', 'batch_number',
            'warehouse', 'warehouse_name', 'expiry_date', 'remaining_quantity',
            'alert_date', 'is_sent', 'is_dismissed', 'created_at',
        ]
        read_only_fields = ['id', 'alert_date', 'created_at']


class InventorySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventorySettings
        fields = ['id', 'auto_po_enabled', 'auto_po_draft_only']
