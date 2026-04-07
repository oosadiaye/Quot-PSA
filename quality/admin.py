from django.contrib import admin
from .models import (
    QualityInspection, InspectionLine, NonConformance, CustomerComplaint,
    QualityChecklist, QualityChecklistLine, CalibrationRecord, SupplierQuality
)


class InspectionLineInline(admin.TabularInline):
    model = InspectionLine
    extra = 0
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']


class QualityChecklistLineInline(admin.TabularInline):
    model = QualityChecklistLine
    extra = 0
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']


@admin.register(QualityInspection)
class QualityInspectionAdmin(admin.ModelAdmin):
    list_display = ['inspection_number', 'inspection_type', 'inspection_date', 'status', 'inspector']
    list_filter = ['inspection_type', 'status', 'inspection_date']
    search_fields = ['inspection_number', 'reference_number', 'notes']
    raw_id_fields = ['inspector', 'goods_received_note', 'production_order', 'item']
    readonly_fields = ['inspection_number', 'created_at', 'updated_at']
    inlines = [InspectionLineInline]


@admin.register(InspectionLine)
class InspectionLineAdmin(admin.ModelAdmin):
    list_display = ['inspection', 'parameter', 'result']
    list_filter = ['result']
    search_fields = ['parameter']


@admin.register(NonConformance)
class NonConformanceAdmin(admin.ModelAdmin):
    list_display = ['ncr_number', 'title', 'severity', 'status', 'assigned_to']
    list_filter = ['severity', 'status']
    search_fields = ['ncr_number', 'title', 'description']
    raw_id_fields = ['related_inspection', 'assigned_to']
    readonly_fields = ['ncr_number', 'created_at', 'updated_at']


@admin.register(CustomerComplaint)
class CustomerComplaintAdmin(admin.ModelAdmin):
    list_display = ['complaint_number', 'customer_name', 'subject', 'status']
    list_filter = ['status']
    search_fields = ['complaint_number', 'customer_name', 'subject']
    readonly_fields = ['complaint_number', 'created_at', 'updated_at']


@admin.register(QualityChecklist)
class QualityChecklistAdmin(admin.ModelAdmin):
    list_display = ['name', 'checklist_type', 'is_active']
    list_filter = ['checklist_type', 'is_active']
    search_fields = ['name', 'description']
    inlines = [QualityChecklistLineInline]


@admin.register(QualityChecklistLine)
class QualityChecklistLineAdmin(admin.ModelAdmin):
    list_display = ['checklist', 'sequence', 'parameter', 'is_critical']
    list_filter = ['is_critical', 'checklist']
    search_fields = ['parameter']


@admin.register(CalibrationRecord)
class CalibrationRecordAdmin(admin.ModelAdmin):
    list_display = ['equipment_code', 'equipment_name', 'equipment_type', 'next_calibration_date', 'status']
    list_filter = ['equipment_type', 'status']
    search_fields = ['equipment_code', 'equipment_name']
    readonly_fields = ['equipment_code', 'created_at', 'updated_at']


@admin.register(SupplierQuality)
class SupplierQualityAdmin(admin.ModelAdmin):
    list_display = ['vendor', 'evaluation_date', 'quality_score', 'delivery_score', 'overall_score', 'rating']
    list_filter = ['rating', 'evaluation_date']
    search_fields = ['vendor__name', 'comments']
    raw_id_fields = ['vendor']
    readonly_fields = ['overall_score', 'created_at', 'updated_at']
