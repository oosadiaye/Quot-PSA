"""Persistence for in-app snapshot jobs.

Lives in the public schema (shared) so superadmins have cross-tenant
visibility. Per-row scoping for tenant admins is enforced at the
queryset layer in views.py, not by schema isolation.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class SnapshotJob(models.Model):
    """One row per snapshot request. Mutated by Celery as the job progresses."""

    class Status(models.TextChoices):
        QUEUED    = 'queued',    'Queued'
        RUNNING   = 'running',   'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED    = 'failed',    'Failed'
        EXPIRED   = 'expired',   'Expired'   # row kept, artifact removed

    id              = models.BigAutoField(primary_key=True)
    schema_name     = models.CharField(max_length=63)
    label           = models.CharField(max_length=120, blank=True)
    status          = models.CharField(
                          max_length=12, choices=Status.choices,
                          default=Status.QUEUED)

    triggered_by    = models.ForeignKey(
                          settings.AUTH_USER_MODEL,
                          on_delete=models.PROTECT,
                          related_name='+')
    triggered_at    = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at      = models.DateTimeField(null=True, blank=True)
    completed_at    = models.DateTimeField(null=True, blank=True)

    artifact_path   = models.CharField(
                          max_length=512, blank=True,
                          help_text='Path relative to SNAPSHOTS_BACKUP_DIR.')
    size_bytes      = models.BigIntegerField(null=True, blank=True)
    sha256          = models.CharField(
                          max_length=64, blank=True,
                          help_text='SHA-256 of the on-disk encrypted artifact bytes.')

    kek_fingerprint = models.CharField(
                          max_length=32, blank=True,
                          help_text='Identifier of the KEK used to encrypt the artifact (e.g., "kek-v1").')
    manifest        = models.JSONField(
                          default=dict, blank=True,
                          help_text='Mirror of the manifest.json embedded in the artifact.')

    error_message   = models.TextField(blank=True)
    error_class     = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-triggered_at', '-id']
        indexes  = [
            models.Index(fields=['schema_name', '-triggered_at']),
            models.Index(fields=['status', '-triggered_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(schema_name__regex=r'^[a-z][a-z0-9_]{0,62}$'),
                name='snapshotjob_schema_name_valid',
            ),
        ]

    def __str__(self) -> str:
        return f'SnapshotJob({self.id}, {self.schema_name}, {self.status})'
