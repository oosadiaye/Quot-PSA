"""Accounting Services Package

This package contains business logic services for the accounting module.
Each service handles a specific domain of accounting operations.

Services:
    - journal_validation: Journal balance and validation logic
    - tax_calculation: Automatic tax and WHT calculation
    - period_control: Unified period control across all modules
    - audit_trail: Comprehensive transaction audit logging
    - journal_sequence: Journal sequence integrity and hash chains
    - approval_workflow: Configurable multi-level approval engine
    - dual_control: Large transaction approval requirements
    - bank_reconciliation: Automated bank statement matching
    - currency_revaluation: Scheduled FX revaluation
    - depreciation_service: Depreciation calculation and consolidation
    - cost_allocation: Automatic cost distribution
    - xbrl_export: XBRL/iXBRL export for audit reporting
    - asset_revaluation: Asset revaluation per IAS 16
    - trial_balance: Trial balance report generator
    - aging_reports: AR/AP aging reports
    - vat_returns: VAT return processing

Transaction Posting Domain Services:
    - base_posting: Shared exception, get_gl_account(), and BasePostingService
    - sales_posting: Sales Orders, Delivery Notes, Returns, Credit Notes, Receipts
    - procurement_posting: Purchase Orders, GRN, Vendor Invoices, Payments, Returns
    - inventory_posting: Stock Movements, Transfers, Stock Reconciliations
    - production_posting: Production Orders, Material Issues/Receipts, Work Orders
    - payroll_posting: Payroll Runs and Payroll Reversals
    - service_posting: Service Tickets
    - quality_posting: Quality Inspections and Non-Conformance Reports
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
from .gl_posting import update_gl_from_journal, InterCompanyPostingService, ConsolidationService

# Transaction posting domain services
from .base_posting import TransactionPostingError, get_gl_account, BasePostingService
from .sales_posting import SalesPostingService
from .procurement_posting import ProcurementPostingService
from .inventory_posting import InventoryPostingService
from .production_posting import ProductionPostingService
from .payroll_posting import PayrollPostingService
from .service_posting import ServicePostingService
from .quality_posting import QualityPostingService

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
    'InterCompanyPostingService',
    'ConsolidationService',
    # Transaction posting
    'TransactionPostingError',
    'get_gl_account',
    'BasePostingService',
    'SalesPostingService',
    'ProcurementPostingService',
    'InventoryPostingService',
    'ProductionPostingService',
    'PayrollPostingService',
    'ServicePostingService',
    'QualityPostingService',
]
