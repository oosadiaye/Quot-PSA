"""DRF serializers for payment batching."""
from __future__ import annotations

from rest_framework import serializers

from accounting.models import BankLetterSettings, PaymentBatch, PaymentBatchLine


class PaymentBatchLineSerializer(serializers.ModelSerializer):
    payment_number = serializers.CharField(source='payment.payment_number',
                                           read_only=True, default='')

    class Meta:
        model = PaymentBatchLine
        fields = ['id', 'sequence', 'payment', 'payment_number',
                  'payee_name', 'payee_bank', 'payee_account',
                  'purpose', 'amount', 'is_active_membership']
        read_only_fields = fields


class PaymentBatchSerializer(serializers.ModelSerializer):
    lines = PaymentBatchLineSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=20, decimal_places=2,
                                            read_only=True)
    line_count = serializers.SerializerMethodField()
    source_bank_account_name = serializers.CharField(
        source='source_bank_account.name', read_only=True, default='')

    class Meta:
        model = PaymentBatch
        fields = ['id', 'batch_number', 'batch_date', 'source_bank_account',
                  'source_bank_account_name', 'addressee_bank_name',
                  'addressee_account_no', 'status', 'total_amount',
                  'line_count', 'lines', 'notes', 'cancelled_reason',
                  'dispatched_at', 'confirmed_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'batch_number', 'addressee_bank_name',
                            'addressee_account_no', 'status', 'total_amount',
                            'line_count', 'lines', 'cancelled_reason',
                            'dispatched_at', 'confirmed_at',
                            'created_at', 'updated_at']

    def get_line_count(self, obj) -> int:
        return obj.lines.filter(is_active_membership=True).count()


class PaymentBatchCreateSerializer(serializers.Serializer):
    source_bank_account = serializers.IntegerField()
    batch_date = serializers.DateField(required=False, allow_null=True)
    payment_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False)


class AddLinesSerializer(serializers.Serializer):
    payment_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False)


class RemoveLineSerializer(serializers.Serializer):
    line_id = serializers.IntegerField()


class CancelBatchSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class BankLetterSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankLetterSettings
        fields = ['id', 'ministry_name', 'office_name', 'office_address',
                  'letterhead_logo',
                  'accountant_general_name', 'accountant_general_title',
                  'accountant_general_signature',
                  'director_treasury_name', 'director_treasury_title',
                  'director_treasury_signature',
                  'director_mgmt_acct_name', 'director_mgmt_acct_title',
                  'director_mgmt_acct_signature']
        read_only_fields = ['id']
