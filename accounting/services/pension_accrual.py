"""
IPSAS 39 monthly pension-accrual scheduler.

For every Defined Benefit scheme with an active ``ActuarialValuation``,
this service posts the monthly service-cost + interest-cost accrual:

    DR  pension_service_cost_code            (annual service_cost / 12)
    DR  pension_interest_expense_code        (annual interest_cost / 12)
    CR  defined_benefit_obligation_code

The DBO credit accumulates to the balance-sheet liability until next
valuation. At the next valuation date the difference between the rolled-
forward accrual balance and the new measurement flows through
``actuarial_gains_losses`` per IPSAS 39 ¶68 (those remeasurements are
posted separately — this service handles only routine monthly accrual).

Idempotency
-----------
Each valuation's ``notes`` field is stamped ``PEN-ACCR:YYYY-MM`` once the
service accrues against it for that month. A re-run with the same
parameters skips stamped valuations; a new valuation ID for the same
scheme has empty notes and accrues cleanly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from decimal import Decimal
from typing import Optional

from django.db import transaction


@dataclass
class PensionAccrualResult:
    year: int
    month: int
    journal_id: Optional[int] = None
    journal_reference: str = ''
    schemes_posted: int = 0
    schemes_skipped: int = 0
    total_accrual: Decimal = field(default_factory=lambda: Decimal('0'))
    skipped_details: list[dict] = field(default_factory=list)


class PensionAccrualError(Exception):
    """Raised when the accrual run cannot proceed (missing config / accounts)."""


class PensionAccrualService:

    @classmethod
    def run_monthly(
        cls,
        *,
        year: int,
        month: int,
        user=None,
        dry_run: bool = False,
    ) -> PensionAccrualResult:
        """Post the monthly pension accrual journal.

        ``dry_run=True`` validates + stamps checks but does not save.
        """
        from accounting.models import (
            PensionScheme, ActuarialValuation, AccountingSettings, Account,
            JournalHeader, JournalLine,
        )

        if not (1 <= month <= 12):
            raise PensionAccrualError(f'month must be 1-12, got {month!r}.')

        settings_obj = AccountingSettings.objects.first()
        interest_code = _resolve(settings_obj, 'pension_interest_expense_code', '24100000')
        service_code = _resolve(settings_obj, 'pension_service_cost_code', '21400000')
        dbo_code = _resolve(settings_obj, 'defined_benefit_obligation_code', '42201000')

        interest_account = Account.objects.filter(code=interest_code).first()
        service_account = Account.objects.filter(code=service_code).first()
        dbo_account = Account.objects.filter(code=dbo_code).first()

        missing = []
        if interest_account is None:
            missing.append(f'pension_interest_expense_code={interest_code!r}')
        if service_account is None:
            missing.append(f'pension_service_cost_code={service_code!r}')
        if dbo_account is None:
            missing.append(f'defined_benefit_obligation_code={dbo_code!r}')
        if missing:
            raise PensionAccrualError(
                'Account(s) not found in the chart of accounts: '
                + '; '.join(missing)
                + '. Configure via AccountingSettings.'
            )

        period_stamp = f'PEN-ACCR:{year:04d}-{month:02d}'
        posting_date = cls._month_end(year, month)

        result = PensionAccrualResult(year=year, month=month)

        # ── Eligibility: one latest valuation per active DB scheme ──
        db_schemes = list(
            PensionScheme.objects
            .filter(scheme_type='DEFINED_BENEFIT', status='ACTIVE')
        )

        plans: list[dict] = []
        for scheme in db_schemes:
            latest = (
                ActuarialValuation.objects
                .filter(scheme=scheme)
                .order_by('-valuation_date')
                .first()
            )
            if latest is None:
                result.schemes_skipped += 1
                result.skipped_details.append({
                    'scheme_id':   scheme.id,
                    'scheme_code': scheme.code,
                    'reason':      'No actuarial valuation on file.',
                })
                continue

            if period_stamp in (latest.notes or ''):
                result.schemes_skipped += 1
                result.skipped_details.append({
                    'scheme_id':    scheme.id,
                    'scheme_code':  scheme.code,
                    'valuation_id': latest.id,
                    'reason':       f'Already accrued for {year:04d}-{month:02d}.',
                })
                continue

            # 1/12 of the annual figures (IPSAS 39 ¶64).
            monthly_service = (
                (latest.service_cost or Decimal('0')) / Decimal('12')
            ).quantize(Decimal('0.01'))
            monthly_interest = (
                (latest.interest_cost or Decimal('0')) / Decimal('12')
            ).quantize(Decimal('0.01'))
            total_monthly = monthly_service + monthly_interest

            if total_monthly <= 0:
                result.schemes_skipped += 1
                result.skipped_details.append({
                    'scheme_id':    scheme.id,
                    'scheme_code':  scheme.code,
                    'valuation_id': latest.id,
                    'reason':       'Zero monthly accrual charge.',
                })
                continue

            plans.append({
                'scheme':           scheme,
                'valuation':        latest,
                'monthly_service':  monthly_service,
                'monthly_interest': monthly_interest,
                'total_monthly':    total_monthly,
            })
            result.total_accrual += total_monthly

        if dry_run or not plans:
            return result

        # ── Post journal atomically ─────────────────────────────────
        reference = f'PEN-ACCR-{year:04d}-{month:02d}'
        with transaction.atomic():
            header = JournalHeader.objects.create(
                posting_date=posting_date,
                description=(
                    f'IPSAS 39 monthly pension accrual — '
                    f'{year:04d}-{month:02d}. {len(plans)} DB scheme(s), '
                    f'total NGN {result.total_accrual:,.2f}.'
                ),
                reference_number=reference,
                status='Draft',
                source_module='pension_accrual',
            )

            lines: list[JournalLine] = []
            for plan in plans:
                scheme = plan['scheme']
                memo = f'Pension accrual {scheme.code} ({year:04d}-{month:02d})'
                if plan['monthly_service'] > 0:
                    lines.append(JournalLine(
                        header=header,
                        account=service_account,
                        debit=plan['monthly_service'],
                        credit=Decimal('0'),
                        memo=f'Service cost — {memo}',
                    ))
                if plan['monthly_interest'] > 0:
                    lines.append(JournalLine(
                        header=header,
                        account=interest_account,
                        debit=plan['monthly_interest'],
                        credit=Decimal('0'),
                        memo=f'Interest cost — {memo}',
                    ))
                # Offsetting credit to DBO — one line per scheme.
                lines.append(JournalLine(
                    header=header,
                    account=dbo_account,
                    debit=Decimal('0'),
                    credit=plan['total_monthly'],
                    memo=f'DBO accrual — {memo}',
                ))
            JournalLine.objects.bulk_create(lines)

            from django.utils import timezone
            header.status = 'Posted'
            header.posted_at = timezone.now()
            header.save(update_fields=['status', 'posted_at'])

            # Stamp each valuation's notes so re-runs skip.
            from accounting.models import ActuarialValuation
            for plan in plans:
                valuation = plan['valuation']
                new_notes = (
                    (valuation.notes + '\n' if valuation.notes else '')
                    + period_stamp
                )
                ActuarialValuation.objects.filter(pk=valuation.pk).update(
                    notes=new_notes,
                )

            result.journal_id = header.pk
            result.journal_reference = header.reference_number
            result.schemes_posted = len(plans)

        return result

    @staticmethod
    def _month_end(year: int, month: int) -> _date:
        from calendar import monthrange
        return _date(year, month, monthrange(year, month)[1])


def _resolve(settings_obj, attr: str, default: str) -> str:
    if settings_obj is None:
        return default
    val = getattr(settings_obj, attr, None)
    if val is None:
        return default
    stripped = str(val).strip()
    return stripped if stripped else default
