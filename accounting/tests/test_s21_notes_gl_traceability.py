"""
Sprint-21 tests — GL-linked Notes to the Financial Statements.

Verifies that each Note that should reconcile against the GL now
carries a ``gl_balances`` section with the expected shape, so auditors
can trace disclosed figures back to the ledger.
"""
from __future__ import annotations

from unittest.mock import patch



class TestGLBalancesForNoteHelper:

    def test_helper_exists(self):
        from accounting.services.ipsas_reports import IPSASReportService
        assert hasattr(IPSASReportService, '_gl_balances_for_note')

    @patch('accounting.models.balances.GLBalance.objects')
    @patch('accounting.models.gl.Account.objects')
    def test_empty_gl_returns_valid_shape(self, m_acc, m_gl):
        """Shape must be stable even when no rows exist."""
        from accounting.services.ipsas_reports import IPSASReportService

        m_gl.filter.return_value.select_related.return_value.filter.return_value.values.return_value.annotate.return_value.order_by.return_value = []
        m_gl.filter.return_value.select_related.return_value.values.return_value.annotate.return_value.order_by.return_value = []
        m_acc.filter.return_value.filter.return_value.order_by.return_value = []

        result = IPSASReportService._gl_balances_for_note(
            2026, code_prefixes=['32'],
        )
        assert 'fiscal_year' in result
        assert 'filter' in result
        assert 'lines' in result
        assert 'total_debit' in result
        assert 'total_credit' in result
        assert 'total_net' in result

    @patch('accounting.models.balances.GLBalance.objects')
    @patch('accounting.models.gl.Account.objects')
    def test_filter_records_prefixes_and_exact(self, m_acc, m_gl):
        from accounting.services.ipsas_reports import IPSASReportService

        m_gl.filter.return_value.select_related.return_value.filter.return_value.values.return_value.annotate.return_value.order_by.return_value = []
        m_gl.filter.return_value.select_related.return_value.values.return_value.annotate.return_value.order_by.return_value = []
        m_acc.filter.return_value.filter.return_value.order_by.return_value = []

        result = IPSASReportService._gl_balances_for_note(
            2026, code_prefixes=['42', '24'], exact_codes=['25100000'],
        )
        assert result['filter']['prefixes'] == ['42', '24']
        assert result['filter']['exact'] == ['25100000']


class TestNoteGLCodeResolvers:

    def test_pension_codes_fallback_when_no_settings(self):
        """When AccountingSettings is empty, the documented defaults
        must still be returned so the note doesn't crash."""
        from accounting.services.ipsas_reports import IPSASReportService
        with patch('accounting.models.AccountingSettings.objects') as m:
            m.first.return_value = None
            codes = IPSASReportService._pension_gl_codes()
        assert codes == ['42201000', '21400000', '24100000']

    def test_social_benefit_code_fallback(self):
        from accounting.services.ipsas_reports import IPSASReportService
        with patch('accounting.models.AccountingSettings.objects') as m:
            m.first.return_value = None
            codes = IPSASReportService._social_benefit_gl_codes()
        assert codes == ['25100000']


class TestNoteBuildersCallGLHelper:
    """Source-level assertion: each note that should carry GL data
    actually invokes ``_gl_balances_for_note``. Fast, no DB required."""

    def test_ppe_note_references_gl_helper(self):
        import inspect
        from accounting.services.ipsas_reports import IPSASReportService
        src = inspect.getsource(IPSASReportService._note_ppe_movement)
        assert '_gl_balances_for_note' in src
        assert "code_prefixes=['32']" in src or 'code_prefixes=["32"]' in src

    def test_receivables_note_references_gl_helper(self):
        import inspect
        from accounting.services.ipsas_reports import IPSASReportService
        src = inspect.getsource(IPSASReportService._note_receivables_aging)
        assert '_gl_balances_for_note' in src
        assert '312' in src  # receivables prefix

    def test_payables_note_references_gl_helper(self):
        import inspect
        from accounting.services.ipsas_reports import IPSASReportService
        src = inspect.getsource(IPSASReportService._note_payables_aging)
        assert '_gl_balances_for_note' in src
        assert '411' in src  # payables prefix

    def test_pension_note_references_gl_helper(self):
        import inspect
        from accounting.services.ipsas_reports import IPSASReportService
        src = inspect.getsource(IPSASReportService._note_pension_ipsas_39)
        assert '_gl_balances_for_note' in src
        assert '_pension_gl_codes' in src

    def test_social_benefit_note_references_gl_helper(self):
        import inspect
        from accounting.services.ipsas_reports import IPSASReportService
        src = inspect.getsource(IPSASReportService._note_social_benefits_ipsas_42)
        assert '_gl_balances_for_note' in src
        assert '_social_benefit_gl_codes' in src
