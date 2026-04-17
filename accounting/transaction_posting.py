"""
Real-time Transaction Posting Service — Facade Module (Quot PSE)

This module is a backward-compatible facade. All implementation has been
moved into domain-specific services under accounting/services/:

    base_posting.py        — shared exception, get_gl_account(), BasePostingService
    procurement_posting.py — Purchase Orders, GRN, Vendor Invoices, Payments, Returns
    inventory_posting.py   — Stock Movements, Transfers, Stock Reconciliations
    asset_posting.py       — Fixed Asset Maintenance
    payroll_posting.py     — Payroll Runs and Payroll Reversals

Removed for public sector (modules deleted):
    sales_posting, production_posting, service_posting, quality_posting
"""

from accounting.services.base_posting import TransactionPostingError, get_gl_account
from accounting.services.procurement_posting import ProcurementPostingService
from accounting.services.inventory_posting import InventoryPostingService
from accounting.services.asset_posting import AssetPostingService
from accounting.services.payroll_posting import PayrollPostingService


class TransactionPostingService(
    ProcurementPostingService,
    InventoryPostingService,
    AssetPostingService,
    PayrollPostingService,
):
    """Unified facade — imports all remaining domain posting services."""
    pass


__all__ = [
    'TransactionPostingError',
    'get_gl_account',
    'TransactionPostingService',
]
