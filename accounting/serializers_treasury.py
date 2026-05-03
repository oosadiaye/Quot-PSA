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
    gl_cash_account_code = serializers.CharField(
        source='gl_cash_account.code', read_only=True, default='',
    )
    gl_cash_account_name = serializers.CharField(
        source='gl_cash_account.name', read_only=True, default='',
    )
    ncoa_cash_code_value = serializers.CharField(
        source='ncoa_cash_code.code', read_only=True, default='',
    )
    ncoa_cash_code_name = serializers.CharField(
        source='ncoa_cash_code.name', read_only=True, default='',
    )
    sub_account_count = serializers.SerializerMethodField()

    class Meta:
        model = TreasuryAccount
        fields = [
            'id', 'account_number', 'account_name', 'bank', 'sort_code',
            'account_type', 'mda', 'mda_name', 'fund_segment', 'fund_name',
            'parent_account', 'parent_account_number',
            'gl_cash_account', 'gl_cash_account_code', 'gl_cash_account_name',
            'ncoa_cash_code', 'ncoa_cash_code_value', 'ncoa_cash_code_name',
            'is_active', 'current_balance', 'last_reconciled', 'description',
            'sub_account_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'current_balance']

    def get_sub_account_count(self, obj: TreasuryAccount) -> int:
        return obj.sub_accounts.count()

    def validate_gl_cash_account(self, value):
        """Enforce Asset-only and active GL accounts on the cash-side link."""
        if value is None:
            return value
        if value.account_type != 'Asset':
            raise serializers.ValidationError(
                f"GL cash account must be of type 'Asset' — got '{value.account_type}'."
            )
        if not value.is_active:
            raise serializers.ValidationError(
                "GL cash account is inactive — activate it before assigning."
            )
        return value


# ─── Payment Voucher ──────────────────────────────────────────────────


class PaymentVoucherDeductionSerializer(serializers.ModelSerializer):
    """Deduction / charge line on a PaymentVoucher.

    Exposed as a nested writable serializer on the parent PV — clients
    POST/PUT the full set of deductions with the PV body and the parent
    serializer rebuilds the children in one transaction.
    """
    deduction_type_display = serializers.CharField(
        source='get_deduction_type_display', read_only=True,
    )
    gl_account_code = serializers.CharField(source='gl_account.code', read_only=True)
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)
    withholding_tax_code = serializers.CharField(
        source='withholding_tax.code', read_only=True, allow_null=True,
    )

    class Meta:
        from accounting.models.treasury import PaymentVoucherDeduction  # local to avoid circular
        model = PaymentVoucherDeduction
        fields = [
            'id', 'deduction_type', 'deduction_type_display',
            'description', 'withholding_tax', 'withholding_tax_code',
            'rate', 'amount',
            'gl_account', 'gl_account_code', 'gl_account_name',
        ]
        read_only_fields = [
            'id', 'deduction_type_display',
            'gl_account_code', 'gl_account_name', 'withholding_tax_code',
        ]

    def validate_amount(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Deduction amount must be greater than zero.")
        return value


class PaymentVoucherSerializer(serializers.ModelSerializer):
    ncoa_full_code = serializers.CharField(source='ncoa_code.full_code', read_only=True)
    ncoa_account_name = serializers.CharField(source='ncoa_code.account_name', read_only=True)
    ncoa_mda_name = serializers.CharField(source='ncoa_code.mda_name', read_only=True)
    appropriation_ref = serializers.SerializerMethodField()
    tsa_account_number = serializers.CharField(
        source='tsa_account.account_number', read_only=True,
    )
    has_instruction = serializers.SerializerMethodField()
    deductions = PaymentVoucherDeductionSerializer(many=True, required=False)
    total_deductions = serializers.SerializerMethodField()

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
            'deductions', 'total_deductions',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'voucher_number', 'net_amount',
            'total_deductions',
            'created_at', 'updated_at', 'journal',
        ]

    def get_total_deductions(self, obj: PaymentVoucherGov) -> str:
        total = sum((d.amount for d in obj.deductions.all()), Decimal('0'))
        return str(total)

    def _sync_deductions(self, pv, deductions_data):
        """Rebuild the deduction child rows from the payload.

        Payment-time recognition: the caller sends the complete deduction
        set on every save. We delete the previous rows and recreate them
        inside the parent's transaction — simpler than diffing ids and
        safer when a deduction is later corrected before payment.
        """
        from accounting.models.treasury import PaymentVoucherDeduction
        if pv.status in ('PAID', 'REVERSED'):
            raise serializers.ValidationError(
                {'deductions': f"Cannot modify deductions on a {pv.status} voucher."}
            )
        PaymentVoucherDeduction.objects.filter(payment_voucher=pv).delete()
        for d in (deductions_data or []):
            # Nested serializer already validated amount/rate etc.
            PaymentVoucherDeduction.objects.create(
                payment_voucher=pv, **d,
            )
        # Force net_amount to refresh from the new set.
        pv.save()

    def create(self, validated_data):
        deductions_data = validated_data.pop('deductions', None)
        pv = super().create(validated_data)

        # Auto-apply WHT from the linked invoice when:
        #   • the operator referenced an invoice (invoice_number set), AND
        #   • no explicit WHT deduction was sent in the payload.
        # This mirrors Nigerian PFM cash-basis recognition: WHT is
        # determined at invoice and *recognised* at payment. If the
        # invoice is flagged exempt (vendor master OR per-transaction)
        # the helper returns is_exempt=True and we skip the deduction.
        derived_wht = None
        if pv.invoice_number:
            try:
                from accounting.services.wht_payment_derivation import (
                    derive_wht_for_invoice,
                )
                derived_wht = derive_wht_for_invoice(
                    invoice_number=pv.invoice_number,
                )
            except Exception:
                derived_wht = None  # never block PV creation on WHT lookup

        # Decide whether to inject the auto-derived WHT.
        # If the operator sent deductions but none of them is WHT, AND
        # the invoice has a non-exempt WHT determination, append it so
        # the deduction always lands on the PV. If the operator already
        # sent a WHT deduction, respect their override.
        if deductions_data is None:
            deductions_data = []
        already_has_wht = any(
            (d.get('deduction_type') == 'WHT') for d in deductions_data
        )
        if (
            derived_wht is not None
            and not derived_wht.get('is_exempt', False)
            and derived_wht.get('amount', 0) > 0
            and not already_has_wht
        ):
            from accounting.models import WithholdingTax, Account
            wht_obj = (
                WithholdingTax.objects.filter(pk=derived_wht['withholding_tax']).first()
                if derived_wht.get('withholding_tax') else None
            )
            gl_obj = (
                Account.objects.filter(pk=derived_wht['gl_account']).first()
                if derived_wht.get('gl_account') else None
            )
            if wht_obj and gl_obj:
                deductions_data.append({
                    'deduction_type': 'WHT',
                    'description':    derived_wht.get('description', ''),
                    'withholding_tax': wht_obj,
                    'rate':            derived_wht.get('rate', 0),
                    'amount':          derived_wht.get('amount', 0),
                    'gl_account':      gl_obj,
                })

        # Always rebuild deduction rows from the (possibly augmented) set.
        if deductions_data:
            self._sync_deductions(pv, deductions_data)
        return pv

    def update(self, instance, validated_data):
        deductions_data = validated_data.pop('deductions', None)
        pv = super().update(instance, validated_data)
        if deductions_data is not None:
            self._sync_deductions(pv, deductions_data)
        return pv

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
        # Pop deductions so BudgetValidationService doesn't choke on the
        # nested payload — the parent serializer's create() will re-pop
        # and sync them. We re-attach here to stay inside the same call.
        deductions_holder = validated_data.pop('deductions', None)
        if deductions_holder is not None:
            validated_data['deductions'] = deductions_holder
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
