"""Accounting views package — re-exports all ViewSets for backward compatibility.

The views were split from a single 3774-line views.py into domain-based modules.
Import from this package (``from accounting.views import FundViewSet``) or
directly from a sub-module (``from accounting.views.dimensions import FundViewSet``).
"""

# Common
from .common import AccountingPagination, DimensionImportExportMixin  # noqa: F401

# Dimensions
from .dimensions import (  # noqa: F401
    FundViewSet, FunctionViewSet, ProgramViewSet, GeoViewSet,
)

# Core GL
from .core_gl import (  # noqa: F401
    AccountViewSet, JournalViewSet, CurrencyViewSet, GLBalanceViewSet, MDAViewSet,
)

# Payables
from .payables import VendorInvoiceViewSet, PaymentViewSet, PaymentAllocationViewSet  # noqa: F401

# Receivables
from .receivables import CustomerInvoiceViewSet, ReceiptViewSet, ReceiptAllocationViewSet, CustomerLedgerView  # noqa: F401

# Assets
from .assets import (  # noqa: F401
    FixedAssetViewSet,
    AssetClassViewSet, AssetConfigurationViewSet, AssetCategoryViewSet,
    AssetLocationViewSet, AssetInsuranceViewSet, AssetMaintenanceViewSet,
    AssetTransferViewSet, AssetDepreciationScheduleViewSet,
    AssetRevaluationViewSet, AssetDisposalViewSet, AssetImpairmentViewSet,
)

# Budget
from .budget import (  # noqa: F401
    BudgetPeriodViewSet, BudgetViewSet, BudgetEncumbranceViewSet,
    BudgetAmendmentViewSet, BudgetTransferViewSet, BudgetCheckLogViewSet,
    BudgetForecastViewSet, BudgetAnomalyViewSet,
)

# Banking
from .banking import (  # noqa: F401
    BankAccountViewSet, CheckbookViewSet, CheckViewSet,
    BankReconciliationViewSet, CashFlowCategoryViewSet, CashFlowForecastViewSet,
    BankStatementViewSet,
)

# Tax
from .tax import (  # noqa: F401
    TaxRegistrationViewSet, TaxExemptionViewSet, TaxReturnViewSet,
    WithholdingTaxViewSet, TaxCodeViewSet,
)

# Cost & Profit Centers
from .cost_profit import (  # noqa: F401
    CostCenterViewSet, ProfitCenterViewSet, CostAllocationRuleViewSet,
)

# Intercompany & Consolidation
from .intercompany import (  # noqa: F401
    InterCompanyViewSet, InterCompanyTransactionViewSet,
    CompanyViewSet, InterCompanyConfigViewSet, InterCompanyInvoiceViewSet,
    InterCompanyTransferViewSet, InterCompanyAllocationViewSet,
    InterCompanyCashTransferViewSet,
    ConsolidationRunViewSet,
    FinancialReportTemplateViewSet, FinancialReportViewSet,
    AccountingDocumentViewSet,
    ConsolidationGroupViewSet, ConsolidationViewSet,
)

# Deferred, Leases, Treasury
from .deferred_treasury import (  # noqa: F401
    DeferredRevenueViewSet, DeferredExpenseViewSet,
    LeaseViewSet, LeasePaymentViewSet,
    TreasuryForecastViewSet, InvestmentViewSet, LoanViewSet, LoanRepaymentViewSet,
    ExchangeRateHistoryViewSet, ForeignCurrencyRevaluationViewSet,
)

# Period & Fiscal
from .period_fiscal import (  # noqa: F401
    FiscalPeriodViewSet, FiscalYearViewSet, PeriodAccessViewSet, PeriodCloseCheckViewSet,
    PeriodCloseChecklistView,
)

# Recurring Journals, Accruals, Period Management
from .recurring_accrual import (  # noqa: F401
    RecurringJournalViewSet, RecurringJournalRunViewSet,
    AccrualViewSet, DeferralViewSet,
    PeriodStatusViewSet, YearEndClosingViewSet, RetainedEarningsViewSet,
    CurrencyRevaluationViewSet,
)

# Reports
from .reports import (  # noqa: F401
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
)

# Workflows (Credit/Debit Notes, Bad Debt, Petty Cash, Cheque, Suspense, Budget Period)
from .workflows import (  # noqa: F401
    CreditNoteViewSet, DebitNoteViewSet,
    BadDebtProvisionViewSet, BadDebtWriteOffViewSet,
    PettyCashFundViewSet, PettyCashVoucherViewSet, PettyCashReplenishmentViewSet,
    ChequeRegisterViewSet,
    BudgetPeriodManagementViewSet,
    SuspenseClearingViewSet,
)

# Settings (function-based views)
from .settings_views import accounting_settings_api, seed_default_coa  # noqa: F401
