"""The revenue administration lifecycle: assess, bill, age, clear.

Every function here is idempotent or refuses a repeat, because revenue work is run by people who retry.
Numbers come from accounting's TransactionSequence, so they are unique per tenant and never reused.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from accounting.models.gl import TransactionSequence

from .models import ArrearsLedger, Assessment, BillingRun, DemandNotice, TaxAccount, TaxClearanceCertificate

ZERO = Decimal('0')
PAYMENT_TERM_DAYS = 30            # a demand notice falls due this many days after it is issued
OUTSTANDING_STATUSES = ('issued', 'partial', 'overdue', 'disputed')


class LifecycleError(Exception):
    """The action is not allowed in the record's current state."""


class ClearanceRefused(LifecycleError):
    """The taxpayer still owes money, so no clearance certificate can be issued."""


@dataclass(frozen=True)
class AgeingSummary:
    notices_marked_overdue: int
    arrears_aged: int


def _today(today: date | None) -> date:
    return today or timezone.localdate()


def issue_assessment(assessment: Assessment, *, today: date | None = None) -> DemandNotice:
    """Issue a draft assessment: it becomes ``issued``, a demand notice is raised for it and the taxpayer's liability
    on that revenue head goes up by the assessed amount. Issuing the same assessment again returns the same notice."""
    today = _today(today)
    with transaction.atomic():
        assessment = Assessment.objects.select_for_update().get(pk=assessment.pk)
        existing = DemandNotice.objects.filter(assessment=assessment).first()
        if existing is not None:
            return existing
        if assessment.status != 'draft':
            raise LifecycleError(f'Only a draft assessment can be issued (this one is {assessment.status}).')
        if assessment.assessed_amount <= ZERO:
            raise LifecycleError('An assessment with no amount cannot be issued.')

        notice = DemandNotice.objects.create(
            taxpayer=assessment.taxpayer,
            assessment=assessment,
            notice_number=TransactionSequence.get_next('demand_notice', prefix='DN-'),
            amount_due=assessment.assessed_amount,
            due_date=today + timedelta(days=PAYMENT_TERM_DAYS),
            status='issued',
        )
        assessment.status = 'issued'
        assessment.issued_at = timezone.now()
        assessment.save(update_fields=['status', 'issued_at'])

        account, _ = TaxAccount.objects.get_or_create(taxpayer=assessment.taxpayer, revenue_head=assessment.revenue_head)
        TaxAccount.objects.filter(pk=account.pk).update(running_balance=F('running_balance') + assessment.assessed_amount)
        return notice


def process_billing_run(run: BillingRun, *, today: date | None = None) -> BillingRun:
    """Issue every draft assessment of the run's revenue head and fiscal year, once."""
    today = _today(today)
    with transaction.atomic():
        run = BillingRun.objects.select_for_update().get(pk=run.pk)
        if run.status != 'draft':
            raise LifecycleError(f'A billing run can be processed once (this one is {run.status}).')
        drafts = Assessment.objects.filter(
            revenue_head=run.revenue_head, fiscal_year=run.fiscal_year, status='draft', assessed_amount__gt=0)
        count, total = 0, ZERO
        for assessment in drafts.order_by('id'):
            notice = issue_assessment(assessment, today=today)
            DemandNotice.objects.filter(pk=notice.pk).update(billing_run=run)
            count += 1
            total += notice.amount_due
        run.status = 'processed'
        run.notices_created = count
        run.total_amount = total
        run.processed_at = timezone.now()
        run.save(update_fields=['status', 'notices_created', 'total_amount', 'processed_at'])
        return run


def update_ageing(*, as_of: date | None = None) -> AgeingSummary:
    """Mark unpaid notices past their due date overdue, and set the age in days on every unsettled arrears row."""
    as_of = _today(as_of)
    with transaction.atomic():
        late = DemandNotice.objects.filter(status__in=('issued', 'partial'), due_date__lt=as_of, amount_paid__lt=F('amount_due'))
        marked = late.update(status='overdue')
        aged = 0
        for arrears in ArrearsLedger.objects.filter(is_settled=False, amount__gt=0):
            days = max((as_of - arrears.arrears_date).days, 0)
            if arrears.ageing_days != days:
                ArrearsLedger.objects.filter(pk=arrears.pk).update(ageing_days=days)
                aged += 1
        return AgeingSummary(notices_marked_overdue=marked, arrears_aged=aged)


def issue_clearance_certificate(taxpayer, *, fiscal_year: int, today: date | None = None) -> TaxClearanceCertificate:
    """Issue a tax clearance certificate for the fiscal year, but only to a taxpayer who owes nothing that is due."""
    today = _today(today)
    reasons = []
    arrears = ArrearsLedger.objects.filter(taxpayer=taxpayer, is_settled=False, amount__gt=0).aggregate(t=Sum('amount'))['t']
    if arrears:
        reasons.append(f'unsettled arrears of {arrears}')
    overdue = DemandNotice.objects.filter(
        taxpayer=taxpayer, status__in=OUTSTANDING_STATUSES, due_date__lt=today, amount_paid__lt=F('amount_due'))
    if overdue.exists():
        reasons.append(f'{overdue.count()} unpaid demand notice(s) past their due date')
    if reasons:
        raise ClearanceRefused('Clearance refused: ' + '; '.join(reasons) + '.')
    return TaxClearanceCertificate.objects.create(
        taxpayer=taxpayer,
        certificate_number=TransactionSequence.get_next('tax_clearance', prefix='TCC-'),
        status='issued',
        fiscal_year=fiscal_year,
        issue_date=today,
        expiry_date=date(fiscal_year, 12, 31),
    )
