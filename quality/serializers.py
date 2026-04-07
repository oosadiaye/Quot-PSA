from rest_framework import serializers
from django.db import transaction as db_transaction
from .models import (
    QualityInspection, InspectionLine, NonConformance, CustomerComplaint,
    QualityChecklist, QualityChecklistLine, CalibrationRecord, SupplierQuality,
    QAConfiguration
)


class QAConfigurationSerializer(serializers.ModelSerializer):
    trigger_event_display = serializers.CharField(source='get_trigger_event_display', read_only=True)
    inspection_type_display = serializers.CharField(source='get_inspection_type_display', read_only=True)
    
    class Meta:
        model = QAConfiguration
        fields = [
            'id', 'name', 'trigger_event', 'trigger_event_display',
            'inspection_type', 'inspection_type_display',
            'is_required', 'auto_create', 'item_category', 'product_type',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InspectionLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionLine
        fields = [
            'id', 'inspection', 'parameter', 'specification', 'result',
            'measurement', 'notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class QualityInspectionSerializer(serializers.ModelSerializer):
    lines = InspectionLineSerializer(many=True, read_only=True)
    inspector_name = serializers.CharField(source='inspector.username', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    inspection_type_display = serializers.CharField(source='get_inspection_type_display', read_only=True)

    class Meta:
        model = QualityInspection
        fields = [
            'id', 'inspection_number', 'inspection_type', 'inspection_type_display',
            'reference_type', 'reference_number', 'inspection_date', 'status', 'status_display',
            'inspector', 'inspector_name',
            'goods_received_note', 'production_order', 'item',
            'notes', 'lines',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'inspection_number', 'created_at', 'updated_at']

    def create(self, validated_data):
        with db_transaction.atomic():
            last = QualityInspection.objects.select_for_update().order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            validated_data['inspection_number'] = f"INS-{next_num:06d}"
            return super().create(validated_data)


class NonConformanceSerializer(serializers.ModelSerializer):
    related_inspection_number = serializers.CharField(source='related_inspection.inspection_number', read_only=True, allow_null=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)

    class Meta:
        model = NonConformance
        fields = [
            'id', 'ncr_number', 'title', 'description',
            'severity', 'severity_display', 'status', 'status_display',
            'related_inspection', 'related_inspection_number',
            'source_type', 'source_id',
            'root_cause', 'corrective_action', 'preventive_action',
            'assigned_to', 'assigned_to_name', 'closed_date', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'ncr_number', 'created_at', 'updated_at']

    def create(self, validated_data):
        with db_transaction.atomic():
            last = NonConformance.objects.select_for_update().order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            validated_data['ncr_number'] = f"NCR-{next_num:06d}"
            return super().create(validated_data)


class CustomerComplaintSerializer(serializers.ModelSerializer):
    related_ncr_number = serializers.CharField(source='related_ncr.ncr_number', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = CustomerComplaint
        fields = [
            'id', 'complaint_number', 'customer_name', 'customer_email', 'customer_phone',
            'subject', 'description', 'status', 'status_display',
            'related_sales_order', 'related_ncr', 'related_ncr_number',
            'resolution', 'resolution_date', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'complaint_number', 'created_at', 'updated_at']

    def create(self, validated_data):
        with db_transaction.atomic():
            last = CustomerComplaint.objects.select_for_update().order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            validated_data['complaint_number'] = f"CC-{next_num:06d}"
            return super().create(validated_data)


class QualityChecklistLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityChecklistLine
        fields = [
            'id', 'checklist', 'sequence', 'parameter', 'description',
            'is_critical',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class QualityChecklistSerializer(serializers.ModelSerializer):
    lines = QualityChecklistLineSerializer(many=True, read_only=True)

    class Meta:
        model = QualityChecklist
        fields = [
            'id', 'name', 'description', 'checklist_type', 'is_active', 'lines',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CalibrationRecordSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    equipment_type_display = serializers.CharField(source='get_equipment_type_display', read_only=True)

    class Meta:
        model = CalibrationRecord
        fields = [
            'id', 'equipment_name', 'equipment_code', 'equipment_type', 'equipment_type_display',
            'manufacturer', 'model_number', 'serial_number',
            'last_calibration_date', 'next_calibration_date', 'calibration_interval_months',
            'status', 'status_display', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'equipment_code', 'created_at', 'updated_at']


class SupplierQualitySerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    rating_display = serializers.CharField(source='get_rating_display', read_only=True)

    class Meta:
        model = SupplierQuality
        fields = [
            'id', 'vendor', 'vendor_name', 'evaluation_date',
            'quality_score', 'delivery_score', 'overall_score',
            'rating', 'rating_display', 'comments', 'next_evaluation_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'overall_score', 'created_at', 'updated_at']
