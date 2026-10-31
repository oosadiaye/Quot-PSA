"""Hand an incorporated budget submission over to Budget & Appropriation as DRAFT appropriations.

One-way and optional: this module imports ``budget``; ``budget`` imports nothing from here. The link back is two
plain string columns on ``Appropriation`` (``source_module`` / ``source_reference``), so the appropriations survive
this module being switched off or removed.

Lines are summed by ``(administrative, economic, fund, fiscal_year)``, exactly the tuple ``Appropriation`` requires to
be unique among ACTIVE rows, so the drafts can later be activated without tripping that constraint. The legislature's
flow (submit, approve, enact, activate) stays entirely in ``budget``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from accounting.models.advanced import FiscalYear
from budget.models import Appropriation

SOURCE_MODULE = 'budget_prep'
_REQUIRED = ('administrative', 'economic', 'functional', 'programme', 'fund')


class IncorporationError(Exception):
    """The hand-off cannot proceed; ``lines`` names the submission lines that need attention."""

    def __init__(self, message: str, *, lines: list | None = None):
        super().__init__(message)
        self.lines = lines or []


@dataclass
class IncorporationResult:
    created: int = 0
    updated: int = 0
    removed: int = 0
    appropriation_ids: list = field(default_factory=list)


def _reference(submission) -> str:
    return f'submission:{submission.pk}'


def _key(appropriation) -> tuple:
    return (appropriation.administrative_id, appropriation.economic_id, appropriation.fund_id)


def _resolve(line, defaults: dict) -> dict:
    """The value of each required dimension for one line: its own, else the caller's default."""
    values = {}
    for name in _REQUIRED:
        value = getattr(line, f'{name}_id', None) or defaults.get(name)
        values[name] = getattr(value, 'pk', value)
    return values


def _aggregate(submission, defaults: dict) -> dict:
    groups: dict = {}
    problems: list = []
    members = defaultdict(list)
    for line in submission.lines.all().order_by('pk'):
        resolved = _resolve(line, defaults)
        missing = [n for n in _REQUIRED if not resolved[n]]
        if missing:
            problems.append({'line': line.pk, 'missing': missing})
            continue
        key = (resolved['administrative'], resolved['economic'], resolved['fund'])
        members[key].append(line.pk)
        group = groups.get(key)
        if group is None:
            groups[key] = {**resolved, 'amount_approved': Decimal(line.proposed_amount or 0),
                           'description': (line.description or '')[:500]}
            continue
        if (group['functional'], group['programme']) != (resolved['functional'], resolved['programme']):
            problems.append({'line': line.pk, 'conflict': 'functional/programme differ within the same appropriation line'})
            continue
        group['amount_approved'] += Decimal(line.proposed_amount or 0)
    if problems:
        raise IncorporationError(
            f'{len(problems)} submission line(s) cannot be handed off; fix them in Budget Preparation.', lines=problems)
    if not groups:
        raise IncorporationError('This submission has no lines to hand off.')
    return groups


def incorporate_submission(submission, *, defaults: dict | None = None) -> IncorporationResult:
    """Create or refresh the DRAFT appropriations for an incorporated submission. Idempotent by ``source_reference``.

    Refuses once any appropriation from this submission has left DRAFT: from then on the legislature owns it.
    """
    defaults = defaults or {}
    if submission.stage != 'incorporated':
        raise IncorporationError('Only an incorporated submission can be handed off.')
    fiscal_year = FiscalYear.objects.filter(year=submission.fiscal_year).first()
    if fiscal_year is None:
        raise IncorporationError(f'No fiscal year {submission.fiscal_year} exists in Budget. Create it first.')

    reference = _reference(submission)
    mine = Appropriation.objects.filter(source_module=SOURCE_MODULE, source_reference=reference)
    if mine.exclude(status='DRAFT').exists():
        raise IncorporationError(
            'Appropriations from this submission are already past Draft, so re-incorporation is refused.')

    groups = _aggregate(submission, defaults)
    result = IncorporationResult()
    with transaction.atomic():
        existing = {_key(a): a for a in mine.select_for_update()}
        for key, row in groups.items():
            fields = dict(
                administrative_id=row['administrative'], economic_id=row['economic'], functional_id=row['functional'],
                programme_id=row['programme'], fund_id=row['fund'], amount_approved=row['amount_approved'],
                description=row['description'],
            )
            obj = existing.pop(key, None)
            if obj is None:
                obj = Appropriation.objects.create(
                    fiscal_year=fiscal_year, status='DRAFT', appropriation_type='ORIGINAL',
                    source_module=SOURCE_MODULE, source_reference=reference, **fields)
                result.created += 1
            else:
                for name, value in fields.items():
                    setattr(obj, name, value)
                obj.save()
                result.updated += 1
            result.appropriation_ids.append(obj.pk)
        for stale in existing.values():          # a line removed upstream drops its draft
            stale.delete()
            result.removed += 1
    return result
