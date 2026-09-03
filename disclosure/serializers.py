from rest_framework import serializers

from .models import DeclarationCycle, AssetDeclaration, DeclarationItem, DisclosureAccessLog


class DeclarationCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeclarationCycle
        fields = ['id', 'name', 'fiscal_year', 'opens_at', 'closes_at', 'is_open']


class DeclarationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeclarationItem
        fields = [
            'id', 'declaration', 'asset_type', 'description',
            'value_encrypted', 'value_ciphertext',
        ]
        read_only_fields = ['value_encrypted', 'value_ciphertext']


class AssetDeclarationSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source='employee.first_name', read_only=True, default='',
    )
    items = DeclarationItemSerializer(many=True, read_only=True)

    class Meta:
        model = AssetDeclaration
        fields = [
            'id', 'cycle', 'employee', 'employee_name', 'status',
            'submitted_at', 'acknowledged_at', 'acknowledged_by', 'items',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['submitted_at', 'acknowledged_at', 'acknowledged_by', 'created_at', 'updated_at']


class DisclosureAccessLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisclosureAccessLog
        fields = [
            'id', 'declaration', 'accessed_by', 'accessed_at', 'action', 'ip_address',
        ]
        read_only_fields = ['accessed_at']
