"""
IPSAS 31 intangible-asset monthly amortisation scheduler.

Given a target (year, month), builds one journal that debits the
Amortisation Expense account and credits the Accumulated Amortisation
account for every active intangible asset whose useful life hasn't
expired and whose monthly charge is non-zero.

Idempotency
-----------
Re-running the scheduler for the same (year, month) is **not** silently
safe — it would double-charge the expense and double the accumulated
amortisation. The service records a stamp in each asset's ``notes``
field of the form ``AMORT:YYYY-MM`` and refuses to post if every
eligible asset already has that stamp. When a mix is found (some new
assets added since the last run, some already stamped), only the
unstamped assets get a journal line.

Result shape
------------
    AmortisationRunResult(
        year, month,
        journal_id,
        journal_reference,
        assets_posted,
        assets_skipped,
        total_amortisation,
    )

Non-goals
---------
This service handles ONLY the straight-line method. Reducing-balance
and units-of-use require per-period curve tracking; those assets are
skipped with a marker in ``assets_skipped``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import F


@dataclass
class AmortisationRunResult:
    year: int
    month: int
    journal_id: Optional[int] = None
    journal_reference: str = ''
    assets_posted: int = 0
    assets_skipped: int = 0
    total_amortisation: Decimal = field(default_factory=lambda: Decimal('0'))
    skipped_details: list[dict] = field(default_factory=list)


class AmortisationRunError(Exception):
    """Raised when the run cannot proceed (bad config, missing accounts, etc.)."""


class IntangibleAmortisationService:

    @classmethod
    def run_monthly(
        cls,
        *,
        year: int,
        month: int,
        user=None,
        dry_run: bool = False,
    ) -> AmortisationRunResult:
        """Build and post the monthly amortisation journal.

        ``dry_run=True`` does all validation + stamp checking but does
        not save. Useful for previewing what would post before actually
        committing.
        """
        from accounting.models import (
            IntangibleAsset, AccountingSettings, Account,
            JournalHeader, JournalLine,
        )

        if not (1 <= month <= 12):
            raise AmortisationRunError(
                f'month must be 1-12, got {month!r}.'
            )

        settings_obj = AccountingSettings.objects.first()
        exp_code = _resolve_setting_code(
            settings_obj, 'intangible_amortisation_expense_code', '22301000',
        )
        acc_code = _resolve_setting_code(
            settings_obj, 'intangible_accumulated_amortisation_code', '32201000',
        )

        expense_account = Account.objects.filter(code=exp_code).first()
        accum_account = Account.objects.filter(code=acc_code).first()
        if expense_account is None:
            raise AmortisationRunError(
                f'Amortisation expense account {exp_code!r} is not in the '
                f'chart of accounts. Configure '
                f'AccountingSettings.intangible_amortisation_expense_code.'
            )
        if accum_account is None:
            raise AmortisationRunError(
                f'Accumulated amortisation account {acc_code!r} is not in '
                f'the chart of accounts. Configure '
                f'AccountingSettings.intangible_accumulated_amortisation_code.'
            )

        period_stamp = f'AMORT:{year:04d}-{month:02d}'
        posting_date = cls._month_end(year, month)

        result = AmortisationRunResult(year=year, month=month)

        # ── Eligibility pass ─────────────────────────────────────────
        # Only ACTIVE, straight-line, not-fully-amortised, not-yet-
        # stamped-for-this-period assets with a non-zero monthly charge.
        eligible = (
            IntangibleAsset.objects
            .filter(status='ACTIVE', amortisation_method='STRAIGHT_LINE')
            .exclude(useful_life_months__isnull=True)
            .exclude(useful_life_months__lte=0)
            .select_related('mda')
        )

        lines_to_post: list[dict] = []
        for asset in eligible:
            skip_reason = cls._should_skip(asset, period_stamp)
            if skip_reason is not None:
                result.assets_skipped += 1
                result.skipped_details.append({
                    'asset_id':     asset.id,
                    'asset_number': asset.asset_number,
                    'reason':       skip_reason,
                })
                continue
            charge = asset.monthly_amortisation
            if charge <= 0:
                result.assets_skipped += 1
                result.skipped_details.append({
                    'asset_id':     asset.id,
                    'asset_number': asset.asset_number,
                    'reason':       'Zero monthly charge.',
                })
                continue
            # Cap the charge so we never drive carrying amount below residual.
            charge = cls._cap_to_remaining(asset, charge)
            if charge <= 0:
                result.assets_skipped += 1
                result.skipped_details.append({
                    'asset_id':     asset.id,
                    'asset_number': asset.asset_number,
                    'reason':       'Remaining amortisable balance is zero.',
                })
                continue
            lines_to_post.append({
                'asset':  asset,
                'charge': charge,
            })
            result.total_amortisation += charge

        if dry_run or not lines_to_post:
            # Return the plan without posting; caller can inspect.
            return result

        # ── Post the journal atomically ───────────────────────────────
        reference = f'INTAN-AMORT-{year:04d}-{month:02d}'

        with transaction.atomic():
            header = JournalHeader.objects.create(
                posting_date=posting_date,
                description=(
                    f'Monthly amortisation of intangible assets '
                    f'(IPSAS 31) — {year:04d}-{month:02d}. '
                    f'{len(lines_to_post)} asset(s), total '
                    f'NGN {result.total_amortisation:,.2f}.'
                ),
                reference_number=reference,
                status='Draft',
                source_module='intangible_amortisation',
            )

            journal_lines = []
            asset_updates = []
            for plan in lines_to_post:
                asset = plan['asset']
                charge = plan['charge']
                # DR expense
                journal_lines.append(JournalLine(
                    header=header,
                    account=expense_account,
                    debit=charge,
                    credit=Decimal('0'),
                    memo=(
                        f'Amortisation {asset.asset_number} '
                        f'({asset.name})'
                    ),
                ))
                # CR accumulated amortisation
                journal_lines.append(JournalLine(
                    header=header,
                    account=accum_account,
                    debit=Decimal('0'),
                    credit=charge,
                    memo=(
                        f'Accumulated amortisation {asset.asset_number}'
                    ),
                ))
                asset_updates.append((asset.id, charge, asset.notes))

            JournalLine.objects.bulk_create(journal_lines)

            # Flip journal to Posted.
            from django.utils import timezone
            header.status = 'Posted'
            header.posted_at = timezone.now()
            header.save(update_fields=['status', 'posted_at'])

            # Bump accumulated_amortisation + stamp the notes on each asset.
            for asset_id, charge, prior_notes in asset_updates:
                new_notes = (prior_notes + '\n' if prior_notes else '') + period_stamp
                IntangibleAsset.objects.filter(pk=asset_id).update(
                    accumulated_amortisation=F('accumulated_amortisation') + charge,
                    notes=new_notes,
                )

            result.journal_id = header.pk
            result.journal_reference = header.reference_number
            result.assets_posted = len(lines_to_post)

        return result

    # ── Helpers ────────────────────────────────────────────────────────

    @classmethod
    def _should_skip(cls, asset, period_stamp: str) -> Optional[str]:
        """Return a human reason to skip, or None if the asset is eligible."""
        if asset.is_fully_amortised:
            return 'Fully amortised.'
        if period_stamp in (asset.notes or ''):
            return f'Already stamped for this period ({period_stamp}).'
        return None

    @classmethod
    def _cap_to_remaining(cls, asset, charge: Decimal) -> Decimal:
        """Never post more than the remaining amortisable balance.

        Remaining = carrying_amount − residual_value. If this month's
        normal straight-line charge would exceed it (last month of useful
        life), cap to the residual.
        """
        residual = asset.residual_value or Decimal('0')
        remaining = asset.carrying_amount - residual
        if remaining <= 0:
            return Decimal('0')
        return charge if charge <= remaining else remaining

    @staticmethod
    def _month_end(year: int, month: int) -> _date:
        from calendar import monthrange
        return _date(year, month, monthrange(year, month)[1])


def _resolve_setting_code(settings_obj, attr: str, default: str) -> str:
    if settings_obj is None:
        return default
    val = getattr(settings_obj, attr, None)
    return val.strip() if val else default
