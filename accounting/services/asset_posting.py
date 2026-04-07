"""
Asset Posting Service — accounting domain.

Handles GL posting for Fixed Asset maintenance transactions.
Called by AssetMaintenance.post_to_gl() to keep GL logic out of models.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


class AssetPostingService(BasePostingService):
    """
    GL posting service for the Fixed Assets domain.

    Covers:
      - Asset Maintenance cost posting (Dr Maintenance Expense / Cr AP or Cash)
    """

    @staticmethod
    @transaction.atomic
    def post_asset_maintenance(maintenance):
        """
        Post asset maintenance costs to the General Ledger.

        Journal entry:
            DR  Maintenance & Repairs Expense  (61300000)
            CR  Accounts Payable               (if vendor exists)
               or Cash                         (if no vendor — petty cash maintenance)

        Args:
            maintenance: AssetMaintenance instance (status='Completed', journal_entry=None)

        Returns:
            JournalHeader: The posted journal, or None if preconditions not met.
        """
        if maintenance.status != 'Completed':
            raise TransactionPostingError(
                f"AssetMaintenance {maintenance.pk} must be 'Completed' before GL posting "
                f"(current status: {maintenance.status})."
            )
        if maintenance.journal_entry_id:
            raise TransactionPostingError(
                f"AssetMaintenance {maintenance.pk} has already been posted "
                f"(journal: {maintenance.journal_entry})."
            )

        ref = f"MTN-{maintenance.pk}"
        AssetPostingService._check_duplicate_posting(ref)
        AssetPostingService._validate_fiscal_period(timezone.now().date())

        total_cost = Decimal(str(maintenance.total_cost or 0))
        if total_cost <= 0:
            raise TransactionPostingError(
                f"AssetMaintenance {maintenance.pk} has zero or negative total_cost."
            )

        # Resolve accounts
        expense_account = get_gl_account('MAINTENANCE_EXPENSE', 'Expense', 'Maintenance')
        if not expense_account:
            # Fall back to the Maintenance and Repairs parent account
            from accounting.models import Account
            expense_account = Account.objects.filter(code='61300000', is_active=True).first()
        if not expense_account:
            raise TransactionPostingError(
                "Maintenance Expense account not found. "
                "Add MAINTENANCE_EXPENSE to DEFAULT_GL_ACCOUNTS or ensure code 61300000 exists."
            )

        if maintenance.vendor:
            credit_account = get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
        else:
            credit_account = get_gl_account('CASH_ACCOUNT', 'Asset', 'Cash')

        if not credit_account:
            raise TransactionPostingError(
                "Credit account (AP or Cash) not found for maintenance posting."
            )

        asset_ref = maintenance.asset.asset_number if maintenance.asset else f"ASSET-{maintenance.pk}"
        description = f"Maintenance - {asset_ref}"

        journal = JournalHeader.objects.create(
            reference_number=ref,
            description=description,
            posting_date=timezone.now().date(),
            status='Posted',
            mda=maintenance.asset.mda if (maintenance.asset and hasattr(maintenance.asset, 'mda')) else None,
            source_module='assets',
            source_document_id=maintenance.pk,
            posted_at=timezone.now(),
        )

        # DR Maintenance Expense
        JournalLine.objects.create(
            header=journal,
            account=expense_account,
            debit=total_cost,
            credit=Decimal('0.00'),
            memo=f"Maintenance: {asset_ref}",
        )

        # CR Accounts Payable / Cash
        cr_memo = f"Vendor: {maintenance.vendor.name}" if maintenance.vendor else f"Cash payment: {asset_ref}"
        JournalLine.objects.create(
            header=journal,
            account=credit_account,
            debit=Decimal('0.00'),
            credit=total_cost,
            memo=cr_memo,
        )

        AssetPostingService._validate_journal_balanced(journal)
        AssetPostingService._update_gl_balances(journal)
        return journal
