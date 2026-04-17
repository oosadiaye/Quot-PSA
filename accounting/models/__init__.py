"""
accounting.models package
=========================
Re-exports every model class from the sub-modules so that existing code that
imports from `accounting.models` continues to work without modification.
"""

from accounting.models.gl import *
from accounting.models.ncoa import *
from accounting.models.balances import *
from accounting.models.receivables import *
from accounting.models.assets import *
from accounting.models.tax import *
from accounting.models.treasury import *
from accounting.models.revenue import *
from accounting.models.tsa_reconciliation import *
from accounting.models.report_snapshot import ReportSnapshot  # noqa: F401
from accounting.models.provision import (  # noqa: F401
    Provision, ContingentLiability, ContingentAsset,
)
from accounting.models.mda_import_log import MDAImportLog  # noqa: F401
from accounting.models.intangible_asset import IntangibleAsset  # noqa: F401
from accounting.models.opening_balance import (  # noqa: F401
    OpeningBalanceSheet, OpeningBalanceItem,
)
from accounting.models.pension import (  # noqa: F401
    PensionScheme, ActuarialValuation, PensionContribution,
)
from accounting.models.social_benefit import (  # noqa: F401
    SocialBenefitScheme, SocialBenefitClaim,
)
from accounting.models.advanced import *
from accounting.models.audit import *

__all__ = [
    # gl.py — soft-delete infrastructure (importable by other apps)
    'SoftDeleteMixin',
    'SoftDeleteManager',
    # gl.py
    'tenant_upload_path',
    'Fund',
    'Function',
    'Program',
    'Geo',
    'Account',
    'MDA',
    'TransactionSequence',
    'JournalHeader',
    'JournalLine',
    'JournalReversal',
    'Currency',

    # balances.py
    'GLBalance',
    'BudgetPeriod',
    'Budget',
    'BudgetEncumbrance',
    'BankAccount',
    'BudgetCheckLog',
    'BudgetAmendment',
    'BudgetTransfer',
    'BudgetForecast',
    'BudgetAnomaly',

    # receivables.py
    'VendorInvoice',
    'VendorInvoiceLine',
    'Payment',
    'PaymentAllocation',
    'CustomerInvoice',
    'CustomerInvoiceLine',
    'Receipt',
    'ReceiptAllocation',
    'Checkbook',
    'Check',
    'BankReconciliation',
    'CashFlowCategory',
    'CashFlowForecast',

    # assets.py
    'CostCenter',
    'JournalLineCostCenter',
    'ProfitCenter',
    'CostAllocationRule',
    'AssetClass',
    'AssetCategory',
    'AssetConfiguration',
    'AssetLocation',
    'FixedAsset',
    'DepreciationSchedule',
    'AssetInsurance',
    'AssetMaintenance',
    'MaintenanceBudget',
    'AssetTransfer',
    'AssetDepreciationSchedule',
    'AssetImpairment',
    'AssetRevaluationRun',
    'AssetRevaluationDetail',
    'AssetDisposal',
    'DepreciationRun',
    'DepreciationDetail',

    # tax.py
    'TaxRegistration',
    'TaxExemption',
    'TaxReturn',
    'WithholdingTax',
    'TaxCode',
    'TaxRate',
    'VATReturn',
    'VATReturnDetail',
    'WHTCertificate',

    # ncoa.py — Nigeria National Chart of Accounts (52-digit, 6-segment)
    'AdministrativeSegment',
    'EconomicSegment',
    'FunctionalSegment',
    'ProgrammeSegment',
    'FundSegment',
    'GeographicSegment',
    'NCoACode',

    # treasury.py — TSA & Payment Vouchers
    'TreasuryAccount',
    'PaymentVoucherGov',
    'PaymentInstruction',

    # revenue.py — IGR Revenue Collection
    'RevenueHead',
    'RevenueCollection',

    # tsa_reconciliation.py — Treasury bank reconciliation
    'TSABankStatement',
    'TSABankStatementLine',
    'TSAReconciliation',

    # advanced.py
    'FinancialReportTemplate',
    'FinancialReport',
    'ReportColumnConfig',
    'AccountingDocument',
    'DocumentSignature',
    'FiscalPeriod',
    'FiscalYear',
    'PeriodAccess',
    'PeriodCloseCheck',
    'DeferredRevenue',
    'DeferredExpense',
    'AmortizationSchedule',
    'Lease',
    'LeasePayment',
    'TreasuryForecast',
    'Investment',
    'Loan',
    'LoanRepayment',
    'ExchangeRateHistory',
    'ForeignCurrencyRevaluation',
    'RecurringJournal',
    'RecurringJournalLine',
    'RecurringJournalRun',
    'Accrual',
    'Deferral',
    'DeferralRecognition',
    'PeriodStatus',
    'CurrencyRevaluation',
    'RetainedEarnings',
    'AccountingSettings',
    'CurrencyRevaluationRun',
    'CurrencyRevaluationDetail',
    'CostAllocationRun',
    'CostAllocationDetail',
    'XBRLReport',
    'PettyCashFund',
    'PettyCashVoucher',
    'PettyCashReplenishment',
    'ChequeRegister',
    'PaymentVoucher',
    'BankStatement',
    'BankStatementLine',
    'CashFlowEntry',

    # audit.py
    'TransactionAuditLog',
    'ApprovalRule',
    'ApprovalLevel',
    'ApprovalInstance',
    'DualControlSetting',
    'DualControlOverride',
    'CustomerAging',
    'BadDebtProvision',
    'BadDebtWriteOff',
    'CreditNote',
    'DebitNote',
    'SuspenseClearing',
    'FinancialRatio',
    'PeriodClosing',
    'YearEndClosing',

    # report_snapshot.py — S10-03
    'ReportSnapshot',

    # provision.py — S10-04 — IPSAS 19
    'Provision',
    'ContingentLiability',
    'ContingentAsset',

    # mda_import_log.py — S12-01
    'MDAImportLog',

    # intangible_asset.py — S12-03 — IPSAS 31
    'IntangibleAsset',

    # opening_balance.py — S12-05 — IPSAS 33
    'OpeningBalanceSheet',
    'OpeningBalanceItem',

    # pension.py — S14-01 — IPSAS 39
    'PensionScheme',
    'ActuarialValuation',
    'PensionContribution',

    # social_benefit.py — S14-02 — IPSAS 42
    'SocialBenefitScheme',
    'SocialBenefitClaim',
]
