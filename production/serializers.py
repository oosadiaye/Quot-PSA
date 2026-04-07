from rest_framework import serializers
from .models import (
    WorkCenter, BillOfMaterials, BOMLine, ProductionOrder,
    MaterialIssue, MaterialReceipt, JobCard, Routing
)


class WorkCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkCenter
        fields = [
            'id', 'name', 'code', 'description', 'capacity_hours',
            'efficiency', 'labor_rate', 'overhead_rate', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class BOMLineSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component.item_name', read_only=True)

    class Meta:
        model = BOMLine
        fields = ['id', 'bom', 'component', 'component_name', 'quantity', 'unit',
                  'scrap_percentage', 'total_quantity', 'notes',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class BillOfMaterialsSerializer(serializers.ModelSerializer):
    lines = BOMLineSerializer(many=True, read_only=True)
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)

    class Meta:
        model = BillOfMaterials
        fields = ['id', 'item_code', 'item_name', 'item_type', 'item_type_display',
                  'unit', 'standard_cost', 'is_active', 'requires_quality_inspection', 'lines',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class ProductionOrderSerializer(serializers.ModelSerializer):
    bom_name = serializers.CharField(source='bom.item_name', read_only=True)
    work_center_name = serializers.CharField(source='work_center.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    bom_requires_quality_inspection = serializers.BooleanField(
        source='bom.requires_quality_inspection', read_only=True)

    class Meta:
        model = ProductionOrder
        fields = ['id', 'order_number', 'bom', 'bom_name', 'quantity_planned',
                  'quantity_produced', 'start_date', 'end_date', 'status', 'status_display',
                  'work_center', 'work_center_name', 'notes', 'bom_requires_quality_inspection',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class MaterialIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialIssue
        fields = [
            'id', 'production_order', 'bom_line', 'quantity_issued',
            'issue_date', 'notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class MaterialReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialReceipt
        fields = [
            'id', 'production_order', 'quantity_received', 'receipt_date',
            'is_scrap', 'scrap_quantity', 'notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class JobCardSerializer(serializers.ModelSerializer):
    production_order_number = serializers.CharField(source='production_order.order_number', read_only=True)
    work_center_name = serializers.CharField(source='work_center.name', read_only=True)
    operator_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = JobCard
        fields = ['id', 'production_order', 'production_order_number', 'work_center',
                  'work_center_name', 'operator', 'operator_name', 'sequence',
                  'operation_name', 'time_planned', 'time_actual', 'labor_cost',
                  'status', 'status_display', 'notes',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_operator_name(self, obj):
        if obj.operator:
            return obj.operator.user.get_full_name()
        return None


class RoutingSerializer(serializers.ModelSerializer):
    bom_name = serializers.CharField(source='bom.item_name', read_only=True)
    work_center_name = serializers.CharField(source='work_center.name', read_only=True)

    class Meta:
        model = Routing
        fields = ['id', 'bom', 'bom_name', 'sequence', 'operation_name', 'work_center',
                  'work_center_name', 'time_hours', 'labor_cost', 'notes',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']
