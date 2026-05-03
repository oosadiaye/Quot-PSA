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
    FinancialReportTemplate, FinancialReport, AccountingDocument, DeferredRevenue, DeferredExpense, Lease, LeasePayment,
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

    # Read-only convenience labels for the Asset Category linkage so the
    # frontend list view can show "32100100 — Land" without resolving the FK.
    asset_category_code = serializers.CharField(
        source='asset_category.code', read_only=True, default='',
    )
    asset_category_name = serializers.CharField(
        source='asset_category.name', read_only=True, default='',
    )

    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'account_type', 'is_active',
            'is_reconciliation', 'reconciliation_type', 'reconciliation_type_display',
            'current_balance',
            # Phase 1 asset auto-capitalisation linkage. Both fields are
            # writable so the COA Add/Edit form can configure them; the
            # ``*_code``/``*_name`` companions are read-only display helpers.
            'auto_create_asset', 'asset_category',
            'asset_category_code', 'asset_category_name',
        ]
        read_only_fields = ['id', 'current_balance', 'asset_category_code', 'asset_category_name']

    def validate(self, attrs):
        # Mirror the model's clean(): cannot enable auto-create without a
        # category. Surface as a per-field error so the form highlights the
        # right input.
        merged_auto = attrs.get('auto_create_asset',
                                getattr(self.instance, 'auto_create_asset', False))
        merged_cat = attrs.get('asset_category',
                               getattr(self.instance, 'asset_category', None))
        if merged_auto and not merged_cat:
            raise serializers.ValidationError({
                'asset_category':
                    'An Asset Category is required when "Auto-create asset on debit" is enabled.'
            })
        return attrs

    # ── Nigeria Chart of Accounts number-series map ─────────────────
    # Hard-coded here (was previously read from AccountingSettings)
    # because Nigeria COA compliance mandates a fixed mapping —
    # tenants are NOT supposed to customise these prefixes. Equity
    # has no enforced prefix and can use any first digit.
    #
    #   1xxxxxxx → Revenue (stored as 'Income' in Account.account_type)
    #   2xxxxxxx → Expense
    #   3xxxxxxx → Asset
    #   4xxxxxxx → Liability
    #
    # The Account model still stores 'Income' (not 'Revenue') because
    # that's the choice value on the field; UI labels can say Revenue.
    NIGERIA_COA_SERIES = {
        '1': 'Income',     # Revenue
        '2': 'Expense',
        '3': 'Asset',
        '4': 'Liability',
    }

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

        # ── Code validation (two independent checks) ───────────────
        if code and account_type:
            # (1) Digit-count enforcement — tenant-configurable via
            #     AccountingSettings.is_digit_enforcement_active. Does
            #     NOT validate series; that's step 2 below.
            from accounting.models import AccountingSettings
            settings_obj = AccountingSettings.objects.first()
            if settings_obj and settings_obj.is_digit_enforcement_active:
                digit_errors = []
                if not code.isdigit():
                    digit_errors.append(
                        'Account code must contain only digits when digit '
                        'enforcement is active.'
                    )
                if len(code) != settings_obj.account_code_digits:
                    digit_errors.append(
                        f'Account code must be exactly '
                        f'{settings_obj.account_code_digits} digits '
                        f'(got {len(code)}).'
                    )
                if digit_errors:
                    raise serializers.ValidationError({'code': digit_errors})

            # (2) Nigeria COA series enforcement — HARDCODED, not
            #     tenant-configurable. The first digit of the code
            #     dictates the account type per Nigerian CoA standards.
            first_digit = code[0] if code else ''
            expected_type = self.NIGERIA_COA_SERIES.get(first_digit)
            if expected_type and expected_type != account_type:
                # Show "Revenue" in the user-facing message even though
                # the internal choice value is 'Income'.
                expected_label = 'Revenue' if expected_type == 'Income' else expected_type
                actual_label = 'Revenue' if account_type == 'Income' else account_type
                raise serializers.ValidationError({'code': [
                    f"Nigeria CoA violation: account code '{code}' "
                    f"starts with '{first_digit}' — that prefix is reserved "
                    f"for {expected_label} accounts, but the selected "
                    f"account type is {actual_label}. Either change the "
                    f"code's first digit or pick the matching account type."
                ]})

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
        if dims_enabled:
            # ── PSA Budget Control (MANDATORY) ──────────────────
            # Administrative (MDA) + Fund are required for budget
            # validation — Appropriation lookup needs admin + economic + fund
            for field in ['mda', 'fund']:
                self.fields[field].required = True
                self.fields[field].allow_null = False

            # ── Reporting Dimensions (MANDATORY for IPSAS reports) ──
            # Function, Programme, Geographic are required on all
            # transactions for government performance reporting but
            # do NOT gate budget approval (only MDA + Account + Fund do)
            for field in ['function', 'program', 'geo']:
                self.fields[field].required = True
                self.fields[field].allow_null = False
        else:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                self.fields[field].required = False
                self.fields[field].allow_null = True


class JournalLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalLine
        fields = ['id', 'header', 'account', 'debit', 'credit', 'memo', 'document_number', 'asset']
        read_only_fields = ['id', 'document_number']


class JournalLineDetailSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True, default='')
    account_name = serializers.CharField(source='account.name', read_only=True, default='')
    asset_number = serializers.CharField(source='asset.asset_number', read_only=True, default='')
    asset_name = serializers.CharField(source='asset.name', read_only=True, default='')

    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'account_code', 'account_name', 'debit', 'credit', 'memo', 'document_number',
                  'asset', 'asset_number', 'asset_name']
        read_only_fields = ['id', 'document_number', 'asset_number', 'asset_name']


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

    # Read-only denormalisations the AP list UI needs. Without these the
    # frontend reads undefined and falls back to zero (balance_due) or
    # blank (vendor_name) — which is why the list was showing ₦0.00
    # across every row and an empty Vendor column.
    vendor_name    = serializers.CharField(source='vendor.name', read_only=True)
    balance_due    = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    currency_code  = serializers.CharField(source='currency.code', read_only=True, allow_null=True)
    mda_name       = serializers.CharField(source='mda.name', read_only=True, allow_null=True)
    account_code   = serializers.CharField(source='account.code', read_only=True, allow_null=True)
    account_name   = serializers.CharField(source='account.name', read_only=True, allow_null=True)
    fund_name      = serializers.CharField(source='fund.name', read_only=True, allow_null=True)

    class Meta:
        model = VendorInvoice
        fields = [
            'id', 'invoice_number', 'reference', 'description',
            'vendor', 'vendor_name',
            'invoice_date', 'due_date',
            'purchase_order', 'account', 'account_code', 'account_name',
            'mda', 'mda_name', 'fund', 'fund_name',
            'function', 'program', 'geo',
            'subtotal', 'tax_amount', 'total_amount',
            'paid_amount', 'balance_due',
            'currency', 'currency_code',
            'status', 'journal_entry', 'attachment',
            'document_number', 'document_type', 'lines',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = [
            'id', 'invoice_number', 'balance_due',
            'created_at', 'updated_at', 'created_by', 'updated_by', 'document_number',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dims_enabled = is_dimensions_enabled(self.context)
        if dims_enabled:
            # Budget control pillars (MDA + Fund) — required
            for field in ['mda', 'fund']:
                self.fields[field].required = True
                self.fields[field].allow_null = False
            # Reporting dimensions — required for IPSAS reports, not for budget gating
            for field in ['function', 'program', 'geo']:
                self.fields[field].required = True
                self.fields[field].allow_null = False
        else:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                self.fields[field].required = False
                self.fields[field].allow_null = True

    def validate(self, data):
        """Three-pillar budget validation at the SERIALIZER level.

        Fires at create (Draft save) AND at update — blocks the record from
        ever being persisted if the (MDA + Economic Code + Fund) triple
        doesn't map to an active appropriation, or if the amount would
        exceed the remaining appropriation / warrant balance.

        This closes the loophole where a verifier could save a Draft
        invoice for a wrong/non-existent budget line and only discover
        the mismatch at posting time (by which point the data-entry
        context is lost).

        The appropriation ceiling check re-runs at posting too (defense
        in depth) — running it here makes errors appear earlier in the
        flow, with the exact fields highlighted.
        """
        data = super().validate(data)

        # Resolve pillars from request payload, falling back to the
        # existing instance on PATCH/PUT.
        mda = data.get('mda', getattr(self.instance, 'mda', None))
        fund = data.get('fund', getattr(self.instance, 'fund', None))
        account = data.get('account', getattr(self.instance, 'account', None))
        # Header account may be empty if user filled in per-line accounts;
        # fall back to the first line's account for validation purposes.
        if not account:
            lines_data = data.get('lines', [])
            if lines_data:
                first_line_account = lines_data[0].get('account') if isinstance(lines_data[0], dict) else None
                if first_line_account:
                    account = first_line_account
            elif self.instance and hasattr(self.instance, 'lines'):
                first_line = self.instance.lines.select_related('account').first()
                if first_line:
                    account = first_line.account

        amount = data.get('total_amount', getattr(self.instance, 'total_amount', None))

        # If the tenant doesn't have dimensions enabled OR the request
        # lacks any of the three pillars, skip gating and let the model
        # save proceed (legacy path).
        if not (is_dimensions_enabled(self.context) and mda and fund and account and amount):
            return data

        # Resolve the three pillars to NCoA segments so we can match
        # the Appropriation. Parent-walk the economic segment so a leaf
        # account (e.g. 23100100) validates against a parent
        # appropriation (e.g. 23000000).
        from accounting.models.ncoa import (
            AdministrativeSegment, EconomicSegment, FundSegment,
        )
        from accounting.models.advanced import FiscalYear
        from budget.models import Appropriation
        from decimal import Decimal as _D

        admin_seg = AdministrativeSegment.objects.filter(legacy_mda=mda).first()
        econ_seg  = EconomicSegment.objects.filter(legacy_account=account).first()
        fund_seg  = FundSegment.objects.filter(legacy_fund=fund).first()
        active_fy = FiscalYear.objects.filter(is_active=True).first()

        # If ANY of the three pillars can't be resolved, we have a
        # mapping gap — tell the user exactly which pillar failed.
        missing = []
        if not admin_seg:  missing.append('MDA')
        if not econ_seg:   missing.append('Economic Code')
        if not fund_seg:   missing.append('Fund')
        if not active_fy:  missing.append('Active Fiscal Year')
        if missing:
            raise serializers.ValidationError({
                'budget': (
                    f"Budget dimension mapping missing: {', '.join(missing)}. "
                    f"This invoice cannot be saved because one of the three "
                    f"budget pillars (MDA, Economic Code, Fund) has no NCoA "
                    f"bridge, or no active Fiscal Year is configured. Contact "
                    f"the Budget Office."
                ),
                'missing_dimensions': missing,
            })

        # Find the active Appropriation for this triple. Walk the
        # economic parent chain — a leaf-coded transaction may be
        # legally authorised against a parent appropriation.
        econ_candidates = [econ_seg]
        cursor = econ_seg.parent
        while cursor is not None:
            econ_candidates.append(cursor)
            cursor = cursor.parent

        appro = Appropriation.objects.filter(
            administrative=admin_seg,
            economic__in=econ_candidates,
            fund=fund_seg,
            fiscal_year=active_fy,
            status__iexact='ACTIVE',
        ).first()

        if not appro:
            raise serializers.ValidationError({
                'budget': (
                    f"No active appropriation found for the selected "
                    f"combination: MDA {admin_seg.code} — "
                    f"Economic Code {econ_seg.code} — Fund {fund_seg.code}. "
                    f"Either the budget line was never appropriated, or you "
                    f"picked the wrong MDA/Code/Fund for this invoice. "
                    f"Verify with the Budget Office."
                ),
                'no_appropriation': True,
                'dimensions': {
                    'mda': admin_seg.code,
                    'economic': econ_seg.code,
                    'fund': fund_seg.code,
                },
            })

        # Check amount against appropriation available balance. Exclude
        # this instance's previous total_amount on update so we don't
        # double-count when the user is just editing an existing Draft.
        try:
            requested = _D(str(amount))
        except (ArithmeticError, ValueError, TypeError):
            return data  # non-numeric amount — another validator will flag it

        available = appro.available_balance or _D('0')
        # Add-back: if we're updating an existing Posted/Approved invoice,
        # its current amount is already in total_expended — reverse that
        # so we check only the delta.
        if self.instance and self.instance.status == 'Posted':
            # Posted records are already consumed in available_balance —
            # if the user is somehow editing (shouldn't happen due to
            # ImmutableModelMixin), allow up to the existing + remaining.
            available += (self.instance.total_amount or _D('0'))

        if requested > available:
            deficit = requested - available
            raise serializers.ValidationError({
                'budget': (
                    f"Insufficient appropriation balance for "
                    f"{admin_seg.name} — {econ_seg.name} — Fund "
                    f"{fund_seg.code}.\n"
                    f"  Requested:  NGN {requested:>15,.2f}\n"
                    f"  Available:  NGN {available:>15,.2f}\n"
                    f"  Deficit:    NGN {deficit:>15,.2f}\n"
                    f"A Supplementary Appropriation or Virement is "
                    f"required to post this invoice."
                ),
                'appropriation_exceeded': True,
                'appropriation_id': appro.pk,
                'requested': str(requested),
                'available': str(available),
                'deficit': str(deficit),
            })

        return data

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
    # Read-only denormalisations that help the Outgoing Payment list show
    # "Payment #123 (PV-2026-0004)" without an extra lookup.
    payment_voucher_number = serializers.CharField(source='payment_voucher.voucher_number', read_only=True, default='')

    class Meta:
        model = Payment
        fields = [
            'id', 'payment_number', 'payment_date', 'payment_method',
            'reference_number', 'total_amount', 'currency', 'currency_code',
            'status', 'journal_entry', 'bank_account', 'bank_account_name',
            'vendor', 'vendor_name', 'is_advance', 'advance_type', 'advance_remaining',
            'payment_voucher', 'payment_voucher_number',
            'document_number', 'is_reconciled', 'bank_reconciliation',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'document_number', 'is_reconciled', 'bank_reconciliation']

    def validate(self, attrs):
        """Enforce `require_pv_before_payment` gate.

        When the tenant's AccountingSettings has
        ``require_pv_before_payment=True``, every Payment must reference
        a PaymentVoucherGov via ``payment_voucher``. Otherwise the
        field stays optional and direct vendor-invoice payments are
        allowed. Check only on CREATE (not every update) so an existing
        Payment doesn't suddenly become invalid when the flag is toggled
        — retro-enforcement would break in-flight workflows.
        """
        attrs = super().validate(attrs)
        if self.instance is None:  # create path only
            from accounting.models import AccountingSettings
            acct_settings = AccountingSettings.objects.first()
            if acct_settings and acct_settings.require_pv_before_payment:
                pv = attrs.get('payment_voucher')
                if not pv:
                    raise serializers.ValidationError({
                        'payment_voucher': (
                            'Payment Voucher (PV) is required before an outgoing '
                            'payment can be created. The MDA has enabled the '
                            'PV-before-Payment workflow in Accounting Settings — '
                            'raise a PV first, then post the payment against it. '
                            'To allow direct payments, disable '
                            '"Require PV before Payment" in Accounting Settings.'
                        ),
                        'require_pv_before_payment': True,
                    })
        return attrs


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
            'customer_name', 'customer_tin', 'invoice_date', 'due_date',
            'mda', 'fund', 'function', 'program', 'geo',
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
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = Receipt
        fields = [
            'id', 'receipt_number', 'receipt_date', 'payment_method',
            'reference_number', 'total_amount', 'currency', 'currency_code',
            'status', 'journal_entry', 'bank_account', 'bank_account_name',
            'customer_name', 'is_advance', 'advance_type', 'advance_remaining',
            'document_number', 'is_reconciled', 'bank_reconciliation',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'document_number', 'is_reconciled', 'bank_reconciliation']


class ReceiptAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptAllocation
        fields = ['id', 'receipt', 'invoice', 'amount']
        read_only_fields = ['id']


class FixedAssetSerializer(serializers.ModelSerializer):
    mda_name = serializers.CharField(source='mda.name', read_only=True, default='')
    net_book_value = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    # Auto-generated when blank (see FixedAsset._generate_asset_number).
    # Tagging-imports that carry legacy numbers can still pass one in.
    asset_number = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True,
        help_text='Leave blank to auto-generate FA-YYYY-NNNNN.',
    )

    class Meta:
        model = FixedAsset
        fields = [
            'id', 'asset_number', 'name', 'description', 'asset_category',
            'acquisition_date', 'acquisition_cost', 'salvage_value',
            'useful_life_years', 'depreciation_method', 'accumulated_depreciation',
            'asset_account', 'depreciation_expense_account',
            'accumulated_depreciation_account', 'mda', 'mda_name', 'fund', 'function',
            'program', 'geo', 'status', 'net_book_value',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'mda_name', 'net_book_value']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dims_enabled = is_dimensions_enabled(self.context)
        if dims_enabled:
            # PSA: MDA and Fund are MANDATORY for government assets
            # Every asset must belong to an MDA for budget control
            for field in ['mda', 'fund']:
                self.fields[field].required = True
                self.fields[field].allow_null = False

            # Reporting dimensions — required for IPSAS reports
            for field in ['function', 'program', 'geo']:
                self.fields[field].required = True
                self.fields[field].allow_null = False
        else:
            for field in ['mda', 'fund', 'function', 'program', 'geo']:
                self.fields[field].required = False
                self.fields[field].allow_null = True

    def validate(self, attrs):
        """Pre-flight budget check on the asset's dimension tuple.

        Runs the centralised ``check_policy`` engine against the
        economic code of the asset's GL account (or, if no explicit
        asset_account is set, the cost_account of the selected
        AssetCategory). The policy is decided by the
        ``BudgetCheckRule`` the tenant has configured for that GL
        range:

          * NONE    → allow silently
          * WARNING → allow + attach a soft warning to the serializer
          * STRICT  → refuse the save when no matching Appropriation
                      exists for (MDA, Economic, Fund, FiscalYear)

        The balance check runs later at AP invoice / PO invoice
        verification time — at creation we don't yet know the cost.
        """
        attrs = super().validate(attrs)

        # Resolve the three control dimensions + the economic account
        mda = attrs.get('mda') or (self.instance.mda if self.instance else None)
        fund = attrs.get('fund') or (self.instance.fund if self.instance else None)
        asset_account = (
            attrs.get('asset_account')
            or (self.instance.asset_account if self.instance else None)
        )

        # Fall back to the category's cost_account if the asset doesn't
        # have an explicit asset_account yet (the new form inherits
        # everything from the category).
        if asset_account is None:
            category_label = attrs.get('asset_category') or (
                self.instance.asset_category if self.instance else ''
            )
            if category_label:
                from accounting.models.assets import AssetCategory
                cat = AssetCategory.objects.filter(
                    is_active=True, code=category_label,
                ).first() or AssetCategory.objects.filter(
                    is_active=True, name=category_label,
                ).first()
                if cat and cat.cost_account_id:
                    asset_account = cat.cost_account

        # Without the three control pillars there's nothing to check.
        if not (mda and fund and asset_account):
            return attrs

        from accounting.services.budget_check_rules import (
            check_policy, find_matching_appropriation,
        )
        fiscal_year = (
            attrs.get('acquisition_date')
            or (self.instance.acquisition_date if self.instance else None)
            or __import__('datetime').date.today()
        ).year

        appropriation = find_matching_appropriation(
            mda=mda, fund=fund, account=asset_account,
            fiscal_year=fiscal_year,
        )
        result = check_policy(
            account_code=asset_account.code,
            appropriation=appropriation,
            requested_amount=None,  # cost not known at creation
            transaction_label='asset acquisition',
            account_name=asset_account.name,
        )
        if result.blocked:
            raise serializers.ValidationError({
                'non_field_errors': [result.reason],
                'code': 'BUDGET_STRICT_BLOCK',
                'mda_code': getattr(mda, 'code', None),
                'fund_code': getattr(fund, 'code', None),
                'economic_code': asset_account.code,
            })

        # Carry warnings through to the view so it can surface them
        # (WARNING-level rule with no appropriation → soft notice).
        self._bcr_warnings = list(result.warnings or [])
        return attrs


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
    gl_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(is_active=True),
        required=False, allow_null=True,
    )
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
            'id', 'tax_registration', 'entity_name', 'vendor',
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


# Intercompany & Consolidation serializers — REMOVED for public sector


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


class DeferredRevenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeferredRevenue
        fields = [
            'id', 'name', 'payer_name', 'initial_amount', 'start_date',
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
    from_currency_code = serializers.CharField(source='from_currency.code', read_only=True)
    to_currency_code = serializers.CharField(source='to_currency.code', read_only=True)

    class Meta:
        model = ExchangeRateHistory
        fields = [
            'id', 'from_currency', 'to_currency', 'rate_date',
            'rate_valid_from', 'rate_valid_to',
            'exchange_rate',
            'from_currency_code', 'to_currency_code',
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
            'id', 'asset', 'maintenance_type', 'status',
            'scheduled_date', 'completed_date',
            'labor_cost', 'parts_cost', 'external_cost', 'total_cost',
            'vendor', 'description',
        ]
        read_only_fields = ['id', 'total_cost']


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
    class Meta:
        model = YearEndClosing
        fields = ['id', 'fiscal_year', 'closing_date', 'status',
                  'revenue_total', 'expense_total', 'net_income',
                  'retained_earnings_before', 'retained_earnings_after',
                  'closing_journal_id', 'net_income_journal_id',
                  'next_fiscal_year', 'notes',
                  'created_by', 'created_at', 'approved_by', 'approved_at']
        read_only_fields = ['id', 'created_at', 'approved_at']


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
    default_currency_5_detail = CurrencySerializer(source='default_currency_5', read_only=True)

    class Meta:
        model = AccountingSettings
        fields = [
            'id', 'account_code_digits', 'is_digit_enforcement_active',
            'account_number_series',
            # Workflow flag: when True, outgoing Payments require a PV
            # reference. Read by the frontend Outgoing Payment form to
            # toggle the PV picker between optional and mandatory.
            'require_pv_before_payment',
            'default_currency_1', 'default_currency_2',
            'default_currency_3', 'default_currency_4',
            'default_currency_5',
            'default_currency_1_detail', 'default_currency_2_detail',
            'default_currency_3_detail', 'default_currency_4_detail',
            'default_currency_5_detail',
            'require_vendor_registration_invoice',
            # GL account credited when a vendor pays their registration
            # invoice. Lets the tenant choose whichever Income account on
            # their CoA represents registration revenue (no hardcoded
            # NCoA code in the posting path).
            'vendor_registration_revenue_account',
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
            'id', 'credit_note_number', 'customer_name',
            'original_invoice', 'original_invoice_number',
            'credit_note_date', 'reason', 'reason_type',
            'subtotal', 'tax_amount', 'total_amount',
            'status', 'applied_amount', 'applied_invoices',
            'created_by', 'created_at', 'journal_id', 'currency_code',
        ]
        read_only_fields = ['id', 'created_at', 'journal_id']

    def create(self, validated_data):
        if not validated_data.get('currency_code'):
            from accounting.utils import get_base_currency_code
            validated_data['currency_code'] = get_base_currency_code()
        return super().create(validated_data)


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

    def create(self, validated_data):
        if not validated_data.get('currency_code'):
            from accounting.utils import get_base_currency_code
            validated_data['currency_code'] = get_base_currency_code()
        return super().create(validated_data)


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
            'id', 'write_off_number', 'customer_name',
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


# ─────────────────────────────────────────────────────────────────
# BudgetCheckRule — tenant-configurable budget-check policy
# ─────────────────────────────────────────────────────────────────
from accounting.models.budget_check_rules import BudgetCheckRule


class BudgetCheckRuleSerializer(serializers.ModelSerializer):
    check_level_display = serializers.CharField(source='get_check_level_display', read_only=True)

    class Meta:
        model = BudgetCheckRule
        fields = [
            'id',
            'gl_from', 'gl_to',
            'check_level', 'check_level_display',
            'warning_threshold_pct',
            'description', 'priority', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        gl_from = attrs.get('gl_from') or (self.instance.gl_from if self.instance else None)
        gl_to = attrs.get('gl_to') or (self.instance.gl_to if self.instance else None)
        if gl_from and gl_to and gl_from > gl_to:
            raise serializers.ValidationError(
                {'gl_to': f'"{gl_to}" must be >= "gl_from" ("{gl_from}"). Check the range.'}
            )
        level = attrs.get('check_level') or (self.instance.check_level if self.instance else None)
        thr = attrs.get('warning_threshold_pct')
        if thr is not None and (thr < 0 or thr > 100):
            raise serializers.ValidationError(
                {'warning_threshold_pct': 'Must be between 0 and 100.'}
            )
        # Only WARNING level uses the threshold — silently pin to default
        # for NONE/STRICT so the DB doesn't carry stale values.
        if level in ('NONE', 'STRICT') and thr is None:
            attrs['warning_threshold_pct'] = 80
        return attrs
