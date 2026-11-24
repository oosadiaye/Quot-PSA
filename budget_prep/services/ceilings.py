"""MDA ceilings: what an MDA may propose, checked from its lines, and the controlled way to go over.

The check reads the submission's lines (never the typed-in totals, which can disagree) against the ``MDACeiling`` for the
same fiscal year and MDA. A submission over any ceiling cannot be submitted unless the officer gives a reason, which is
kept on the submission as a review comment so the Budget Office sees it. A line type with no ceiling set is reported as
"no ceiling" rather than silently allowed or blocked: there is nothing to enforce.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from budget_prep.models import MDACeiling, ReviewComment, SubmissionLine

LINE_TYPES = ('personnel', 'overhead', 'capital')
SUBMITTABLE_STAGES = ('draft', 'revised')
_CEILING_FIELD = {'personnel': 'personnel_ceiling', 'overhead': 'overhead_ceiling', 'capital': 'capital_ceiling'}


class SubmissionError(Exception):
    """The submission cannot be submitted; ``check`` carries the per-type detail when the cause is a ceiling."""

    def __init__(self, message: str, *, check: 'CeilingCheck | None' = None):
        super().__init__(message)
        self.check = check


@dataclass
class CeilingRow:
    line_type: str
    proposed: Decimal
    ceiling: Decimal | None      # None: no ceiling record, so nothing to enforce

    @property
    def over_by(self) -> Decimal:
        if self.ceiling is None or self.proposed <= self.ceiling:
            return Decimal('0')
        return self.proposed - self.ceiling


@dataclass
class CeilingCheck:
    has_ceiling: bool
    rows: list = field(default_factory=list)

    @property
    def exceeded(self) -> list:
        return [r for r in self.rows if r.over_by > 0]

    @property
    def ok(self) -> bool:
        return not self.exceeded

    def as_dict(self) -> dict:
        return {
            'has_ceiling': self.has_ceiling, 'ok': self.ok,
            'rows': [{'line_type': r.line_type, 'proposed': str(r.proposed),
                      'ceiling': None if r.ceiling is None else str(r.ceiling), 'over_by': str(r.over_by)}
                     for r in self.rows],
        }


def _ceiling_for(submission) -> MDACeiling | None:
    return MDACeiling.objects.filter(
        fiscal_year=submission.fiscal_year, mda_name__iexact=submission.mda_name).order_by('-pk').first()


def check_ceiling(submission) -> CeilingCheck:
    """Proposed total per line type (from the lines) against the MDA's ceiling for the year."""
    proposed = defaultdict(lambda: Decimal('0'))
    for line in SubmissionLine.objects.filter(submission=submission):
        proposed[line.line_type] += Decimal(line.proposed_amount)
    # Ceilings govern the original budget; a supplementary is a separate request with its own justification.
    ceiling = None if submission.kind == 'supplementary' else _ceiling_for(submission)
    rows = [CeilingRow(t, proposed[t], None if ceiling is None else Decimal(getattr(ceiling, _CEILING_FIELD[t])))
            for t in LINE_TYPES]
    return CeilingCheck(has_ceiling=ceiling is not None, rows=rows)


def refresh_totals(submission) -> None:
    """Keep the stored totals equal to the sum of the lines; nothing else maintains them."""
    totals = defaultdict(lambda: Decimal('0'))
    for line in SubmissionLine.objects.filter(submission=submission):
        totals[line.line_type] += Decimal(line.proposed_amount)
    submission.total_personnel = totals['personnel']
    submission.total_overhead = totals['overhead']
    submission.total_capital = totals['capital']
    submission.save(update_fields=['total_personnel', 'total_overhead', 'total_capital', 'updated_at'])


def submit_submission(submission, *, override_reason: str = '', actor_name: str = '') -> CeilingCheck:
    """Move a draft (or sent-back) submission to the Budget Office, enforcing the MDA ceiling.

    Over a ceiling, an ``override_reason`` is required and is recorded as a review comment flagged for the reviewer.
    """
    if submission.stage not in SUBMITTABLE_STAGES:
        raise SubmissionError('Only a draft or sent-back submission can be submitted.')
    if not SubmissionLine.objects.filter(submission=submission).exists():
        raise SubmissionError('This submission has no lines yet.')
    if submission.kind == 'supplementary' and not (submission.justification or '').strip():
        raise SubmissionError('A supplementary budget needs a justification before it is submitted.')
    check = check_ceiling(submission)
    reason = (override_reason or '').strip()
    if not check.ok and not reason:
        over = '; '.join(f'{r.line_type} is over by {r.over_by:,.2f}' for r in check.exceeded)
        raise SubmissionError(f'Over the MDA ceiling ({over}). Reduce the lines, or give a reason to submit anyway.',
                              check=check)
    with transaction.atomic():
        if not check.ok:
            ReviewComment.objects.create(
                submission=submission, action_required=True, commented_by=actor_name[:200],
                comment='Submitted over ceiling: ' + '; '.join(
                    f'{r.line_type} {r.proposed:,.2f} against {r.ceiling:,.2f}' for r in check.exceeded) + f'. Reason given: {reason}')
        refresh_totals(submission)
        submission.stage = 'submitted'
        submission.submitted_at = timezone.now()
        submission.save(update_fields=['stage', 'submitted_at', 'updated_at'])
    return check
