"""
Celery tasks for the contracts workflow.

Three responsibility bands:

1. **Escalation** (periodic)
     - ``escalate_stale_variations`` / ``escalate_stale_ipcs`` scan each
       tenant schema for approvals whose status has been unchanged for
       longer than the SLA and record an ESCALATE audit step. The next
       approval tier is pinged and the event is logged for supervisory
       dashboards. Objects are **not** force-advanced — escalation is a
       visibility control, not a rubber-stamp.

2. **Reminder** (periodic)
     - ``send_pending_approval_reminders`` warns the current assignee
       N hours before SLA expiry so they act before escalation.

3. **Notification** (one-shot, enqueued by service layer)
     - ``notify_approval_assigned`` fires on submit/certify/approve to
       let the *next* actor know there's work queued for them.

All tasks iterate tenants via ``get_tenant_model().objects.exclude(
schema_name='public')`` and wrap per-tenant work in ``schema_context``
so the ORM reads/writes land in the correct schema.

Intentionally *not* implemented here:
  - email/SMS delivery — the project has no notifier abstraction yet;
    tasks currently emit structured logs + Sentry breadcrumbs. When a
    notifier lands (S-level), replace ``_notify(...)`` with the real call.
  - force-advance on SLA breach — policy decision. Public-sector audit
    practice is to escalate *visibility*, not bypass the approver.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("contracts.tasks")


# ── Tenant iteration helper ────────────────────────────────────────────

def _iter_tenant_schemas() -> Iterable[str]:
    """Yield non-public tenant schema names.

    Defensive against the tenant table being missing (fresh installs)
    or containing a schemaless row — we skip and carry on.
    """
    try:
        from django_tenants.utils import get_tenant_model
    except ImportError:   # pragma: no cover — django-tenants always installed
        return []
    Tenant = get_tenant_model()
    return (
        Tenant.objects
        .exclude(schema_name="public")
        .exclude(schema_name="")
        .values_list("schema_name", flat=True)
    )


def _schema_context(schema_name: str):
    """Late import so the module imports cleanly in non-tenant contexts."""
    from django_tenants.utils import schema_context
    return schema_context(schema_name)


# ── Notification stub ──────────────────────────────────────────────────

def _notify(event: str, **context) -> None:
    """Structured-log a workflow event. Replace with real notifier later."""
    logger.info("contracts.workflow.%s %s", event, context)


# ── 1. Variation escalation ────────────────────────────────────────────

_ESCALATABLE_VARIATION_STATUSES: dict[str, str] = {
    # DB value → SLA-table key
    "SUBMITTED": "variation_submitted",
    "REVIEWED":  "variation_reviewed",
}


@shared_task(name="contracts.tasks.escalate_stale_variations",
             ignore_result=True)
def escalate_stale_variations() -> dict[str, int]:
    """Scan every tenant for variations that have sat too long.

    Returns a ``{schema: count}`` dict for observability; Celery logs
    capture it but we also return it so unit tests can assert on the
    shape without standing up a broker.
    """
    from contracts.models import (
        ApprovalAction,
        ApprovalObjectType,
        ContractApprovalStep,
        ContractVariation,
    )
    from contracts.sla import sla_delta

    totals: dict[str, int] = {}
    now = timezone.now()

    for schema in _iter_tenant_schemas():
        escalated = 0
        with _schema_context(schema):
            for status, sla_key in _ESCALATABLE_VARIATION_STATUSES.items():
                cutoff = now - sla_delta(sla_key)
                qs = (
                    ContractVariation.objects
                    .filter(status=status, updated_at__lt=cutoff)
                    .select_related("contract", "updated_by")
                )
                for variation in qs:
                    with transaction.atomic():
                        # Idempotency: don't double-escalate the same (object,
                        # status, day) bucket. A single ESCALATE step per UTC
                        # day per object is enough to drive the dashboard.
                        already = (
                            ContractApprovalStep.objects
                            .filter(
                                object_type=ApprovalObjectType.VARIATION,
                                object_id=variation.pk,
                                action=ApprovalAction.ESCALATE,
                                action_at__date=now.date(),
                            )
                            .exists()
                        )
                        if already:
                            continue

                        ContractApprovalStep.objects.create(
                            object_type=ApprovalObjectType.VARIATION,
                            object_id=variation.pk,
                            contract=variation.contract,
                            step_number=999,
                            role_required="contracts.escalate_variation",
                            action=ApprovalAction.ESCALATE,
                            action_by=variation.updated_by,
                            notes=(
                                f"Auto-escalated after SLA breach at "
                                f"{status} status (SLA key {sla_key})."
                            ),
                        )
                        _notify(
                            "variation_escalated",
                            schema=schema,
                            variation_id=variation.pk,
                            contract_id=variation.contract_id,
                            status=status,
                            tier=variation.approval_tier,
                            age_hours=_age_hours(variation.updated_at, now),
                        )
                        escalated += 1
        totals[schema] = escalated
        if escalated:
            logger.warning(
                "contracts.sla variations escalated schema=%s count=%d",
                schema, escalated,
            )
    return totals


# ── 2. IPC escalation ──────────────────────────────────────────────────

_ESCALATABLE_IPC_STATUSES: dict[str, str] = {
    "SUBMITTED":          "ipc_submitted",
    "CERTIFIER_REVIEWED": "ipc_certifier_reviewed",
    "APPROVED":           "ipc_approved",
    "VOUCHER_RAISED":     "ipc_voucher_raised",
}


@shared_task(name="contracts.tasks.escalate_stale_ipcs", ignore_result=True)
def escalate_stale_ipcs() -> dict[str, int]:
    from contracts.models import (
        ApprovalAction,
        ApprovalObjectType,
        ContractApprovalStep,
        InterimPaymentCertificate,
    )
    from contracts.sla import sla_delta

    totals: dict[str, int] = {}
    now = timezone.now()

    for schema in _iter_tenant_schemas():
        escalated = 0
        with _schema_context(schema):
            for status, sla_key in _ESCALATABLE_IPC_STATUSES.items():
                cutoff = now - sla_delta(sla_key)
                qs = (
                    InterimPaymentCertificate.objects
                    .filter(status=status, updated_at__lt=cutoff)
                    .select_related("contract", "updated_by")
                )
                for ipc in qs:
                    with transaction.atomic():
                        already = (
                            ContractApprovalStep.objects
                            .filter(
                                object_type=ApprovalObjectType.IPC,
                                object_id=ipc.pk,
                                action=ApprovalAction.ESCALATE,
                                action_at__date=now.date(),
                            )
                            .exists()
                        )
                        if already:
                            continue

                        ContractApprovalStep.objects.create(
                            object_type=ApprovalObjectType.IPC,
                            object_id=ipc.pk,
                            contract=ipc.contract,
                            step_number=999,
                            role_required="contracts.escalate_ipc",
                            action=ApprovalAction.ESCALATE,
                            action_by=ipc.updated_by,
                            notes=(
                                f"Auto-escalated after SLA breach at "
                                f"{status} status (SLA key {sla_key})."
                            ),
                        )
                        _notify(
                            "ipc_escalated",
                            schema=schema,
                            ipc_id=ipc.pk,
                            contract_id=ipc.contract_id,
                            status=status,
                            age_hours=_age_hours(ipc.updated_at, now),
                        )
                        escalated += 1
        totals[schema] = escalated
        if escalated:
            logger.warning(
                "contracts.sla ipcs escalated schema=%s count=%d",
                schema, escalated,
            )
    return totals


# ── 3. Pending-approval reminders ──────────────────────────────────────

@shared_task(name="contracts.tasks.send_pending_approval_reminders",
             ignore_result=True)
def send_pending_approval_reminders() -> dict[str, int]:
    """Warn assignees shortly before SLA expiry.

    For each tenant, find approvals that will breach SLA within the
    ``reminder_lead_hours`` window and emit a reminder event. A simple
    bucketing guard (one reminder per object per day) keeps us from
    spamming if beat fires more often than the lead window.
    """
    from contracts.models import (
        ApprovalAction,
        ApprovalObjectType,
        ContractApprovalStep,
        ContractVariation,
        InterimPaymentCertificate,
    )
    from contracts.sla import reminder_lead, sla_delta

    totals: dict[str, int] = {}
    now = timezone.now()
    lead = reminder_lead()

    for schema in _iter_tenant_schemas():
        reminded = 0
        with _schema_context(schema):
            reminded += _remind(
                ContractVariation,
                ApprovalObjectType.VARIATION,
                _ESCALATABLE_VARIATION_STATUSES,
                sla_delta, lead, now,
                ApprovalAction, ContractApprovalStep,
                schema, "variation_reminder",
            )
            reminded += _remind(
                InterimPaymentCertificate,
                ApprovalObjectType.IPC,
                _ESCALATABLE_IPC_STATUSES,
                sla_delta, lead, now,
                ApprovalAction, ContractApprovalStep,
                schema, "ipc_reminder",
            )
        totals[schema] = reminded
    return totals


def _remind(
    Model, object_type, status_map, sla_delta_fn, lead, now,
    ApprovalAction, ContractApprovalStep, schema, event_name,
) -> int:
    reminded = 0
    for status, sla_key in status_map.items():
        window_end   = now - (sla_delta_fn(sla_key) - lead)
        window_start = now - sla_delta_fn(sla_key)
        qs = (
            Model.objects
            .filter(
                status=status,
                updated_at__gte=window_start,
                updated_at__lt=window_end,
            )
            .select_related("contract")
        )
        for obj in qs:
            already = (
                ContractApprovalStep.objects
                .filter(
                    object_type=object_type,
                    object_id=obj.pk,
                    action=ApprovalAction.REQUEST_INFO,
                    notes__startswith="[reminder]",
                    action_at__date=now.date(),
                )
                .exists()
            )
            if already:
                continue
            _notify(event_name, schema=schema,
                    object_id=obj.pk, contract_id=obj.contract_id,
                    status=status, expires_in_hours=lead.total_seconds() / 3600)
            reminded += 1
    return reminded


# ── 4. One-shot assignment notification ────────────────────────────────

@shared_task(name="contracts.tasks.notify_approval_assigned",
             ignore_result=True)
def notify_approval_assigned(
    schema: str, object_type: str, object_id: int, role: str,
) -> None:
    """Fire-and-forget: a new approval step was assigned. Called by the
    service layer after submit/certify/approve transitions."""
    _notify(
        "approval_assigned",
        schema=schema,
        object_type=object_type,
        object_id=object_id,
        role=role,
    )


# ── 5. Nightly balance reconciliation ──────────────────────────────────

@shared_task(name="contracts.tasks.reconcile_contract_balances",
             ignore_result=True)
def reconcile_contract_balances() -> dict[str, int]:
    """Recompute balance.cumulative_gross_certified from the IPC log
    and flag drift. *Read-only* — writes would fight the trigger — the
    task only emits an audit event for any discrepancy.
    """
    from decimal import Decimal

    from django.db.models import Sum

    from contracts.models import ContractBalance, InterimPaymentCertificate

    totals: dict[str, int] = {}
    for schema in _iter_tenant_schemas():
        drift = 0
        with _schema_context(schema):
            for balance in ContractBalance.objects.select_related("contract"):
                certified_from_ipcs = (
                    InterimPaymentCertificate.objects
                    .filter(
                        contract=balance.contract,
                        status__in=("APPROVED", "VOUCHER_RAISED", "PAID"),
                    )
                    .aggregate(s=Sum("this_certificate_gross"))
                    ["s"] or Decimal("0.00")
                )
                if certified_from_ipcs != balance.cumulative_gross_certified:
                    logger.error(
                        "contracts.balance_drift schema=%s contract=%s "
                        "ipc_sum=%s balance=%s",
                        schema, balance.contract_id,
                        certified_from_ipcs,
                        balance.cumulative_gross_certified,
                    )
                    drift += 1
        totals[schema] = drift
    return totals


# ── Helpers ────────────────────────────────────────────────────────────

def _age_hours(ts: datetime, now: datetime) -> float:
    return round((now - ts).total_seconds() / 3600.0, 1)
