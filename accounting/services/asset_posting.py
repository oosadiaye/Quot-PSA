"""
Asset Posting Service — accounting domain.

Handles GL posting for Fixed Asset transactions:
  - Depreciation runs  (Dr Depreciation Expense / Cr Accum Depreciation)
  - Asset disposal      (Dr Accum Depr + Dr Cash|Loss / Cr Asset + Cr Gain)
  - Asset maintenance   (Dr Maintenance Expense / Cr AP or Cash)
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)

# ── Category → DEFAULT_GL_ACCOUNTS key mapping ──────────────────────────
# Maps FixedAsset.asset_category choices to the settings keys for cost,
# accumulated depreciation, and depreciation expense accounts.
CATEGORY_GL_MAP = {
    'Land':      {'cost': 'ASSET_LAND',      'accum_depr': None,                   'depr_expense': None},
    'Building':  {'cost': 'ASSET_BUILDINGS',  'accum_depr': 'ACCUM_DEPR_BUILDINGS', 'depr_expense': 'DEPR_EXPENSE_BUILDINGS'},
    'Equipment': {'cost': 'ASSET_EQUIPMENT',  'accum_depr': 'ACCUM_DEPR_EQUIPMENT', 'depr_expense': 'DEPR_EXPENSE_EQUIPMENT'},
    'IT':        {'cost': 'ASSET_EQUIPMENT',  'accum_depr': 'ACCUM_DEPR_EQUIPMENT', 'depr_expense': 'DEPR_EXPENSE_EQUIPMENT'},
    'Vehicle':   {'cost': 'ASSET_VEHICLES',   'accum_depr': 'ACCUM_DEPR_VEHICLES',  'depr_expense': 'DEPR_EXPENSE_VEHICLES'},
    'Furniture': {'cost': 'ASSET_FURNITURE',  'accum_depr': 'ACCUM_DEPR_FURNITURE', 'depr_expense': 'DEPR_EXPENSE_FURNITURE'},
}


def _resolve_asset_accounts(asset):
    """Resolve cost and accum-depr GL accounts for a FixedAsset.

    Priority:
      1. Per-asset FK overrides (asset.asset_account / asset.accumulated_depreciation_account)
      2. Category-based lookup via DEFAULT_GL_ACCOUNTS
    """
    mapping = CATEGORY_GL_MAP.get(asset.asset_category, {})

    # Cost account
    cost_account = asset.asset_account
    if not cost_account and mapping.get('cost'):
        cost_account = get_gl_account(mapping['cost'], 'Asset')
    if not cost_account:
        raise TransactionPostingError(
            f"No GL cost account for asset {asset.asset_number} "
            f"(category: {asset.asset_category}). "
            f"Set asset.asset_account or add {mapping.get('cost', '???')} to DEFAULT_GL_ACCOUNTS."
        )

    # Accumulated depreciation account
    accum_depr_account = asset.accumulated_depreciation_account
    if not accum_depr_account and mapping.get('accum_depr'):
        accum_depr_account = get_gl_account(mapping['accum_depr'], 'Asset')

    # Depreciation expense account: per-asset FK → per-category key → global fallback
    depr_expense_account = asset.depreciation_expense_account
    if not depr_expense_account and mapping.get('depr_expense'):
        depr_expense_account = get_gl_account(mapping['depr_expense'], 'Expense', 'Depreciation')
    if not depr_expense_account:
        depr_expense_account = get_gl_account('DEPRECIATION_EXPENSE', 'Expense', 'Depreciation')

    return cost_account, accum_depr_account, depr_expense_account


class AssetPostingService(BasePostingService):
    """
    GL posting service for the Fixed Assets domain.

    Covers:
      - Depreciation run posting     (Dr Depreciation Expense / Cr Accum Depr)
      - Asset disposal posting        (Dr Accum Depr + Dr Cash|Loss / Cr Asset + Cr Gain)
      - Asset maintenance cost posting (Dr Maintenance Expense / Cr AP or Cash)
    """

    # ── Depreciation Run ─────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def post_depreciation_run(depreciation_run):
        """Post a DepreciationRun to the General Ledger.

        Creates one journal with N line-pairs (one per asset in the run).

        Journal pattern per asset:
            DR  Depreciation Expense             (66100000 or per-asset override)
            CR  Accumulated Depreciation - [Cat]  (category-specific)

        Args:
            depreciation_run: DepreciationRun instance (status='CALCULATED')

        Returns:
            JournalHeader
        """
        if depreciation_run.status not in ('CALCULATED',):
            raise TransactionPostingError(
                f"DepreciationRun {depreciation_run.pk} must be 'CALCULATED' before posting "
                f"(current: {depreciation_run.status})."
            )
        if depreciation_run.journal_id:
            raise TransactionPostingError(
                f"DepreciationRun {depreciation_run.pk} already posted (journal: {depreciation_run.journal_id})."
            )

        details = depreciation_run.details.select_related('asset').all()
        if not details.exists():
            raise TransactionPostingError(
                f"DepreciationRun {depreciation_run.pk} has no detail lines."
            )

        ref = f"DEP-{depreciation_run.pk}"
        AssetPostingService._check_duplicate_posting(ref)
        AssetPostingService._validate_fiscal_period(depreciation_run.run_date)

        journal = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Depreciation - FY{depreciation_run.fiscal_year} P{depreciation_run.period}",
            posting_date=depreciation_run.run_date,
            status='Posted',
            source_module='assets',
            source_document_id=depreciation_run.pk,
            posted_at=timezone.now(),
        )

        for detail in details:
            amount = Decimal(str(detail.period_depreciation))
            if amount <= 0:
                continue

            asset = detail.asset
            _cost, accum_depr_account, depr_expense_account = _resolve_asset_accounts(asset)

            if not accum_depr_account:
                raise TransactionPostingError(
                    f"No accumulated depreciation account for asset {asset.asset_number} "
                    f"(category: {asset.asset_category}). Cannot post depreciation."
                )
            if not depr_expense_account:
                raise TransactionPostingError(
                    f"No depreciation expense account for asset {asset.asset_number}."
                )

            # DR Depreciation Expense
            JournalLine.objects.create(
                header=journal,
                account=depr_expense_account,
                debit=amount,
                credit=Decimal('0.00'),
                memo=f"Depreciation: {asset.asset_number} - {asset.name}",
            )

            # CR Accumulated Depreciation
            JournalLine.objects.create(
                header=journal,
                account=accum_depr_account,
                debit=Decimal('0.00'),
                credit=amount,
                memo=f"Accum Depr: {asset.asset_number} - {asset.name}",
            )

        AssetPostingService._validate_journal_balanced(journal)
        AssetPostingService._update_gl_balances(journal)

        # Update run record
        depreciation_run.journal_id = journal.pk
        depreciation_run.status = 'POSTED'
        depreciation_run.posted_at = timezone.now()
        depreciation_run.save(update_fields=['journal_id', 'status', 'posted_at'])

        return journal

    # ── Asset Disposal ───────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def post_asset_disposal(disposal):
        """Post an AssetDisposal to the General Ledger.

        Journal pattern:
            DR  Accumulated Depreciation    (remove contra-asset)
            DR  Cash / AR                   (sale proceeds, if any)
            DR  Loss on Disposal            (if NBV > net proceeds)
            CR  Asset Cost Account          (remove asset from BS)
            CR  Gain on Disposal            (if net proceeds > NBV)

        Args:
            disposal: AssetDisposal instance (status='APPROVED')

        Returns:
            JournalHeader
        """
        if disposal.status != 'APPROVED':
            raise TransactionPostingError(
                f"AssetDisposal {disposal.disposal_number} must be 'APPROVED' before posting "
                f"(current: {disposal.status})."
            )
        if disposal.journal_id:
            raise TransactionPostingError(
                f"AssetDisposal {disposal.disposal_number} already posted "
                f"(journal: {disposal.journal_id})."
            )

        asset = disposal.asset
        cost_account, accum_depr_account, _depr_exp = _resolve_asset_accounts(asset)

        ref = f"DSP-{disposal.disposal_number}"
        AssetPostingService._check_duplicate_posting(ref)
        AssetPostingService._validate_fiscal_period(disposal.disposal_date)

        acquisition_cost = Decimal(str(disposal.acquisition_cost or asset.acquisition_cost))
        accum_depr = Decimal(str(disposal.accum_depreciation or asset.accumulated_depreciation))
        nbv = acquisition_cost - accum_depr
        net_proceeds = Decimal(str(disposal.net_proceeds or 0))

        journal = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Disposal - {asset.asset_number} ({disposal.get_disposal_method_display()})",
            posting_date=disposal.disposal_date,
            status='Posted',
            source_module='assets',
            source_document_id=disposal.pk,
            posted_at=timezone.now(),
        )

        # DR Accumulated Depreciation (remove contra-asset)
        if accum_depr > 0 and accum_depr_account:
            JournalLine.objects.create(
                header=journal,
                account=accum_depr_account,
                debit=accum_depr,
                credit=Decimal('0.00'),
                memo=f"Remove accum depr: {asset.asset_number}",
            )

        # DR Cash/AR (sale proceeds)
        if net_proceeds > 0:
            cash_account = get_gl_account('CASH_ACCOUNT', 'Asset', 'Cash')
            if not cash_account:
                raise TransactionPostingError("Cash account not found for disposal proceeds.")
            JournalLine.objects.create(
                header=journal,
                account=cash_account,
                debit=net_proceeds,
                credit=Decimal('0.00'),
                memo=f"Disposal proceeds: {asset.asset_number}",
            )

        # Gain or Loss
        gain_loss = net_proceeds - nbv
        if gain_loss > 0:
            # Gain on disposal
            gain_account = get_gl_account('GAIN_ON_DISPOSAL', 'Income', 'Gain')
            if not gain_account:
                raise TransactionPostingError("Gain on Disposal account not found.")
            JournalLine.objects.create(
                header=journal,
                account=gain_account,
                debit=Decimal('0.00'),
                credit=gain_loss,
                memo=f"Gain on disposal: {asset.asset_number}",
            )
        elif gain_loss < 0:
            # Loss on disposal
            loss_account = get_gl_account('LOSS_ON_DISPOSAL', 'Expense', 'Loss')
            if not loss_account:
                raise TransactionPostingError("Loss on Disposal account not found.")
            JournalLine.objects.create(
                header=journal,
                account=loss_account,
                debit=abs(gain_loss),
                credit=Decimal('0.00'),
                memo=f"Loss on disposal: {asset.asset_number}",
            )

        # CR Asset Cost Account (remove asset from balance sheet)
        JournalLine.objects.create(
            header=journal,
            account=cost_account,
            debit=Decimal('0.00'),
            credit=acquisition_cost,
            memo=f"Remove asset: {asset.asset_number}",
        )

        AssetPostingService._validate_journal_balanced(journal)
        AssetPostingService._update_gl_balances(journal)

        # Update disposal and asset records
        disposal.journal_id = journal.pk
        disposal.gain_on_disposal = max(gain_loss, Decimal('0'))
        disposal.loss_on_disposal = abs(min(gain_loss, Decimal('0')))
        disposal.net_book_value = nbv
        disposal.status = 'POSTED'
        disposal.save(update_fields=[
            'journal_id', 'gain_on_disposal', 'loss_on_disposal',
            'net_book_value', 'status',
        ])

        # Mark asset as Disposed
        asset.status = 'Disposed'
        asset.save(update_fields=['status'])

        return journal

    # ── Asset Maintenance ────────────────────────────────────────────────

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
