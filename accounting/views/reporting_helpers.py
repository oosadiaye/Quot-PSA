"""
Shared report-delivery helpers for IPSAS + statutory view modules.

``serve_report(request, result, filename_stem, *, report_type=None,
fiscal_year=None, period=None)`` handles the full delivery path:

  1. **Format negotiation** via ``?format=json|html|pdf|xlsx`` (default json).
     Delegates to ``accounting.services.report_rendering.ReportRenderer``
     for non-json formats.

  2. **Snapshot persistence** via ``?persist=true``. Calls
     ``ReportSnapshotService.persist()`` with the current result dict
     before serving. The resulting snapshot ID is attached to JSON
     responses under ``_snapshot`` and to non-JSON responses via the
     ``X-Snapshot-Id`` header.

Both features are opt-in so existing callers remain unaffected.

Usage
-----
In an IPSAS or statutory view ``.get()``::

    result = SomeService.method(...)            # dict or ExportResult
    return serve_report(
        request, result,
        filename_stem='sofp-2026-04',
        report_type='ipsas.sofp',
        fiscal_year=2026, period=4,
    )
"""
from __future__ import annotations

from dataclasses import is_dataclass, asdict
from typing import Any, Optional

from django.http import HttpResponse
from rest_framework.response import Response


def serve_report(
    request,
    result: Any,
    filename_stem: str = 'report',
    *,
    report_type: Optional[str] = None,
    fiscal_year: Optional[int] = None,
    period: Optional[int] = None,
) -> HttpResponse:
    """Serve ``result`` in the format the caller asked for + optionally
    persist it as a ReportSnapshot.

    ``result`` can be:
      * a dict (IPSAS report output)
      * an ``accounting.statutory.ExportResult`` dataclass
      * any ``dataclasses`` instance — it'll be coerced to a dict

    The helper only supports GET-shaped responses; viewsets that need
    to mutate state should do it explicitly in the action body before
    calling this helper.
    """
    payload = _to_dict(result)
    fmt = (request.query_params.get('format') or 'json').strip().lower()
    persist_flag = _truthy(request.query_params.get('persist'))

    # ── Snapshot persistence (best-effort, non-blocking for the render path)
    snapshot_meta: Optional[dict] = None
    if persist_flag and report_type and fiscal_year is not None:
        snapshot_meta = _try_persist(
            payload=payload,
            report_type=report_type,
            fiscal_year=fiscal_year,
            period=period,
            user=getattr(request, 'user', None),
        )

    # ── Format negotiation
    if fmt in ('', 'json'):
        body = _prepare_json_body(payload, snapshot_meta)
        return Response(body)

    if fmt in ('html', 'pdf', 'xlsx', 'excel'):
        # The renderer understands 'xlsx' natively; normalise 'excel' → 'xlsx'.
        normalised_fmt = 'xlsx' if fmt == 'excel' else fmt
        from accounting.services.report_rendering import ReportRenderer
        rendered = ReportRenderer.render(payload, normalised_fmt)

        # Use the caller's filename_stem as a hint but honour what the
        # renderer suggests (it knows the right extension).
        filename = rendered.get('suggested_filename') or f'{filename_stem}.{normalised_fmt}'
        response = HttpResponse(
            rendered['content'],
            content_type=rendered['content_type'],
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{filename}"'
        )

        # Surface snapshot id in a header so client scripts can log it.
        if snapshot_meta:
            response['X-Snapshot-Id'] = str(snapshot_meta['id'])
            response['X-Snapshot-Hash'] = snapshot_meta['content_hash'][:16]

        # Surface fallback reason from the PDF→HTML degradation path so
        # clients can show a helpful "PDF not available on this server"
        # notice to the user.
        if rendered.get('fallback_reason'):
            response['X-Render-Fallback'] = rendered['fallback_reason']

        return response

    return Response(
        {
            'error': f'Unsupported format {fmt!r}. '
                     f'Supported: json, html, pdf, xlsx.',
        },
        status=400,
    )


# ── Helpers ────────────────────────────────────────────────────────────

def _to_dict(result: Any) -> dict:
    """Coerce various result shapes into a plain dict for rendering."""
    if isinstance(result, dict):
        return result
    # ExportResult + any other dataclass.
    if is_dataclass(result):
        return asdict(result)
    # Fallback: if the object exposes a .data or .as_dict, use it.
    if hasattr(result, 'as_dict'):
        return result.as_dict()
    if hasattr(result, 'data'):
        return result.data
    raise TypeError(
        f'serve_report cannot coerce {type(result).__name__} to dict. '
        f'Return a dict or dataclass from the underlying service.'
    )


def _try_persist(
    *, payload: dict, report_type: str, fiscal_year: int,
    period: Optional[int], user,
) -> Optional[dict]:
    """Run ``ReportSnapshotService.persist()`` and return metadata.

    Wrapped in try/except because snapshotting is an enhancement, not
    a hard requirement — a snapshot failure must not block a report
    download. On failure we return ``None`` (and the response carries
    no X-Snapshot-Id header).
    """
    try:
        from accounting.services.report_snapshot import ReportSnapshotService
        snap = ReportSnapshotService.persist(
            report_type=report_type,
            fiscal_year=fiscal_year,
            period=period or 0,
            payload=payload,
            user=user,
        )
        return {
            'id':            snap.id,
            'content_hash':  snap.content_hash,
            'generated_at':  snap.generated_at.isoformat(),
            'report_type':   snap.report_type,
            'fiscal_year':   snap.fiscal_year,
            'period':        snap.period,
        }
    except Exception as exc:
        # Swallow — render the report anyway. A warning would be
        # appropriate here; keeping log-less for now since this helper
        # stays deployment-agnostic.
        import logging
        logging.getLogger(__name__).warning(
            'ReportSnapshot persistence failed for %s FY%s P%s: %s',
            report_type, fiscal_year, period, exc,
        )
        return None


def _prepare_json_body(payload: dict, snapshot_meta: Optional[dict]) -> dict:
    """Attach snapshot metadata under ``_snapshot`` without clobbering
    the payload's own keys.

    Uses the underscore prefix so it's visually distinct from domain
    fields and won't collide with OAGF/IPSAS column names.
    """
    if snapshot_meta is None:
        return payload
    # Shallow-copy so we don't mutate the caller's dict. For nested
    # objects we'd want deepcopy — not needed here since we're only
    # adding a single top-level key.
    enriched = dict(payload)
    enriched['_snapshot'] = snapshot_meta
    return enriched


def _truthy(value) -> bool:
    """Parse querystring-style truthiness."""
    if value is None:
        return False
    return str(value).strip().lower() in ('true', '1', 'yes', 'y', 't')
