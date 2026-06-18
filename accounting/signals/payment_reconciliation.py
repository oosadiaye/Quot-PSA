"""
PaymentCascadeFailure post-create notification (H2 deferred — WS6).

When a new ``PaymentCascadeFailure`` row is persisted, emit:

1. A structured WARNING log entry suitable for routing to a log
   aggregator (Datadog / CloudWatch / etc.) for paging / alerting.
2. A Sentry breadcrumb if Sentry is initialised — matches the
   convention used by ``contracts/tasks.py`` where the comment notes
   "the project has no notifier abstraction yet; tasks currently emit
   structured logs + Sentry breadcrumbs". When a notifier surface
   lands (S-level), replace this hook with a real email/webhook call.

Operator workflow:
  * Alert fires from the structured log → triage in Sentry / log UI
  * Operator opens the payment-cascade reconciliation queue
    (``/api/v1/accounting/payment-cascade-failures/``)
  * Resolves via the per-row ``resolve`` action with a ≥10-char note
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounting.models import PaymentCascadeFailure

logger = logging.getLogger(__name__)


@receiver(post_save, sender=PaymentCascadeFailure)
def notify_new_cascade_failure(sender, instance, created, **kwargs):
    """Emit a structured log + Sentry breadcrumb for new rows.

    Only fires on create (``created=True``) so resolution updates
    don't double-page.
    """
    if not created:
        return

    payload = {
        'event': 'payment.cascade_failure.created',
        'failure_id': instance.pk,
        'payment_id': instance.payment_id,
        'ipc_id': instance.ipc_id,
        'error_class': instance.error_class,
        'error_message': instance.error_message,
        'action_required': (
            instance.error_context.get('action_required')
            if isinstance(instance.error_context, dict)
            else None
        ),
    }

    # Structured log for the alerting pipeline. Most log aggregators
    # parse the ``extra`` kwarg into searchable fields, so AP/finance
    # can route alerts on event=payment.cascade_failure.created.
    logger.warning(
        'Payment cascade failure persisted: payment=%s ipc=%s error=%s',
        instance.payment_id, instance.ipc_id, instance.error_class,
        extra=payload,
    )

    # Sentry breadcrumb — best-effort, never raises. Matches the
    # convention in ``contracts/tasks.py``.
    try:
        import sentry_sdk  # type: ignore[import-not-found]
        sentry_sdk.add_breadcrumb(
            category='accounting.payment_cascade',
            message=(
                f'Cascade failure on payment={instance.payment_id}, '
                f'ipc={instance.ipc_id}'
            ),
            level='warning',
            data=payload,
        )
    except ImportError:
        pass  # Sentry not installed; logging is sufficient.
    except Exception:  # noqa: BLE001
        # Breadcrumb push should never affect the originating
        # transaction. Sentry SDK errors are silently swallowed
        # because they are observability noise, not correctness signal.
        pass
