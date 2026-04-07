"""
accounting.models package
=========================
Re-exports every model class from the sub-modules so that existing code that
imports from `accounting.models` continues to work without modification.
"""

from accounting.models.gl import *
from accounting.models.balances import *
from accounting.models.receivables import *
from accounting.models.assets import *
from accounting.models.tax import *
from accounting.models.intercompany import *
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

    # intercompany.py
    'Company',
    'InterCompanyConfig',
    'InterCompanyInvoice',
    'InterCompanyTransfer',
    'InterCompanyAllocation',
    'InterCompanyCashTransfer',
    'ConsolidationGroup',
    'ConsolidationRun',
    'InterCompany',
    'InterCompanyAccountMapping',
    'InterCompanyTransaction',
    'InterCompanyElimination',
    'Consolidation',

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
]
