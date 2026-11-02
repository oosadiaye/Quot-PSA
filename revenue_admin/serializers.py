from rest_framework import serializers

from .models import (
    Taxpayer,
    TaxAccount,
    Assessment,
    BillingRun,
    DemandNotice,
    ArrearsLedger,
    EnforcementCase,
    TaxClearanceCertificate,
)


class TaxpayerSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Taxpayer
        fields = [
            'id', 'tin', 'case_type', 'full_name', 'business_name', 'bvn',
            'email', 'phone', 'address', 'is_active', 'display_name',
        ]


class TaxAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxAccount
        fields = ['id', 'taxpayer', 'revenue_head', 'running_balance']


class AssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assessment
        fields = [
            'id', 'taxpayer', 'revenue_head', 'fiscal_year', 'assessment_type',
            'status', 'assessed_amount', 'objection', 'issued_at',
        ]
        read_only_fields = ['issued_at']


class BillingRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingRun
        fields = [
            'id', 'revenue_head', 'fiscal_year', 'cycle', 'status',
            'notices_created', 'total_amount', 'processed_at',
        ]
        read_only_fields = ['processed_at']


class DemandNoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemandNotice
        fields = [
            'id', 'taxpayer', 'billing_run', 'assessment', 'notice_number',
            'amount_due', 'amount_paid', 'due_date', 'status', 'issued_at',
        ]
        read_only_fields = ['issued_at']


class ArrearsLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArrearsLedger
        fields = [
            'id', 'taxpayer', 'fiscal_year', 'revenue_head', 'amount',
            'arrears_date', 'ageing_days', 'is_settled',
        ]


class EnforcementCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnforcementCase
        fields = [
            'id', 'taxpayer', 'arrears', 'amount_in_dispute', 'status',
            'distraint_order', 'opened_at', 'resolved_at',
        ]
        read_only_fields = ['opened_at']


class TaxClearanceCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxClearanceCertificate
        fields = [
            'id', 'taxpayer', 'certificate_number', 'status', 'fiscal_year',
            'issue_date', 'expiry_date', 'verified_at',
        ]
        read_only_fields = ['verified_at']
