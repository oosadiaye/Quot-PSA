from django.contrib import admin
from .models import (
    WorkCenter, BillOfMaterials, BOMLine, ProductionOrder,
    MaterialIssue, MaterialReceipt, JobCard, Routing
)


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    fk_name = 'bom'
    extra = 1
    fields = ['component', 'quantity', 'unit', 'scrap_percentage', 'notes']


class RoutingInline(admin.TabularInline):
    model = Routing
    extra = 1
    fields = ['sequence', 'operation_name', 'work_center', 'time_hours', 'labor_cost']


class JobCardInline(admin.TabularInline):
    model = JobCard
    extra = 0
    fields = ['sequence', 'operation_name', 'work_center', 'operator', 'status', 'time_planned', 'time_actual', 'labor_cost']
    raw_id_fields = ['operator']


@admin.register(WorkCenter)
class WorkCenterAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'capacity_hours', 'efficiency', 'labor_rate', 'overhead_rate', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']


@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    list_display = ['item_code', 'item_name', 'item_type', 'standard_cost', 'is_active']
    list_filter = ['item_type', 'is_active']
    search_fields = ['item_code', 'item_name']
    inlines = [BOMLineInline, RoutingInline]


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'bom', 'quantity_planned', 'quantity_produced', 'status', 'start_date', 'end_date']
    list_filter = ['status']
    search_fields = ['order_number', 'bom__item_name']
    inlines = [JobCardInline]


@admin.register(MaterialIssue)
class MaterialIssueAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'bom_line', 'quantity_issued', 'issue_date']
    list_filter = ['issue_date']
    search_fields = ['production_order__order_number']


@admin.register(MaterialReceipt)
class MaterialReceiptAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'quantity_received', 'receipt_date', 'is_scrap', 'scrap_quantity']
    list_filter = ['is_scrap', 'receipt_date']
    search_fields = ['production_order__order_number']


@admin.register(JobCard)
class JobCardAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'operation_name', 'sequence', 'work_center', 'operator', 'status', 'time_planned', 'time_actual', 'labor_cost']
    list_filter = ['status']
    search_fields = ['production_order__order_number', 'operation_name']
    raw_id_fields = ['operator']


@admin.register(Routing)
class RoutingAdmin(admin.ModelAdmin):
    list_display = ['bom', 'sequence', 'operation_name', 'work_center', 'time_hours', 'labor_cost']
    search_fields = ['bom__item_code', 'operation_name']
