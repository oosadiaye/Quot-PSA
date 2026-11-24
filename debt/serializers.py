from rest_framework import serializers

from .models import (
    DebtClassification,
    DebtDrawdown,
    DebtInstrument,
    AmortisationSchedule,
    AmortisationCoupon,
    AmortisationLedger,
    DebtServiceCost,
    DebtAversionStatement,
)


class DebtInstrumentSerializer(serializers.ModelSerializer):
    outstanding_principal = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)
    drawn_amount = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)
    principal_repaid = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)
    liability_account_name = serializers.CharField(source='liability_account.name', read_only=True, default='')
    current_portion_account_name = serializers.CharField(source='current_portion_account.name', read_only=True, default='')
    interest_expense_account_name = serializers.CharField(source='interest_expense_account.name', read_only=True, default='')
    bank_account_name = serializers.CharField(source='bank_account.name', read_only=True, default='')

    class Meta:
        model = DebtInstrument
        fields = [
            'id', 'instrument_number', 'instrument_type', 'creditor', 'currency',
            'principal_amount', 'interest_rate', 'commitment_fee_rate',
            'start_date', 'maturity_date', 'grace_period', 'status',
            'is_concessional', 'outstanding_principal', 'drawn_amount', 'principal_repaid',
            'liability_account', 'liability_account_name', 'current_portion_account', 'current_portion_account_name',
            'interest_expense_account', 'interest_expense_account_name', 'fee_expense_account',
            'bank_account', 'bank_account_name', 'current_portion_booked',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'current_portion_booked']

    def validate(self, attrs):
        # Each mapped account must be a usable GL account of the right kind, so a bad choice fails here and not at posting.
        for name, kind in (('liability_account', 'Liability'), ('current_portion_account', 'Liability'),
                           ('interest_expense_account', 'Expense'), ('fee_expense_account', 'Expense')):
            account = attrs.get(name)
            if account is None:
                continue
            if account.account_type != kind:
                raise serializers.ValidationError({name: f'This must be a {kind} account ({account.code} is {account.account_type}).'})
            if not account.is_active or not account.is_postable:
                raise serializers.ValidationError({name: f'{account.code} is not an active, postable account.'})
        bank = attrs.get('bank_account')
        if bank is not None and not bank.gl_account_id:
            raise serializers.ValidationError({'bank_account': 'This bank account has no GL account.'})
        return attrs


class AmortisationScheduleSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)

    class Meta:
        model = AmortisationSchedule
        fields = [
            'id', 'instrument', 'coupon_date', 'principal_amount',
            'interest_amount', 'commitment_fee', 'total_amount', 'is_released',
        ]


class AmortisationCouponSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)
    due_date = serializers.DateField(source='schedule.coupon_date', read_only=True)
    instrument = serializers.IntegerField(source='schedule.instrument_id', read_only=True)

    class Meta:
        model = AmortisationCoupon
        fields = [
            'id', 'schedule', 'due_date', 'instrument', 'principal_amount', 'interest_amount',
            'commitment_fee', 'total_amount', 'status', 'warrant', 'paid_at', 'bank_account', 'journal',
        ]
        read_only_fields = ['paid_at', 'bank_account', 'journal']


class AmortisationLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AmortisationLedger
        fields = [
            'id', 'coupon', 'event', 'amount', 'warrant', 'description',
            'recorded_by', 'recorded_at',
        ]
        read_only_fields = ['recorded_at']


class DebtServiceCostSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtServiceCost
        fields = [
            'id', 'fiscal_year', 'month', 'instrument', 'principal_paid',
            'interest_paid', 'fees_paid',
        ]


class DebtAversionStatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtAversionStatement
        fields = [
            'id', 'fiscal_year', 'pillar', 'outstanding_balance', 'gdp',
            'revenue', 'debt_to_gdp', 'debt_service_to_revenue', 'assessment',
        ]


class DebtDrawdownSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source='bank_account.name', read_only=True)
    instrument_number = serializers.CharField(source='instrument.instrument_number', read_only=True)
    journal_number = serializers.CharField(source='journal.document_number', read_only=True, default='')

    class Meta:
        model = DebtDrawdown
        fields = ['id', 'instrument', 'instrument_number', 'drawdown_date', 'amount', 'bank_account', 'bank_account_name',
                  'reference', 'status', 'journal', 'journal_number', 'created_at']
        read_only_fields = fields


class DebtClassificationSerializer(serializers.ModelSerializer):
    journal_number = serializers.CharField(source='journal.document_number', read_only=True, default='')

    class Meta:
        model = DebtClassification
        fields = ['id', 'instrument', 'as_of', 'current_portion', 'adjustment', 'journal', 'journal_number', 'created_at']
        read_only_fields = fields
