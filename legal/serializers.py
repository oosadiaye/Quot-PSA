from rest_framework import serializers

from .models import (
    LegalCase,
    HearingDiary,
    CaseCost,
    RiskRegister,
    LitigationProvisionLink,
)


class LegalCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalCase
        fields = [
            'id', 'case_number', 'title', 'court', 'claimant', 'defendant',
            'stage', 'next_hearing_date', 'assigned_counsel', 'summary',
        ]


class HearingDiarySerializer(serializers.ModelSerializer):
    class Meta:
        model = HearingDiary
        fields = ['id', 'case', 'hearing_date', 'outcome', 'next_hearing_date']


class CaseCostSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseCost
        fields = [
            'id', 'case', 'cost_date', 'description', 'amount', 'cost_type',
            'is_award',
        ]


class RiskRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskRegister
        fields = [
            'id', 'title', 'category', 'likelihood', 'impact', 'mitigation',
            'mitigation_owner', 'is_active', 'case',
        ]


class LitigationProvisionLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = LitigationProvisionLink
        fields = [
            'id', 'case', 'provision', 'contingent_liability', 'amount',
            'linked_by', 'linked_at',
        ]
        read_only_fields = ['linked_by', 'linked_at']
