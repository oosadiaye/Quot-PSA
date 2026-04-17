"""
GL Data Quality diagnostics service.

Runs five fast audit checks against the live GL and budget state and
returns a structured report with per-check status (``ok`` / ``warn`` /
``fail``), a count, and a drill-down sample of the offending records.

Checks
------
1. **Unbalanced posted journals** — any posted JournalHeader whose sum of
   debit-line amounts differs from the sum of credit-line amounts by
   more than 1 kobo. Violates double-entry.

2. **Posted journals with no lines** — posted headers that have zero
   JournalLine children. Means the posting pipeline accepted an empty
   journal — should be impossible but we check defensively.

3. **Aged draft journals** — drafts older than 30 days by posting_date.
   Operational hygiene: drafts left in limbo either need to be posted,
   revised, or cancelled.

4. **Postings to inactive accounts** — journal lines whose account has
   ``is_active=False``. Usually indicates a CoA admin disabled an
   account without retiring the recurring journal that still targets
   it.

5. **Over-committed appropriations** — active appropriations where
   ``total_committed + total_expended > amount_approved``. Budget-breach
   gate may have been bypassed by a force-post.

The service returns a plain dict — no database writes, no mutation. The
fast path executes in a single round-trip per check (all aggregates).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum, Q, F

_TOL = Decimal('0.01')
_DRAFT_MAX_AGE_DAYS = 30
_SAMPLE_SIZE = 25


@dataclass
class CheckResult:
    key: str
    label: str
    description: str
    status: str                     # 'ok' | 'warn' | 'fail'
    count: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'key':         self.key,
            'label':       self.label,
            'description': self.description,
            'status':      self.status,
            'count':       self.count,
            'samples':     self.samples,
        }


class DataQualityService:

    @classmethod
    def run_all(cls) -> dict:
        checks = [
            cls._unbalanced_posted_journals(),
            cls._posted_journals_without_lines(),
            cls._aged_draft_journals(),
            cls._postings_to_inactive_accounts(),
            cls._over_committed_appropriations(),
        ]

        summary = {
            'ok':   sum(1 for c in checks if c.status == 'ok'),
            'warn': sum(1 for c in checks if c.status == 'warn'),
            'fail': sum(1 for c in checks if c.status == 'fail'),
            'total': len(checks),
        }
        overall = 'fail' if summary['fail'] else ('warn' if summary['warn'] else 'ok')

        return {
            'generated_at': _now_iso(),
            'overall':      overall,
            'summary':      summary,
            'checks':       [c.to_dict() for c in checks],
        }

    # -----------------------------------------------------------------
    # 1. Unbalanced posted journals
    # -----------------------------------------------------------------
    @classmethod
    def _unbalanced_posted_journals(cls) -> CheckResult:
        from accounting.models import JournalHeader

        qs = (
            JournalHeader.objects
            .filter(status='Posted')
            .annotate(
                sum_debit=Sum('lines__debit'),
                sum_credit=Sum('lines__credit'),
            )
            .annotate(delta=F('sum_debit') - F('sum_credit'))
            .filter(Q(delta__gt=_TOL) | Q(delta__lt=-_TOL))
            .order_by('-posting_date', '-id')
        )

        count = qs.count()
        samples = [
            {
                'id':               h.pk,
                'reference_number': h.reference_number or '',
                'posting_date':     h.posting_date.isoformat() if h.posting_date else None,
                'description':      (h.description or '')[:120],
                'sum_debit':        str(h.sum_debit or Decimal('0')),
                'sum_credit':       str(h.sum_credit or Decimal('0')),
                'delta':            str(h.delta or Decimal('0')),
            }
            for h in qs[:_SAMPLE_SIZE]
        ]

        return CheckResult(
            key='unbalanced_posted_journals',
            label='Unbalanced posted journals',
            description=(
                'Every posted journal must satisfy Σ debits = Σ credits. A '
                'non-zero delta violates double-entry and will desynchronise '
                'the Trial Balance from the Balance Sheet.'
            ),
            status='fail' if count else 'ok',
            count=count,
            samples=samples,
        )

    # -----------------------------------------------------------------
    # 2. Posted journals with no lines
    # -----------------------------------------------------------------
    @classmethod
    def _posted_journals_without_lines(cls) -> CheckResult:
        from accounting.models import JournalHeader

        qs = (
            JournalHeader.objects
            .filter(status='Posted')
            .annotate(line_count=Count('lines'))
            .filter(line_count=0)
            .order_by('-posting_date', '-id')
        )

        count = qs.count()
        samples = [
            {
                'id':               h.pk,
                'reference_number': h.reference_number or '',
                'posting_date':     h.posting_date.isoformat() if h.posting_date else None,
                'description':      (h.description or '')[:120],
            }
            for h in qs[:_SAMPLE_SIZE]
        ]

        return CheckResult(
            key='posted_journals_without_lines',
            label='Posted journals with no lines',
            description=(
                'Posted journal headers must carry at least two lines. A '
                'header with zero lines means the posting pipeline admitted '
                'an empty transaction — investigate and void.'
            ),
            status='fail' if count else 'ok',
            count=count,
            samples=samples,
        )

    # -----------------------------------------------------------------
    # 3. Aged draft journals
    # -----------------------------------------------------------------
    @classmethod
    def _aged_draft_journals(cls) -> CheckResult:
        from accounting.models import JournalHeader

        cutoff = date.today() - timedelta(days=_DRAFT_MAX_AGE_DAYS)
        qs = (
            JournalHeader.objects
            .filter(status='Draft', posting_date__lte=cutoff)
            .order_by('posting_date', 'id')
        )

        count = qs.count()
        samples = [
            {
                'id':               h.pk,
                'reference_number': h.reference_number or '',
                'posting_date':     h.posting_date.isoformat() if h.posting_date else None,
                'description':      (h.description or '')[:120],
                'age_days':         (date.today() - h.posting_date).days if h.posting_date else None,
            }
            for h in qs[:_SAMPLE_SIZE]
        ]

        return CheckResult(
            key='aged_draft_journals',
            label=f'Drafts older than {_DRAFT_MAX_AGE_DAYS} days',
            description=(
                f'Drafts past their posting_date by more than '
                f'{_DRAFT_MAX_AGE_DAYS} days usually indicate abandoned '
                'work. Post them, revise them, or cancel them so the period '
                'can close cleanly.'
            ),
            status='warn' if count else 'ok',
            count=count,
            samples=samples,
        )

    # -----------------------------------------------------------------
    # 4. Postings to inactive accounts
    # -----------------------------------------------------------------
    @classmethod
    def _postings_to_inactive_accounts(cls) -> CheckResult:
        from accounting.models import JournalLine

        qs = (
            JournalLine.objects
            .filter(
                header__status='Posted',
                account__is_active=False,
            )
            .select_related('account', 'header')
            .order_by('-header__posting_date', '-id')
        )

        count = qs.count()
        samples = [
            {
                'line_id':          l.pk,
                'journal_id':       l.header_id,
                'reference_number': l.header.reference_number or '',
                'posting_date':     l.header.posting_date.isoformat() if l.header.posting_date else None,
                'account_code':     l.account.code if l.account else '',
                'account_name':     l.account.name if l.account else '',
                'debit':            str(l.debit or Decimal('0')),
                'credit':           str(l.credit or Decimal('0')),
            }
            for l in qs[:_SAMPLE_SIZE]
        ]

        return CheckResult(
            key='postings_to_inactive_accounts',
            label='Postings to inactive accounts',
            description=(
                'A posted journal line targets an account flagged '
                'is_active=False in the chart of accounts. Either reactivate '
                'the account or reassign the posting to a live code.'
            ),
            status='warn' if count else 'ok',
            count=count,
            samples=samples,
        )

    # -----------------------------------------------------------------
    # 5. Over-committed appropriations
    # -----------------------------------------------------------------
    @classmethod
    def _over_committed_appropriations(cls) -> CheckResult:
        from budget.models import Appropriation

        # Use Python-side filter because total_committed / total_expended
        # are @property, not aggregates on the row.
        active = list(
            Appropriation.objects
            .filter(status__in=['ACTIVE', 'ENACTED'])
            .select_related('administrative', 'economic', 'fund', 'fiscal_year')
        )

        offenders = []
        for appro in active:
            committed = Decimal(str(appro.total_committed or 0))
            expended = Decimal(str(appro.total_expended or 0))
            approved = Decimal(str(appro.amount_approved or 0))
            if committed + expended > approved + _TOL:
                offenders.append(appro)

        count = len(offenders)
        samples = [
            {
                'id':              appro.pk,
                'mda':             getattr(appro.administrative, 'name', ''),
                'economic':        getattr(appro.economic, 'name', ''),
                'fund':            getattr(appro.fund, 'name', ''),
                'fiscal_year':     getattr(appro.fiscal_year, 'year', None),
                'amount_approved': str(appro.amount_approved or Decimal('0')),
                'total_committed': str(appro.total_committed or Decimal('0')),
                'total_expended':  str(appro.total_expended or Decimal('0')),
                'breach':          str(
                    (Decimal(str(appro.total_committed or 0))
                     + Decimal(str(appro.total_expended or 0)))
                    - Decimal(str(appro.amount_approved or 0))
                ),
            }
            for appro in offenders[:_SAMPLE_SIZE]
        ]

        return CheckResult(
            key='over_committed_appropriations',
            label='Over-committed appropriations',
            description=(
                'An active appropriation where committed + expended exceeds '
                'the approved amount. Either the budget gate was bypassed, '
                'an amendment is missing, or a commitment should be '
                'cancelled. Investigate before period close.'
            ),
            status='fail' if count else 'ok',
            count=count,
            samples=samples,
        )


def _now_iso() -> str:
    from django.utils import timezone
    return timezone.now().isoformat()
