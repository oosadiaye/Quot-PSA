"""
MDAImportLog — audit trail for every MDA bulk-import commit.

Each row records:
  * What was imported (``data_type`` + ``row_count``)
  * Idempotency key (SHA-256 over data_type + canonical rows)
  * Who imported + when (``created_by``, ``created_at``)
  * A small payload echo ({'created_count', 'updated_count',
    'created_ids'}) so a reversal or audit can reconstruct what landed.

Used by :class:`~accounting.services.mda_data_commit.MDAImportCommitService`
to short-circuit a re-commit of an already-imported payload — the client
gets the original ``CommitResult`` echoed back rather than duplicate rows.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class MDAImportLog(models.Model):
    data_type = models.CharField(
        max_length=64, db_index=True,
        help_text='journal_summary | revenue_collection | payroll_summary | provisions',
    )
    idempotency_key = models.CharField(
        max_length=64, unique=True, db_index=True,
        help_text='SHA-256 key — commits with the same payload collide here.',
    )
    row_count = models.IntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mda_import_logs',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['data_type', '-created_at']),
        ]

    def __str__(self):
        return (
            f'MDAImport {self.data_type} '
            f'{self.row_count} rows '
            f'@ {self.created_at.isoformat()} '
            f'({self.idempotency_key[:8]})'
        )
