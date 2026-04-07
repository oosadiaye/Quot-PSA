from rest_framework import serializers
from .models import (
    Account, Fund, Function, Program, Geo, Currency, GLBalance,
    JournalHeader, JournalLine,
    VendorInvoice, Payment, PaymentAllocation, VendorInvoiceLine,
    CustomerInvoice, Receipt, ReceiptAllocation, FixedAsset, DepreciationSchedule, CustomerInvoiceLine,
    MDA, BudgetPeriod, Budget, BudgetEncumbrance, BudgetAmendment, BudgetTransfer,
    BudgetCheckLog, BudgetForecast, BudgetAnomaly,
    BankAccount, Checkbook, Check, BankReconciliation,
    CashFlowCategory, CashFlowForecast,
    TaxRegistration, TaxExemption, TaxReturn, WithholdingTax, TaxCode,
    CostCenter, ProfitCenter, CostAllocationRule, JournalLineCostCenter,
    InterCompany, InterCompanyAccountMapping, InterCompanyTransaction, InterCompanyElimination,
    FinancialReportTemplate, FinancialReport, ReportColumnConfig,
    AccountingDocument, DocumentSignature,
    ConsolidationGroup, Consolidation,
    DeferredRevenue, DeferredExpense, AmortizationSchedule,
    Lease, LeasePayment,
    TreasuryForecast, Investment, Loan, LoanRepayment,
    ExchangeRateHistory, ForeignCurrencyRevaluation,
    FiscalPeriod, PeriodCloseCheck, FiscalYear, PeriodAccess,
    AssetClass, AssetCategory, AssetConfiguration, AssetLocation, AssetInsurance,
    AssetMaintenance, AssetTransfer, AssetDepreciationSchedule, AssetRevaluationRun, AssetRevaluationDetail,
    AssetDisposal, AssetImpairment,
    JournalReversal,
    RecurringJournal, RecurringJournalLine, RecurringJournalRun,
    Accrual, Deferral, DeferralRecognition,
    PeriodStatus, YearEndClosing, CurrencyRevaluation, RetainedEarnings,
    AccountingSettings,
    Company, InterCompanyConfig, InterCompanyInvoice,
    InterCompanyTransfer, InterCompanyAllocation, InterCompanyCashTransfer,
    ConsolidationRun,
)


def is_dimensions_enabled(context):
    """Check if dimensions module is enabled based on request context."""
    if not context:
        return True
    request = context.get('request')
    if not request or not hasattr(request, 'tenant'):
        return True
    from tenants.models import is_dimensions_enabled as check_dimensions
    try:
        return check_dimensions(request.tenant)
    except Exception:
        return True


class FundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fund
        fields = ['id', 'code', 'name', 'description', 'is_active']
        read_only_fields = ['id']


class FunctionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Function
        fields = ['id', 'code', 'name', 'description', 'is_active']
        read_only_fields = ['id']


class ProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = ['id', 'code', 'name', 'description', 'is_active']
        read_only_fields = ['id']


class GeoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Geo
        fields = ['id', 'code', 'name', 'description', 'is_active']
        read_only_fields = ['id']


class AccountSerializer(serializers.ModelSerializer):
    reconciliation_type_display = serializers.CharField(
        source='get_reconciliation_type_display', read_only=True
    )

    current_balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'account_type', 'is_active',
            'is_reconciliation', 'reconciliation_type', 'reconciliation_type_display',
            'current_balance',
        ]
        read_only_fields = ['id', 'current_balance']

    def validate(self, attrs):
        account_type = attrs.get('account_type', getattr(self.instance, 'account_type', None))
        is_recon = attrs.get('is_reconciliation', getattr(self.instance, 'is_reconciliation', False))
        recon_type = attrs.get('reconciliation_type', getattr(self.instance, 'reconciliation_type', ''))
        code = attrs.get('code', getattr(self.instance, 'code', ''))

        if is_recon and account_type not in ('Asset', 'Liability'):
            raise serializers.ValidationError({
                'is_reconciliation': 'Reconciliation accounts are only valid for Asset or Liability types.'
            })
        if is_recon and not recon_type:
            raise serializers.ValidationError({
                'reconciliation_type': 'Please select a reconciliation type.'
            })
        if not is_recon:
            attrs['reconciliation_type'] = ''

        # Validate account code against digit enforcement and number series
        if code and account_type:
            from accounting.models import AccountingSettings
            settings_obj = AccountingSettings.objects.first()

            if settings_obj:
                is_valid, errors = settings_obj.validate_account_code(code, account_type)
                if not is_valid:
                    raise serializers.ValidationError({'code': errors})

        return attrs

    def get_current_balance(self, obj):
        # Use pre-annotated values if available (from AccountViewSet.get_queryset)
        if hasattr(obj, '_total_debit') and hasattr(obj, '_total_credit'):
            total_debit = obj._total_debit or 0
            total_credit = obj._total_credit or 0
        else:
            from accounting.models import GLBalance
            from django.db.models import Sum

            balances = GLBalance.objects.filter(account=obj).aggregate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance')
            )
            total_debit = balances['total_debit'] or 0
            total_credit = balances['total_credit'] or 0

        if obj.account_type in ['Asset', 'Expense']:
            return str(total_debit - total_credit)
        else:
            return str(total_credit - total_debit)


class JournalHeaderSerializer(serializers.ModelSerializer):
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()
    document_number = serializers.SerializerMethodField()

    class Meta:
        model = JournalHeader
        fields = [
            'id', 'posting_date', 'description', 'reference_number',
            'mda', 'fund', 'function', 'program', 'geo', 'status',
            'total_debit', 'total_credit', 'document_number',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'total_debit', 'total_credit', 'document_number']

    def get_total_debit(self, obj):
        from django.db.models import Sum
        return obj.lines.aggregate(total=Sum('debit'))['total'] or 0

    def get_total_credit(self, obj):
        from django.db.models import Sum
        return obj.lines.aggregate(total=Sum('credit'))['total'] or 0

    def get_document_number(self, obj):
        return obj.document_number or '-'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dims_enabled = is_dimensions_enabled(self.context)
        if not dims_enabled:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                self.fields[field].required = False
                self.fields[field].allow_null = True
                self.fields[field].allow_empty = True


class JournalLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalLine
        fields = ['id', 'header', 'account', 'debit', 'credit', 'memo', 'document_number']
        read_only_fields = ['id', 'document_number']


class JournalLineDetailSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True, default='')
    account_name = serializers.CharField(source='account.name', read_only=True, default='')

    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'account_code', 'account_name', 'debit', 'credit', 'memo', 'document_number']
        read_only_fields = ['id', 'document_number']


class JournalDetailSerializer(JournalHeaderSerializer):
    lines = JournalLineDetailSerializer(many=True, read_only=True)
    fund_name = serializers.CharField(source='fund.name', read_only=True, default='')

    class Meta(JournalHeaderSerializer.Meta):
        fields = JournalHeaderSerializer.Meta.fields + ['lines', 'fund_name']


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = [
            'id', 'code', 'name', 'symbol', 'exchange_rate',
            'is_base_currency', 'is_active',
        ]
        read_only_fields = ['id']


class GLBalanceSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True, default='')
    account_name = serializers.CharField(source='account.name', read_only=True, default='')
    fund_code = serializers.CharField(source='fund.code', read_only=True, default='')
    reference = serializers.CharField(read_only=True, default='')
    journal_number = serializers.CharField(read_only=True, default='')

    class Meta:
        model = GLBalance
        fields = [
            'id', 'account', 'account_code', 'account_name',
            'fund', 'fund_code', 'function', 'program', 'geo',
            'fiscal_year', 'period', 'debit_balance', 'credit_balance',
            'reference', 'journal_number',
        ]
        read_only_fields = ['id']


class VendorInvoiceLineDetailSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True, default='')
    account_name = serializers.CharField(source='account.name', read_only=True, default='')

    class Meta:
        model = VendorInvoiceLine
        fields = ['id', 'account', 'account_code', 'account_name', 'description', 'amount', 'tax_code', 'withholding_tax']
        read_only_fields = ['id']


class VendorInvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorInvoiceLine
        fields = ['id', 'account', 'description', 'amount', 'tax_code', 'withholding_tax']
        read_only_fields = ['id']


class VendorInvoiceSerializer(serializers.ModelSerializer):
    lines = VendorInvoiceLineSerializer(many=True, required=False)

    class Meta:
        model = VendorInvoice
        fields = [
            'id', 'invoice_number', 'reference', 'description',
            'vendor', 'invoice_date', 'due_date',
            'purchase_order', 'account', 'mda', 'fund', 'function',
            'program', 'geo', 'subtotal', 'tax_amount', 'total_amount',
            'paid_amount', 'currency', 'status', 'journal_entry', 'attachment',
            'document_number', 'document_type', 'lines',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at', 'updated_at', 'created_by', 'updated_by', 'document_number']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dims_enabled = is_dimensions_enabled(self.context)
        if not dims_enabled:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                self.fields[field].required = False
                self.fields[field].allow_null = True
                self.fields[field].allow_empty = True

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        invoice = VendorInvoice.objects.create(**validated_data)
        for line_data in lines_data:
            VendorInvoiceLine.objects.create(invoice=invoice, **line_data)
        return invoice

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', [])
        # Update existing fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update lines: for simplicity we recreate them
        if self.initial_data.get('lines') is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                VendorInvoiceLine.objects.create(invoice=instance, **line_data)
        return instance


class PaymentSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source='bank_account.name', read_only=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'payment_number', 'payment_date', 'payment_method',
            'reference_number', 'total_amount', 'currency', 'currency_code',
            'status', 'journal_entry', 'bank_account', 'bank_account_name',
            'vendor', 'vendor_name', 'is_advance', 'advance_type', 'advance_remaining',
            'document_number',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'document_number']


class PaymentAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAllocation
        fields = ['id', 'payment', 'invoice', 'amount']
        read_only_fields = ['id']


class CustomerInvoiceLineDetailSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True, default='')
    account_name = serializers.CharField(source='account.name', read_only=True, default='')

    class Meta:
        model = CustomerInvoiceLine
        fields = ['id', 'account', 'account_code', 'account_name', 'description', 'amount', 'tax_code', 'withholding_tax']
        read_only_fields = ['id']


class CustomerInvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerInvoiceLine
        fields = ['id', 'account', 'description', 'amount', 'tax_code', 'withholding_tax']
        read_only_fields = ['id']

class CustomerInvoiceSerializer(serializers.ModelSerializer):
    lines = CustomerInvoiceLineSerializer(many=True, required=False)

    class Meta:
        model = CustomerInvoice
        fields = [
            'id', 'invoice_number', 'reference', 'description',
            'customer', 'invoice_date', 'due_date',
            'sales_order', 'mda', 'fund', 'function', 'program', 'geo',
            'subtotal', 'tax_amount', 'total_amount', 'received_amount',
            'currency', 'status', 'journal_entry',
            'document_number', 'document_type', 'lines',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at', 'updated_at', 'created_by', 'updated_by', 'document_number']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dims_enabled = is_dimensions_enabled(self.context)
        if not dims_enabled:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                self.fields[field].required = False
                self.fields[field].allow_null = True
                self.fields[field].allow_empty = True

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        invoice = CustomerInvoice.objects.create(**validated_data)
        for line_data in lines_data:
            CustomerInvoiceLine.objects.create(invoice=invoice, **line_data)
        return invoice

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', [])
        # Update existing fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if self.initial_data.get('lines') is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                CustomerInvoiceLine.objects.create(invoice=instance, **line_data)
        return instance


class ReceiptSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source='bank_account.name', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = Receipt
        fields = [
            'id', 'receipt_number', 'receipt_date', 'payment_method',
            'reference_number', 'total_amount', 'currency', 'currency_code',
            'status', 'journal_entry', 'bank_account', 'bank_account_name',
            'customer', 'customer_name', 'is_advance', 'advance_type', 'advance_remaining',
            'document_number',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'document_number']


class ReceiptAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptAllocation
        fields = ['id', 'receipt', 'invoice', 'amount']
        read_only_fields = ['id']


class FixedAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = FixedAsset
        fields = [
            'id', 'asset_number', 'name', 'description', 'asset_category',
            'acquisition_date', 'acquisition_cost', 'salvage_value',
            'useful_life_years', 'depreciation_method', 'accumulated_depreciation',
            'asset_account', 'depreciation_expense_account',
            'accumulated_depreciation_account', 'mda', 'fund', 'function',
            'program', 'geo', 'status',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dims_enabled = is_dimensions_enabled(self.context)
        if not dims_enabled:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                self.fields[field].required = False
                self.fields[field].allow_null = True
                self.fields[field].allow_empty = True


class DepreciationScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepreciationSchedule
        fields = [
            'id', 'asset', 'period_date', 'depreciation_amount',
            'journal_entry', 'is_posted',
        ]
        read_only_fields = ['id']


class MDASerializer(serializers.ModelSerializer):
    class Meta:
        model = MDA
        fields = [
            'id', 'code', 'name', 'short_name', 'mda_type',
            'parent_mda', 'is_active',
        ]
        read_only_fields = ['id']


class BudgetPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetPeriod
        fields = [
            'id', 'fiscal_year', 'period_type', 'period_number',
            'start_date', 'end_date', 'status',
        ]
        read_only_fields = ['id']


class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = [
            'id', 'budget_code', 'period', 'mda', 'account', 'fund',
            'function', 'program', 'geo', 'cost_center',
            'allocated_amount', 'revised_amount',
            'control_level', 'enable_encumbrance', 'created_by',
        ]
        read_only_fields = ['id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dims_enabled = is_dimensions_enabled(self.context)
        if not dims_enabled:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                self.fields[field].required = False
                self.fields[field].allow_null = True
                self.fields[field].allow_empty = True


class BudgetEncumbranceSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetEncumbrance
        fields = [
            'id', 'budget', 'reference_type', 'reference_id',
            'encumbrance_date', 'amount', 'liquidated_amount',
            'status', 'description',
        ]
        read_only_fields = ['id']


class BudgetAmendmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetAmendment
        fields = [
            'id', 'budget', 'amendment_type', 'original_amount',
            'new_amount', 'reason', 'requested_by', 'approved_by',
            'status', 'requested_date', 'approved_date',
        ]
        read_only_fields = ['id', 'requested_date']


class BudgetTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetTransfer
        fields = [
            'id', 'from_budget', 'to_budget', 'amount', 'reason',
            'requested_by', 'approved_by', 'status', 'transfer_date',
        ]
        read_only_fields = ['id', 'transfer_date']


class BudgetCheckLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetCheckLog
        fields = [
            'id', 'budget', 'transaction_type', 'transaction_id',
            'requested_amount', 'available_amount', 'check_result',
            'override_by', 'override_reason', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class BudgetForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetForecast
        fields = [
            'id', 'budget', 'forecast_date', 'projected_revenue',
            'projected_expense', 'notes',
        ]
        read_only_fields = ['id']


class BudgetAnomalySerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetAnomaly
        fields = [
            'id', 'budget', 'anomaly_type', 'detected_amount',
            'expected_amount', 'description', 'detected_date',
            'reviewed', 'reviewed_by',
        ]
        read_only_fields = ['id', 'detected_date']


class BankAccountSerializer(serializers.ModelSerializer):
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)
    gl_account_code = serializers.CharField(source='gl_account.code', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = BankAccount
        fields = [
            'id', 'name', 'account_number', 'account_type', 'gl_account',
            'gl_account_name', 'gl_account_code', 'currency', 'currency_code',
            'opening_balance', 'current_balance', 'is_active', 'is_default',
            'bank_name', 'branch_name', 'swift_code', 'iban',
            'advance_customer_balance', 'advance_supplier_balance',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class CheckbookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checkbook
        fields = [
            'id', 'bank_account', 'checkbook_number', 'start_number',
            'end_number', 'next_number', 'status',
        ]
        read_only_fields = ['id']


class CheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = Check
        fields = [
            'id', 'checkbook', 'check_number', 'payment', 'amount',
            'payee', 'date_issued', 'date_cleared', 'status',
        ]
        read_only_fields = ['id']


class BankReconciliationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankReconciliation
        fields = [
            'id', 'bank_account', 'statement_date', 'statement_balance',
            'book_balance', 'reconciled_balance', 'deposits_in_transit',
            'outstanding_checks', 'bank_charges', 'difference',
            'reconciled_by', 'approved_by', 'status', 'reconciliation_date',
        ]
        read_only_fields = ['id']


class CashFlowCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowCategory
        fields = ['id', 'name', 'category_type', 'is_active']
        read_only_fields = ['id']


class CashFlowForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowForecast
        fields = [
            'id', 'bank_account', 'forecast_date', 'projected_inflow',
            'projected_outflow', 'notes',
        ]
        read_only_fields = ['id']


class TaxRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRegistration
        fields = [
            'id', 'tax_type', 'registration_number', 'effective_date',
            'is_active',
        ]
        read_only_fields = ['id']


class TaxExemptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxExemption
        fields = [
            'id', 'tax_registration', 'customer', 'vendor',
            'exemption_certificate', 'valid_from', 'valid_until', 'is_active',
        ]
        read_only_fields = ['id']


class TaxReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxReturn
        fields = [
            'id', 'tax_registration', 'period_start', 'period_end',
            'status', 'tax_type', 'output_tax', 'input_tax', 'tax_due',
        ]
        read_only_fields = ['id']


class WithholdingTaxSerializer(serializers.ModelSerializer):
    withholding_account_display = serializers.SerializerMethodField()

    class Meta:
        model = WithholdingTax
        fields = [
            'id', 'code', 'name', 'income_type', 'rate',
            'withholding_account', 'withholding_account_display',
            'is_active',
        ]
        read_only_fields = ['id']

    def get_withholding_account_display(self, obj):
        if obj.withholding_account:
            return {
                'id': obj.withholding_account.id,
                'code': obj.withholding_account.code,
                'name': obj.withholding_account.name,
            }
        return None


class TaxCodeSerializer(serializers.ModelSerializer):
    tax_account_display = serializers.SerializerMethodField()
    input_tax_account_display = serializers.SerializerMethodField()
    output_tax_account_display = serializers.SerializerMethodField()
    tax_type_display = serializers.CharField(
        source='get_tax_type_display', read_only=True,
    )
    direction_display = serializers.CharField(
        source='get_direction_display', read_only=True,
    )

    class Meta:
        model = TaxCode
        fields = [
            'id', 'code', 'name', 'tax_type', 'tax_type_display',
            'direction', 'direction_display', 'rate',
            'tax_account', 'tax_account_display',
            'input_tax_account', 'input_tax_account_display',
            'output_tax_account', 'output_tax_account_display',
            'is_active', 'description',
        ]
        read_only_fields = ['id']

    def _account_display(self, acc):
        if acc:
            return {'id': acc.id, 'code': acc.code, 'name': acc.name}
        return None

    def get_tax_account_display(self, obj):
        return self._account_display(obj.tax_account)

    def get_input_tax_account_display(self, obj):
        return self._account_display(obj.input_tax_account)

    def get_output_tax_account_display(self, obj):
        return self._account_display(obj.output_tax_account)

    def validate_rate(self, value):
        if value < 0:
            raise serializers.ValidationError('Rate cannot be negative.')
        if value > 100:
            raise serializers.ValidationError('Rate cannot exceed 100%.')
        return value


class CostCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostCenter
        fields = [
            'id', 'name', 'code', 'center_type', 'parent', 'manager',
            'is_active', 'is_operational', 'gl_account',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class ProfitCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfitCenter
        fields = ['id', 'name', 'code', 'manager', 'is_active']
        read_only_fields = ['id']


class CostAllocationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostAllocationRule
        fields = [
            'id', 'name', 'source_cost_center', 'source_account',
            'target_cost_center', 'allocation_method', 'percentage',
            'is_active',
        ]
        read_only_fields = ['id']


class JournalLineCostCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalLineCostCenter
        fields = ['id', 'journal_line', 'cost_center', 'amount']
        read_only_fields = ['id']


class InterCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = InterCompany
        fields = [
            'id', 'name', 'company_code', 'default_currency', 'is_active',
        ]
        read_only_fields = ['id']


class InterCompanyTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterCompanyTransaction
        fields = [
            'id', 'inter_company', 'transaction_type', 'transaction_date',
            'amount', 'currency', 'status', 'description',
        ]
        read_only_fields = ['id']


class CompanySerializer(serializers.ModelSerializer):
    parent_company_name = serializers.CharField(source='parent_company.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'company_code', 'company_type', 'parent_company', 'parent_company_name',
            'registration_number', 'tax_id', 'currency', 'currency_code',
            'address', 'phone', 'email', 'is_active', 'is_internal',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InterCompanyConfigSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    partner_company_name = serializers.CharField(source='partner_company.name', read_only=True)
    ar_account_name = serializers.CharField(source='ar_account.name', read_only=True)
    ap_account_name = serializers.CharField(source='ap_account.name', read_only=True)
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True)
    revenue_account_name = serializers.CharField(source='revenue_account.name', read_only=True)

    class Meta:
        model = InterCompanyConfig
        fields = [
            'id', 'company', 'company_name', 'partner_company', 'partner_company_name',
            'ar_account', 'ar_account_name', 'ap_account', 'ap_account_name',
            'expense_account', 'expense_account_name', 'revenue_account', 'revenue_account_name',
            'auto_post', 'auto_match', 'is_active',
        ]
        read_only_fields = ['id']


class InterCompanyInvoiceSerializer(serializers.ModelSerializer):
    from_company_name = serializers.CharField(source='from_company.name', read_only=True)
    to_company_name = serializers.CharField(source='to_company.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = InterCompanyInvoice
        fields = [
            'id', 'invoice_number', 'from_company', 'from_company_name', 'to_company', 'to_company_name',
            'invoice_date', 'due_date', 'total_amount', 'currency', 'currency_code',
            'status', 'description', 'auto_posted', 'linked_journal',
            'created_at', 'created_by', 'created_by_name',
        ]
        read_only_fields = ['id', 'created_at']


class InterCompanyTransferSerializer(serializers.ModelSerializer):
    from_company_name = serializers.CharField(source='from_company.name', read_only=True)
    to_company_name = serializers.CharField(source='to_company.name', read_only=True)

    class Meta:
        model = InterCompanyTransfer
        fields = [
            'id', 'transfer_number', 'from_company', 'from_company_name',
            'to_company', 'to_company_name', 'transfer_date',
            'items', 'total_value', 'status', 'auto_posted', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class InterCompanyAllocationSerializer(serializers.ModelSerializer):
    source_company_name = serializers.CharField(source='source_company.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = InterCompanyAllocation
        fields = [
            'id', 'allocation_number', 'source_company', 'source_company_name',
            'allocation_date', 'total_amount', 'currency', 'currency_code',
            'allocation_method', 'allocations', 'status', 'auto_posted', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class InterCompanyCashTransferSerializer(serializers.ModelSerializer):
    from_company_name = serializers.CharField(source='from_company.name', read_only=True)
    to_company_name = serializers.CharField(source='to_company.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = InterCompanyCashTransfer
        fields = [
            'id', 'transfer_number', 'from_company', 'from_company_name',
            'to_company', 'to_company_name', 'transfer_date', 'amount',
            'currency', 'currency_code', 'exchange_rate', 'status',
            'auto_posted', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ConsolidationGroupSerializer(serializers.ModelSerializer):
    companies_list = serializers.SerializerMethodField()
    reporting_currency_code = serializers.CharField(source='reporting_currency.code', read_only=True)

    class Meta:
        model = ConsolidationGroup
        fields = [
            'id', 'name', 'companies', 'companies_list', 'consolidation_method',
            'reporting_currency', 'reporting_currency_code', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_companies_list(self, obj):
        return [{'id': c.id, 'name': c.name, 'code': c.company_code} for c in obj.companies.all()]


class ConsolidationRunSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='group.name', read_only=True)
    period_info = serializers.SerializerMethodField()
    run_by_name = serializers.CharField(source='run_by.username', read_only=True)

    class Meta:
        model = ConsolidationRun
        fields = [
            'id', 'group', 'group_name', 'period', 'period_info', 'run_date',
            'status', 'total_assets', 'total_liabilities', 'total_equity',
            'total_revenue', 'total_expenses', 'elimination_entries',
            'consolidated_data', 'error_message', 'run_by', 'run_by_name',
        ]
        read_only_fields = ['id']

    def get_period_info(self, obj):
        return f"FY{obj.period.fiscal_year} - P{obj.period.period_number}"


class FinancialReportTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialReportTemplate
        fields = [
            'id', 'name', 'report_type', 'description', 'is_active',
        ]
        read_only_fields = ['id']


class FinancialReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialReport
        fields = ['id', 'template', 'report_date', 'generated_by', 'data']
        read_only_fields = ['id']


class AccountingDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountingDocument
        fields = [
            'id', 'document_type', 'reference_number', 'document_date',
            'title', 'description', 'file', 'uploaded_by', 'uploaded_at',
        ]
        read_only_fields = ['id', 'uploaded_at']


class ConsolidationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consolidation
        fields = [
            'id', 'group', 'period', 'consolidation_date', 'status',
            'total_assets', 'total_liabilities', 'total_equity',
        ]
        read_only_fields = ['id']


class DeferredRevenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeferredRevenue
        fields = [
            'id', 'name', 'customer', 'initial_amount', 'start_date',
            'recognition_periods', 'recognized_amount', 'is_active',
        ]
        read_only_fields = ['id']


class DeferredExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeferredExpense
        fields = [
            'id', 'name', 'vendor', 'initial_amount', 'start_date',
            'recognition_periods', 'recognized_amount', 'is_active',
        ]
        read_only_fields = ['id']


class LeaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lease
        fields = [
            'id', 'lease_number', 'lessor', 'start_date', 'end_date',
            'lease_amount', 'payment_frequency', 'is_active',
        ]
        read_only_fields = ['id']


class LeasePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeasePayment
        fields = ['id', 'lease', 'payment_date', 'amount', 'is_paid']
        read_only_fields = ['id']


class TreasuryForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasuryForecast
        fields = [
            'id', 'forecast_date', 'projected_cash_inflow',
            'projected_cash_outflow', 'notes',
        ]
        read_only_fields = ['id']


class InvestmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Investment
        fields = [
            'id', 'investment_number', 'investment_type', 'amount',
            'purchase_date', 'maturity_date', 'expected_return', 'is_active',
        ]
        read_only_fields = ['id']


class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = [
            'id', 'loan_number', 'lender', 'principal_amount',
            'interest_rate', 'start_date', 'end_date', 'is_active',
        ]
        read_only_fields = ['id']


class LoanRepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanRepayment
        fields = [
            'id', 'loan', 'repayment_date', 'principal_amount',
            'interest_amount', 'is_paid',
        ]
        read_only_fields = ['id']


class ExchangeRateHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRateHistory
        fields = [
            'id', 'from_currency', 'to_currency', 'rate_date',
            'exchange_rate',
        ]
        read_only_fields = ['id']


class ForeignCurrencyRevaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ForeignCurrencyRevaluation
        fields = [
            'id', 'revaluation_date', 'currency', 'revalued_amount',
            'exchange_rate', 'gain_loss', 'is_posted',
        ]
        read_only_fields = ['id']


class FiscalPeriodSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.CharField(source='closed_by.username', read_only=True, allow_null=True)
    period_type_display = serializers.CharField(source='get_period_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = FiscalPeriod
        fields = [
            'id', 'fiscal_year', 'period_number', 'period_type', 'period_type_display',
            'start_date', 'end_date', 'is_closed', 'is_locked', 'status', 'status_display',
            'closed_by', 'closed_by_name', 'closed_date', 'closed_reason',
            'allow_journal_entry', 'allow_invoice', 'allow_payment',
            'allow_procurement', 'allow_inventory', 'allow_sales',
        ]
        read_only_fields = ['id']


class FiscalYearSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.CharField(source='closed_by.username', read_only=True, allow_null=True)
    period_type_display = serializers.CharField(source='get_period_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    periods_count = serializers.SerializerMethodField()
    open_periods_count = serializers.SerializerMethodField()
    closed_periods_count = serializers.SerializerMethodField()

    class Meta:
        model = FiscalYear
        fields = [
            'id', 'year', 'name', 'start_date', 'end_date', 'period_type', 'period_type_display',
            'status', 'status_display', 'is_active',
            'closed_by', 'closed_by_name', 'closed_date',
            'periods_count', 'open_periods_count', 'closed_periods_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_periods_count(self, obj):
        return obj.periods.count()

    def get_open_periods_count(self, obj):
        return obj.open_periods.count()

    def get_closed_periods_count(self, obj):
        return obj.closed_periods.count()


class PeriodAccessSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    granted_by_name = serializers.CharField(source='granted_by.username', read_only=True, allow_null=True)
    access_type_display = serializers.CharField(source='get_access_type_display', read_only=True)
    period_info = serializers.SerializerMethodField()

    class Meta:
        model = PeriodAccess
        fields = [
            'id', 'period', 'period_info', 'user', 'user_name',
            'access_type', 'access_type_display',
            'granted_by', 'granted_by_name', 'start_date', 'end_date',
            'reason', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_period_info(self, obj):
        return f"FY{obj.period.fiscal_year} - P{obj.period.period_number} ({obj.period.period_type})"


class PeriodCloseCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = PeriodCloseCheck
        fields = [
            'id', 'period', 'check_name', 'check_result', 'details',
            'checked_at',
        ]
        read_only_fields = ['id', 'checked_at']


class AssetClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetClass
        fields = [
            'id', 'name', 'code', 'default_life', 'depreciation_method',
        ]
        read_only_fields = ['id']


class AssetCategorySerializer(serializers.ModelSerializer):
    cost_account_display = serializers.SerializerMethodField()
    accumulated_depreciation_account_display = serializers.SerializerMethodField()
    depreciation_expense_account_display = serializers.SerializerMethodField()
    depreciation_method_display = serializers.CharField(
        source='get_depreciation_method_display', read_only=True,
    )
    residual_value_type_display = serializers.CharField(
        source='get_residual_value_type_display', read_only=True,
    )

    class Meta:
        model = AssetCategory
        fields = [
            'id', 'name', 'code', 'is_active',
            'cost_account', 'accumulated_depreciation_account',
            'depreciation_expense_account',
            'cost_account_display', 'accumulated_depreciation_account_display',
            'depreciation_expense_account_display',
            'depreciation_method', 'depreciation_method_display',
            'default_life_years',
            'residual_value_type', 'residual_value_type_display',
            'residual_value',
        ]
        read_only_fields = ['id']

    def _account_display(self, account):
        if account:
            return {'id': account.id, 'code': account.code, 'name': account.name}
        return None

    def get_cost_account_display(self, obj):
        return self._account_display(obj.cost_account)

    def get_accumulated_depreciation_account_display(self, obj):
        return self._account_display(obj.accumulated_depreciation_account)

    def get_depreciation_expense_account_display(self, obj):
        return self._account_display(obj.depreciation_expense_account)

    def validate_cost_account(self, value):
        if value is None:
            return value
        if value.account_type != 'Asset':
            raise serializers.ValidationError('Cost account must be an Asset type account.')
        if not value.is_reconciliation or value.reconciliation_type != 'asset_accounting':
            raise serializers.ValidationError(
                'Cost account must be a reconciliation account with type "Asset Accounting".'
            )
        return value

    def validate_accumulated_depreciation_account(self, value):
        if value is None:
            return value
        if value.account_type != 'Asset':
            raise serializers.ValidationError(
                'Accumulated depreciation account must be an Asset type account.'
            )
        return value

    def validate_depreciation_expense_account(self, value):
        if value is None:
            return value
        if value.account_type != 'Expense':
            raise serializers.ValidationError(
                'Depreciation expense account must be an Expense type account.'
            )
        return value

    def validate_residual_value(self, value):
        if value < 0:
            raise serializers.ValidationError('Residual value cannot be negative.')
        return value

    def validate(self, attrs):
        rv_type = attrs.get(
            'residual_value_type',
            getattr(self.instance, 'residual_value_type', 'percentage'),
        )
        rv = attrs.get('residual_value', getattr(self.instance, 'residual_value', 0))
        if rv_type == 'percentage' and rv > 100:
            raise serializers.ValidationError({
                'residual_value': 'Percentage residual value cannot exceed 100.',
            })
        return attrs


class AssetConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetConfiguration
        fields = [
            'id', 'name', 'default_useful_life', 'default_depreciation_method',
        ]
        read_only_fields = ['id']


class AssetLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetLocation
        fields = ['id', 'name', 'code', 'is_active']
        read_only_fields = ['id']


class AssetInsuranceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetInsurance
        fields = [
            'id', 'asset', 'provider', 'policy_number', 'start_date',
            'end_date', 'premium_amount', 'is_active',
        ]
        read_only_fields = ['id']


class AssetMaintenanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetMaintenance
        fields = [
            'id', 'asset', 'maintenance_type', 'scheduled_date',
            'completed_date', 'cost', 'description',
        ]
        read_only_fields = ['id']


class AssetTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetTransfer
        fields = [
            'id', 'asset', 'from_location', 'to_location',
            'transfer_date', 'transferred_by',
        ]
        read_only_fields = ['id']


class AssetDepreciationScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetDepreciationSchedule
        fields = [
            'id', 'asset', 'period_date', 'depreciation_amount', 'is_posted',
        ]
        read_only_fields = ['id']


class AssetRevaluationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetRevaluationRun
        fields = [
            'id', 'revaluation_number', 'revaluation_date', 'revaluation_method',
            'valuator_name', 'valuator_qualification', 'valuation_report_reference',
            'fiscal_period', 'total_cost_adjustment', 'total_accum_depr_adjustment',
            'total_revaluation_surplus', 'total_revaluation_loss', 'status',
            'revaluation_gain_account', 'revaluation_loss_account', 'revaluation_surplus_account',
            'notes', 'created_by', 'created_at', 'approved_by', 'approved_at', 'journal_id',
        ]
        read_only_fields = ['id', 'created_at']


class AssetRevaluationDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetRevaluationDetail
        fields = [
            'id', 'revaluation', 'asset', 'asset_code', 'asset_name',
            'cost_before', 'accum_depr_before', 'nbv_before',
            'cost_after', 'accum_depr_after', 'nbv_after',
            'cost_adjustment', 'accum_depr_adjustment', 'revaluation_surplus',
            'revaluation_loss',
        ]
        read_only_fields = ['id']


class AssetDisposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetDisposal
        fields = [
            'id', 'disposal_number', 'asset', 'disposal_date', 'disposal_reason',
            'disposal_method', 'buyer_name', 'buyer_address',
            'sale_proceeds', 'disposal_costs', 'net_proceeds',
            'acquisition_cost', 'accum_depreciation', 'net_book_value',
            'gain_on_disposal', 'loss_on_disposal', 'status',
            'gain_account', 'loss_account',
            'created_by', 'created_at', 'approved_by', 'approved_at', 'journal_id', 'fiscal_period',
        ]
        read_only_fields = ['id', 'created_at']


class AssetImpairmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetImpairment
        fields = [
            'id', 'asset', 'impairment_date', 'impairment_amount',
            'reason', 'documented_by',
        ]
        read_only_fields = ['id']


class JournalReversalSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalReversal
        fields = [
            'id', 'original_journal', 'reversal_journal', 'reversal_type',
            'reason', 'reversed_by', 'gl_balances_reversed',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


# ===================== Advanced Accounting Serializers =====================

class RecurringJournalLineSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)

    class Meta:
        model = RecurringJournalLine
        fields = ['id', 'recurring_journal', 'account', 'account_name', 'account_code',
                  'description', 'debit', 'credit']
        read_only_fields = ['id']


class RecurringJournalSerializer(serializers.ModelSerializer):
    lines = RecurringJournalLineSerializer(many=True, read_only=True)
    fund_name = serializers.CharField(source='fund.name', read_only=True)
    function_name = serializers.CharField(source='function.name', read_only=True)
    program_name = serializers.CharField(source='program.name', read_only=True)
    geo_name = serializers.CharField(source='geo.name', read_only=True)

    class Meta:
        model = RecurringJournal
        fields = ['id', 'name', 'code', 'description', 'frequency', 'start_date',
                  'start_type', 'scheduled_posting_date', 'end_date', 'next_run_date', 
                  'is_active', 'auto_post', 
                  'use_month_end_default', 'auto_reverse_on_month_start', 'code_prefix',
                  'fund', 'fund_name', 'function', 'function_name',
                  'program', 'program_name', 'geo', 'geo_name', 'lines',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'code']


class RecurringJournalRunSerializer(serializers.ModelSerializer):
    journal_number = serializers.CharField(source='journal.journal_number', read_only=True)

    class Meta:
        model = RecurringJournalRun
        fields = ['id', 'recurring_journal', 'journal', 'journal_number',
                  'run_date', 'status', 'error_message']
        read_only_fields = ['id']


class AccrualSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    counterpart_name = serializers.CharField(source='counterpart_account.name', read_only=True)
    counterpart_code = serializers.CharField(source='counterpart_account.code', read_only=True)
    period_name = serializers.SerializerMethodField()
    journal_number = serializers.CharField(source='journal_entry.reference_number', read_only=True)
    reversal_journal_number = serializers.CharField(source='reversal_journal.reference_number', read_only=True)
    recurring_journal_name = serializers.CharField(source='recurring_journal.name', read_only=True)

    class Meta:
        model = Accrual
        fields = ['id', 'name', 'code', 'accrual_type', 'account', 'account_name', 'account_code',
                  'counterpart_account', 'counterpart_name', 'counterpart_code', 'amount', 'period', 'period_name',
                  'description', 'source_document', 
                  'posting_date', 'reversal_date',
                  'is_reversed', 'reversal_journal', 'reversal_journal_number', 
                  'auto_reverse', 'auto_reverse_on_month_start', 'use_default_dates',
                  'is_posted', 'journal_entry', 'journal_number',
                  'recurring_journal', 'recurring_journal_name',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'code']
    
    def get_period_name(self, obj):
        if not obj.period:
            return ''
        return f"FY{obj.period.fiscal_year} - {obj.period.get_period_type_display()} {obj.period.period_number}"


class DeferralRecognitionSerializer(serializers.ModelSerializer):
    period_name = serializers.SerializerMethodField()
    journal_number = serializers.CharField(source='journal_entry.reference_number', read_only=True)

    class Meta:
        model = DeferralRecognition
        fields = ['id', 'deferral', 'period', 'period_name', 'recognition_date',
                  'amount', 'journal_entry', 'journal_number', 'is_posted']
        read_only_fields = ['id']
    
    def get_period_name(self, obj):
        if not obj.period:
            return ''
        return f"FY{obj.period.fiscal_year} - {obj.period.get_period_type_display()} {obj.period.period_number}"


class DeferralSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    counterpart_name = serializers.CharField(source='counterpart_account.name', read_only=True)
    counterpart_code = serializers.CharField(source='counterpart_account.code', read_only=True)
    recognitions = DeferralRecognitionSerializer(many=True, read_only=True)
    recurring_journal_name = serializers.CharField(source='recurring_journal.name', read_only=True)

    class Meta:
        model = Deferral
        fields = ['id', 'name', 'code', 'deferral_type', 
                  'account', 'account_name', 'account_code',
                  'counterpart_account', 'counterpart_name', 'counterpart_code',
                  'original_amount', 'remaining_amount', 'recognition_amount', 
                  'start_date', 'recognition_periods', 'current_period',
                  'auto_recognize', 'auto_recognize_on_month_start',
                  'description', 'source_document', 
                  'is_active', 'is_fully_recognized', 
                  'recurring_journal', 'recurring_journal_name',
                  'recognitions',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'code']


class PeriodStatusSerializer(serializers.ModelSerializer):
    period_name = serializers.CharField(source='period.start_date', read_only=True)
    closed_by_name = serializers.CharField(source='closed_by.username', read_only=True)

    class Meta:
        model = PeriodStatus
        fields = ['id', 'period', 'period_name', 'status', 'closed_by', 'closed_by_name',
                  'closed_date', 'lock_reason', 'allow_journal_entry',
                  'allow_invoice', 'allow_payment',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class YearEndClosingSerializer(serializers.ModelSerializer):
    closing_journal_number = serializers.CharField(source='closing_journal.journal_number', read_only=True)
    opening_journal_number = serializers.CharField(source='opening_journal.journal_number', read_only=True)
    closed_by_name = serializers.CharField(source='closed_by.username', read_only=True)

    class Meta:
        model = YearEndClosing
        fields = ['id', 'fiscal_year', 'closing_date', 'status',
                  'income_summary_debit', 'income_summary_credit', 'net_income',
                  'retained_earnings_debit', 'retained_earnings_credit',
                  'closing_journal', 'closing_journal_number',
                  'opening_journal', 'opening_journal_number',
                  'closed_by', 'closed_by_name', 'closed_date', 'notes',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class CurrencyRevaluationSerializer(serializers.ModelSerializer):
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    currency_name = serializers.CharField(source='currency.name', read_only=True)
    journal_number = serializers.CharField(source='journal_entry.journal_number', read_only=True)

    class Meta:
        model = CurrencyRevaluation
        fields = ['id', 'revaluation_date', 'currency', 'currency_code', 'currency_name',
                  'exchange_rate', 'total_assets', 'total_liabilities',
                  'unrealized_gain', 'unrealized_loss', 'status',
                  'journal_entry', 'journal_number',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class RetainedEarningsSerializer(serializers.ModelSerializer):
    journal_number = serializers.CharField(source='closing_journal.journal_number', read_only=True)

    class Meta:
        model = RetainedEarnings
        fields = ['id', 'fiscal_year', 'beginning_balance', 'net_income',
                  'dividends', 'ending_balance', 'closing_journal', 'journal_number',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class AccountingSettingsSerializer(serializers.ModelSerializer):
    default_currency_1_detail = CurrencySerializer(source='default_currency_1', read_only=True)
    default_currency_2_detail = CurrencySerializer(source='default_currency_2', read_only=True)
    default_currency_3_detail = CurrencySerializer(source='default_currency_3', read_only=True)
    default_currency_4_detail = CurrencySerializer(source='default_currency_4', read_only=True)

    class Meta:
        model = AccountingSettings
        fields = [
            'id', 'account_code_digits', 'is_digit_enforcement_active',
            'account_number_series',
            'default_currency_1', 'default_currency_2',
            'default_currency_3', 'default_currency_4',
            'default_currency_1_detail', 'default_currency_2_detail',
            'default_currency_3_detail', 'default_currency_4_detail',
            'enable_sales_downpayment', 'downpayment_default_type',
            'downpayment_default_value', 'downpayment_gl_account',
        ]
        read_only_fields = ['id']

    def validate_account_number_series(self, value):
        """Validate that number series maps prefixes to valid account types."""
        valid_types = {'Asset', 'Liability', 'Equity', 'Income', 'Expense'}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Number series must be a JSON object mapping prefixes to account types.")
        for prefix, acct_type in value.items():
            if not isinstance(prefix, str) or not prefix.isdigit():
                raise serializers.ValidationError(f"Prefix '{prefix}' must be a numeric string.")
            if acct_type not in valid_types:
                raise serializers.ValidationError(
                    f"Account type '{acct_type}' for prefix '{prefix}' is not valid. "
                    f"Must be one of: {', '.join(sorted(valid_types))}"
                )
        return value


# ===================== Workflow Serializers =====================

from .models import (
    CreditNote, DebitNote,
    BadDebtProvision, BadDebtWriteOff,
    PettyCashFund, PettyCashVoucher, PettyCashReplenishment,
    ChequeRegister, SuspenseClearing,
)


class CreditNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditNote
        fields = [
            'id', 'credit_note_number', 'customer', 'customer_name',
            'original_invoice', 'original_invoice_number',
            'credit_note_date', 'reason', 'reason_type',
            'subtotal', 'tax_amount', 'total_amount',
            'status', 'applied_amount', 'applied_invoices',
            'created_by', 'created_at', 'journal_id', 'currency_code',
        ]
        read_only_fields = ['id', 'created_at', 'journal_id']


class DebitNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebitNote
        fields = [
            'id', 'debit_note_number', 'vendor', 'vendor_name',
            'original_invoice', 'original_invoice_number',
            'debit_note_date', 'reason', 'reason_type',
            'subtotal', 'tax_amount', 'total_amount',
            'status', 'applied_amount', 'applied_invoices',
            'created_by', 'created_at', 'journal_id', 'currency_code',
        ]
        read_only_fields = ['id', 'created_at', 'journal_id']


class BadDebtProvisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BadDebtProvision
        fields = [
            'id', 'provision_date', 'fiscal_year', 'period',
            'provision_type', 'opening_provision', 'new_provisions',
            'write_offs', 'recoveries', 'closing_provision',
            'provisioning_method', 'status',
            'created_by', 'created_at', 'approved_by', 'approved_at',
            'journal_id', 'fiscal_period',
        ]
        read_only_fields = ['id', 'created_at', 'journal_id']


class BadDebtWriteOffSerializer(serializers.ModelSerializer):
    class Meta:
        model = BadDebtWriteOff
        fields = [
            'id', 'write_off_number', 'customer', 'customer_name',
            'original_invoice', 'original_invoice_number',
            'write_off_date', 'invoice_date', 'invoice_amount',
            'amount_paid', 'amount_written_off', 'reason',
            'age_at_write_off', 'days_overdue', 'status',
            'provision_reference', 'created_by', 'created_at',
            'approved_by', 'approved_at', 'journal_id',
            'recovered_amount', 'recovered_date',
        ]
        read_only_fields = ['id', 'created_at', 'journal_id']


class PettyCashFundSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source='bank_account.name', read_only=True, default='')
    bank_account_number = serializers.CharField(source='bank_account.account_number', read_only=True, default='')
    gl_account_code = serializers.CharField(source='bank_account.gl_account.code', read_only=True, default='')
    gl_account_name = serializers.CharField(source='bank_account.gl_account.name', read_only=True, default='')
    gl_account_id = serializers.IntegerField(source='bank_account.gl_account.id', read_only=True, default=None)

    class Meta:
        model = PettyCashFund
        fields = [
            'id', 'name', 'code', 'bank_account',
            'bank_account_name', 'bank_account_number',
            'gl_account_id', 'gl_account_code', 'gl_account_name',
            'float_amount', 'current_balance',
            'custodian', 'is_active', 'minimum_balance',
        ]
        read_only_fields = ['id', 'bank_account_name', 'bank_account_number',
                            'gl_account_id', 'gl_account_code', 'gl_account_name']


class PettyCashVoucherSerializer(serializers.ModelSerializer):
    class Meta:
        model = PettyCashVoucher
        fields = [
            'id', 'voucher_number', 'petty_cash_fund',
            'voucher_date', 'payee', 'description', 'amount',
            'account', 'cost_center', 'approval_status',
            'approved_by', 'approved_at', 'created_by', 'created_at',
            'receipt_attached', 'journal_id',
        ]
        read_only_fields = ['id', 'created_at', 'journal_id']


class PettyCashReplenishmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PettyCashReplenishment
        fields = [
            'id', 'replenishment_number', 'petty_cash_fund',
            'replenishment_date', 'vouchers_total', 'reimbursement_amount',
            'bank_account', 'vouchers', 'status',
            'created_by', 'created_at', 'journal_id',
        ]
        read_only_fields = ['id', 'created_at', 'journal_id']


class ChequeRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChequeRegister
        fields = [
            'id', 'cheque_number', 'bank_account', 'cheque_type',
            'payee', 'amount', 'issue_date', 'presentation_date', 'expiry_date',
            'reference_document', 'status',
            'issued_by', 'presented_by', 'presented_at',
            'bounce_reason', 'stop_reason', 'journal_id',
        ]
        read_only_fields = ['id', 'journal_id']


class SuspenseClearingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuspenseClearing
        fields = [
            'id', 'clearing_number', 'journal_header',
            'suspense_account', 'clearing_account',
            'clearing_date', 'suspense_amount', 'cleared_amount', 'balance',
            'description', 'status', 'created_by', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
