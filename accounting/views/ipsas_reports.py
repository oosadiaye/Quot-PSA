"""
IPSAS Financial Statement API — Quot PSE

Exposes the five mandatory IPSAS financial statements plus Notes, the
three NCoA dimension reports, Revenue Performance, and TSA Cash Position.

All endpoints accept:
  * ``?comparative=true|false`` (default true) — prior-year column per IPSAS 1 ¶53
  * ``?format=json|html|pdf|xlsx`` (default json) — delivered via the shared
    ``serve_report`` helper; PDF falls back to HTML when WeasyPrint is
    not installed on the server
  * ``?persist=true`` — snapshot the payload to ``ReportSnapshot`` before
    serving so auditors can reproduce the exact filed version later.
    The snapshot id is attached to JSON payloads under ``_snapshot`` and
    to non-JSON responses via ``X-Snapshot-Id`` / ``X-Snapshot-Hash``
    headers.
"""
import datetime
from rest_framework.views import APIView
from rest_framework.response import Response

# S5-03 — every IPSAS endpoint uses the role-aware permission class.
from accounting.permissions import CanViewFinancialStatements
from accounting.services.ipsas_reports import IPSASReportService
# P6-T4 — Redis cache wrapper for hot IPSAS reports.
from accounting.services.report_cache import get_or_compute, report_generation
# S11 — shared format + snapshot helper.
from accounting.views.reporting_helpers import serve_report


def _parse_int_param(request, name: str, required: bool = False, default: int = None):
    """Parse an integer query param with error handling."""
    val = request.query_params.get(name)
    if val is None:
        if required:
            return None, Response(
                {'error': f'{name} parameter is required'}, status=400,
            )
        return default, None
    try:
        return int(val), None
    except (ValueError, TypeError):
        return None, Response(
            {'error': f'{name} must be an integer, got: {val}'}, status=400,
        )


def _parse_bool(request, name: str, default: bool = True) -> bool:
    """Parse a truthy/falsy query param (supports 'true'/'false'/'1'/'0')."""
    val = request.query_params.get(name)
    if val is None:
        return default
    return str(val).strip().lower() in ('true', '1', 'yes', 'y', 't')


class StatementOfFinancialPositionView(APIView):
    """IPSAS 1 — Balance Sheet (with prior-year comparative)."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, err = _parse_int_param(request, 'period')
        if err:
            return err
        comparative = _parse_bool(request, 'comparative', default=True)
        data = get_or_compute(
            report='sofp',
            params={
                'fiscal_year': fiscal_year, 'period': period,
                'comparative': comparative,
                'gen': report_generation(fiscal_year),
            },
            compute=lambda: IPSASReportService.statement_of_financial_position(
                fiscal_year, period, comparative=comparative,
            ),
        )
        return serve_report(
            request, data,
            filename_stem=f'sofp-{fiscal_year}{"-" + str(period) if period else ""}',
            report_type='ipsas.sofp',
            fiscal_year=fiscal_year,
            period=period or 0,
        )


class StatementOfFinancialPerformanceView(APIView):
    """IPSAS 1 — Income & Expenditure Statement (with prior-year comparative)."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, err = _parse_int_param(request, 'period')
        if err:
            return err
        comparative = _parse_bool(request, 'comparative', default=True)
        data = get_or_compute(
            report='sofperf',
            params={
                'fiscal_year': fiscal_year, 'period': period,
                'comparative': comparative,
                'gen': report_generation(fiscal_year),
            },
            compute=lambda: IPSASReportService.statement_of_financial_performance(
                fiscal_year, period, comparative=comparative,
            ),
        )
        return serve_report(
            request, data,
            filename_stem=f'sofperformance-{fiscal_year}{"-" + str(period) if period else ""}',
            report_type='ipsas.sofperformance',
            fiscal_year=fiscal_year,
            period=period or 0,
        )


class BudgetPerformanceStatementView(APIView):
    """IPSAS 24 — Budget Performance Statement in SoFP layout.

    Two budget columns (original / final) plus Actual and Variance, grouped
    into revenue → expenditure → surplus/deficit so the report reads like
    the Statement of Financial Performance a user already knows. Completely
    separate from the flat ``budget-vs-actual`` (IPSAS 24 three-column list)
    endpoint so adding this doesn't disturb any existing consumer.
    """
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, err = _parse_int_param(request, 'period')
        if err:
            return err
        data = get_or_compute(
            report='budgetperf',
            params={
                'fiscal_year': fiscal_year,
                'period': period,
                'gen': report_generation(fiscal_year),
            },
            compute=lambda: IPSASReportService.budget_performance_statement(
                fiscal_year, period,
            ),
        )
        return serve_report(
            request, data,
            filename_stem=f'budget-performance-{fiscal_year}{"-" + str(period) if period else ""}',
            report_type='ipsas.budgetperf',
            fiscal_year=fiscal_year,
            period=period or 0,
        )


class CashFlowStatementView(APIView):
    """IPSAS 2 — Cash Flow Statement (direct method)."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, err = _parse_int_param(request, 'period')
        if err:
            return err
        comparative = _parse_bool(request, 'comparative', default=True)
        data = IPSASReportService.cash_flow_statement(
            fiscal_year, period, comparative=comparative,
        )
        return serve_report(
            request, data,
            filename_stem=f'cashflow-{fiscal_year}{"-" + str(period) if period else ""}',
            report_type='ipsas.cashflow',
            fiscal_year=fiscal_year,
            period=period or 0,
        )


class StatementOfChangesInNetAssetsView(APIView):
    """IPSAS 1 — Statement of Changes in Net Assets / Equity."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, err = _parse_int_param(request, 'period')
        if err:
            return err
        comparative = _parse_bool(request, 'comparative', default=True)
        data = IPSASReportService.statement_of_changes_in_net_assets(
            fiscal_year, period, comparative=comparative,
        )
        return serve_report(
            request, data,
            filename_stem=f'changes-in-net-assets-{fiscal_year}{"-" + str(period) if period else ""}',
            report_type='ipsas.changes_in_net_assets',
            fiscal_year=fiscal_year,
            period=period or 0,
        )


class NotesToFinancialStatementsView(APIView):
    """IPSAS 1 — Notes to Financial Statements (minimum set)."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        data = IPSASReportService.notes_to_financial_statements(fiscal_year)
        return serve_report(
            request, data,
            filename_stem=f'notes-{fiscal_year}',
            report_type='ipsas.notes',
            fiscal_year=fiscal_year,
            period=0,
        )


class BudgetVsActualIPSASView(APIView):
    """IPSAS 24 — Budget vs Actual Comparison (three-column)."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year_id, err = _parse_int_param(request, 'fiscal_year_id', required=True)
        if err:
            return err
        data = get_or_compute(
            report='bva',
            params={'fiscal_year_id': fiscal_year_id, 'gen': report_generation()},
            compute=lambda: IPSASReportService.budget_vs_actual(fiscal_year_id),
        )
        # fiscal_year_id is the DB pk; for snapshot we also try to resolve
        # the year integer to key snapshots consistently with other reports.
        try:
            from accounting.models.advanced import FiscalYear
            fy = FiscalYear.objects.filter(pk=fiscal_year_id).first()
            fiscal_year_value = fy.year if fy else fiscal_year_id
        except Exception:
            fiscal_year_value = fiscal_year_id
        return serve_report(
            request, data,
            filename_stem=f'budget-vs-actual-{fiscal_year_value}',
            report_type='ipsas.budget_vs_actual',
            fiscal_year=fiscal_year_value,
            period=0,
        )


class RevenuePerformanceView(APIView):
    """Revenue collection performance by head and month."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        data = IPSASReportService.revenue_performance(fiscal_year)
        return serve_report(
            request, data,
            filename_stem=f'revenue-performance-{fiscal_year}',
            report_type='ipsas.revenue_performance',
            fiscal_year=fiscal_year,
            period=0,
        )


class TSACashPositionView(APIView):
    """Real-time TSA cash position."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        data = IPSASReportService.tsa_cash_position()
        # Cash position is a point-in-time snapshot, not period-scoped —
        # persist under the current year with period=0 so auditors can
        # still find the latest filing.
        today = datetime.date.today()
        return serve_report(
            request, data,
            filename_stem=f'tsa-cash-position-{today.isoformat()}',
            report_type='ipsas.tsa_cash_position',
            fiscal_year=today.year,
            period=0,
        )


class FunctionalClassificationView(APIView):
    """Expenditure by COFOG functional classification."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, _ = _parse_int_param(request, 'period')
        data = IPSASReportService.functional_classification_report(fiscal_year, period)
        return serve_report(
            request, data,
            filename_stem=f'functional-classification-{fiscal_year}',
            report_type='ipsas.functional_classification',
            fiscal_year=fiscal_year,
            period=period or 0,
        )


class ProgrammePerformanceView(APIView):
    """Budget vs actual by programme."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, _ = _parse_int_param(request, 'period')
        data = IPSASReportService.programme_performance_report(fiscal_year, period)
        return serve_report(
            request, data,
            filename_stem=f'programme-performance-{fiscal_year}',
            report_type='ipsas.programme_performance',
            fiscal_year=fiscal_year,
            period=period or 0,
        )


class FundPerformanceView(APIView):
    """Budget vs actual by Fund segment."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, _ = _parse_int_param(request, 'period')
        data = IPSASReportService.fund_performance_report(fiscal_year, period)
        return serve_report(
            request, data,
            filename_stem=f'fund-performance-{fiscal_year}',
            report_type='ipsas.fund_performance',
            fiscal_year=fiscal_year,
            period=period or 0,
        )


class GeographicDistributionView(APIView):
    """Expenditure by geographic zone/LGA."""
    permission_classes = [CanViewFinancialStatements]

    def get(self, request):
        fiscal_year, err = _parse_int_param(
            request, 'fiscal_year', default=datetime.date.today().year,
        )
        if err:
            return err
        period, _ = _parse_int_param(request, 'period')
        data = IPSASReportService.geographic_distribution_report(fiscal_year, period)
        return serve_report(
            request, data,
            filename_stem=f'geographic-distribution-{fiscal_year}',
            report_type='ipsas.geographic_distribution',
            fiscal_year=fiscal_year,
            period=period or 0,
        )
