from rest_framework import serializers

from .models import Vehicle, VehicleAssignment, FuelLog, MileageLog, MaintenanceRecord


class VehicleSerializer(serializers.ModelSerializer):
    is_expiring = serializers.BooleanField(read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'fixed_asset', 'registration_number', 'chassis_number', 'make',
            'model', 'year', 'fuel_type', 'status', 'licence_expiry',
            'insurance_expiry', 'roadworthiness_expiry', 'is_expiring',
        ]


class VehicleAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleAssignment
        fields = [
            'id', 'vehicle', 'assigned_to', 'department', 'assigned_from',
            'assigned_to_date', 'notes',
        ]


class FuelLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelLog
        fields = [
            'id', 'vehicle', 'log_date', 'litres', 'cost', 'odometer_reading',
            'vendor',
        ]


class MileageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MileageLog
        fields = [
            'id', 'vehicle', 'log_date', 'odometer_reading', 'trip_purpose',
            'driver',
        ]


class MaintenanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceRecord
        fields = [
            'id', 'vehicle', 'service_date', 'next_due_date', 'service_type',
            'description', 'cost', 'service_provider',
        ]
