from django.contrib import admin
from .admin_ncoa import *  # noqa — imports all NCoA admin classes
from .admin_treasury import *  # noqa — imports Treasury/Revenue admin classes
from .models import (
    Fund, Function, Program, Geo, Account, MDA,
    JournalHeader, JournalLine, Currency,
    VendorInvoice, Payment, PaymentAllocation,
    CustomerInvoice, Receipt, ReceiptAllocation,
    FixedAsset, DepreciationSchedule, GLBalance,
    Budget, BudgetPeriod, BudgetEncumbrance,
    BankAccount, BankReconciliation,
    CostCenter, ProfitCenter,
    TaxCode, WithholdingTax, TaxReturn, TaxRegistration,
    RecurringJournal, Accrual, Deferral,
    FiscalPeriod, FiscalYear,
    AssetCategory, AssetClass,
    AccountingSettings,
    ExchangeRateHistory,
)

@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'description']
    search_fields = ['code', 'name']

@admin.register(Function)
class FunctionAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'description']
    search_fields = ['code', 'name']

@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'description']
    search_fields = ['code', 'name']

@admin.register(Geo)
class GeoAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'description']
    search_fields = ['code', 'name']

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'account_type', 'is_active']
    list_filter = ['account_type', 'is_active']
    search_fields = ['code', 'name']

class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 1

@admin.register(JournalHeader)
class JournalHeaderAdmin(admin.ModelAdmin):
    list_display = ['reference_number', 'posting_date', 'fund', 'function', 'program', 'geo', 'status']
    list_filter = ['status', 'fund', 'function', 'program']
    search_fields = ['reference_number', 'description']
    inlines = [JournalLineInline]

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'symbol', 'exchange_rate', 'is_base_currency']
    list_filter = ['is_base_currency', 'is_active']
    search_fields = ['code', 'name']

class PaymentAllocationReadOnlyInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    readonly_fields = ['payment', 'amount']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(VendorInvoice)
class VendorInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'vendor', 'invoice_date', 'total_amount', 'status']
    list_filter = ['status']
    search_fields = ['invoice_number', 'vendor__name']
    inlines = [PaymentAllocationReadOnlyInline]

class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 1

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'payment_date', 'total_amount', 'status']
    list_filter = ['status', 'payment_method']
    search_fields = ['payment_number']
    inlines = [PaymentAllocationInline]

class ReceiptAllocationReadOnlyInline(admin.TabularInline):
    model = ReceiptAllocation
    extra = 0
    readonly_fields = ['receipt', 'amount']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(CustomerInvoice)
class CustomerInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'customer_name', 'invoice_date', 'total_amount', 'status']
    list_filter = ['status']
    search_fields = ['invoice_number', 'customer_name']
    inlines = [ReceiptAllocationReadOnlyInline]

class ReceiptAllocationInline(admin.TabularInline):
    model = ReceiptAllocation
    extra = 1

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'receipt_date', 'total_amount', 'status']
    list_filter = ['status', 'payment_method']
    search_fields = ['receipt_number']
    inlines = [ReceiptAllocationInline]

class DepreciationScheduleInline(admin.TabularInline):
    model = DepreciationSchedule
    extra = 0
    readonly_fields = ['period_date', 'depreciation_amount', 'journal_entry', 'is_posted']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ['asset_number', 'name', 'asset_category', 'acquisition_date', 'acquisition_cost', 'status']
    list_filter = ['asset_category', 'status', 'depreciation_method']
    search_fields = ['asset_number', 'name']
    inlines = [DepreciationScheduleInline]

@admin.register(DepreciationSchedule)
class DepreciationScheduleAdmin(admin.ModelAdmin):
    list_display = ['asset', 'period_date', 'depreciation_amount', 'is_posted']
    list_filter = ['is_posted']

@admin.register(GLBalance)
class GLBalanceAdmin(admin.ModelAdmin):
    list_display = ['account', 'fund', 'function', 'program', 'geo', 'fiscal_year', 'period', 'debit_balance', 'credit_balance']
    list_filter = ['fiscal_year', 'period', 'fund', 'function', 'program', 'geo']
    search_fields = ['account__code', 'account__name']


# ============================================================================
# ADDITIONAL MODEL REGISTRATIONS
# ============================================================================

@admin.register(MDA)
class MDAAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'short_name', 'mda_type', 'is_active']
    list_filter = ['mda_type', 'is_active']
    search_fields = ['code', 'name', 'short_name']


@admin.register(BudgetPeriod)
class BudgetPeriodAdmin(admin.ModelAdmin):
    list_display = ['fiscal_year', 'period_type', 'period_number', 'start_date', 'end_date', 'status']
    list_filter = ['status', 'period_type', 'fiscal_year']


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['budget_code', 'period', 'mda', 'account', 'allocated_amount', 'revised_amount']
    list_filter = ['period', 'mda', 'control_level']
    search_fields = ['budget_code']


@admin.register(BudgetEncumbrance)
class BudgetEncumbranceAdmin(admin.ModelAdmin):
    list_display = ['reference_type', 'reference_id', 'amount', 'liquidated_amount', 'status']
    list_filter = ['status', 'reference_type']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'account_number', 'account_type', 'current_balance', 'is_active']
    list_filter = ['account_type', 'is_active']
    search_fields = ['name', 'account_number']


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ['bank_account', 'statement_date', 'statement_balance', 'book_balance', 'difference', 'status']
    list_filter = ['status']
    search_fields = ['bank_account__name']


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']


@admin.register(ProfitCenter)
class ProfitCenterAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']


@admin.register(TaxCode)
class TaxCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'tax_type', 'direction', 'rate', 'is_active']
    list_filter = ['tax_type', 'direction', 'is_active']
    search_fields = ['code', 'name']


@admin.register(WithholdingTax)
class WithholdingTaxAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'income_type', 'rate', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']


@admin.register(TaxRegistration)
class TaxRegistrationAdmin(admin.ModelAdmin):
    list_display = ['tax_type', 'registration_number', 'effective_date', 'is_active']
    list_filter = ['tax_type', 'is_active']


@admin.register(TaxReturn)
class TaxReturnAdmin(admin.ModelAdmin):
    list_display = ['tax_type', 'period_start', 'period_end', 'tax_due', 'status']
    list_filter = ['status', 'tax_type']


@admin.register(RecurringJournal)
class RecurringJournalAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'frequency', 'is_active', 'next_run_date']
    list_filter = ['frequency', 'is_active']
    search_fields = ['code', 'name']


@admin.register(Accrual)
class AccrualAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'accrual_type', 'amount']
    list_filter = ['accrual_type']
    search_fields = ['code', 'name']


@admin.register(Deferral)
class DeferralAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'original_amount', 'remaining_amount', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ['year', 'name', 'start_date', 'end_date', 'status']
    list_filter = ['status']


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(admin.ModelAdmin):
    list_display = ['fiscal_year', 'period_type', 'period_number', 'start_date', 'end_date', 'status']
    list_filter = ['status', 'period_type', 'fiscal_year']


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'depreciation_method', 'default_life_years', 'is_active']
    list_filter = ['depreciation_method', 'is_active']
    search_fields = ['code', 'name']


@admin.register(AssetClass)
class AssetClassAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'default_life', 'depreciation_method']
    search_fields = ['code', 'name']


@admin.register(AccountingSettings)
class AccountingSettingsAdmin(admin.ModelAdmin):
    list_display = ['account_code_digits', 'is_digit_enforcement_active']


@admin.register(ExchangeRateHistory)
class ExchangeRateHistoryAdmin(admin.ModelAdmin):
    list_display = ['from_currency', 'to_currency', 'rate_date', 'exchange_rate']
    list_filter = ['from_currency', 'to_currency']


# Company and ConsolidationGroup admin removed — public sector
