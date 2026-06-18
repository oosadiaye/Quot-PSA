"""
Celery task wrappers for workflow approval notifications.

Mirrors the pattern used in contracts/tasks.py: a shared_task that dispatches
to notification functions, plus an enqueue helper that wraps everything in
transaction.on_commit so notifications only fire after the DB commit succeeds.
"""
from __future__ import annotations

import logging

try:
    from celery import shared_task
    _HAS_CELERY = True
except ImportError:
    _HAS_CELERY = False

    def shared_task(*dargs, **dkwargs):  # type: ignore[misc]
        """No-op decorator used when Celery is not installed."""
        if dargs and callable(dargs[0]) and not dkwargs:
            return dargs[0]

        def _decorator(fn):
            return fn

        return _decorator


logger = logging.getLogger('workflow.tasks')


@shared_task(name='workflow.send_approval_notification')
def send_approval_notification(event: str, approval_id: int, **kwargs) -> None:
    """
    Dispatch an approval event to the appropriate notification function.

    Supported events:
      - 'submitted'      → notify_approval_submitted(approval_id)
      - 'step_advanced'  → notify_approval_step_advanced(approval_id, new_step_number=...)
      - 'completed'      → notify_approval_completed(approval_id)
      - 'rejected'       → notify_approval_rejected(approval_id, rejecting_step_number=...)
      - 'cancelled'      → notify_approval_cancelled(approval_id)
      - 'sla_breach'     → notify_approval_sla_breach(approval_step_id=...)
    """
    from workflow.notifications import (
        notify_approval_submitted,
        notify_approval_step_advanced,
        notify_approval_completed,
        notify_approval_rejected,
        notify_approval_cancelled,
        notify_approval_sla_breach,
    )

    dispatch = {
        'submitted': lambda: notify_approval_submitted(approval_id),
        'step_advanced': lambda: notify_approval_step_advanced(
            approval_id, kwargs['new_step_number']
        ),
        'completed': lambda: notify_approval_completed(approval_id),
        'rejected': lambda: notify_approval_rejected(
            approval_id, kwargs['rejecting_step_number']
        ),
        'cancelled': lambda: notify_approval_cancelled(approval_id),
        'sla_breach': lambda: notify_approval_sla_breach(kwargs['approval_step_id']),
    }

    fn = dispatch.get(event)
    if fn is not None:
        fn()
    else:
        logger.warning('send_approval_notification: unknown event %r', event)


def enqueue_approval_notification(event: str, approval_id: int, **kwargs) -> None:
    """
    Schedule an approval notification to fire after the current DB transaction commits.

    Uses Celery's .delay() when available; falls back to a synchronous call.
    Always wrapped in transaction.on_commit() so no email/in-app notification
    fires if the surrounding transaction is rolled back.
    """
    from django.db import transaction

    def _go() -> None:
        try:
            if _HAS_CELERY:
                send_approval_notification.delay(event, approval_id, **kwargs)
            else:
                send_approval_notification(event, approval_id, **kwargs)
        except Exception:
            logger.exception(
                'enqueue_approval_notification failed for event=%s approval=%s',
                event,
                approval_id,
            )

    transaction.on_commit(_go)
