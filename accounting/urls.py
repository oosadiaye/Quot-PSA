"""
Quot PSE — Accounting API URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    # Dimensions
    FundViewSet, FunctionViewSet, ProgramViewSet, GeoViewSet,
    # Core GL
    AccountViewSet, JournalViewSet, CurrencyViewSet,
    GLBalanceViewSet, MDAViewSet,
    # Payables
    VendorInvoiceViewSet, PaymentViewSet, PaymentAllocationViewSet,
    # Receivables
    CustomerInvoiceViewSet, ReceiptViewSet, ReceiptAllocationViewSet, CustomerLedgerView,
    # Budget (legacy accounting-level budget)
    BudgetPeriodViewSet, BudgetViewSet, BudgetEncumbranceViewSet,
    BudgetAmendmentViewSet, BudgetTransferViewSet, BudgetCheckLogViewSet,
    BudgetForecastViewSet, BudgetAnomalyViewSet,
    # Banking
    BankAccountViewSet, CheckbookViewSet, CheckViewSet, BankReconciliationViewSet,
    CashFlowCategoryViewSet, CashFlowForecastViewSet, BankStatementViewSet,
    # Tax
    TaxRegistrationViewSet, TaxExemptionViewSet, TaxReturnViewSet,
    WithholdingTaxViewSet, TaxCodeViewSet,
    # Cost & Profit Centers
    CostCenterViewSet, ProfitCenterViewSet, CostAllocationRuleViewSet,
    # Deferred, Leases, Treasury
    DeferredRevenueViewSet, DeferredExpenseViewSet,
    LeaseViewSet, LeasePaymentViewSet,
    TreasuryForecastViewSet, InvestmentViewSet, LoanViewSet, LoanRepaymentViewSet,
    ExchangeRateHistoryViewSet, ForeignCurrencyRevaluationViewSet,
    # Period & Fiscal
    FiscalPeriodViewSet, PeriodCloseCheckViewSet, FiscalYearViewSet, PeriodAccessViewSet,
    PeriodCloseChecklistView,
    # Fixed Assets
    AssetClassViewSet, AssetConfigurationViewSet, AssetCategoryViewSet,
    AssetLocationViewSet, AssetInsuranceViewSet, AssetMaintenanceViewSet,
    AssetTransferViewSet, AssetDepreciationScheduleViewSet,
    AssetRevaluationViewSet, AssetDisposalViewSet, AssetImpairmentViewSet,
    FixedAssetViewSet,
    # Recurring, Accruals, Period Mgmt
    RecurringJournalViewSet, RecurringJournalRunViewSet,
    AccrualViewSet, DeferralViewSet,
    PeriodStatusViewSet, YearEndClosingViewSet, RetainedEarningsViewSet,
    CurrencyRevaluationViewSet,
    # Reports
    BalanceSheetViewSet, IncomeStatementViewSet, CashFlowStatementViewSet,
    BudgetVsActualViewSet, BudgetPerformanceViewSet,
    CostCenterReportViewSet, IFRSComparisonViewSet,
    GeneralLedgerViewSet, TrialBalanceViewSet,
    InventoryStockValuationViewSet, InventoryLowStockViewSet, InventoryMovementViewSet,
    HRHeadcountViewSet, HRPayrollSummaryViewSet,
    ProcurementSummaryViewSet, ProcurementVendorsViewSet,
    # Workflows
    CreditNoteViewSet, DebitNoteViewSet,
    BadDebtProvisionViewSet, BadDebtWriteOffViewSet,
    PettyCashFundViewSet, PettyCashVoucherViewSet, PettyCashReplenishmentViewSet,
    ChequeRegisterViewSet,
    BudgetPeriodManagementViewSet,
    SuspenseClearingViewSet,
    # Treasury & Revenue (Phase 4)
    TreasuryAccountViewSet, PaymentVoucherViewSet, PaymentInstructionViewSet,
    RevenueHeadViewSet, RevenueCollectionViewSet,
    # NCoA Segment API (Phase 8)
    NCoAAdminSegViewSet, NCoAEconSegViewSet, NCoAFuncSegViewSet,
    NCoAProgSegViewSet, NCoAFundSegViewSet, NCoAGeoSegViewSet,
    NCoACodeViewSet,
    # IPSAS Reports (Phase 7)
    StatementOfFinancialPositionView, StatementOfFinancialPerformanceView,
    CashFlowStatementView,
    StatementOfChangesInNetAssetsView,
    NotesToFinancialStatementsView,
    BudgetVsActualIPSASView, RevenuePerformanceView, TSACashPositionView,
    FunctionalClassificationView, ProgrammePerformanceView, GeographicDistributionView,
    FundPerformanceView,
    # Settings
    accounting_settings_api, seed_default_coa,
)

router = DefaultRouter()

# ─── Core Accounting ───────────────────────────────────────────
router.register(r'funds', FundViewSet, basename='fund')
router.register(r'functions', FunctionViewSet, basename='function')
router.register(r'programs', ProgramViewSet, basename='program')
router.register(r'geos', GeoViewSet, basename='geo')
router.register(r'accounts', AccountViewSet, basename='account')
router.register(r'journals', JournalViewSet, basename='journal')
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'mdas', MDAViewSet, basename='mda')

# ─── Payables ──────────────────────────────────────────────────
router.register(r'vendor-invoices', VendorInvoiceViewSet, basename='vendor-invoice')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'payment-allocations', PaymentAllocationViewSet, basename='payment-allocation')

# ─── Receivables ───────────────────────────────────────────────
router.register(r'customer-invoices', CustomerInvoiceViewSet, basename='customer-invoice')
router.register(r'receipts', ReceiptViewSet, basename='receipt')
router.register(r'receipt-allocations', ReceiptAllocationViewSet, basename='receipt-allocation')
router.register(r'customer-ledger', CustomerLedgerView, basename='customer-ledger')

# ─── Fixed Assets ──────────────────────────────────────────────
router.register(r'fixed-assets', FixedAssetViewSet, basename='fixed-asset')
router.register(r'gl-balances', GLBalanceViewSet, basename='gl-balance')
router.register(r'asset-classes', AssetClassViewSet, basename='asset-class')
router.register(r'asset-configs', AssetConfigurationViewSet, basename='asset-config')
router.register(r'asset-categories', AssetCategoryViewSet, basename='asset-category')
router.register(r'asset-locations', AssetLocationViewSet, basename='asset-location')
router.register(r'asset-insurance', AssetInsuranceViewSet, basename='asset-insurance')
router.register(r'asset-maintenance', AssetMaintenanceViewSet, basename='asset-maintenance')
router.register(r'asset-transfers', AssetTransferViewSet, basename='asset-transfer')
router.register(r'asset-dep-schedules', AssetDepreciationScheduleViewSet, basename='asset-dep-schedule')
router.register(r'asset-revaluations', AssetRevaluationViewSet, basename='asset-revaluation')
router.register(r'asset-disposals', AssetDisposalViewSet, basename='asset-disposal')
router.register(r'asset-impairments', AssetImpairmentViewSet, basename='asset-impairment')

# ─── Budget (Legacy) ──────────────────────────────────────────
router.register(r'budget-periods', BudgetPeriodViewSet, basename='budget-period')
router.register(r'budgets', BudgetViewSet, basename='budget')
router.register(r'budget-encumbrances', BudgetEncumbranceViewSet, basename='budget-encumbrance')
router.register(r'budget-amendments', BudgetAmendmentViewSet, basename='budget-amendment')
router.register(r'budget-transfers', BudgetTransferViewSet, basename='budget-transfer')
router.register(r'budget-check-logs', BudgetCheckLogViewSet, basename='budget-check-log')
router.register(r'budget-forecasts', BudgetForecastViewSet, basename='budget-forecast')
router.register(r'budget-anomalies', BudgetAnomalyViewSet, basename='budget-anomaly')

# ─── Banking & Cash ───────────────────────────────────────────
router.register(r'bank-accounts', BankAccountViewSet, basename='bank-account')
router.register(r'checkbooks', CheckbookViewSet, basename='checkbook')
router.register(r'checks', CheckViewSet, basename='check')
router.register(r'bank-reconciliations', BankReconciliationViewSet, basename='bank-reconciliation')
router.register(r'cashflow-categories', CashFlowCategoryViewSet, basename='cashflow-category')
router.register(r'cashflow-forecasts', CashFlowForecastViewSet, basename='cashflow-forecast')
router.register(r'bank-statements', BankStatementViewSet, basename='bank-statement')

# ─── Tax ───────────────────────────────────────────────────────
router.register(r'tax-registrations', TaxRegistrationViewSet, basename='tax-registration')
router.register(r'tax-exemptions', TaxExemptionViewSet, basename='tax-exemption')
router.register(r'tax-returns', TaxReturnViewSet, basename='tax-return')
router.register(r'withholding-taxes', WithholdingTaxViewSet, basename='withholding-tax')
router.register(r'tax-codes', TaxCodeViewSet, basename='tax-code')

# ─── Cost & Profit Centers ────────────────────────────────────
router.register(r'cost-centers', CostCenterViewSet, basename='cost-center')
router.register(r'profit-centers', ProfitCenterViewSet, basename='profit-center')
router.register(r'cost-allocation-rules', CostAllocationRuleViewSet, basename='cost-allocation-rule')

# ─── Reporting ─────────────────────────────────────────────────
router.register(r'report-templates', BalanceSheetViewSet, basename='report-template')

# ─── Deferred / Leases / Treasury ─────────────────────────────
router.register(r'deferred-revenues', DeferredRevenueViewSet, basename='deferred-revenue')
router.register(r'deferred-expenses', DeferredExpenseViewSet, basename='deferred-expense')
router.register(r'leases', LeaseViewSet, basename='lease')
router.register(r'lease-payments', LeasePaymentViewSet, basename='lease-payment')
router.register(r'treasury-forecasts', TreasuryForecastViewSet, basename='treasury-forecast')
router.register(r'investments', InvestmentViewSet, basename='investment')
router.register(r'loans', LoanViewSet, basename='loan')
router.register(r'loan-repayments', LoanRepaymentViewSet, basename='loan-repayment')
router.register(r'exchange-rates', ExchangeRateHistoryViewSet, basename='exchange-rate')
router.register(r'currency-revaluations', ForeignCurrencyRevaluationViewSet, basename='currency-revaluation')

# ─── Period & Fiscal ──────────────────────────────────────────
router.register(r'fiscal-periods', FiscalPeriodViewSet, basename='fiscal-period')
router.register(r'fiscal-years', FiscalYearViewSet, basename='fiscal-year')
router.register(r'period-access', PeriodAccessViewSet, basename='period-access')
router.register(r'period-close-checks', PeriodCloseCheckViewSet, basename='period-close-check')

# ─── Recurring & Accrual ─────────────────────────────────────
router.register(r'recurring-journals', RecurringJournalViewSet, basename='recurring-journal')
router.register(r'recurring-journal-runs', RecurringJournalRunViewSet, basename='recurring-journal-run')
router.register(r'accruals', AccrualViewSet, basename='accrual')
router.register(r'deferrals', DeferralViewSet, basename='deferral')
router.register(r'period-statuses', PeriodStatusViewSet, basename='period-status')
router.register(r'year-end-closings', YearEndClosingViewSet, basename='year-end-closing')
router.register(r'retained-earnings', RetainedEarningsViewSet, basename='retained-earnings')
router.register(r'currency-reval-runs', CurrencyRevaluationViewSet, basename='currency-reval-run')

# ─── Credit/Debit Notes, Bad Debt, Petty Cash, Cheques ───────
router.register(r'credit-notes', CreditNoteViewSet, basename='credit-note')
router.register(r'debit-notes', DebitNoteViewSet, basename='debit-note')
router.register(r'bad-debt-provisions', BadDebtProvisionViewSet, basename='bad-debt-provision')
router.register(r'bad-debt-writeoffs', BadDebtWriteOffViewSet, basename='bad-debt-writeoff')
router.register(r'petty-cash-funds', PettyCashFundViewSet, basename='petty-cash-fund')
router.register(r'petty-cash-vouchers', PettyCashVoucherViewSet, basename='petty-cash-voucher')
router.register(r'petty-cash-replenishments', PettyCashReplenishmentViewSet, basename='petty-cash-replenishment')
router.register(r'cheque-registers', ChequeRegisterViewSet, basename='cheque-register')
router.register(r'suspense-clearing', SuspenseClearingViewSet, basename='suspense-clearing')

# ─── Treasury & Revenue (Phase 4) ────────────────────────
router.register(r'tsa-accounts', TreasuryAccountViewSet, basename='tsa-account')
router.register(r'payment-vouchers', PaymentVoucherViewSet, basename='payment-voucher')
router.register(r'payment-instructions', PaymentInstructionViewSet, basename='payment-instruction')
router.register(r'revenue-heads', RevenueHeadViewSet, basename='revenue-head')
router.register(r'revenue-collections', RevenueCollectionViewSet, basename='revenue-collection')

# ─── TSA Bank Reconciliation ─────────────────────────────
# Lives after the TSA block so it inherits logical grouping; registered
# here (rather than in a separate sub-router) to keep URL prefixes flat.
from accounting.views.data_quality import DataQualityView
from accounting.views.tsa_reconciliation_views import (
    TSABankStatementViewSet, TSABankStatementLineViewSet,
    TSAReconciliationViewSet,
)
router.register(r'tsa-bank-statements', TSABankStatementViewSet, basename='tsa-bank-statement')
router.register(r'tsa-bank-statement-lines', TSABankStatementLineViewSet, basename='tsa-bank-statement-line')
router.register(r'tsa-bank-reconciliations', TSAReconciliationViewSet, basename='tsa-bank-reconciliation')

# ─── NCoA Segments (Phase 8) ─────────────────────────────
router.register(r'ncoa/administrative', NCoAAdminSegViewSet, basename='ncoa-administrative')
router.register(r'ncoa/economic', NCoAEconSegViewSet, basename='ncoa-economic')
router.register(r'ncoa/functional', NCoAFuncSegViewSet, basename='ncoa-functional')
router.register(r'ncoa/programme', NCoAProgSegViewSet, basename='ncoa-programme')
router.register(r'ncoa/fund', NCoAFundSegViewSet, basename='ncoa-fund')
router.register(r'ncoa/geographic', NCoAGeoSegViewSet, basename='ncoa-geographic')
router.register(r'ncoa/codes', NCoACodeViewSet, basename='ncoa-code')

# ─── Financial Reports ────────────────────────────────────────
router.register(r'reports/balance-sheet', BalanceSheetViewSet, basename='balance-sheet')
router.register(r'reports/income-statement', IncomeStatementViewSet, basename='income-statement')
router.register(r'reports/cash-flow', CashFlowStatementViewSet, basename='cash-flow')
router.register(r'reports/budget-vs-actual', BudgetVsActualViewSet, basename='budget-vs-actual')
router.register(r'reports/budget-performance', BudgetPerformanceViewSet, basename='budget-performance')
router.register(r'reports/cost-center', CostCenterReportViewSet, basename='cost-center-report')
router.register(r'reports/ifrs', IFRSComparisonViewSet, basename='ifrs-comparison')
router.register(r'reports/general-ledger', GeneralLedgerViewSet, basename='general-ledger')
router.register(r'reports/trial-balance', TrialBalanceViewSet, basename='trial-balance')
router.register(r'reports/inventory-valuation', InventoryStockValuationViewSet, basename='inventory-valuation')
router.register(r'reports/inventory-low-stock', InventoryLowStockViewSet, basename='inventory-low-stock')
router.register(r'reports/inventory-movement', InventoryMovementViewSet, basename='inventory-movement')
router.register(r'reports/hr-headcount', HRHeadcountViewSet, basename='hr-headcount')
router.register(r'reports/hr-payroll', HRPayrollSummaryViewSet, basename='hr-payroll')
router.register(r'reports/procurement-summary', ProcurementSummaryViewSet, basename='procurement-summary')
router.register(r'reports/procurement-vendors', ProcurementVendorsViewSet, basename='procurement-vendors')

# S25 — Approval rules admin.
from accounting.views.approval_rules import (  # noqa: E402
    ApprovalRuleViewSet, DualControlOverrideViewSet,
)
router.register(r'approval-rules', ApprovalRuleViewSet, basename='approval-rule')
# P4-T5 — dual-control override audit feed.
router.register(r'dual-control-overrides', DualControlOverrideViewSet, basename='dual-control-override')

# ── Budget Check Rules (tenant-configurable policy) ──────────────────
# MUST be registered BEFORE the urlpatterns=[] assignment below — that
# snapshot captures router.urls eagerly, so later router.register() calls
# won't appear in resolved URLs.
from .views.budget_check_rules import BudgetCheckRuleViewSet
router.register(r'budget-check-rules', BudgetCheckRuleViewSet, basename='budget-check-rule')

urlpatterns = [
    path('', include(router.urls)),
    path('settings/', accounting_settings_api, name='accounting-settings'),
    path('seed-coa/', seed_default_coa, name='seed-coa'),
    path('period-close-checklist/', PeriodCloseChecklistView.as_view({'get': 'list'}), name='period-close-checklist'),

    # Sprint 16 — GL Data Quality diagnostics.
    path('data-quality/', DataQualityView.as_view(), name='data-quality'),
    path('budget-period-mgmt/', BudgetPeriodManagementViewSet.as_view({'get': 'list'}), name='budget-period-mgmt'),

    # IPSAS Financial Statements (Phase 7)
    path('ipsas/financial-position/', StatementOfFinancialPositionView.as_view(), name='ipsas-financial-position'),
    path('ipsas/financial-performance/', StatementOfFinancialPerformanceView.as_view(), name='ipsas-financial-performance'),
    # Sprint 2 — complete the five-statement IPSAS set.
    path('ipsas/cash-flow/',              CashFlowStatementView.as_view(),            name='ipsas-cash-flow'),
    path('ipsas/changes-in-net-assets/',  StatementOfChangesInNetAssetsView.as_view(), name='ipsas-changes-in-net-assets'),
    path('ipsas/notes/',                  NotesToFinancialStatementsView.as_view(),   name='ipsas-notes'),
    path('ipsas/budget-vs-actual/', BudgetVsActualIPSASView.as_view(), name='ipsas-budget-vs-actual'),
    path('ipsas/revenue-performance/', RevenuePerformanceView.as_view(), name='ipsas-revenue-performance'),
    path('ipsas/tsa-cash-position/', TSACashPositionView.as_view(), name='ipsas-tsa-cash-position'),
    path('ipsas/functional-classification/', FunctionalClassificationView.as_view(), name='ipsas-functional'),
    path('ipsas/programme-performance/', ProgrammePerformanceView.as_view(), name='ipsas-programme'),
    path('ipsas/geographic-distribution/', GeographicDistributionView.as_view(), name='ipsas-geographic'),
    path('ipsas/fund-performance/',        FundPerformanceView.as_view(),        name='ipsas-fund-performance'),

]

# Document Print Templates (Phase 11) — imported separately to avoid circular imports
from accounting.views.document_views import (
    payment_voucher_print, revenue_receipt_print, payment_voucher_pdf_data,
)
urlpatterns += [
    path('print/payment-voucher/<int:pk>/', payment_voucher_print, name='print-payment-voucher'),
    path('print/revenue-receipt/<int:pk>/', revenue_receipt_print, name='print-revenue-receipt'),
    path('api-print/payment-voucher/<int:pk>/', payment_voucher_pdf_data, name='api-print-payment-voucher'),
]

# ── Treasury Operations ─────────────────────────────────────────
from .views.treasury_revenue import (
    execute_cash_sweep, reconciliation_status, reconcile_payment, mark_reconciled,
)
urlpatterns += [
    path('treasury/cash-sweep/', execute_cash_sweep, name='cash-sweep'),
    path('treasury/reconciliation/', reconciliation_status, name='reconciliation-status'),
    path('treasury/reconcile/', reconcile_payment, name='reconcile-payment'),
    path('treasury/mark-reconciled/', mark_reconciled, name='mark-reconciled'),
]

# ── S7 — Statutory exporters (FIRS WHT, PAYE) ────────────────────────
# ── S8 — PENCOM, NSITF, NHIA monthly + ITF annual ────────────────────
# ── S9 — OAGF Monthly Financial Report + FIRS VAT + index ────────────
from .views.statutory_reports import (
    WHTScheduleView, PAYEScheduleView,
    PENCOMScheduleView, NSITFScheduleView, NHIAScheduleView, ITFScheduleView,
    OAGFMFRView, VATReturnView, StatutoryIndexView,
)
urlpatterns += [
    # Index / catalogue — call this first to discover what's available.
    path('statutory/',          StatutoryIndexView.as_view(), name='statutory-index'),
    # Per-regulator endpoints.
    path('statutory/firs/wht/', WHTScheduleView.as_view(),    name='firs-wht-schedule'),
    path('statutory/firs/vat/', VATReturnView.as_view(),      name='firs-vat-return'),
    path('statutory/paye/',     PAYEScheduleView.as_view(),   name='paye-schedule'),
    path('statutory/pencom/',   PENCOMScheduleView.as_view(), name='pencom-schedule'),
    path('statutory/nsitf/',    NSITFScheduleView.as_view(),  name='nsitf-schedule'),
    path('statutory/nhia/',     NHIAScheduleView.as_view(),   name='nhia-schedule'),
    path('statutory/itf/',      ITFScheduleView.as_view(),    name='itf-schedule'),
    path('statutory/oagf/',     OAGFMFRView.as_view(),        name='oagf-mfr'),
]

# ── S10 — Report snapshots ───────────────────────────────────────────
from .views.snapshots import ReportSnapshotViewSet
router.register(r'snapshots', ReportSnapshotViewSet, basename='snapshot')

# ── S11 — IPSAS 19 registries ────────────────────────────────────────
from .views.provisions import (
    ProvisionViewSet, ContingentLiabilityViewSet, ContingentAssetViewSet,
)
router.register(r'provisions',            ProvisionViewSet,           basename='provision')
router.register(r'contingent-liabilities', ContingentLiabilityViewSet, basename='contingent-liability')
router.register(r'contingent-assets',     ContingentAssetViewSet,      basename='contingent-asset')

# ── S12 — IPSAS 31 (intangibles) + IPSAS 33 (opening balance sheet) ─
from .views.ipsas_registers import (
    IntangibleAssetViewSet,
    OpeningBalanceSheetViewSet, OpeningBalanceItemViewSet,
)
router.register(r'intangible-assets',      IntangibleAssetViewSet,     basename='intangible-asset')
router.register(r'opening-balance-sheets', OpeningBalanceSheetViewSet, basename='opening-balance-sheet')
router.register(r'opening-balance-items',  OpeningBalanceItemViewSet,  basename='opening-balance-item')

# ── S14 — IPSAS 39 (pension) + IPSAS 42 (social benefits) ────────────
from .views.pension_social import (
    PensionSchemeViewSet, ActuarialValuationViewSet, PensionContributionViewSet,
    SocialBenefitSchemeViewSet, SocialBenefitClaimViewSet,
)
router.register(r'pension-schemes',          PensionSchemeViewSet,          basename='pension-scheme')
router.register(r'actuarial-valuations',     ActuarialValuationViewSet,     basename='actuarial-valuation')
router.register(r'pension-contributions',    PensionContributionViewSet,    basename='pension-contribution')
router.register(r'social-benefit-schemes',   SocialBenefitSchemeViewSet,    basename='social-benefit-scheme')
router.register(r'social-benefit-claims',    SocialBenefitClaimViewSet,     basename='social-benefit-claim')

# ── S11 — MDA bulk data import (OAGF consumption path) ───────────────
from .views.mda_data_import import (
    MDAImportPreviewView, MDAImportCatalogueView, MDAImportCommitView,
)
urlpatterns += [
    path('mda-imports/preview/',   MDAImportPreviewView.as_view(),   name='mda-import-preview'),
    path('mda-imports/catalogue/', MDAImportCatalogueView.as_view(), name='mda-import-catalogue'),
    path('mda-imports/commit/',    MDAImportCommitView.as_view(),    name='mda-import-commit'),
]
