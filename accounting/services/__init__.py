"""Accounting Services Package — Quot PSE (Public Sector Edition)

Services for government IFMIS financial operations:
    - journal_validation: Journal balance and validation logic
    - ipsas_journal_service: IPSAS-compliant journal posting engine
    - ncoa_service: NCoA code resolution and validation
    - tax_calculation: Automatic tax and WHT calculation
    - period_control: Unified period control across all modules
    - audit_trail: Comprehensive transaction audit logging
    - journal_sequence: Journal sequence integrity and hash chains
    - approval_workflow: Configurable multi-level approval engine
    - dual_control: Large transaction approval requirements
    - bank_reconciliation: Automated bank statement matching
    - currency_revaluation: Scheduled FX revaluation
    - depreciation_service: Depreciation calculation
    - cost_allocation: Automatic cost distribution
    - xbrl_export: XBRL/iXBRL export for audit reporting
    - asset_revaluation: Asset revaluation per IPSAS 17
    - trial_balance: Trial balance report generator
    - aging_reports: AR/AP aging reports
    - vat_returns: VAT return processing
    - gl_posting: GL balance update service

Transaction Posting:
    - base_posting: Shared exception, get_gl_account(), BasePostingService
    - procurement_posting: Purchase Orders, GRN, Vendor Invoices, Payments
    - inventory_posting: Stock Movements, Transfers, Reconciliations
    - payroll_posting: Payroll Runs and Reversals
"""

from .journal_validation import JournalValidationService
from .tax_calculation import TaxCalculationService
from .period_control import PeriodControlService
from .audit_trail import AuditTrailService
from .journal_sequence import JournalSequenceService
from .approval_workflow import ApprovalWorkflowService
from .dual_control import DualControlService
from .bank_reconciliation import BankReconciliationService
from .currency_revaluation import CurrencyRevaluationService
from .depreciation_service import DepreciationService
from .cost_allocation import CostAllocationService
from .xbrl_export import XBRLExportService
from .asset_revaluation import AssetRevaluationRunService
from .trial_balance import TrialBalanceService
from .aging_reports import AgingReportService
from .vat_returns import VATReturnService
from .gl_posting import update_gl_from_journal

# Transaction posting domain services
from .base_posting import TransactionPostingError, get_gl_account, BasePostingService
from .procurement_posting import ProcurementPostingService
from .inventory_posting import InventoryPostingService
from .payroll_posting import PayrollPostingService

# IPSAS & NCoA services (new for Quot PSE)
from .ipsas_journal_service import IPSASJournalService, JournalPostingError

__all__ = [
    'JournalValidationService',
    'TaxCalculationService',
    'PeriodControlService',
    'AuditTrailService',
    'JournalSequenceService',
    'ApprovalWorkflowService',
    'DualControlService',
    'BankReconciliationService',
    'CurrencyRevaluationService',
    'DepreciationService',
    'CostAllocationService',
    'XBRLExportService',
    'AssetRevaluationRunService',
    'TrialBalanceService',
    'AgingReportService',
    'VATReturnService',
    'update_gl_from_journal',
    # Transaction posting
    'TransactionPostingError',
    'get_gl_account',
    'BasePostingService',
    'ProcurementPostingService',
    'InventoryPostingService',
    'PayrollPostingService',
    # IPSAS
    'IPSASJournalService',
    'JournalPostingError',
]
