"""
NCoA Segment API Serializers — Quot PSE
"""
from rest_framework import serializers
from accounting.models.ncoa import (
    AdministrativeSegment, EconomicSegment, FunctionalSegment,
    ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
)


class AdministrativeSegmentSerializer(serializers.ModelSerializer):
    full_path = serializers.CharField(source='get_full_path', read_only=True)

    class Meta:
        model = AdministrativeSegment
        fields = [
            'id', 'code', 'name', 'short_name', 'level', 'sector_code',
            'organization_code', 'sub_org_code', 'sub_sub_org_code', 'unit_code',
            'parent', 'is_active', 'is_mda', 'mda_type', 'description', 'full_path',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EconomicSegmentSerializer(serializers.ModelSerializer):
    account_type_label = serializers.CharField(read_only=True)

    class Meta:
        model = EconomicSegment
        fields = [
            'id', 'code', 'name', 'account_type_code', 'account_type_label',
            'sub_type_code', 'account_class_code', 'sub_class_code', 'line_item_code',
            'parent', 'is_active', 'is_posting_level', 'is_control_account',
            'normal_balance', 'legacy_account', 'legacy_account_type', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EconomicSegmentTreeSerializer(serializers.ModelSerializer):
    """Hierarchical tree view with children."""
    children = serializers.SerializerMethodField()
    account_type_label = serializers.CharField(read_only=True)

    class Meta:
        model = EconomicSegment
        fields = [
            'id', 'code', 'name', 'account_type_code', 'account_type_label',
            'is_posting_level', 'is_control_account', 'normal_balance',
            'is_active', 'children',
        ]

    def get_children(self, obj):
        children = obj.children.filter(is_active=True).order_by('code')
        return EconomicSegmentTreeSerializer(children, many=True).data


class FunctionalSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunctionalSegment
        fields = [
            'id', 'code', 'name', 'division_code', 'group_code', 'class_code',
            'parent', 'is_active', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProgrammeSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgrammeSegment
        fields = [
            'id', 'code', 'name', 'policy_code', 'programme_code',
            'project_code', 'objective_code', 'activity_code',
            'parent', 'is_active', 'is_capital',
            'project_start', 'project_end', 'total_project_cost', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FundSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FundSegment
        fields = [
            'id', 'code', 'name', 'main_fund_code', 'sub_fund_code',
            'fund_source_code', 'donor_name', 'parent',
            'is_active', 'is_restricted', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GeographicSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeographicSegment
        fields = [
            'id', 'code', 'name', 'zone_code', 'state_code',
            'senatorial_code', 'lga_code', 'ward_code',
            'parent', 'is_active', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NCoACodeSerializer(serializers.ModelSerializer):
    full_code = serializers.CharField(read_only=True)
    account_name = serializers.CharField(read_only=True)
    mda_name = serializers.CharField(read_only=True)
    administrative_code = serializers.CharField(source='administrative.code', read_only=True)
    economic_code = serializers.CharField(source='economic.code', read_only=True)
    functional_code = serializers.CharField(source='functional.code', read_only=True)
    programme_code_display = serializers.CharField(source='programme.code', read_only=True)
    fund_code = serializers.CharField(source='fund.code', read_only=True)
    geographic_code = serializers.CharField(source='geographic.code', read_only=True)

    class Meta:
        model = NCoACode
        fields = [
            'id', 'full_code', 'account_name', 'mda_name',
            'administrative', 'administrative_code',
            'economic', 'economic_code',
            'functional', 'functional_code',
            'programme', 'programme_code_display',
            'fund', 'fund_code',
            'geographic', 'geographic_code',
            'is_active', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
