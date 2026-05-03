"""Multi-step leave request approval state machine.

Flow:
    Draft ─► Pending (on submit)
                │
                ▼
    step 1 (Line_Manager) ─ approve ─► step 2 (HR, optional)
                │                              │
                └── reject ─► LeaveRequest.status = Rejected
                                               │
                                               ▼
                                     all steps Approved
                                               │
                                               ▼
                              LeaveRequest.status = Approved
                              + debit balance (implicit via
                              aggregation; no ledger row yet)

A ``Rejected`` decision at any step short-circuits the chain and the
request status flips to ``Rejected``. Remaining pending steps become
``Skipped``.

Public API:
    submit_request(request, *, user) -> LeaveRequest
    decide_step(step, *, user, decision, comments='') -> LeaveRequest
    pending_steps_for(user) -> QuerySet[LeaveApprovalStep]
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from hrm.models import LeaveApprovalStep, LeavePolicy, LeaveRequest

DECISION_APPROVED = 'Approved'
DECISION_REJECTED = 'Rejected'
DECISION_PENDING = 'Pending'
DECISION_SKIPPED = 'Skipped'

VALID_DECISIONS = frozenset({DECISION_APPROVED, DECISION_REJECTED})


class ApprovalError(Exception):
    """Raised for invalid state transitions."""


# --------------------------------------------------------------------------- #
# Chain construction
# --------------------------------------------------------------------------- #

def _build_chain(leave_request: LeaveRequest, *, user=None) -> None:
    """Create the ordered LeaveApprovalStep rows for a request.

    Step 1 is always Line_Manager (routed to employee.supervisor if set).
    Step 2 is HR, conditional on the policy's ``requires_hr_approval`` flag.
    """
    policy = LeavePolicy.objects.filter(leave_type=leave_request.leave_type).first()
    include_hr = True if policy is None else policy.requires_hr_approval

    supervisor_user = None
    supervisor_emp = leave_request.employee.supervisor
    if supervisor_emp is not None:
        supervisor_user = getattr(supervisor_emp, 'user', None)

    LeaveApprovalStep.objects.create(
        leave_request=leave_request,
        step_order=1,
        role='Line_Manager',
        assigned_to=supervisor_user,
        created_by=user,
        updated_by=user,
    )
    if include_hr:
        LeaveApprovalStep.objects.create(
            leave_request=leave_request,
            step_order=2,
            role='HR',
            created_by=user,
            updated_by=user,
        )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

@transaction.atomic
def submit_request(leave_request: LeaveRequest, *, user=None) -> LeaveRequest:
    """Transition a Draft/Pending request into the approval chain."""
    if leave_request.status not in ('Draft', 'Pending'):
        raise ApprovalError(
            f'Cannot submit a request in status {leave_request.status!r}.'
        )
    if leave_request.start_date > leave_request.end_date:
        raise ApprovalError('start_date must be on or before end_date.')

    # Wipe any stale chain (e.g. resubmit) then rebuild.
    leave_request.approval_steps.all().delete()
    _build_chain(leave_request, user=user)

    leave_request.status = 'Pending'
    leave_request.save(update_fields=['status'])
    return leave_request


@transaction.atomic
def decide_step(
    step: LeaveApprovalStep,
    *,
    user,
    decision: str,
    comments: str = '',
) -> LeaveRequest:
    """Record an Approved/Rejected decision on a step.

    * Rejects short-circuit: remaining pending steps become ``Skipped``
      and the parent request flips to ``Rejected``.
    * If this was the final pending step and all prior are Approved,
      the request flips to ``Approved``.
    """
    if decision not in VALID_DECISIONS:
        raise ApprovalError(f'Invalid decision: {decision!r}')
    if step.decision != DECISION_PENDING:
        raise ApprovalError(
            f'Step already decided ({step.decision}); cannot overwrite.'
        )

    # Ensure earlier steps are done.
    earlier_pending = step.leave_request.approval_steps.filter(
        step_order__lt=step.step_order, decision=DECISION_PENDING,
    ).exists()
    if earlier_pending:
        raise ApprovalError(
            'Earlier steps in the chain are still pending.'
        )

    step.decision = decision
    step.approver = user
    step.decided_at = timezone.now()
    step.comments = comments
    step.updated_by = user
    step.save(update_fields=[
        'decision', 'approver', 'decided_at', 'comments', 'updated_by',
    ])

    request = step.leave_request
    if decision == DECISION_REJECTED:
        request.approval_steps.filter(decision=DECISION_PENDING).update(
            decision=DECISION_SKIPPED,
        )
        request.status = 'Rejected'
        request.comments = comments
        request.approved_by = user
        request.approved_date = timezone.now()
        request.save(update_fields=[
            'status', 'comments', 'approved_by', 'approved_date',
        ])
        return request

    # Approved — check if the chain is complete.
    still_pending = request.approval_steps.filter(
        decision=DECISION_PENDING,
    ).exists()
    if not still_pending:
        request.status = 'Approved'
        request.approved_by = user
        request.approved_date = timezone.now()
        request.save(update_fields=['status', 'approved_by', 'approved_date'])

    return request


def pending_steps_for(user):
    """Steps awaiting this specific user (by assignment)."""
    return LeaveApprovalStep.objects.filter(
        assigned_to=user, decision=DECISION_PENDING,
    ).select_related('leave_request', 'leave_request__employee')
