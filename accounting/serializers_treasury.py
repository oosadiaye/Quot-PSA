"""
Treasury & Revenue API Serializers — Quot PSE
"""
from decimal import Decimal
from rest_framework import serializers
from accounting.models.treasury import TreasuryAccount, PaymentVoucherGov, PaymentInstruction
from accounting.models.revenue import RevenueHead, RevenueCollection


# ─── Treasury Account ─────────────────────────────────────────────────

class TreasuryAccountSerializer(serializers.ModelSerializer):
    mda_name = serializers.CharField(source='mda.name', read_only=True, default='')
    fund_name = serializers.CharField(source='fund_segment.name', read_only=True, default='')
    parent_account_number = serializers.CharField(
        source='parent_account.account_number', read_only=True, default='',
    )
    sub_account_count = serializers.SerializerMethodField()

    class Meta:
        model = TreasuryAccount
        fields = [
            'id', 'account_number', 'account_name', 'bank', 'sort_code',
            'account_type', 'mda', 'mda_name', 'fund_segment', 'fund_name',
            'parent_account', 'parent_account_number',
            'is_active', 'current_balance', 'last_reconciled', 'description',
            'sub_account_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'current_balance']

    def get_sub_account_count(self, obj: TreasuryAccount) -> int:
        return obj.sub_accounts.count()


# ─── Payment Voucher ──────────────────────────────────────────────────

class PaymentVoucherSerializer(serializers.ModelSerializer):
    ncoa_full_code = serializers.CharField(source='ncoa_code.full_code', read_only=True)
    ncoa_account_name = serializers.CharField(source='ncoa_code.account_name', read_only=True)
    ncoa_mda_name = serializers.CharField(source='ncoa_code.mda_name', read_only=True)
    appropriation_ref = serializers.SerializerMethodField()
    tsa_account_number = serializers.CharField(
        source='tsa_account.account_number', read_only=True,
    )
    has_instruction = serializers.SerializerMethodField()

    # Payee details are optional at PV creation time — the Treasury/Bank
    # processing workflow may capture them later (e.g., via vendor master
    # lookup or from the linked invoice). We use ``allow_blank=True`` so
    # empty strings pass validation; the underlying CharField on the
    # model accepts '' at the DB level already (CharField default=No NOT NULL
    # constraint on empty string). No migration needed.
    payee_name     = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    payee_account  = serializers.CharField(max_length=20,  required=False, allow_blank=True, default='')
    payee_bank     = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    class Meta:
        model = PaymentVoucherGov
        fields = [
            'id', 'voucher_number', 'payment_type',
            'ncoa_code', 'ncoa_full_code', 'ncoa_account_name', 'ncoa_mda_name',
            'appropriation', 'appropriation_ref', 'warrant',
            'payee_name', 'payee_account', 'payee_bank', 'payee_sort_code',
            'gross_amount', 'wht_amount', 'net_amount',
            'narration', 'tsa_account', 'tsa_account_number',
            'source_document', 'invoice_number', 'invoice_date',
            'status', 'journal', 'notes',
            'has_instruction',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'voucher_number', 'net_amount',
            'created_at', 'updated_at', 'journal',
        ]

    def get_appropriation_ref(self, obj: PaymentVoucherGov) -> str:
        if obj.appropriation:
            return str(obj.appropriation)
        return ''

    def get_has_instruction(self, obj: PaymentVoucherGov) -> bool:
        return hasattr(obj, 'payment_instruction') and obj.payment_instruction is not None

    def validate_gross_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Gross amount must be greater than zero.")
        return value

    def validate(self, attrs):
        gross = attrs.get('gross_amount', Decimal('0'))
        wht = attrs.get('wht_amount', Decimal('0'))
        if wht < 0:
            raise serializers.ValidationError({'wht_amount': 'WHT cannot be negative.'})
        if wht > gross:
            raise serializers.ValidationError({'wht_amount': 'WHT cannot exceed gross amount.'})
        return attrs


class PaymentVoucherCreateSerializer(PaymentVoucherSerializer):
    """Extended serializer for PV creation with budget validation."""

    class Meta(PaymentVoucherSerializer.Meta):
        read_only_fields = [
            'id', 'voucher_number', 'net_amount', 'status',
            'created_at', 'updated_at', 'journal',
        ]

    def create(self, validated_data):
        # Auto-generate voucher number
        from accounting.models.gl import TransactionSequence
        validated_data['voucher_number'] = TransactionSequence.get_next(
            'payment_voucher', prefix='PV-',
        )
        # Budget validation (if appropriation is set)
        if validated_data.get('appropriation'):
            from budget.services import BudgetValidationService, BudgetExceededError
            try:
                appro = validated_data['appropriation']
                BudgetValidationService.validate_expenditure(
                    administrative_id=appro.administrative_id,
                    economic_id=appro.economic_id,
                    fund_id=appro.fund_id,
                    fiscal_year_id=appro.fiscal_year_id,
                    amount=validated_data['gross_amount'],
                )
            except BudgetExceededError as e:
                raise serializers.ValidationError({'appropriation': str(e)})
        return super().create(validated_data)


# ─── Payment Instruction ─────────────────────────────────────────────

class PaymentInstructionSerializer(serializers.ModelSerializer):
    voucher_number = serializers.CharField(
        source='payment_voucher.voucher_number', read_only=True,
    )
    tsa_account_number = serializers.CharField(
        source='tsa_account.account_number', read_only=True,
    )

    class Meta:
        model = PaymentInstruction
        fields = [
            'id', 'payment_voucher', 'voucher_number',
            'tsa_account', 'tsa_account_number',
            'beneficiary_name', 'beneficiary_account', 'beneficiary_bank',
            'beneficiary_sort', 'amount', 'narration',
            'batch_reference', 'bank_reference',
            'submitted_at', 'processed_at', 'status', 'failure_reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'bank_reference', 'submitted_at', 'processed_at',
            'created_at', 'updated_at',
        ]


# ─── Revenue Head ────────────────────────────────────────────────────

class RevenueHeadSerializer(serializers.ModelSerializer):
    economic_code = serializers.CharField(
        source='economic_segment.code', read_only=True,
    )
    economic_name = serializers.CharField(
        source='economic_segment.name', read_only=True,
    )
    collection_mda_name = serializers.CharField(
        source='collection_mda.name', read_only=True, default='',
    )

    class Meta:
        model = RevenueHead
        fields = [
            'id', 'code', 'name', 'economic_segment', 'economic_code',
            'economic_name', 'revenue_type', 'collection_mda',
            'collection_mda_name', 'remittance_rate', 'is_active',
            'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ─── Revenue Collection ─────────────────────────────────────────────

class RevenueCollectionSerializer(serializers.ModelSerializer):
    revenue_head_name = serializers.CharField(
        source='revenue_head.name', read_only=True,
    )
    ncoa_full_code = serializers.CharField(
        source='ncoa_code.full_code', read_only=True,
    )
    tsa_account_number = serializers.CharField(
        source='tsa_account.account_number', read_only=True,
    )
    collecting_mda_name = serializers.CharField(
        source='collecting_mda.name', read_only=True, default='',
    )

    class Meta:
        model = RevenueCollection
        fields = [
            'id', 'receipt_number', 'revenue_head', 'revenue_head_name',
            'ncoa_code', 'ncoa_full_code',
            'payer_name', 'payer_tin', 'payer_phone', 'payer_address',
            'amount', 'payment_reference', 'rrr',
            'tsa_account', 'tsa_account_number',
            'collection_date', 'value_date', 'collection_channel',
            'collecting_mda', 'collecting_mda_name',
            'status', 'journal',
            'period_month', 'period_year', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'receipt_number', 'status', 'journal',
            'created_at', 'updated_at',
        ]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def create(self, validated_data):
        from accounting.models.gl import TransactionSequence
        validated_data['receipt_number'] = TransactionSequence.get_next(
            'revenue_receipt', prefix='OR-',
        )
        return super().create(validated_data)
