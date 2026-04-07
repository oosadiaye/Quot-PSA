from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FundViewSet, FunctionViewSet, ProgramViewSet, GeoViewSet,
    AccountViewSet, JournalViewSet, CurrencyViewSet,
    VendorInvoiceViewSet, PaymentViewSet, PaymentAllocationViewSet, CustomerInvoiceViewSet,
    ReceiptViewSet, FixedAssetViewSet, GLBalanceViewSet, ReceiptAllocationViewSet, CustomerLedgerView,
    MDAViewSet, BudgetPeriodViewSet, BudgetViewSet, BudgetEncumbranceViewSet,
    BudgetAmendmentViewSet, BudgetTransferViewSet, BudgetCheckLogViewSet,
    BudgetForecastViewSet, BudgetAnomalyViewSet,
    BankAccountViewSet, CheckbookViewSet, CheckViewSet, BankReconciliationViewSet,
    CashFlowCategoryViewSet, CashFlowForecastViewSet, BankStatementViewSet,
    TaxRegistrationViewSet, TaxExemptionViewSet, TaxReturnViewSet, WithholdingTaxViewSet, TaxCodeViewSet,
    CostCenterViewSet, ProfitCenterViewSet, CostAllocationRuleViewSet,
    InterCompanyViewSet, InterCompanyTransactionViewSet,
    CompanyViewSet, InterCompanyConfigViewSet, InterCompanyInvoiceViewSet,
    InterCompanyTransferViewSet, InterCompanyAllocationViewSet, InterCompanyCashTransferViewSet,
    FinancialReportTemplateViewSet, FinancialReportViewSet,
    AccountingDocumentViewSet,
    ConsolidationGroupViewSet, ConsolidationViewSet, ConsolidationRunViewSet,
    DeferredRevenueViewSet, DeferredExpenseViewSet,
    LeaseViewSet, LeasePaymentViewSet,
    TreasuryForecastViewSet, InvestmentViewSet, LoanViewSet, LoanRepaymentViewSet,
    ExchangeRateHistoryViewSet, ForeignCurrencyRevaluationViewSet,
    FiscalPeriodViewSet, PeriodCloseCheckViewSet, FiscalYearViewSet, PeriodAccessViewSet,
    PeriodCloseChecklistView,
    AssetClassViewSet, AssetConfigurationViewSet, AssetCategoryViewSet,
    AssetLocationViewSet, AssetInsuranceViewSet, AssetMaintenanceViewSet,
    AssetTransferViewSet, AssetDepreciationScheduleViewSet,
    AssetRevaluationViewSet, AssetDisposalViewSet, AssetImpairmentViewSet,
    RecurringJournalViewSet, RecurringJournalRunViewSet,
    AccrualViewSet, DeferralViewSet,
    PeriodStatusViewSet, YearEndClosingViewSet, RetainedEarningsViewSet,
    CurrencyRevaluationViewSet,
    BalanceSheetViewSet, IncomeStatementViewSet, CashFlowStatementViewSet,
    BudgetVsActualViewSet, BudgetPerformanceViewSet,
    CostCenterReportViewSet, IFRSComparisonViewSet,
    GeneralLedgerViewSet, TrialBalanceViewSet,
    InventoryStockValuationViewSet, InventoryLowStockViewSet, InventoryMovementViewSet,
    HRHeadcountViewSet, HRPayrollSummaryViewSet,
    SalesSummaryViewSet, SalesCustomersViewSet,
    ProcurementSummaryViewSet, ProcurementVendorsViewSet,
    ProductionSummaryViewSet, ProductionMaterialConsumptionViewSet,
    ProductionCostReportViewSet, ProductProfitabilityViewSet,
    accounting_settings_api, seed_default_coa,
    CreditNoteViewSet, DebitNoteViewSet,
    BadDebtProvisionViewSet, BadDebtWriteOffViewSet,
    PettyCashFundViewSet, PettyCashVoucherViewSet, PettyCashReplenishmentViewSet,
    ChequeRegisterViewSet,
    BudgetPeriodManagementViewSet,
    SuspenseClearingViewSet,
)

router = DefaultRouter()

# Core Accounting
router.register(r'funds', FundViewSet, basename='fund')
router.register(r'functions', FunctionViewSet, basename='function')
router.register(r'programs', ProgramViewSet, basename='program')
router.register(r'geos', GeoViewSet, basename='geo')
router.register(r'accounts', AccountViewSet, basename='account')
router.register(r'journals', JournalViewSet, basename='journal')
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'vendor-invoices', VendorInvoiceViewSet, basename='vendor-invoice')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'payment-allocations', PaymentAllocationViewSet, basename='payment-allocation')
router.register(r'customer-invoices', CustomerInvoiceViewSet, basename='customer-invoice')
router.register(r'receipts', ReceiptViewSet, basename='receipt')
router.register(r'receipt-allocations', ReceiptAllocationViewSet, basename='receipt-allocation')
router.register(r'customer-ledger', CustomerLedgerView, basename='customer-ledger')
router.register(r'fixed-assets', FixedAssetViewSet, basename='fixed-asset')
router.register(r'gl-balances', GLBalanceViewSet, basename='gl-balance')

# Budget
router.register(r'mdas', MDAViewSet, basename='mda')
router.register(r'budget-periods', BudgetPeriodViewSet, basename='budget-period')
router.register(r'budgets', BudgetViewSet, basename='budget')
router.register(r'budget-encumbrances', BudgetEncumbranceViewSet, basename='budget-encumbrance')
router.register(r'budget-amendments', BudgetAmendmentViewSet, basename='budget-amendment')
router.register(r'budget-transfers', BudgetTransferViewSet, basename='budget-transfer')
router.register(r'budget-check-logs', BudgetCheckLogViewSet, basename='budget-check-log')
router.register(r'budget-forecasts', BudgetForecastViewSet, basename='budget-forecast')
router.register(r'budget-anomalies', BudgetAnomalyViewSet, basename='budget-anomaly')

# Bank & Cash
router.register(r'bank-accounts', BankAccountViewSet, basename='bank-account')
router.register(r'checkbooks', CheckbookViewSet, basename='checkbook')
router.register(r'checks', CheckViewSet, basename='check')
router.register(r'bank-reconciliations', BankReconciliationViewSet, basename='bank-reconciliation')
router.register(r'cashflow-categories', CashFlowCategoryViewSet, basename='cashflow-category')
router.register(r'cashflow-forecasts', CashFlowForecastViewSet, basename='cashflow-forecast')
router.register(r'bank-statements', BankStatementViewSet, basename='bank-statement')

# Tax
router.register(r'tax-registrations', TaxRegistrationViewSet, basename='tax-registration')
router.register(r'tax-exemptions', TaxExemptionViewSet, basename='tax-exemption')
router.register(r'tax-returns', TaxReturnViewSet, basename='tax-return')
router.register(r'withholding-taxes', WithholdingTaxViewSet, basename='withholding-tax')
router.register(r'tax-codes', TaxCodeViewSet, basename='tax-code')

# Cost Center
router.register(r'cost-centers', CostCenterViewSet, basename='cost-center')
router.register(r'profit-centers', ProfitCenterViewSet, basename='profit-center')
router.register(r'cost-allocation-rules', CostAllocationRuleViewSet, basename='cost-allocation-rule')

# Intercompany
router.register(r'inter-companies', InterCompanyViewSet, basename='inter-company')
router.register(r'intercompany-transactions', InterCompanyTransactionViewSet, basename='intercompany-transaction')
router.register(r'companies', CompanyViewSet, basename='company')
router.register(r'ic-configs', InterCompanyConfigViewSet, basename='ic-config')
router.register(r'ic-invoices', InterCompanyInvoiceViewSet, basename='ic-invoice')
router.register(r'ic-transfers', InterCompanyTransferViewSet, basename='ic-transfer')
router.register(r'ic-allocations', InterCompanyAllocationViewSet, basename='ic-allocation')
router.register(r'ic-cash-transfers', InterCompanyCashTransferViewSet, basename='ic-cash-transfer')

# Reporting
router.register(r'report-templates', FinancialReportTemplateViewSet, basename='report-template')
router.register(r'financial-reports', FinancialReportViewSet, basename='financial-report')

# Documents
router.register(r'accounting-documents', AccountingDocumentViewSet, basename='accounting-document')

# Consolidation
router.register(r'consolidation-groups', ConsolidationGroupViewSet, basename='consolidation-group')
router.register(r'consolidation-runs', ConsolidationRunViewSet, basename='consolidation-run')
router.register(r'consolidations', ConsolidationViewSet, basename='consolidation')

# Deferred
router.register(r'deferred-revenues', DeferredRevenueViewSet, basename='deferred-revenue')
router.register(r'deferred-expenses', DeferredExpenseViewSet, basename='deferred-expense')

# Leases
router.register(r'leases', LeaseViewSet, basename='lease')
router.register(r'lease-payments', LeasePaymentViewSet, basename='lease-payment')

# Treasury
router.register(r'treasury-forecasts', TreasuryForecastViewSet, basename='treasury-forecast')
router.register(r'investments', InvestmentViewSet, basename='investment')
router.register(r'loans', LoanViewSet, basename='loan')
router.register(r'loan-repayments', LoanRepaymentViewSet, basename='loan-repayment')

# Currency
router.register(r'exchange-rates', ExchangeRateHistoryViewSet, basename='exchange-rate')
router.register(r'currency-revaluations', ForeignCurrencyRevaluationViewSet, basename='currency-revaluation')

# Period Management
router.register(r'fiscal-periods', FiscalPeriodViewSet, basename='fiscal-period')
router.register(r'fiscal-years', FiscalYearViewSet, basename='fiscal-year')
router.register(r'period-access', PeriodAccessViewSet, basename='period-access')
router.register(r'period-close-checks', PeriodCloseCheckViewSet, basename='period-close-check')

# Asset Enhancement
router.register(r'asset-classes', AssetClassViewSet, basename='asset-class')
router.register(r'asset-configurations', AssetConfigurationViewSet, basename='asset-configuration')
router.register(r'asset-categories', AssetCategoryViewSet, basename='asset-category')
router.register(r'asset-locations', AssetLocationViewSet, basename='asset-location')
router.register(r'asset-insurances', AssetInsuranceViewSet, basename='asset-insurance')
router.register(r'asset-maintenances', AssetMaintenanceViewSet, basename='asset-maintenance')
router.register(r'asset-transfers', AssetTransferViewSet, basename='asset-transfer')
router.register(r'asset-depreciation-schedules', AssetDepreciationScheduleViewSet, basename='asset-depreciation-schedule')
router.register(r'asset-revaluations', AssetRevaluationViewSet, basename='asset-revaluation')
router.register(r'asset-disposals', AssetDisposalViewSet, basename='asset-disposal')
router.register(r'asset-impairments', AssetImpairmentViewSet, basename='asset-impairment')

# Credit / Debit Notes
router.register(r'credit-notes', CreditNoteViewSet, basename='credit-note')
router.register(r'debit-notes', DebitNoteViewSet, basename='debit-note')

# Bad Debt
router.register(r'bad-debt-provisions', BadDebtProvisionViewSet, basename='bad-debt-provision')
router.register(r'bad-debt-writeoffs', BadDebtWriteOffViewSet, basename='bad-debt-writeoff')

# Petty Cash
router.register(r'petty-cash-funds', PettyCashFundViewSet, basename='petty-cash-fund')
router.register(r'petty-cash-vouchers', PettyCashVoucherViewSet, basename='petty-cash-voucher')
router.register(r'petty-cash-replenishments', PettyCashReplenishmentViewSet, basename='petty-cash-replenishment')

# Cheque Register
router.register(r'cheque-register', ChequeRegisterViewSet, basename='cheque-register')

# Budget Period Management (extended with close/lock/reopen)
router.register(r'budget-period-mgmt', BudgetPeriodManagementViewSet, basename='budget-period-mgmt')

# Suspense Clearing
router.register(r'suspense-clearings', SuspenseClearingViewSet, basename='suspense-clearing')

# Advanced Accounting
router.register(r'recurring-journals', RecurringJournalViewSet, basename='recurring-journal')
router.register(r'recurring-journal-runs', RecurringJournalRunViewSet, basename='recurring-journal-run')
router.register(r'accruals', AccrualViewSet, basename='accrual')
router.register(r'deferrals', DeferralViewSet, basename='deferral')
router.register(r'period-statuses', PeriodStatusViewSet, basename='period-status')
router.register(r'year-end-closings', YearEndClosingViewSet, basename='year-end-closing')
router.register(r'retained-earnings', RetainedEarningsViewSet, basename='retained-earnings')
router.register(r'advanced-currency-revaluations', CurrencyRevaluationViewSet, basename='currency-revaluation-advanced')

# Financial Reports
router.register(r'reports/balance-sheet', BalanceSheetViewSet, basename='balance-sheet')
router.register(r'reports/income-statement', IncomeStatementViewSet, basename='income-statement')
router.register(r'reports/cash-flow', CashFlowStatementViewSet, basename='cash-flow')
router.register(r'reports/trial-balance', TrialBalanceViewSet, basename='trial-balance')
router.register(r'reports/general-ledger', GeneralLedgerViewSet, basename='general-ledger')

# Budget Reports
router.register(r'reports/budget-vs-actual', BudgetVsActualViewSet, basename='budget-vs-actual')
router.register(r'reports/budget-performance', BudgetPerformanceViewSet, basename='budget-performance')

# Cost Center Reports
router.register(r'reports/cost-center', CostCenterReportViewSet, basename='cost-center-report')

# IFRS Reports
router.register(r'reports/ifrs-comparison', IFRSComparisonViewSet, basename='ifrs-comparison')

# Inventory Reports
router.register(r'reports/inventory-stock-valuation', InventoryStockValuationViewSet, basename='inventory-stock-valuation')
router.register(r'reports/inventory-low-stock', InventoryLowStockViewSet, basename='inventory-low-stock')
router.register(r'reports/inventory-movement', InventoryMovementViewSet, basename='inventory-movement')

# HR Reports
router.register(r'reports/hr-headcount', HRHeadcountViewSet, basename='hr-headcount')
router.register(r'reports/hr-payroll-summary', HRPayrollSummaryViewSet, basename='hr-payroll-summary')

# Sales Reports
router.register(r'reports/sales-summary', SalesSummaryViewSet, basename='sales-summary')
router.register(r'reports/sales-customers', SalesCustomersViewSet, basename='sales-customers')

# Procurement Reports
router.register(r'reports/procurement-summary', ProcurementSummaryViewSet, basename='procurement-summary')
router.register(r'reports/procurement-vendors', ProcurementVendorsViewSet, basename='procurement-vendors')

# Production Reports
router.register(r'reports/production-summary', ProductionSummaryViewSet, basename='production-summary')
router.register(r'reports/production-material-consumption', ProductionMaterialConsumptionViewSet, basename='production-material-consumption')
router.register(r'reports/production-cost', ProductionCostReportViewSet, basename='production-cost')
router.register(r'reports/product-profitability', ProductProfitabilityViewSet, basename='product-profitability')

router.register(r'period-close/checklist', PeriodCloseChecklistView, basename='period-close-checklist')

urlpatterns = [
    path('settings/', accounting_settings_api, name='accounting-settings'),
    path('settings/seed-coa/', seed_default_coa, name='seed-default-coa'),
    path('', include(router.urls)),
]
