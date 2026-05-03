"""Monthly depreciation run — service layer.

Extracted from the ``FixedAssetViewSet.bulk_depreciation`` action so it
can be reused by:

  * the UI / API (``POST /fixed-assets/bulk-depreciation/``)
  * the scheduled auto-run (``run_monthly_depreciation`` management
    command fired by cron / django-celery-beat)

The two callers share the same eligibility rules and the same posting
logic so the user can dry-run a simulation in the UI, verify the
numbers match what the scheduled run will produce, and trust that the
two code paths can't drift.

Eligibility rules:

  * ``FixedAsset.status == 'Active'``  — retired / disposed assets skip
  * ``acquisition_cost > 0``            — "only posted values can be
    depreciated" (no cost = no depreciation base)
  * ``depreciation_expense_account`` AND ``accumulated_depreciation_account``
    must both be set (or resolvable from the category at save time)
  * Not already posted for ``period_date``

Returns a structured dict the view and management command both emit.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date

from django.db import transaction


def run_monthly_depreciation(
    *,
    period_date: date,
    asset_ids: list | None = None,
    simulate: bool = True,
    user=None,
) -> dict:
    """Execute (or simulate) a monthly depreciation run.

    Parameters
    ----------
    period_date
        The period the depreciation applies to. Usually month-end.
    asset_ids
        Optional filter — when omitted, every eligible active asset
        on the tenant is depreciated. Scheduled auto-runs always pass
        ``None`` so newly-added assets are picked up.
    simulate
        ``True`` → dry-run preview (no DB writes).
        ``False`` → post journals + update GL balances + mark schedules.
    user
        Optional user for audit trails. Not required.
    """
    from accounting.models import (
        FixedAsset, JournalHeader, JournalLine, DepreciationSchedule,
    )
    # Build the eligibility queryset — the "posted values only" rule
    # lives here so every caller (UI bulk + scheduled auto-run) uses
    # the same definition.
    assets_qs = (
        FixedAsset.objects
        .filter(status='Active', acquisition_cost__gt=0)
        .select_related(
            'fund', 'function', 'program', 'geo',
            'depreciation_expense_account', 'accumulated_depreciation_account',
        )
    )
    if asset_ids:
        assets_qs = assets_qs.filter(id__in=asset_ids)

    results: list[dict] = []
    total_amount = Decimal('0.00')
    skipped = 0

    def _build_result(asset, *, amount, status_str, journal_id, message):
        return {
            'asset_id':            asset.id,
            'asset_number':        asset.asset_number,
            'asset_name':          asset.name,
            'depreciation_amount': str(amount),
            'accumulated_after':   str(asset.accumulated_depreciation
                                       + (amount if status_str == 'success' and not simulate else Decimal('0'))),
            'nbv_after':           str(asset.acquisition_cost
                                       - (asset.accumulated_depreciation
                                          + (amount if status_str == 'success' and not simulate else Decimal('0')))),
            'status':              status_str,
            'journal_id':          journal_id,
            'message':             message,
        }

    if simulate:
        # ── Dry-run preview — no DB writes ──────────────────────
        for asset in assets_qs:
            if not asset.depreciation_expense_account or not asset.accumulated_depreciation_account:
                results.append(_build_result(
                    asset, amount=Decimal('0.00'),
                    status_str='skipped', journal_id=None,
                    message='Missing GL account configuration (see Asset Category)',
                ))
                skipped += 1
                continue
            if DepreciationSchedule.objects.filter(
                asset=asset, period_date=period_date, is_posted=True,
            ).exists():
                results.append(_build_result(
                    asset, amount=Decimal('0.00'),
                    status_str='already_posted', journal_id=None,
                    message='Already posted for this period',
                ))
                skipped += 1
                continue
            annual = asset.calculate_annual_depreciation()
            monthly = (annual / 12).quantize(Decimal('0.01'))
            results.append(_build_result(
                asset, amount=monthly, status_str='success',
                journal_id=None, message='',
            ))
            total_amount += monthly
        return {
            'mode':        'simulation',
            'period_date': str(period_date),
            'summary': {
                'total_assets': len(results),
                'total_amount': str(total_amount),
                'skipped':      skipped,
                'posted':       sum(1 for r in results if r['status'] == 'success'),
            },
            'results': results,
        }

    # ── Live run — post journals inside a single atomic tx ──────
    with transaction.atomic():
        for asset in assets_qs:
            if not asset.depreciation_expense_account or not asset.accumulated_depreciation_account:
                results.append(_build_result(
                    asset, amount=Decimal('0.00'),
                    status_str='skipped', journal_id=None,
                    message='Missing GL account configuration',
                ))
                skipped += 1
                continue

            schedule, _ = DepreciationSchedule.objects.get_or_create(
                asset=asset, period_date=period_date,
                defaults={
                    'depreciation_amount': (
                        asset.calculate_annual_depreciation() / 12
                    ).quantize(Decimal('0.01')),
                },
            )
            if schedule.is_posted:
                results.append(_build_result(
                    asset, amount=Decimal('0.00'),
                    status_str='already_posted',
                    journal_id=schedule.journal_entry_id,
                    message='Already posted for this period',
                ))
                skipped += 1
                continue

            amt = schedule.depreciation_amount
            journal = JournalHeader.objects.create(
                reference_number=(
                    f"DEP-{asset.asset_number}-{period_date.strftime('%Y%m')}"
                ),
                description=(
                    f"Depreciation: {asset.name} ({period_date.strftime('%b %Y')})"
                ),
                posting_date=period_date,
                mda=asset.mda,
                fund=asset.fund,
                function=asset.function,
                program=asset.program,
                geo=asset.geo,
                status='Posted',
                source_module='depreciation',
                source_document_id=asset.pk,
            )
            # Mark as already-enforced so the JV pre-save signal
            # doesn't try to re-evaluate the budget for a depreciation
            # entry (non-cash, doesn't draw appropriation).
            journal._budget_checked = True

            JournalLine.objects.create(
                header=journal,
                account=asset.depreciation_expense_account,
                debit=amt, credit=Decimal('0.00'),
                memo=f"Depreciation: {asset.name}",
                asset=asset,
            )
            JournalLine.objects.create(
                header=journal,
                account=asset.accumulated_depreciation_account,
                debit=Decimal('0.00'), credit=amt,
                memo=f"Accumulated depreciation: {asset.name}",
                asset=asset,
            )

            from accounting.services import update_gl_from_journal
            update_gl_from_journal(
                journal, fund=asset.fund, function=asset.function,
                program=asset.program, geo=asset.geo,
            )

            asset.accumulated_depreciation += amt
            asset.save()

            schedule.journal_entry = journal
            schedule.is_posted = True
            schedule.save()

            results.append(_build_result(
                asset, amount=amt, status_str='success',
                journal_id=journal.id, message='',
            ))
            total_amount += amt

    return {
        'mode':        'posted',
        'period_date': str(period_date),
        'summary': {
            'total_assets': len(results),
            'total_amount': str(total_amount),
            'skipped':      skipped,
            'posted':       sum(1 for r in results if r['status'] == 'success'),
        },
        'results': results,
    }
