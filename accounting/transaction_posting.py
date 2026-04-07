"""
Real-time Transaction Posting Service — Facade Module

This module is a backward-compatible facade. All implementation has been
moved into domain-specific services under accounting/services/:

    base_posting.py        — shared exception, get_gl_account(), BasePostingService
    sales_posting.py       — Sales Orders, Delivery Notes, Returns, Credit Notes, Receipts
    procurement_posting.py — Purchase Orders, GRN, Vendor Invoices, Payments, Returns
    inventory_posting.py   — Stock Movements, Transfers, Stock Reconciliations
    production_posting.py  — Production Orders, Material Issues/Receipts, Work Orders
    asset_posting.py       — Fixed Asset Maintenance
    payroll_posting.py     — Payroll Runs and Payroll Reversals
    service_posting.py     — Service Tickets
    quality_posting.py     — Quality Inspections and Non-Conformance Reports

All existing callers that import TransactionPostingService, TransactionPostingError,
or get_gl_account from this module continue to work without any changes.
"""

from accounting.services.base_posting import TransactionPostingError, get_gl_account
from accounting.services.sales_posting import SalesPostingService
from accounting.services.procurement_posting import ProcurementPostingService
from accounting.services.inventory_posting import InventoryPostingService
from accounting.services.production_posting import ProductionPostingService
from accounting.services.asset_posting import AssetPostingService
from accounting.services.payroll_posting import PayrollPostingService
from accounting.services.service_posting import ServicePostingService
from accounting.services.quality_posting import QualityPostingService


class TransactionPostingService(
    SalesPostingService,
    ProcurementPostingService,
    InventoryPostingService,
    ProductionPostingService,
    AssetPostingService,
    PayrollPostingService,
    ServicePostingService,
    QualityPostingService,
):
    """Unified facade — imports all domain posting services."""
    pass


__all__ = [
    'TransactionPostingError',
    'get_gl_account',
    'TransactionPostingService',
]
