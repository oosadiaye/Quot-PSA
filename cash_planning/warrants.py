"""Warrant recommendations: how much cash release to propose for a quarter, and the controlled step that turns one into a Warrant.

A recommendation is advice, never an issued warrant. Generating writes only ``WarrantRecommendation`` rows; the Warrant
itself is created by an explicit conversion that needs the authority reference of the release letter, and it then
follows Budget's own warrant release process unchanged.

The rule is deliberately plain so an officer can check it by hand. For an ACTIVE appropriation and a quarter:

    phased to date   = the appropriation's budget up to the end of the quarter (its monthly spread, else even twelfths)
    already released = warrants on it that are pending, released or exhausted
    recommended      = phased to date - already released, never below zero, never above the unreleased balance

When the cash available is given and the recommendations together exceed it, every one is scaled down by the same
proportion and says so. Budget Office judgment stays with the officer: the amount can be lowered at conversion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction

from accounting.models.advanced import FiscalYear
from budget.models import Appropriation, Warrant

from .models import WarrantRecommendation

_CENT = Decimal('0.01')
_COUNTED = ('PENDING', 'RELEASED', 'EXHAUSTED')     # warrants that have already used up authority to release cash
_OVERLAPPING = ('PENDING', 'RELEASED')              # warrants whose date window blocks another on the same line


class WarrantPlanError(Exception):
    pass


@dataclass
class GenerationResult:
    created: int = 0
    replaced: int = 0
    total: Decimal = Decimal('0')
    scaled_to: Decimal | None = None
    skipped: list = field(default_factory=list)


def _money(value) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_DOWN)


def _add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    return date(start.year + index // 12, index % 12 + 1, 1)


def quarter_window(fiscal_year: FiscalYear, quarter: int) -> tuple[date, date]:
    """First and last day of the quarter, counted in months from the start of the fiscal year."""
    if quarter not in (1, 2, 3, 4):
        raise WarrantPlanError('quarter must be 1, 2, 3 or 4.')
    first = _add_months(fiscal_year.start_date.replace(day=1), 3 * (quarter - 1))
    return first, _add_months(first, 3) - timedelta(days=1)


def phased_to_quarter_end(appropriation: Appropriation, quarter: int) -> Decimal:
    return sum((appropriation.get_monthly_amount(m) for m in range(1, 3 * quarter + 1)), Decimal('0'))


def _released(appropriation: Appropriation) -> Decimal:
    return sum((w.amount_released for w in Warrant.objects.filter(appropriation=appropriation, status__in=_COUNTED)), Decimal('0'))


def generate_recommendations(fiscal_year: int, quarter: int, *, available_cash=None, mda_name: str = '') -> GenerationResult:
    """Propose a release for every active appropriation of the year. Idempotent per (appropriation, year, quarter)."""
    fy = FiscalYear.objects.filter(year=fiscal_year).first()
    if fy is None:
        raise WarrantPlanError(f'No fiscal year {fiscal_year} exists, so there is nothing to plan.')
    first, last = quarter_window(fy, quarter)
    cap = None if available_cash in (None, '') else Decimal(str(available_cash))
    if cap is not None and cap < 0:
        raise WarrantPlanError('Available cash cannot be negative.')

    lines = Appropriation.objects.filter(fiscal_year=fy, status='ACTIVE').select_related('administrative', 'economic', 'fund')
    if mda_name:
        lines = lines.filter(administrative__name__iexact=mda_name)

    result = GenerationResult()
    proposals = []
    for a in lines:
        taken = WarrantRecommendation.objects.filter(
            appropriation=a, fiscal_year=fiscal_year, quarter=quarter, status__in=('accepted', 'converted'))
        if taken.exists():
            result.skipped.append({'appropriation': a.pk, 'reason': 'already accepted or converted for this quarter'})
            continue
        clash = Warrant.objects.filter(appropriation=a, status__in=_OVERLAPPING, effective_from__lte=last, effective_to__gte=first)
        if clash.exists():
            result.skipped.append({'appropriation': a.pk, 'reason': 'a warrant already covers part of this quarter'})
            continue
        phased, released = phased_to_quarter_end(a, quarter), _released(a)
        amount = max(Decimal('0'), min(phased - released, Decimal(a.amount_approved) - released))
        if amount <= 0:
            result.skipped.append({'appropriation': a.pk, 'reason': 'nothing further is due by the end of this quarter'})
            continue
        proposals.append((a, phased, released, amount))

    needed = sum((p[3] for p in proposals), Decimal('0'))
    factor = Decimal('1')
    if cap is not None and needed > cap:
        factor = cap / needed if needed else Decimal('1')
        result.scaled_to = cap

    with transaction.atomic():
        for a, phased, released, amount in proposals:
            final = _money(amount * factor)
            if final <= 0:
                result.skipped.append({'appropriation': a.pk, 'reason': 'rounds to nothing after scaling to the cash available'})
                continue
            why = (f'Q{quarter} {fiscal_year}: budget phased to the end of the quarter {phased:,.2f} less already released '
                   f'{released:,.2f} = {amount:,.2f}.')
            if factor != 1:
                why += f' Scaled to {factor * 100:.1f}% because the cash available is {cap:,.2f}.'
            replaced, _ = WarrantRecommendation.objects.filter(
                appropriation=a, fiscal_year=fiscal_year, quarter=quarter, status='proposed').delete()
            result.replaced += replaced
            WarrantRecommendation.objects.create(
                appropriation=a, mda_name=a.administrative.name, fiscal_year=fiscal_year, quarter=quarter,
                effective_from=first, effective_to=last, proposed_amount=final, status='proposed', rationale=why)
            result.created += 1
            result.total += final
    return result


def convert_to_warrant(recommendation: WarrantRecommendation, *, authority_reference: str, issued_by=None, amount=None) -> Warrant:
    """Turn a proposed or accepted recommendation into a PENDING Warrant, running the Warrant's own validation.

    The amount may be lowered, never raised: the recommendation is the ceiling of what was advised.
    """
    from django.core.exceptions import ValidationError

    reference = (authority_reference or '').strip()
    if not reference:
        raise WarrantPlanError('The authority reference of the warrant letter is required to issue a warrant.')
    if recommendation.status not in ('proposed', 'accepted'):
        raise WarrantPlanError(f'This recommendation is already {recommendation.get_status_display().lower()}.')
    if recommendation.appropriation_id is None:
        raise WarrantPlanError('This recommendation has no appropriation to release against.')
    value = recommendation.proposed_amount if amount in (None, '') else Decimal(str(amount))
    if value <= 0 or value > recommendation.proposed_amount:
        raise WarrantPlanError(f'The amount must be above zero and no more than the recommended {recommendation.proposed_amount:,.2f}.')

    warrant = Warrant(
        appropriation=recommendation.appropriation, effective_from=recommendation.effective_from,
        effective_to=recommendation.effective_to, amount_released=value, release_date=date.today(),
        authority_reference=reference[:100], issued_by=issued_by, status='PENDING',
        notes=f'From warrant recommendation {recommendation.pk}. {recommendation.rationale}'[:1000])
    try:
        with transaction.atomic():
            warrant.full_clean(exclude=['attachment'])
            warrant.save()
            recommendation.warrant = warrant
            recommendation.status = 'converted'
            recommendation.save(update_fields=['warrant', 'status', 'updated_at'])
    except ValidationError as exc:
        raise WarrantPlanError(' '.join(exc.messages)) from exc
    return warrant
