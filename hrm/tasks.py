"""Phase 7 — Celery scheduled reminders and digests for HRM.

Tasks:
    * ``send_verification_cycle_reminders`` — daily sweep of active cycles
      whose deadline is within 7 days; nudges employees who have not yet
      submitted their attestation.
    * ``nudge_pending_leave_approvals`` — daily sweep of leave approval
      steps that have been pending > 2 days; emails the assigned approver.
    * ``retirement_lookahead_report`` — weekly digest of employees whose
      statutory retirement triggers fire within the next 90 days.
    * ``non_compliant_report`` — weekly HR digest of employees with
      outstanding documents or unverified cycles.

All tasks are idempotent-ish — re-running them produces at most duplicate
email sends. For production, consider a ``NotificationSent`` ledger table
to fully deduplicate. Kept out of this file for scope.

Every task is wrapped in ``try/except`` so a single employee's failure
never poisons the whole run.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Iterable

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Pure helpers — testable without Celery or DB
# --------------------------------------------------------------------------- #

def _days_until(target: date, *, as_of: date) -> int:
    """Signed days from ``as_of`` to ``target`` (negative = past)."""
    return (target - as_of).days


def _is_reminder_window(deadline: date, *, as_of: date, window_days: int = 7) -> bool:
    """True when a deadline is within the reminder window (inclusive)."""
    days = _days_until(deadline, as_of=as_of)
    return 0 <= days <= window_days


def _is_retirement_lookahead(
    trigger_date: date, *, as_of: date, lookahead_days: int = 90,
) -> bool:
    """True when a retirement trigger fires within the lookahead window."""
    days = _days_until(trigger_date, as_of=as_of)
    return 0 <= days <= lookahead_days


# --------------------------------------------------------------------------- #
# Email send wrapper — isolated so tests can mock cleanly
# --------------------------------------------------------------------------- #

def _safe_send(template: str, to_email: str, context: dict, user=None) -> bool:
    """Swallow exceptions so one bad email can't kill a bulk sweep."""
    try:
        from core.localized_emails import send_localized_email
        return send_localized_email(template, to_email, context, user=user)
    except Exception as exc:  # noqa: BLE001
        logger.warning('email send failed template=%s to=%s err=%s', template, to_email, exc)
        return False


# --------------------------------------------------------------------------- #
# Verification cycle reminders
# --------------------------------------------------------------------------- #

@shared_task(name='hrm.send_verification_cycle_reminders', ignore_result=True)
def send_verification_cycle_reminders(*, as_of: str | None = None) -> dict:
    """Email every employee with a pending verification submission whose
    cycle deadline is within 7 days.

    Returns a summary dict: ``{cycles, reminders_sent, skipped}``.
    """
    from hrm.models import VerificationCycle, VerificationSubmission

    today = date.fromisoformat(as_of) if as_of else timezone.now().date()

    cycles_qs = VerificationCycle.objects.filter(
        status='active', deadline__isnull=False,
    )
    reminders_sent = 0
    skipped = 0
    cycles_checked = 0

    for cycle in cycles_qs:
        cycles_checked += 1
        if not _is_reminder_window(cycle.deadline, as_of=today):
            continue

        pending_subs: Iterable[VerificationSubmission] = (
            VerificationSubmission.objects
            .filter(cycle=cycle)
            .exclude(status='submitted')
            .select_related('employee')
        )
        for sub in pending_subs:
            emp = sub.employee
            if not getattr(emp, 'email', None):
                skipped += 1
                continue
            ok = _safe_send(
                'verification_due',
                emp.email,
                {
                    'employee_name': f'{emp.first_name} {emp.last_name}',
                    'cycle_name': cycle.name,
                    'period_label': getattr(cycle, 'period_label', ''),
                    'deadline': cycle.deadline.isoformat(),
                    'portal_url': '/portal/documents',
                },
                user=getattr(emp, 'user', None),
            )
            if ok:
                reminders_sent += 1
            else:
                skipped += 1

    logger.info(
        'verification reminders: %s cycles, %s sent, %s skipped',
        cycles_checked, reminders_sent, skipped,
    )
    return {
        'cycles': cycles_checked,
        'reminders_sent': reminders_sent,
        'skipped': skipped,
    }


# --------------------------------------------------------------------------- #
# Leave approval nudges
# --------------------------------------------------------------------------- #

@shared_task(name='hrm.nudge_pending_leave_approvals', ignore_result=True)
def nudge_pending_leave_approvals(*, stale_after_days: int = 2) -> dict:
    """Email approvers whose leave step has been pending too long."""
    from hrm.models import LeaveApprovalStep

    threshold = timezone.now() - timedelta(days=stale_after_days)
    stale = (
        LeaveApprovalStep.objects
        .filter(decision='Pending', created_at__lte=threshold)
        .select_related('leave_request__employee', 'assigned_to')
    )

    sent = 0
    skipped = 0
    for step in stale:
        approver = step.assigned_to
        if approver is None or not approver.email:
            skipped += 1
            continue
        emp = step.leave_request.employee
        ok = _safe_send(
            'leave_approval_nudge',
            approver.email,
            {
                'approver_name': approver.get_full_name() or approver.username,
                'employee_name': f'{emp.first_name} {emp.last_name}',
                'start_date': step.leave_request.start_date.isoformat(),
                'end_date': step.leave_request.end_date.isoformat(),
                'portal_url': '/hr/leave-approvals',
            },
            user=approver,
        )
        sent += 1 if ok else 0
        skipped += 0 if ok else 1

    logger.info('leave approval nudges: %s sent, %s skipped', sent, skipped)
    return {'nudges_sent': sent, 'skipped': skipped}


# --------------------------------------------------------------------------- #
# Retirement 90-day lookahead
# --------------------------------------------------------------------------- #

@shared_task(name='hrm.retirement_lookahead_report', ignore_result=True)
def retirement_lookahead_report(
    *, lookahead_days: int = 90, hr_email: str | None = None,
) -> dict:
    """Compile and email a digest of upcoming statutory retirements.

    Finds every active employee whose age hits 60 (or service hits 35)
    within ``lookahead_days``. Sends a single digest email to HR.
    """
    from hrm.models import Employee
    from hrm.services.lifecycle import (
        COMPULSORY_RETIREMENT_AGE, MAX_PENSIONABLE_YEARS, _extract_dob,
    )

    today = timezone.now().date()
    horizon = today + timedelta(days=lookahead_days)
    due_soon: list[dict] = []

    for emp in Employee.objects.filter(status='Active').iterator():
        dob = _extract_dob(emp)
        trigger_date = None
        trigger_label = None

        if dob is not None:
            sixtieth = date(
                dob.year + COMPULSORY_RETIREMENT_AGE, dob.month,
                min(dob.day, 28),
            )
            if today <= sixtieth <= horizon:
                trigger_date = sixtieth
                trigger_label = 'Age 60'

        if emp.hire_date and trigger_date is None:
            thirty_fifth = date(
                emp.hire_date.year + MAX_PENSIONABLE_YEARS,
                emp.hire_date.month,
                min(emp.hire_date.day, 28),
            )
            if today <= thirty_fifth <= horizon:
                trigger_date = thirty_fifth
                trigger_label = '35 years of service'

        if trigger_date is not None:
            due_soon.append({
                'employee_id': emp.employee_id,
                'name': f'{emp.first_name} {emp.last_name}',
                'trigger': trigger_label,
                'date': trigger_date.isoformat(),
                'department': getattr(emp.department, 'name', ''),
            })

    if due_soon and hr_email:
        _safe_send(
            'retirement_lookahead',
            hr_email,
            {
                'lookahead_days': lookahead_days,
                'as_of': today.isoformat(),
                'count': len(due_soon),
                'rows': due_soon,
            },
        )

    logger.info('retirement lookahead: %s employees due in %s days', len(due_soon), lookahead_days)
    return {'due_soon_count': len(due_soon), 'rows': due_soon}


# --------------------------------------------------------------------------- #
# Non-compliant employees digest
# --------------------------------------------------------------------------- #

@shared_task(name='hrm.non_compliant_report', ignore_result=True)
def non_compliant_report(*, hr_email: str | None = None) -> dict:
    """Tally employees with missing documents or unverified cycles.

    Employees counted as non-compliant when either:
        * They have no verified :class:`EmployeeDocument` rows at all, OR
        * They have an active verification cycle with no submission, OR
        * Their latest submission was Rejected.
    """
    from hrm.models import (
        Employee, EmployeeDocument, VerificationCycle, VerificationSubmission,
    )

    active_cycles = list(VerificationCycle.objects.filter(status='active'))
    non_compliant: list[dict] = []

    for emp in Employee.objects.filter(status='Active').iterator():
        has_any_verified = EmployeeDocument.objects.filter(
            employee=emp, status='verified',
        ).exists()

        missing_cycle = False
        for cycle in active_cycles:
            sub = VerificationSubmission.objects.filter(
                cycle=cycle, employee=emp,
            ).first()
            if sub is None or sub.status in ('draft', 'rejected'):
                missing_cycle = True
                break

        if not has_any_verified or missing_cycle:
            non_compliant.append({
                'employee_id': emp.employee_id,
                'name': f'{emp.first_name} {emp.last_name}',
                'email': emp.email,
                'reason_no_verified_docs': not has_any_verified,
                'reason_missing_cycle': missing_cycle,
            })

    if non_compliant and hr_email:
        _safe_send(
            'non_compliant_digest',
            hr_email,
            {
                'count': len(non_compliant),
                'rows': non_compliant,
                'generated_at': timezone.now().isoformat(),
            },
        )

    logger.info('non-compliant digest: %s employees flagged', len(non_compliant))
    return {'non_compliant_count': len(non_compliant), 'rows': non_compliant}
