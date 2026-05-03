"""
Contract module signal handlers.

Connected in ``ContractsConfig.ready()``.

The only signal currently wired is a post-save hook on
``ContractApprovalStep`` that fires a best-effort notification to the
*next* approver when a workflow step completes. We deliberately use
``transaction.on_commit`` so the notification is enqueued only after
the enclosing service transaction commits — otherwise an escalation
notice could fire for an approval that gets rolled back by a later
invariant check.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("contracts.signals")


@receiver(post_save, sender="contracts.ContractApprovalStep")
def _enqueue_notify_on_step(sender, instance, created, **_kwargs) -> None:
    """When a new approval step lands, ping the next approver queue.

    Failure to enqueue is logged and swallowed — a broker outage must
    never break the service-layer transaction that *recorded* the step
    (which is the real audit-trail obligation). The workflow advances
    either way.
    """
    if not created:
        return

    def _on_commit() -> None:
        try:
            from django_tenants.utils import connection
            from contracts.tasks import notify_approval_assigned

            schema = getattr(connection, "schema_name", "public")
            notify_approval_assigned.delay(
                schema=schema,
                object_type=instance.object_type,
                object_id=instance.object_id,
                role=instance.role_required or "",
            )
        except Exception:           # noqa: BLE001
            logger.exception(
                "failed to enqueue notify_approval_assigned for step %s",
                instance.pk,
            )

    transaction.on_commit(_on_commit)
