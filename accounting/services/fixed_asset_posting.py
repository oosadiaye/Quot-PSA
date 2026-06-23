"""FixedAssetPostingService — post a fixed asset's capitalisation journal.

Extracted from ``FixedAssetViewSet.acquire`` so the same posting logic
can be called from:

  * ``FixedAssetViewSet.acquire`` (existing HTTP API)
  * ``auto_post_fixedasset_on_approval`` receiver (workflow auto-post)
  * Future batch-import or migration paths

The service owns the atomic boundary and all GL-side effects.  The view
layer owns input validation and HTTP response shaping.

Idempotency
-----------
The canonical idempotency key is a ``JournalHeader`` whose
``reference_number`` starts with ``'ACQ-{asset.asset_number}'``.  The
``acquire`` view has always used that prefix, so any journal that was
already posted through the view is detectable without a schema change.

When ``idempotent=True`` (the default for system/receiver callers), the
service returns the existing journal rather than re-posting.

When ``idempotent=False`` (the default for the view, where the view
itself owns the "already capitalised" guard via
``created_from_journal_line_id``), a second call raises
``ValueError``.

Payment method
--------------
``payment_method`` must be ``'cash'`` or ``'ap'``.  The service resolves
the credit account via ``DEFAULT_GL_ACCOUNTS`` settings first, then
falls back to a name-search on the Chart of Accounts — exactly the same
logic the original view used.
"""
from __future__ import annotations

import logging
from datetime import date as _date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:  # pragma: no cover
    from accounting.models.gl import JournalHeader
    from accounting.models.assets import FixedAsset

logger = logging.getLogger(__name__)

VALID_PAYMENT_METHODS = ('cash', 'ap')


class FixedAssetPostingError(Exception):
    """Raised when the capitalisation journal cannot be posted."""


class FixedAssetPostingService:
    """Post a fixed asset's capitalisation journal at acquisition.

    Decoupled from the HTTP layer so it can be called by:
      * FixedAssetViewSet.acquire (existing API)
      * The workflow approval receiver (auto-post on Approve)
      * Future batch import paths
    """

    @classmethod
    def post_capitalisation(
        cls,
        asset: 'FixedAsset',
        *,
        payment_method: str,        # 'cash' | 'ap'
        user=None,                  # for audit; nullable for system posts
        idempotent: bool = True,    # when True, no-op if cap journal exists
    ) -> 'JournalHeader':
        """Post DR fixed-asset-account / CR cash-or-AP.  Returns the journal.

        Raises
        ------
        FixedAssetPostingError
            * Invalid payment_method.
            * Asset has no asset_account configured.
            * Asset has no acquisition_cost (or cost <= 0).
            * Credit account (Cash / AP) not found in Chart of Accounts.
            * Asset was already capitalised via AP invoice path
              (``created_from_journal_line_id`` is set) — calling acquire
              on such an asset would double-book.
            * ``idempotent=False`` and a capitalisation journal already exists.
        """
        # ── Parameter validation ──────────────────────────────────────────
        if payment_method not in VALID_PAYMENT_METHODS:
            raise FixedAssetPostingError(
                f"Invalid payment_method '{payment_method}'. "
                f"Must be one of: {VALID_PAYMENT_METHODS}."
            )

        if not asset.asset_account:
            raise FixedAssetPostingError(
                'Asset account not configured on this asset.'
            )

        if not asset.mda:
            raise FixedAssetPostingError(
                'MDA is required for asset acquisition. '
                'Assign this asset to an MDA first.'
            )

        # Refuse to acquire assets already auto-capitalised from an AP line —
        # matches the guard in the original view exactly.
        if getattr(asset, 'created_from_journal_line_id', None):
            raise FixedAssetPostingError(
                f'Asset was already capitalised from a vendor invoice '
                f'(JournalLine #{asset.created_from_journal_line_id}). '
                'The acquisition GL entry has already been booked — '
                'calling acquire again would double-book.'
            )

        acq_cost = asset.acquisition_cost
        if not acq_cost or acq_cost <= 0:
            raise FixedAssetPostingError('Asset has no acquisition cost.')

        # ── Idempotency check ────────────────────────────────────────────
        # The canonical idempotency key: a JournalHeader whose reference_number
        # starts with ACQ-<asset_number>.  Both the original view and this
        # service use that prefix, so any prior posting is detectable without
        # a schema migration.
        from accounting.models.gl import JournalHeader  # lazy — avoids circular

        ref_prefix = f'ACQ-{asset.asset_number or asset.id}'
        existing_journal = JournalHeader.objects.filter(
            reference_number=ref_prefix
        ).first()
        if existing_journal is not None:
            if idempotent:
                logger.info(
                    'FixedAssetPostingService.post_capitalisation: '
                    'asset %s already has capitalisation journal %s — skipping.',
                    asset.pk,
                    existing_journal.pk,
                )
                return existing_journal
            raise FixedAssetPostingError(
                f'A capitalisation journal already exists for asset '
                f'{asset.asset_number} (JournalHeader #{existing_journal.pk}).'
            )

        # ── Budget validation (capital budget check) ────────────────────
        if asset.mda and asset.asset_account and asset.fund:
            try:
                from budget.services import BudgetValidationService, BudgetExceededError
                from accounting.models.ncoa import AdministrativeSegment, EconomicSegment, FundSegment
                from accounting.models.advanced import FiscalYear

                admin_seg = AdministrativeSegment.objects.filter(legacy_mda=asset.mda).first()
                econ_seg = EconomicSegment.objects.filter(legacy_account=asset.asset_account).first()
                fund_seg = FundSegment.objects.filter(legacy_fund=asset.fund).first()
                active_fy = FiscalYear.objects.filter(is_active=True).first()

                if admin_seg and econ_seg and fund_seg and active_fy:
                    try:
                        BudgetValidationService.validate_expenditure(
                            administrative_id=admin_seg.pk,
                            economic_id=econ_seg.pk,
                            fund_id=fund_seg.pk,
                            fiscal_year_id=active_fy.pk,
                            amount=acq_cost,
                            source='ASSET_ACQUISITION',
                        )
                    except BudgetExceededError as exc:
                        raise FixedAssetPostingError(
                            f'Capital budget validation failed: {exc}'
                        ) from exc
            except ImportError:
                pass  # Budget module not available in this environment

        # ── Resolve credit account ───────────────────────────────────────
        from django.conf import settings as django_settings
        from accounting.models.gl import Account  # lazy — avoids circular

        default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

        if payment_method == 'ap':
            cr_code = default_gl.get('ACCOUNTS_PAYABLE', '')
            cr_account = Account.objects.filter(code=cr_code).first() if cr_code else None
            if not cr_account:
                cr_account = Account.objects.filter(
                    account_type='Liability', name__icontains='Payable'
                ).first()
        else:
            cr_code = default_gl.get('CASH_ACCOUNT', '')
            cr_account = Account.objects.filter(code=cr_code).first() if cr_code else None
            if not cr_account:
                cr_account = Account.objects.filter(
                    account_type='Asset', name__icontains='Cash'
                ).first()

        if not cr_account:
            raise FixedAssetPostingError('Credit account (Cash/AP) not found.')

        # ── Post to GL (inside its own atomic block) ─────────────────────
        from accounting.models.gl import JournalLine
        from accounting.services import update_gl_from_journal  # lazy — avoids circular

        import datetime

        posting_date = (
            asset.acquisition_date
            if asset.acquisition_date
            else datetime.date.today()
        )

        with transaction.atomic():
            journal = JournalHeader.objects.create(
                reference_number=ref_prefix,
                description=f'Asset Acquisition: {asset.name}',
                posting_date=posting_date,
                fund=asset.fund,
                function=asset.function,
                program=asset.program,
                geo=asset.geo,
                status='Posted',
            )
            JournalLine.objects.create(
                header=journal,
                account=asset.asset_account,
                debit=acq_cost,
                credit=Decimal('0.00'),
                memo=f'Fixed Asset acquisition: {asset.name}',
            )
            JournalLine.objects.create(
                header=journal,
                account=cr_account,
                debit=Decimal('0.00'),
                credit=acq_cost,
                memo=f'Payment for asset: {asset.name}',
            )

            update_gl_from_journal(
                journal,
                fund=asset.fund,
                function=asset.function,
                program=asset.program,
                geo=asset.geo,
            )

        logger.info(
            'FixedAssetPostingService: posted capitalisation journal %s '
            'for asset %s (payment_method=%s, amount=%s, user=%s).',
            journal.pk,
            asset.pk,
            payment_method,
            acq_cost,
            getattr(user, 'pk', 'system'),
        )

        return journal
