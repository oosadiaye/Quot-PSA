"""Adopt actuals to plan: seed a submission's lines from what was approved or actually spent.

Three bases for the baseline (the source year is the one before the submission's fiscal year):

* ``outturn``       - what was actually spent (``Appropriation.total_expended``, the canonical expenditure figure).
* ``appropriation`` - what was approved (``amount_approved``, the final budget after amendments and virements).
* ``run_rate``      - spending so far, annualised over the part of the year already elapsed.

A growth/policy adjustment is then applied: one overall percentage plus optional per-economic-class overrides keyed
by account-code prefix (the longest matching prefix wins). Every adopted line records its basis, the baseline it came
from and the percentage used, so a reviewer can see exactly where a number came from. Re-adopting replaces the
previously adopted lines and never touches lines a person entered by hand.

Read-only on ``budget``/``accounting``: this module imports them, they never import it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from accounting.models.advanced import FiscalYear
from budget.models import Appropriation
from budget_prep.models import SubmissionLine

OUTTURN, APPROPRIATION, RUN_RATE = 'outturn', 'appropriation', 'run_rate'
BASES = (OUTTURN, APPROPRIATION, RUN_RATE)
EDITABLE_STAGES = ('draft', 'revised')
#: NCoA expenditure families: 21 personnel, 22 overheads, 23 capital. Anything else expenditure-like is overhead.
_LINE_TYPE_BY_PREFIX = {'21': 'personnel', '22': 'overhead', '23': 'capital'}
_CENT = Decimal('0.01')
# Appropriation states whose figures are real; DRAFT/SUBMITTED are proposals that may never have been enacted.
_REAL_STATUSES = ('APPROVED', 'ENACTED', 'ACTIVE', 'CLOSED')


class AdoptionError(Exception):
    pass


@dataclass
class AdoptionResult:
    basis: str = ''
    source_year: int = 0
    created: int = 0
    replaced: int = 0
    total_proposed: Decimal = Decimal('0')
    skipped: list = field(default_factory=list)


def _money(value) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _pct_for(code: str, overall: Decimal, by_class: dict) -> Decimal:
    best = ''
    for prefix in by_class:
        if code.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    return Decimal(by_class[best]) if best else overall


def _elapsed_fraction(fiscal_year: FiscalYear, as_of: date) -> Decimal:
    start, end = fiscal_year.start_date, fiscal_year.end_date
    total = (end - start).days + 1
    if total <= 0 or as_of >= end:
        return Decimal('1')
    done = (as_of - start).days + 1
    if done <= 0:
        raise AdoptionError('The source year has not started, so there is no run rate yet.')
    return Decimal(done) / Decimal(total)


def baseline_rows(submission, basis: str, *, as_of: date | None = None) -> tuple[list[dict], int]:
    """The per-(administrative, economic, fund) baseline for this submission's MDA, and the source year used."""
    if basis not in BASES:
        raise AdoptionError(f"Unknown basis '{basis}'. Use one of: {', '.join(BASES)}.")
    source_year = submission.fiscal_year - 1
    fy = FiscalYear.objects.filter(year=source_year).first()
    if fy is None:
        raise AdoptionError(f'No fiscal year {source_year} exists, so there is nothing to adopt from.')
    appropriations = Appropriation.objects.filter(
        fiscal_year=fy, status__in=_REAL_STATUSES, administrative__name__iexact=submission.mda_name,
        economic__code__startswith='2',
    ).select_related('economic')
    if not appropriations.exists():
        raise AdoptionError(
            f"No approved appropriations for '{submission.mda_name}' in {source_year}. "
            'Check the MDA name matches the Budget MDA, or enter lines by hand.')

    scale = _elapsed_fraction(fy, as_of or date.today()) if basis == RUN_RATE else Decimal('1')
    grouped: dict = defaultdict(lambda: {'amount': Decimal('0'), 'ids': []})
    for a in appropriations:
        if basis == APPROPRIATION:
            amount = Decimal(a.amount_approved)
        else:
            spent = Decimal(a.total_expended)
            amount = spent if basis == OUTTURN else spent / scale
        key = (a.administrative_id, a.economic_id, a.functional_id, a.programme_id, a.fund_id)
        grouped[key]['amount'] += amount
        grouped[key]['ids'].append(a.pk)
        grouped[key]['code'] = a.economic.code
    rows = [{'administrative': k[0], 'economic': k[1], 'functional': k[2], 'programme': k[3], 'fund': k[4],
             'code': v['code'], 'amount': _money(v['amount']), 'appropriation_ids': v['ids']}
            for k, v in grouped.items()]
    return rows, source_year


def adopt_actuals(submission, *, basis: str = OUTTURN, growth_pct=0, class_adjustments: dict | None = None,
                  as_of: date | None = None) -> AdoptionResult:
    """Replace the submission's adopted lines with a fresh baseline plus adjustment. Idempotent."""
    if submission.stage not in EDITABLE_STAGES:
        raise AdoptionError('Lines can only be adopted while the submission is a draft or sent back for revision.')
    overall = Decimal(str(growth_pct or 0))
    by_class = {str(k): Decimal(str(v)) for k, v in (class_adjustments or {}).items()}
    rows, source_year = baseline_rows(submission, basis, as_of=as_of)

    result = AdoptionResult(basis=basis, source_year=source_year)
    with transaction.atomic():
        replaced, _ = SubmissionLine.objects.filter(submission=submission).exclude(adopted_basis='').delete()
        result.replaced = replaced
        for row in rows:
            if row['amount'] <= 0:
                result.skipped.append({'economic': row['code'], 'reason': 'nothing spent or approved'})
                continue
            pct = _pct_for(row['code'], overall, by_class)
            proposed = _money(row['amount'] * (Decimal('1') + pct / Decimal('100')))
            SubmissionLine.objects.create(
                submission=submission, line_type=_LINE_TYPE_BY_PREFIX.get(row['code'][:2], 'overhead'),
                administrative_id=row['administrative'], economic_id=row['economic'], functional_id=row['functional'],
                programme_id=row['programme'], fund_id=row['fund'], proposed_amount=proposed,
                description=f"Adopted from {source_year} {basis.replace('_', ' ')}",
                adopted_basis=basis, baseline_amount=row['amount'], adjustment_pct=pct)
            result.created += 1
            result.total_proposed += proposed
        _refresh_totals(submission)
    return result


def _refresh_totals(submission) -> None:
    """Nothing else maintains the submission's three totals, so keep them honest after lines change."""
    totals = defaultdict(lambda: Decimal('0'))
    for line in submission.lines.all():
        totals[line.line_type] += Decimal(line.proposed_amount)
    submission.total_personnel = totals['personnel']
    submission.total_overhead = totals['overhead']
    submission.total_capital = totals['capital']
    submission.save(update_fields=['total_personnel', 'total_overhead', 'total_capital', 'updated_at'])
