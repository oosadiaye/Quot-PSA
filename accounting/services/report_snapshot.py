"""
ReportSnapshot service — persist and retrieve as-filed reports.

Used by IPSAS and statutory report views to optionally snapshot a
generated report:

    from accounting.services.report_snapshot import ReportSnapshotService
    snap = ReportSnapshotService.persist(
        report_type='ipsas.sofp',
        fiscal_year=2026, period=4,
        payload=report_dict, user=request.user,
    )

and to retrieve a previously-filed version:

    snap = ReportSnapshotService.get_latest(
        report_type='ipsas.sofp', fiscal_year=2026, period=4,
    )

The hash is computed over the canonical sorted-JSON serialisation of
the payload so two bit-identical payloads always produce the same hash
(no Python dict-ordering flakiness).
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any


class ReportSnapshotService:

    # ── Persist ─────────────────────────────────────────────────────────

    @classmethod
    def persist(
        cls,
        *,
        report_type: str,
        fiscal_year: int,
        period: int = 0,
        payload: dict,
        user=None,
        notes: str = '',
    ):
        """Record ``payload`` as a snapshot for ``(report_type, fy, period)``.

        Creates a NEW row every call — prior snapshots are retained so
        a re-filing doesn't destroy the original. Returns the persisted
        ``ReportSnapshot`` instance.
        """
        from accounting.models import ReportSnapshot

        serialised, canonical_hash = cls._serialise_and_hash(payload)

        return ReportSnapshot.objects.create(
            report_type=report_type,
            fiscal_year=fiscal_year,
            period=period,
            payload=serialised,
            content_hash=canonical_hash,
            generated_by=user if (user and getattr(user, 'is_authenticated', False)) else None,
            notes=notes or '',
        )

    # ── Retrieve ────────────────────────────────────────────────────────

    @classmethod
    def get_latest(
        cls,
        *,
        report_type: str,
        fiscal_year: int,
        period: int = 0,
    ):
        """Most-recent snapshot for the (report_type, fy, period) triple.

        Returns ``None`` when no snapshot exists — callers typically
        fall back to running the live report in that case.
        """
        from accounting.models import ReportSnapshot
        return (
            ReportSnapshot.objects
            .filter(
                report_type=report_type,
                fiscal_year=fiscal_year,
                period=period,
            )
            .order_by('-generated_at')
            .first()
        )

    @classmethod
    def list_versions(
        cls,
        *,
        report_type: str,
        fiscal_year: int,
        period: int = 0,
    ):
        """All snapshot versions for a (report_type, fy, period) triple,
        newest first. Used by the "filing history" UI."""
        from accounting.models import ReportSnapshot
        return (
            ReportSnapshot.objects
            .filter(
                report_type=report_type,
                fiscal_year=fiscal_year,
                period=period,
            )
            .order_by('-generated_at')
        )

    # ── Hash verification ──────────────────────────────────────────────

    @classmethod
    def verify_hash(cls, snapshot) -> bool:
        """Recompute the hash over ``snapshot.payload`` and compare to
        the stored ``content_hash``.

        Returns True when they match — signalling the stored payload has
        not been tampered with since snapshot creation. A False return
        indicates either (a) row-level tampering or (b) a canonical-
        serialisation discrepancy that the investigator should flag.
        """
        _, recomputed = cls._serialise_and_hash(snapshot.payload)
        return recomputed == snapshot.content_hash

    # ── Internals ──────────────────────────────────────────────────────

    @staticmethod
    def _serialise_and_hash(payload: dict) -> tuple[dict, str]:
        """Canonicalise ``payload`` for stable hashing.

        Two constraints:
          * The payload must survive JSONField round-trip — Decimal and
            date values from IPSAS services don't serialise natively, so
            we coerce them here and also return the canonical-serialised
            dict to ensure the stored JSON matches the hashed bytes.
          * Dict key order must be deterministic — ``sort_keys=True``
            below guarantees this.
        """
        canonical = _canonicalise(payload)
        text = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        return canonical, digest


def _canonicalise(value: Any) -> Any:
    """Recursively normalise a payload so it survives JSON round-trip.

    * ``Decimal`` → string (preserves precision and ensures identical
      hash regardless of locale/float subtleties).
    * ``date`` / ``datetime`` → ISO-8601 string.
    * lists preserve order; dicts preserve keys (sorting happens at
      hash time via ``json.dumps(..., sort_keys=True)``).
    """
    from datetime import date, datetime
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _canonicalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalise(v) for v in value]
    return value
