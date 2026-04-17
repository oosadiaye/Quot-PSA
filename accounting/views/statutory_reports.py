"""
Statutory export endpoints.

Every exporter returns two shapes: ``format=json`` (default, returns
the structured rows + totals + metadata) or ``format=csv`` (streams a
CSV attachment ready for manual upload to the regulator's portal).

All endpoints are gated by ``CanViewFinancialStatements`` — statutory
data is consolidated financial info and follows the same access policy
as IPSAS reports.
"""
from __future__ import annotations

import datetime

from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.permissions import CanViewFinancialStatements


def _parse_int(request, name, default=None, required=False):
    raw = request.query_params.get(name)
    if raw is None:
        if required:
            return None, Response({'error': f'{name} is required'}, status=400)
        return default, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, Response(
            {'error': f'{name} must be an integer, got: {raw!r}'}, status=400,
        )


def _serve(
    request, result, filename_hint: str,
    *, report_type: str | None = None,
    fiscal_year: int | None = None,
    period: int | None = None,
):
    """Serve an ExportResult in the requested format.

    Supports five formats:
      * ``csv`` — raw CSV payload baked into the ExportResult (bespoke
        format produced by the regulator-specific exporter).
      * ``json`` (default) — structured payload for API consumers.
      * ``html`` / ``pdf`` / ``xlsx`` — delegated to
        ``ReportRenderer`` via the shared ``serve_report`` helper,
        which also handles the ``?persist=true`` flag.

    CSV stays on the bespoke path because regulators demand exact
    column orderings that the generic Excel renderer wouldn't replicate.
    The other three formats can be rendered from the structured rows.

    S11 — Added optional ``report_type``, ``fiscal_year``, ``period``
    parameters so callers can opt into ReportSnapshot persistence
    (``?persist=true``).
    """
    fmt = (request.query_params.get('format') or 'json').lower()

    # CSV path — raw bytes baked by the exporter. Intentionally does
    # NOT route through the generic renderer; regulator portals reject
    # column-order variance.
    if fmt == 'csv':
        # Even on the CSV path we allow snapshot persistence of the
        # *structured* payload so auditors can still reproduce the
        # semantic report later.
        _try_persist_if_requested(
            request, result, report_type, fiscal_year, period,
        )
        response = HttpResponse(result.csv, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="{filename_hint}.csv"'
        )
        return response

    # For JSON / HTML / PDF / XLSX, delegate to the shared helper which
    # supports format + persist + snapshot-metadata headers. Coerce the
    # ExportResult to the dict shape the generic renderer expects.
    from accounting.views.reporting_helpers import serve_report as _generic_serve

    as_dict = {
        'title':        result.report_name,
        'regulator':    result.regulator,
        'tenant_name':  result.tenant_name,
        'period_label': result.period_label,
        'currency':     'NGN',
        'rows':         result.rows,
        'totals':       {k: str(v) for k, v in result.totals.items()},
        'generated_at': result.generated_at.isoformat(),
    }
    return _generic_serve(
        request, as_dict,
        filename_stem=filename_hint,
        report_type=report_type,
        fiscal_year=fiscal_year,
        period=period,
    )


def _try_persist_if_requested(
    request, result, report_type, fiscal_year, period,
):
    """Persist the structured payload if the caller passed ?persist=true.

    Used by the CSV-direct path so that even raw-CSV downloads can be
    captured as snapshots (for audit reproducibility of the semantic
    data behind the bespoke CSV).
    """
    val = request.query_params.get('persist')
    if not val or str(val).strip().lower() not in ('true', '1', 'yes', 'y'):
        return
    if not (report_type and fiscal_year is not None):
        return
    try:
        from accounting.services.report_snapshot import ReportSnapshotService
        ReportSnapshotService.persist(
            report_type=report_type,
            fiscal_year=fiscal_year,
            period=period or 0,
            payload={
                'title':        result.report_name,
                'regulator':    result.regulator,
                'tenant_name':  result.tenant_name,
                'period_label': result.period_label,
                'rows':         result.rows,
                'totals':       {k: str(v) for k, v in result.totals.items()},
                'generated_at': result.generated_at.isoformat(),
            },
            user=getattr(request, 'user', None),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            'ReportSnapshot persistence failed (csv path)',
            exc_info=True,
        )


class WHTScheduleView(APIView):
    """GET /api/v1/accounting/statutory/firs/wht/?year=2026&month=4[&format=csv]"""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        from accounting.statutory.firs import export_wht_schedule

        today = datetime.date.today()
        year, err = _parse_int(request, 'year', default=today.year)
        if err:
            return err
        month, err = _parse_int(request, 'month', default=today.month)
        if err:
            return err
        if not (1 <= month <= 12):
            return Response({'error': 'month must be 1-12'}, status=400)

        tenant_name = getattr(getattr(request, 'tenant', None), 'name', '') or ''
        result = export_wht_schedule(year=year, month=month, tenant_name=tenant_name)
        return _serve(
            request, result, f'firs-wht-{year:04d}-{month:02d}',
            report_type='statutory.firs_wht', fiscal_year=year, period=month,
        )


class PAYEScheduleView(APIView):
    """GET /api/v1/accounting/statutory/paye/?year=2026&month=4[&format=csv]"""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        from accounting.statutory.paye import export_paye_schedule

        today = datetime.date.today()
        year, err = _parse_int(request, 'year', default=today.year)
        if err:
            return err
        month, err = _parse_int(request, 'month', default=today.month)
        if err:
            return err
        if not (1 <= month <= 12):
            return Response({'error': 'month must be 1-12'}, status=400)

        tenant_name = getattr(getattr(request, 'tenant', None), 'name', '') or ''
        result = export_paye_schedule(year=year, month=month, tenant_name=tenant_name)
        return _serve(
            request, result, f'paye-{year:04d}-{month:02d}',
            report_type='statutory.paye', fiscal_year=year, period=month,
        )


# ─── S8 — payroll-derived statutory schedules ──────────────────────────
# PENCOM, NSITF, NHIA share the same (year, month) parameter pattern;
# ITF uses (year) only because the filing cadence is annual. Each view
# is a trivial delegation to the exporter, followed by ``_serve`` for
# content-negotiation between JSON and CSV.

class _MonthlyScheduleView(APIView):
    """Base class for monthly (year, month) statutory schedules.

    Subclasses set:
      * ``exporter``      — the ``accounting.statutory.*`` function.
      * ``filename_stem`` — CSV filename prefix (e.g. ``'pencom'``).
      * ``report_type``   — canonical snapshot key (e.g.
        ``'statutory.pencom'``). Enables ``?persist=true``.

    Keeps the boilerplate (arg parsing, validation, content negotiation,
    snapshot wiring) DRY across the monthly-filing regulators.
    """
    permission_classes = [CanViewFinancialStatements]
    exporter = None         # type: ignore[assignment]
    filename_stem = ''      # e.g. 'pencom', 'nsitf', 'nhia'
    report_type = ''        # e.g. 'statutory.pencom'

    def get(self, request):
        today = datetime.date.today()
        year, err = _parse_int(request, 'year', default=today.year)
        if err:
            return err
        month, err = _parse_int(request, 'month', default=today.month)
        if err:
            return err
        if not (1 <= month <= 12):
            return Response({'error': 'month must be 1-12'}, status=400)

        tenant_name = getattr(getattr(request, 'tenant', None), 'name', '') or ''
        result = type(self).exporter(
            year=year, month=month, tenant_name=tenant_name,
        )
        return _serve(
            request, result,
            f'{self.filename_stem}-{year:04d}-{month:02d}',
            report_type=self.report_type or None,
            fiscal_year=year, period=month,
        )


class PENCOMScheduleView(_MonthlyScheduleView):
    """GET /api/v1/accounting/statutory/pencom/?year=2026&month=4[&format=csv]"""
    filename_stem = 'pencom'
    report_type = 'statutory.pencom'

    def get(self, request):
        # Late import of the exporter so the Django app doesn't eagerly
        # load the statutory package on startup.
        from accounting.statutory.pencom import export_pencom_schedule
        type(self).exporter = staticmethod(export_pencom_schedule)
        return super().get(request)


class NSITFScheduleView(_MonthlyScheduleView):
    """GET /api/v1/accounting/statutory/nsitf/?year=2026&month=4[&format=csv]"""
    filename_stem = 'nsitf'
    report_type = 'statutory.nsitf'

    def get(self, request):
        from accounting.statutory.nsitf import export_nsitf_schedule
        type(self).exporter = staticmethod(export_nsitf_schedule)
        return super().get(request)


class NHIAScheduleView(_MonthlyScheduleView):
    """GET /api/v1/accounting/statutory/nhia/?year=2026&month=4[&format=csv]"""
    filename_stem = 'nhia'
    report_type = 'statutory.nhia'

    def get(self, request):
        from accounting.statutory.nhis import export_nhis_schedule
        type(self).exporter = staticmethod(export_nhis_schedule)
        return super().get(request)


class ITFScheduleView(APIView):
    """Annual ITF schedule: GET /api/v1/accounting/statutory/itf/?year=2025[&format=csv]"""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        from accounting.statutory.itf import export_itf_schedule

        today = datetime.date.today()
        year, err = _parse_int(request, 'year', default=today.year)
        if err:
            return err

        tenant_name = getattr(getattr(request, 'tenant', None), 'name', '') or ''
        result = export_itf_schedule(year=year, tenant_name=tenant_name)
        return _serve(
            request, result, f'itf-{year:04d}',
            report_type='statutory.itf', fiscal_year=year, period=0,
        )


# ── S9 — OAGF + VAT + statutory index ──────────────────────────────────

class OAGFMFRView(_MonthlyScheduleView):
    """GET /api/v1/accounting/statutory/oagf/?year=2026&month=4[&format=csv]

    OAGF Monthly Financial Report. Consolidates revenue summary,
    expenditure summary, surplus/deficit, budget execution, and TSA
    fund position.
    """
    filename_stem = 'oagf-mfr'
    report_type = 'statutory.oagf_mfr'

    def get(self, request):
        from accounting.statutory.oagf import export_oagf_mfr
        type(self).exporter = staticmethod(export_oagf_mfr)
        return super().get(request)


class VATReturnView(_MonthlyScheduleView):
    """GET /api/v1/accounting/statutory/firs/vat/?year=2026&month=4[&format=csv]

    FIRS VAT return (Form VAT-002) — Output VAT - Input VAT = Net payable.
    """
    filename_stem = 'firs-vat'
    report_type = 'statutory.firs_vat'

    def get(self, request):
        from accounting.statutory.vat import export_vat_return
        type(self).exporter = staticmethod(export_vat_return)
        return super().get(request)


class StatutoryIndexView(APIView):
    """GET /api/v1/accounting/statutory/

    Returns the catalogue of available statutory exporters — what the
    regulator is, where to call, what cadence, what period parameters.
    Used by the frontend to render a "Statutory Filings" landing page
    and by automation tools to discover available exports.
    """
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        exporters = [
            {
                'regulator':   'FIRS',
                'report_name': 'Withholding Tax Schedule',
                'endpoint':    '/api/v1/accounting/statutory/firs/wht/',
                'cadence':     'monthly',
                'params':      ['year', 'month'],
                'formats':     ['json', 'csv'],
            },
            {
                'regulator':   'FIRS',
                'report_name': 'VAT Return (Form VAT-002)',
                'endpoint':    '/api/v1/accounting/statutory/firs/vat/',
                'cadence':     'monthly',
                'params':      ['year', 'month'],
                'formats':     ['json', 'csv'],
            },
            {
                'regulator':   'State IRS',
                'report_name': 'PAYE Monthly Schedule (JTB format)',
                'endpoint':    '/api/v1/accounting/statutory/paye/',
                'cadence':     'monthly',
                'params':      ['year', 'month'],
                'formats':     ['json', 'csv'],
            },
            {
                'regulator':   'PENCOM',
                'report_name': 'Monthly RSA Contribution Schedule (PRA 2014)',
                'endpoint':    '/api/v1/accounting/statutory/pencom/',
                'cadence':     'monthly',
                'params':      ['year', 'month'],
                'formats':     ['json', 'csv'],
            },
            {
                'regulator':   'NSITF',
                'report_name': 'Employee Compensation Scheme Monthly Contribution',
                'endpoint':    '/api/v1/accounting/statutory/nsitf/',
                'cadence':     'monthly',
                'params':      ['year', 'month'],
                'formats':     ['json', 'csv'],
            },
            {
                'regulator':   'NHIA',
                'report_name': 'Monthly Contribution Schedule (FSSHIP)',
                'endpoint':    '/api/v1/accounting/statutory/nhia/',
                'cadence':     'monthly',
                'params':      ['year', 'month'],
                'formats':     ['json', 'csv'],
            },
            {
                'regulator':   'ITF',
                'report_name': 'Annual Contribution Schedule',
                'endpoint':    '/api/v1/accounting/statutory/itf/',
                'cadence':     'annual',
                'params':      ['year'],
                'formats':     ['json', 'csv'],
            },
            {
                'regulator':   'OAGF',
                'report_name': 'Monthly Financial Report',
                'endpoint':    '/api/v1/accounting/statutory/oagf/',
                'cadence':     'monthly',
                'params':      ['year', 'month'],
                'formats':     ['json', 'csv'],
            },
        ]
        return Response({
            'count':     len(exporters),
            'exporters': exporters,
        })
