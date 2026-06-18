"""Thin lifecycle-event audit recorders for the snapshots feature.

Best-effort: if the audit-log DB write fails, we still emit a structured
log line and continue. Audit failure must never block the action being audited.

Lifecycle events recorded:
    record_created      — snapshot job creation (POST)
    record_started      — status transition → RUNNING
    record_succeeded    — status transition → SUCCEEDED
    record_failed       — status transition → FAILED
    record_downloaded   — download action invoked
    record_deleted      — destroy action invoked
    record_expired      — retention transitions row → EXPIRED
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# AuditLog ACTION_CHOICES don't include domain-specific verbs, so we map
# snapshot events to the closest generic action code supported by the model.
# NOTE: 'snapshot.started', 'snapshot.succeeded', and 'snapshot.expired' all
# map to 'UPDATE' because ACTION_CHOICES has no finer-grained status codes.
# To distinguish them in DB queries, filter on description='snapshot.<event>'.
_ACTION_MAP: dict[str, str] = {
    'snapshot.created':    'CREATE',
    'snapshot.started':    'UPDATE',
    'snapshot.succeeded':  'UPDATE',
    'snapshot.failed':     'UPDATE',
    'snapshot.downloaded': 'EXPORT',
    'snapshot.deleted':    'DELETE',
    'snapshot.expired':    'UPDATE',
}


def _job_pk(job: Any) -> int | None:
    """Return the integer PK whether *job* is a SnapshotJob or a bare int."""
    if job is None:
        return None
    if hasattr(job, 'pk'):
        return job.pk
    try:
        return int(job)
    except (TypeError, ValueError):
        return None


def _actor_id(actor: Any) -> int | None:
    """Return the integer PK whether *actor* is a User or None."""
    if actor is None:
        return None
    return getattr(actor, 'pk', None)


def _emit(action: str, actor: Any = None, job: Any = None, **extras: Any) -> None:
    """Emit a structured log line; then attempt a best-effort DB write."""
    actor_id = _actor_id(actor)
    job_id = _job_pk(job)

    extra_payload: dict[str, Any] = {
        'action': action,
        'actor_id': actor_id,
        'job_id': job_id,
        **extras,
    }

    # Structured log line — key=value pairs for log-aggregation pipelines.
    # - 'action' is excluded from kv_pairs as it already appears in the format
    #   prefix, preventing a duplicate action=foo action=foo pattern.
    # - Structural fields (actor_id, job_id) are always included so system-
    #   triggered events are clearly identified by actor_id=None.
    # - Optional extras with falsy values (e.g. ip_address=None/'') are omitted
    #   to keep log lines clean.
    _STRUCTURAL_KEYS = frozenset({'actor_id', 'job_id'})
    kv_pairs = ' '.join(
        f'{k}={v}' for k, v in extra_payload.items()
        if k != 'action' and (k in _STRUCTURAL_KEYS or v not in (None, ''))
    )
    logger.info(
        'snapshots.audit action=%s %s',
        action,
        kv_pairs,
        extra=extra_payload,
    )

    # Best-effort DB write — never raise on failure.
    try:
        _write_audit_row(action=action, actor=actor, job=job, extras=extras)
    except Exception:
        logger.warning(
            'snapshots.audit: DB write failed for action=%s',
            action,
            exc_info=True,
        )


def _write_audit_row(
    action: str,
    actor: Any,
    job: Any,
    extras: dict[str, Any],
) -> None:
    """Write to core.AuditLog.

    Lazy import so the module works even if 'core' is not in INSTALLED_APPS
    during isolated unit tests that don't touch the DB.
    """
    from core.models import AuditLog  # noqa: PLC0415 (lazy import by design)

    db_action = _ACTION_MAP.get(action, 'UPDATE')
    job_pk = _job_pk(job)

    kwargs: dict[str, Any] = {
        'user': actor,
        'action': db_action,
        'instance': job,
        'object_id': job_pk,
        'object_repr': str(job) if job is not None else '',
        'object_key': f'SnapshotJob:{job_pk}' if job_pk is not None else '',
        'description': action,
        'ip_address': extras.get('ip_address') or None,
    }

    if action == 'snapshot.failed':
        # Persist error context in the changes field so failed-snapshot rows
        # are queryable by error class/message without parsing log lines.
        kwargs['changes'] = {
            'error_class': extras.get('error_class', ''),
            'error_message': extras.get('error_message', ''),
        }

    AuditLog.log_action(**kwargs)


# ── Public recorders ────────────────────────────────────────────────────────

def record_created(actor: Any, job: Any) -> None:
    """Record snapshot job creation (POST)."""
    _emit(
        'snapshot.created',
        actor=actor,
        job=job,
        schema_name=getattr(job, 'schema_name', ''),
    )


def record_started(job: Any) -> None:
    """Record transition → RUNNING (system-triggered, no actor)."""
    _emit(
        'snapshot.started',
        actor=None,
        job=job,
        schema_name=getattr(job, 'schema_name', ''),
    )


def record_succeeded(job: Any) -> None:
    """Record transition → SUCCEEDED."""
    _emit(
        'snapshot.succeeded',
        actor=None,
        job=job,
        schema_name=getattr(job, 'schema_name', ''),
        size_bytes=getattr(job, 'size_bytes', None),
    )


def record_failed(job: Any, error_class: str, error_message: str) -> None:
    """Record transition → FAILED."""
    _emit(
        'snapshot.failed',
        actor=None,
        job=job,
        schema_name=getattr(job, 'schema_name', ''),
        error_class=error_class,
        error_message=(error_message or '')[:200],
    )


def record_downloaded(actor: Any, job: Any, ip_address: str | None = None) -> None:
    """Record download action invocation."""
    _emit(
        'snapshot.downloaded',
        actor=actor,
        job=job,
        schema_name=getattr(job, 'schema_name', ''),
        ip_address=ip_address or None,
    )


def record_deleted(actor: Any, job: Any) -> None:
    """Record destroy action invocation."""
    _emit(
        'snapshot.deleted',
        actor=actor,
        job=job,
        schema_name=getattr(job, 'schema_name', ''),
    )


def record_expired(job: Any) -> None:
    """Record retention transition → EXPIRED (system-triggered, no actor)."""
    _emit(
        'snapshot.expired',
        actor=None,
        job=job,
        schema_name=getattr(job, 'schema_name', ''),
    )
