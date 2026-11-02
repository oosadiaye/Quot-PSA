"""Report on supplementary budgets for a fiscal year.

The source of truth is Budget's own SUPPLEMENTARY appropriations, so the report covers every supplementary line: those
handed over from Budget Preparation and any entered directly in Budget. Nothing here writes; it only reads ``budget``.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum

from budget.models import Appropriation

#: Where a supplementary line is in its life, in the order the legislature handles it.
_DRAFT = ('DRAFT',)
_BEFORE_LEGISLATURE = ('SUBMITTED', 'APPROVED')
_ENACTED = ('ENACTED', 'ACTIVE')
_REAL_ORIGINAL = ('APPROVED', 'ENACTED', 'ACTIVE')
_ZERO = Decimal('0')
_CENT = Decimal('0.01')


def _money(value) -> str:
    return str((value or _ZERO).quantize(_CENT))


def _sum(statuses=None):
    return Sum('amount_approved', filter=Q(status__in=statuses) if statuses else None)


def supplementary_report(fiscal_year: int) -> dict:
    """Per-MDA supplementary totals by stage, against that MDA's original appropriation, plus overall totals."""
    supplementary = Appropriation.objects.filter(fiscal_year__year=fiscal_year, appropriation_type='SUPPLEMENTARY')
    rows = list(
        supplementary.values('administrative_id', 'administrative__name').annotate(
            lines=Count('id'),
            lines_from_prep=Count('id', filter=Q(source_module='budget_prep')),
            total=_sum(), draft=_sum(_DRAFT), before_legislature=_sum(_BEFORE_LEGISLATURE), enacted=_sum(_ENACTED),
        ).order_by('administrative__name'))
    originals = dict(
        Appropriation.objects.filter(fiscal_year__year=fiscal_year, appropriation_type='ORIGINAL', status__in=_REAL_ORIGINAL)
        .values_list('administrative_id').annotate(total=Sum('amount_approved')))

    out_rows = []
    for r in rows:
        original = originals.get(r['administrative_id']) or _ZERO
        total = r['total'] or _ZERO
        out_rows.append({
            'mda': r['administrative__name'], 'lines': r['lines'], 'lines_from_prep': r['lines_from_prep'],
            'total': _money(total), 'draft': _money(r['draft']),
            'before_legislature': _money(r['before_legislature']), 'enacted': _money(r['enacted']),
            'original_appropriation': _money(original),
            'percent_of_original': None if original <= 0 else str((total / original * 100).quantize(Decimal('0.01'))),
        })
    totals = supplementary.aggregate(
        lines=Count('id'), total=_sum(), draft=_sum(_DRAFT), before_legislature=_sum(_BEFORE_LEGISLATURE), enacted=_sum(_ENACTED))
    return {
        'fiscal_year': fiscal_year,
        'rows': out_rows,
        'totals': {k: (_money(v) if k != 'lines' else v) for k, v in totals.items()},
        'original_total': _money(sum(originals.values(), _ZERO)),
    }
