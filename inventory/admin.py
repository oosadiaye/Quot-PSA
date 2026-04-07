from django.contrib import admin
from .models import (
    Warehouse, ItemCategory, Item, ItemStock, ItemBatch,
    StockMovement, StockReconciliation, StockReconciliationLine, ReorderAlert,
    ProductType, ProductCategory, ItemSerialNumber, BatchExpiryAlert,
)

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'is_active', 'is_central']
    search_fields = ['name']

@admin.register(ItemCategory)
class ProductCategoryLegacyAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent']
    search_fields = ['name']

@admin.register(Item)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'category', 'valuation_method', 'total_quantity', 'average_cost', 'is_active']
    list_filter = ['category', 'valuation_method', 'is_active']
    search_fields = ['sku', 'name', 'barcode']

@admin.register(ItemStock)
class ProductStockAdmin(admin.ModelAdmin):
    list_display = ['item', 'warehouse', 'quantity', 'reserved_quantity', 'available_quantity']
    list_filter = ['warehouse']

@admin.register(ItemBatch)
class ProductBatchAdmin(admin.ModelAdmin):
    list_display = ['item', 'batch_number', 'quantity', 'remaining_quantity', 'unit_cost', 'expiry_date']
    search_fields = ['batch_number', 'item__name']

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['item', 'warehouse', 'movement_type', 'quantity', 'unit_price', 'reference_number', 'created_at']
    list_filter = ['movement_type', 'warehouse']
    search_fields = ['reference_number']

@admin.register(StockReconciliation)
class StockReconciliationAdmin(admin.ModelAdmin):
    list_display = ['reconciliation_number', 'warehouse', 'reconciliation_type', 'status', 'reconciliation_date']
    list_filter = ['status', 'reconciliation_type']

@admin.register(StockReconciliationLine)
class StockReconciliationLineAdmin(admin.ModelAdmin):
    list_display = ['reconciliation', 'item', 'system_quantity', 'physical_quantity', 'variance_quantity', 'is_adjusted']
    list_filter = ['is_adjusted']

@admin.register(ReorderAlert)
class ReorderAlertAdmin(admin.ModelAdmin):
    list_display = ['item', 'warehouse', 'current_stock', 'reorder_point', 'suggested_quantity', 'is_sent', 'created_at']
    list_filter = ['is_sent']


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'product_type', 'parent']
    list_filter = ['product_type']
    search_fields = ['name']


@admin.register(ItemSerialNumber)
class ProductSerialNumberAdmin(admin.ModelAdmin):
    list_display = ['serial_number', 'item', 'status', 'warehouse']
    list_filter = ['status', 'warehouse']
    search_fields = ['serial_number', 'item__sku', 'item__name']


@admin.register(BatchExpiryAlert)
class BatchExpiryAlertAdmin(admin.ModelAdmin):
    list_display = ['item', 'batch', 'expiry_date', 'is_sent', 'is_dismissed']
    list_filter = ['is_sent', 'is_dismissed']
