from django.contrib import admin
from .models import ServiceAsset, Technician, ServiceTicket, SLATracking, MaintenanceSchedule, WorkOrder, WorkOrderMaterial, CitizenRequest, ServiceMetric

@admin.register(ServiceAsset)
class ServiceAssetAdmin(admin.ModelAdmin):
    list_display = ['name', 'serial_number', 'purchase_date', 'warranty_expiry']
    search_fields = ['name', 'serial_number']

@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ['name', 'employee_code', 'employee', 'email', 'phone', 'specialization', 'is_active', 'is_available', 'active_tickets']
    list_filter = ['is_active', 'is_available', 'specialization']
    search_fields = ['name', 'employee_code']
    raw_id_fields = ['employee']

@admin.register(ServiceTicket)
class ServiceTicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_number', 'subject', 'status', 'priority', 'technician', 'due_date', 'created_at']
    list_filter = ['status', 'priority']
    search_fields = ['ticket_number', 'subject']

@admin.register(SLATracking)
class SLATrackingAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'response_time_limit', 'resolution_time_limit', 'first_response_at', 'is_response_met', 'is_resolution_met']

@admin.register(MaintenanceSchedule)
class MaintenanceScheduleAdmin(admin.ModelAdmin):
    list_display = ['title', 'asset', 'frequency', 'next_run_date', 'is_active']
    list_filter = ['frequency', 'is_active']
    search_fields = ['title', 'asset__name']

class WorkOrderMaterialInline(admin.TabularInline):
    model = WorkOrderMaterial
    extra = 0


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ['work_order_number', 'title', 'status', 'priority', 'technician', 'scheduled_date', 'total_cost', 'created_at']
    list_filter = ['status', 'priority']
    search_fields = ['work_order_number', 'title']
    inlines = [WorkOrderMaterialInline]

@admin.register(WorkOrderMaterial)
class WorkOrderMaterialAdmin(admin.ModelAdmin):
    list_display = ['work_order', 'item_description', 'quantity', 'unit_price', 'total_price']
    search_fields = ['item_description', 'work_order__work_order_number']

@admin.register(CitizenRequest)
class CitizenRequestAdmin(admin.ModelAdmin):
    list_display = ['request_number', 'citizen_name', 'category', 'subject', 'status', 'created_at']
    list_filter = ['status', 'category']
    search_fields = ['request_number', 'citizen_name', 'subject']

@admin.register(ServiceMetric)
class ServiceMetricAdmin(admin.ModelAdmin):
    list_display = ['name', 'period', 'period_start', 'period_end', 'total_tickets', 'resolved_tickets', 'total_cost']
    list_filter = ['period']
    search_fields = ['name']
