from rest_framework import serializers
from .models import ServiceAsset, Technician, ServiceTicket, SLATracking, MaintenanceSchedule, WorkOrder, WorkOrderMaterial, CitizenRequest, ServiceMetric

class TechnicianSerializer(serializers.ModelSerializer):
    active_tickets = serializers.ReadOnlyField()
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = Technician
        fields = [
            'id', 'name', 'employee_code', 'employee', 'employee_name',
            'email', 'phone', 'specialization',
            'is_active', 'is_available', 'active_tickets',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_employee_name(self, obj):
        if obj.employee:
            return obj.employee.user.get_full_name()
        return None

class ServiceAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceAsset
        fields = [
            'id', 'name', 'serial_number', 'purchase_date', 'warranty_expiry',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

class SLATrackingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SLATracking
        fields = [
            'id', 'ticket', 'response_time_limit', 'resolution_time_limit',
            'first_response_at', 'is_response_met', 'is_resolution_met',
        ]
        read_only_fields = ['id']

class ServiceTicketSerializer(serializers.ModelSerializer):
    asset_name = serializers.ReadOnlyField(source='asset.name')
    asset_serial = serializers.ReadOnlyField(source='asset.serial_number')
    technician_name = serializers.ReadOnlyField(source='technician.name')
    sla = SLATrackingSerializer(read_only=True)

    class Meta:
        model = ServiceTicket
        fields = [
            'id', 'ticket_number', 'subject', 'description', 'status',
            'priority', 'asset', 'asset_name', 'asset_serial', 'technician',
            'technician_name', 'due_date', 'resolved_at', 'started_at', 'sla',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'ticket_number', 'resolved_at', 'created_at', 'updated_at', 'created_by', 'updated_by']

    SLA_DEFAULTS = {
        'Critical': {'response': 30, 'resolution': 240},
        'High': {'response': 60, 'resolution': 480},
        'Medium': {'response': 120, 'resolution': 1440},
        'Low': {'response': 480, 'resolution': 4320},
    }

    def create(self, validated_data):
        import random
        if 'ticket_number' not in validated_data:
            validated_data['ticket_number'] = f"TKT-{random.randint(100000, 999999)}"
        ticket = super().create(validated_data)

        # Auto-create SLA record based on priority
        priority = ticket.priority
        sla_config = self.SLA_DEFAULTS.get(priority, self.SLA_DEFAULTS['Medium'])
        SLATracking.objects.create(
            ticket=ticket,
            response_time_limit=sla_config['response'],
            resolution_time_limit=sla_config['resolution'],
        )

        return ticket

class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    asset_name = serializers.ReadOnlyField(source='asset.name')

    class Meta:
        model = MaintenanceSchedule
        fields = [
            'id', 'asset', 'asset_name', 'title', 'description', 'frequency',
            'next_run_date', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class WorkOrderMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkOrderMaterial
        fields = [
            'id', 'work_order', 'item_description', 'quantity',
            'unit_price', 'total_price',
        ]
        read_only_fields = ['id']


class WorkOrderSerializer(serializers.ModelSerializer):
    materials = WorkOrderMaterialSerializer(many=True, read_only=True)
    asset_name = serializers.ReadOnlyField(source='asset.name')
    technician_name = serializers.ReadOnlyField(source='technician.name')

    class Meta:
        model = WorkOrder
        fields = [
            'id', 'work_order_number', 'title', 'description', 'status',
            'priority', 'asset', 'asset_name', 'technician', 'technician_name',
            'scheduled_date', 'completed_date', 'labor_hours', 'labor_cost',
            'parts_cost', 'total_cost', 'notes', 'materials',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'work_order_number', 'total_cost', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def create(self, validated_data):
        import random
        if 'work_order_number' not in validated_data:
            validated_data['work_order_number'] = f"WO-{random.randint(100000, 999999)}"
        return super().create(validated_data)


class CitizenRequestSerializer(serializers.ModelSerializer):
    related_ticket_number = serializers.ReadOnlyField(source='related_ticket.ticket_number')

    class Meta:
        model = CitizenRequest
        fields = [
            'id', 'request_number', 'citizen_name', 'citizen_email',
            'citizen_phone', 'citizen_address', 'category', 'subject',
            'description', 'status', 'latitude', 'longitude',
            'related_ticket', 'related_ticket_number',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'request_number', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def create(self, validated_data):
        import random
        if 'request_number' not in validated_data:
            validated_data['request_number'] = f"CR-{random.randint(100000, 999999)}"
        return super().create(validated_data)


class ServiceMetricSerializer(serializers.ModelSerializer):
    response_sla_percentage = serializers.ReadOnlyField()
    resolution_sla_percentage = serializers.ReadOnlyField()

    class Meta:
        model = ServiceMetric
        fields = [
            'id', 'name', 'period', 'period_start', 'period_end',
            'total_tickets', 'open_tickets', 'resolved_tickets',
            'closed_tickets', 'avg_response_time', 'avg_resolution_time',
            'sla_response_met', 'sla_response_total', 'sla_resolution_met',
            'sla_resolution_total', 'total_work_orders', 'completed_work_orders',
            'total_labor_hours', 'total_cost',
            'response_sla_percentage', 'resolution_sla_percentage',
        ]
        read_only_fields = ['id']
