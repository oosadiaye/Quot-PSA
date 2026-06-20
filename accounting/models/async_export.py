"""
AsyncExportJob — off-the-web-worker rendering of report exports.

The synchronous export path (``ReportRenderer.render`` called inline in
a DRF view) blocks the web worker for the full duration of the
Excel/PDF render. Under concurrent exports — several operators each
pulling a Statement of Financial Position at month-end — those renders
saturate the worker pool and the whole API stalls (worker starvation).

This model is the persistence side of an ADDITIVE async path: the view
records an ``AsyncExportJob`` row, hands the job id to a Celery task,
and returns ``202 Accepted`` immediately. The task does the heavy
render on a Celery worker and writes the artefact into ``file``. The
client polls the status endpoint and downloads once ``SUCCESS``.

The existing synchronous endpoints are untouched — this is a parallel,
opt-in surface for clients that prefer the non-blocking flow.

Design notes
------------
* ``report_payload`` is the SAME pre-computed report dict the renderer
  already consumes (see ``accounting/services/report_rendering.py``).
  We store it via Django's ``JSONField`` which serialises through
  ``DjangoJSONEncoder`` — Decimals are persisted as STRINGS. The
  renderer's helpers (``_format_value``, ``_to_number``) already coerce
  string amounts, so the round-trip renders cleanly without us having
  to touch the renderer.
* ``file`` uses the tenant-aware ``async_exports/%Y/%m/`` layout,
  mirroring the dated-folder convention already in the codebase
  (e.g. vendor-invoice attachments).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AsyncExportJob(models.Model):
    """A queued / running / completed off-worker report export."""

    # ── Status lifecycle ───────────────────────────────────────────────
    STATUS_PENDING = 'PENDING'
    STATUS_RUNNING = 'RUNNING'
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    # ── What to render ─────────────────────────────────────────────────
    label = models.CharField(
        max_length=255,
        help_text='Human-readable name, e.g. '
                  '"Statement of Financial Position FY2026".',
    )
    fmt = models.CharField(
        max_length=8,
        help_text='Render format: xlsx | pdf | html.',
    )
    report_payload = models.JSONField(
        help_text='Pre-computed report dict to render. Stored via '
                  'DjangoJSONEncoder — Decimals round-trip as strings.',
    )

    # ── Render result ──────────────────────────────────────────────────
    file = models.FileField(
        upload_to='async_exports/%Y/%m/',
        null=True, blank=True,
    )
    filename = models.CharField(max_length=255, blank=True, default='')
    content_type = models.CharField(max_length=128, blank=True, default='')
    file_size = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default='')

    # ── Provenance ─────────────────────────────────────────────────────
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='async_export_jobs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'AsyncExportJob #{self.pk} {self.label} [{self.status}]'
