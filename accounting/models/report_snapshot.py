"""
ReportSnapshot — immutable persistence of IPSAS / statutory reports.

Auditor-General scenario: the AG reviews February's filings in August.
The statutory data behind those filings may have changed since (late-
posted journals, retroactive corrections, new vendor records). Without
a snapshot, re-running the same report returns *current* numbers, not
*as-filed* numbers, and the AG cannot verify what was actually submitted.

This model captures the exact JSON payload + a SHA-256 content hash the
instant a report is "filed" (generated with ``persist=True``). Subsequent
reads of the same (tenant, report_type, period) return the snapshot,
with the hash serving as a tamper-evidence check.

Snapshots are write-once; edits are refused at the save() layer. A new
filing for the same period creates a NEW snapshot row and the prior
one is retained for comparison.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class ReportSnapshot(models.Model):
    """Immutable per-period snapshot of an IPSAS or statutory report."""

    # What was run.
    report_type = models.CharField(
        max_length=64, db_index=True,
        help_text=(
            'Canonical key: "ipsas.sofp", "ipsas.sofperformance", '
            '"ipsas.cashflow", "ipsas.changes_in_net_assets", '
            '"ipsas.notes", "ipsas.budget_vs_actual", '
            '"statutory.firs_wht", "statutory.paye", "statutory.pencom", '
            '"statutory.nsitf", "statutory.nhia", "statutory.itf", '
            '"statutory.oagf_mfr", "statutory.firs_vat".'
        ),
    )
    fiscal_year = models.IntegerField(db_index=True)
    # For monthly reports this is the month number (1-12). For annual
    # reports (ITF, year-level IPSAS runs) this is 0 meaning "full year".
    period = models.IntegerField(default=0, db_index=True)

    # The captured artefact. JSON preserves structured data; hash is
    # computed over the sorted JSON representation so two bit-identical
    # payloads produce the same hash.
    payload = models.JSONField()
    content_hash = models.CharField(max_length=64, db_index=True)

    # Provenance.
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='report_snapshots',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['report_type', 'fiscal_year', 'period']),
            models.Index(fields=['report_type', '-generated_at']),
            models.Index(fields=['content_hash']),
            models.Index(
                fields=['report_type', 'fiscal_year', 'period', '-generated_at'],
                name='rpt_snap_lookup_idx',
            ),
        ]
        # NOT unique on (report_type, fy, period) — re-filings for the
        # same period are allowed. The "latest" snapshot is resolved at
        # read time via ``generated_at DESC``.

    def __str__(self):
        return (
            f'{self.report_type} FY{self.fiscal_year} P{self.period} '
            f'@ {self.generated_at.isoformat()} '
            f'({self.content_hash[:8]})'
        )

    # ── Write-once guarantee ──────────────────────────────────────────
    def save(self, *args, **kwargs):
        """Reject any modification of a persisted snapshot.

        A new filing for the same (report_type, fiscal_year, period)
        creates a NEW row; existing rows are immutable. This mirrors
        the ``TransactionAuditLog`` write-once pattern from Sprint 3.
        """
        if self.pk:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                'ReportSnapshot rows are write-once. To record a new '
                'filing for the same period, call '
                'ReportSnapshotService.persist(...) again — it creates '
                'a new snapshot without mutating the prior one.'
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Snapshots cannot be deleted — preserve forensic trail."""
        from django.core.exceptions import ValidationError
        raise ValidationError(
            'ReportSnapshot rows cannot be deleted. They preserve the '
            'as-filed version of IPSAS / statutory reports for audit.'
        )
