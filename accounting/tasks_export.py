"""
Celery task for off-worker report export rendering (additive).

``run_async_export(job_id)`` is enqueued by the async-export view
(``accounting/views/async_export.py``) immediately after it records an
``AsyncExportJob`` row. It performs the heavy ``ReportRenderer.render``
call on a Celery worker rather than the web worker, then writes the
rendered artefact into the job's ``file`` field.

This fixes worker starvation under concurrent exports: the web worker
returns ``202 Accepted`` the instant the job is queued, freeing it to
serve other requests while the render happens elsewhere.

Failure handling
----------------
The task NEVER crashes silently. Any exception during render or save is
caught, the job is moved to ``FAILED`` with a truncated ``error``
message and a ``completed_at`` stamp, and the error is logged. This
keeps the polling client informed (it sees ``FAILED`` + the reason)
instead of a job stuck in ``RUNNING`` forever.

Decimal round-trip
------------------
``report_payload`` is stored via ``JSONField`` (DjangoJSONEncoder), so
Decimals arrive here as STRINGS. ``ReportRenderer`` already coerces
string amounts (``_format_value`` / ``_to_number``), so we pass the
payload through unchanged — we do NOT modify the renderer.
"""
from __future__ import annotations

import logging

# Celery is an optional runtime dependency — mirror the resilient import
# used in ``contracts/tasks.py`` so this module imports cleanly even on a
# celery-less deployment (the task body still runs when invoked directly,
# e.g. under CELERY_TASK_ALWAYS_EAGER in tests).
try:
    from celery import shared_task  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — exercised only on celery-less envs
    def shared_task(*dargs, **dkwargs):  # type: ignore[no-redef]
        """Fallback when celery isn't installed: the decorated function runs
        INLINE, but we still attach ``.delay`` / ``.apply_async`` so call
        sites (``run_async_export.delay(id)``) work unchanged — they just
        execute synchronously instead of enqueueing. Without this the
        function had no ``.delay`` attribute and every enqueue raised
        ``AttributeError`` on celery-less deployments / brokerless test runs.
        """
        def _wrap(fn):
            fn.delay = lambda *a, **k: fn(*a, **k)  # type: ignore[attr-defined]
            fn.apply_async = (  # type: ignore[attr-defined]
                lambda args=None, kwargs=None, **_k: fn(*(args or ()), **(kwargs or {}))
            )
            return fn

        if dargs and callable(dargs[0]) and not dkwargs:
            return _wrap(dargs[0])
        return _wrap

from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger('accounting.tasks_export')

# Keep the persisted error message bounded — a stack-trace-laden
# exception string should not bloat the row or the API response.
_MAX_ERROR_CHARS = 2000


@shared_task(name='accounting.tasks_export.run_async_export',
             ignore_result=True)
def run_async_export(job_id: int) -> None:
    """Render an ``AsyncExportJob`` off the web worker.

    Loads the job, renders ``report_payload`` in the requested format,
    and stores the artefact on the job. On success: status=SUCCESS with
    filename/content_type/file_size populated. On any failure:
    status=FAILED with a truncated error message. Either way the job is
    stamped ``completed_at`` so the client's poll terminates.
    """
    from accounting.models import AsyncExportJob

    try:
        job = AsyncExportJob.objects.get(pk=job_id)
    except AsyncExportJob.DoesNotExist:
        # Nothing to update — the row was deleted between enqueue and
        # execution. Log and return; re-raising would just bounce the
        # task with no row to mark FAILED.
        logger.warning(
            'run_async_export: AsyncExportJob id=%s no longer exists', job_id,
        )
        return

    job.status = AsyncExportJob.STATUS_RUNNING
    job.save(update_fields=['status'])

    try:
        from accounting.services.report_rendering import ReportRenderer

        result = ReportRenderer.render(job.report_payload, job.fmt)

        content = result['content']
        if isinstance(content, str):
            content = content.encode('utf-8')

        suggested = result.get('suggested_filename') or f'export-{job.pk}'
        job.file.save(
            suggested,
            ContentFile(content, name=suggested),
            save=False,
        )
        job.filename = suggested
        job.content_type = result.get('content_type', '')
        job.file_size = len(content)
        job.error = ''
        job.status = AsyncExportJob.STATUS_SUCCESS
        job.completed_at = timezone.now()
        job.save(update_fields=[
            'file', 'filename', 'content_type', 'file_size',
            'error', 'status', 'completed_at',
        ])
        logger.info(
            'run_async_export: job=%s rendered ok (%s, %d bytes)',
            job.pk, job.fmt, job.file_size,
        )
    except Exception as exc:  # noqa: BLE001 — never let the task crash silently
        job.status = AsyncExportJob.STATUS_FAILED
        job.error = str(exc)[:_MAX_ERROR_CHARS]
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error', 'completed_at'])
        logger.exception(
            'run_async_export: job=%s failed during render/save', job.pk,
        )
