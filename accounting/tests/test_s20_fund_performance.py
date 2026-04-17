"""
Sprint-20 tests — Fund Performance Report structural contract.

Validates the service returns the expected response shape even when
there is no data. Ensures the URL is registered. No-DB fast tier.
"""
from __future__ import annotations

from unittest.mock import patch



class TestFundPerformanceServiceContract:

    @patch('accounting.models.balances.GLBalance.objects')
    @patch('budget.models.Appropriation.objects')
    def test_empty_data_returns_valid_shape(self, m_appro, m_gl):
        """With no data, the service returns a well-formed empty envelope."""
        from accounting.services.ipsas_reports import IPSASReportService

        # Chain mocks: filter(...).exclude(...).values(...).annotate(...).order_by(...) → []
        m_gl.filter.return_value.exclude.return_value.values.return_value.annotate.return_value.order_by.return_value = []
        m_appro.filter.return_value.values.return_value.annotate.return_value = []

        result = IPSASReportService.fund_performance_report(2026)
        assert result['title'] == 'Fund Performance Report'
        assert result['fiscal_year'] == 2026
        assert result['currency'] == 'NGN'
        assert result['rows'] == []
        assert 'grand_budget' in result
        assert 'grand_actual' in result
        assert 'grand_variance' in result
        assert 'grand_total' in result


class TestFundPerformanceURLRegistered:

    def test_view_importable(self):
        from accounting.views.ipsas_reports import FundPerformanceView
        assert FundPerformanceView is not None

    def test_view_permission(self):
        from accounting.views.ipsas_reports import FundPerformanceView
        from accounting.permissions import CanViewFinancialStatements
        assert CanViewFinancialStatements in FundPerformanceView.permission_classes

    def test_url_registered(self):
        from django.urls import reverse
        # The URL name must stay stable for any frontend / exporter that
        # resolves it by name.
        url = reverse('ipsas-fund-performance')
        assert url.endswith('/ipsas/fund-performance/')


class TestSharedResponseShape:
    """All four performance reports (functional, programme, geographic,
    fund) must share the same response shape for the frontend to reuse
    the Performance table layout."""

    REQUIRED_TOP_KEYS = {
        'title', 'fiscal_year', 'currency', 'rows',
        'grand_budget', 'grand_actual', 'grand_variance', 'grand_total',
    }

    @patch('accounting.models.balances.GLBalance.objects')
    @patch('budget.models.Appropriation.objects')
    def test_fund_shape(self, m_appro, m_gl):
        from accounting.services.ipsas_reports import IPSASReportService
        m_gl.filter.return_value.exclude.return_value.values.return_value.annotate.return_value.order_by.return_value = []
        m_appro.filter.return_value.values.return_value.annotate.return_value = []
        result = IPSASReportService.fund_performance_report(2026)
        assert self.REQUIRED_TOP_KEYS.issubset(result.keys())
