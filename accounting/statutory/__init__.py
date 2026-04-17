"""
accounting.statutory
====================

Nigerian statutory reporting exporters.

Each regulator has its own sub-module (see ``firs.py``, ``paye.py``, etc.).
Each exporter is a pure function over the accounting domain:

    input  = (tenant, fiscal_year, period)
    output = structured rows that serialise cleanly to the regulator's
             prescribed format (CSV today; JSON/XML to follow per-regulator
             when API integrations come online).

The exporters intentionally do NOT handle HTTP or file delivery — those
are one-liners at the view layer. This keeps the business logic testable
in the fast tier and swappable if delivery mechanics change (which they
do every couple of years as regulators refresh their portals).

Sub-modules:
  * ``firs``  — FIRS WHT monthly schedule (Form WHT returns)
  * ``paye``  — PAYE monthly schedule for the state internal revenue
                service (LIRS for Lagos, DTSG-BIR for Delta, etc.)
  * (future)  — OAGF Monthly Financial Report, PENCOM RSA schedule,
                NSITF/ITF/NHIS contributions, BPP/NOCOPO procurement
                disclosure, Remita reconciliation.

Common types:
  * ``ExportResult``   — header + rows + CSV payload + metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ExportResult:
    """Return shape for every statutory exporter.

    ``rows`` is the structured per-line data (list of dicts) useful for
    programmatic consumption and JSON APIs. ``csv`` is the same data
    rendered as RFC 4180 CSV with the header row. Metadata is optional
    context the caller renders in a cover page (period, totals).
    """
    regulator: str
    report_name: str
    tenant_name: str
    period_label: str
    rows: list[dict[str, Any]]
    csv: str
    totals: dict[str, Decimal] = field(default_factory=dict)
    generated_at: date = field(default_factory=date.today)


def format_csv(columns: list[str], rows: list[dict[str, Any]]) -> str:
    """Render ``rows`` as RFC 4180 CSV with ``columns`` in that order.

    We use the stdlib ``csv`` module because every regulator's upload
    portal treats CSV as authoritative — JSON-first tools like
    pandas.to_csv would introduce trailing spaces and float formatting
    quirks that portals reject. Values are stringified explicitly so
    Decimals don't render as ``Decimal('100.00')``.
    """
    import csv as _csv
    import io
    buf = io.StringIO()
    writer = _csv.DictWriter(
        buf, fieldnames=columns, extrasaction='ignore',
        quoting=_csv.QUOTE_MINIMAL, lineterminator='\n',
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({
            c: stringify(row.get(c, '')) for c in columns
        })
    return buf.getvalue()


def stringify(value: Any) -> str:
    """Stringify a value for CSV output without Python-specific noise."""
    if value is None:
        return ''
    if isinstance(value, Decimal):
        # Two decimal places is the universal norm for NGN amounts on
        # statutory forms.
        return f'{value:.2f}'
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
