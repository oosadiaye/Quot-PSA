"""
Sprint-9 regression tests: OAGF MFR, FIRS VAT, Statutory Index.

Both the OAGF MFR and VAT exporter delegate heavy lifting to other
services (IPSASReportService, VATReturnService). We mock those
services and verify the OAGF / VAT exporters SHAPE the output
correctly for their regulators' CSV intake formats.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch



# =============================================================================
# OAGF MFR
# =============================================================================

class TestOAGFMFRExporter:

    def _ipsas_performance_stub(self):
        """Shape of ``IPSASReportService.statement_of_financial_performance``."""
        return {
            'revenue': {
                'tax_revenue':      {'items': [
                    {'code': '1101', 'name': 'VAT', 'amount': Decimal('500000')},
                ], 'total': Decimal('500000')},
                'non_tax_revenue':  {'items': [], 'total': Decimal('0')},
                'grants_transfers': {'items': [
                    {'code': '1301', 'name': 'FAAC', 'amount': Decimal('1200000')},
                ], 'total': Decimal('1200000')},
                'other_revenue':    {'items': [], 'total': Decimal('0')},
                'total': Decimal('1700000'),
            },
            'expenditure': {
                'personnel_costs':       {'items': [
                    {'code': '2101', 'name': 'Basic Salary', 'amount': Decimal('800000')},
                ], 'total': Decimal('800000')},
                'overhead_costs':        {'items': [], 'total': Decimal('0')},
                'capital_expenditure':   {'items': [], 'total': Decimal('0')},
                'debt_service':          {'items': [], 'total': Decimal('0')},
                'transfers_subventions': {'items': [], 'total': Decimal('0')},
                'total': Decimal('800000'),
            },
            'surplus_deficit': Decimal('900000'),
        }

    def _tsa_stub(self):
        return {
            'total_balance': Decimal('5000000'),
            'by_account_type': [
                {'account_type': 'MAIN_TSA', 'balance': Decimal('4000000'), 'count': 1},
                {'account_type': 'SUB_ACCOUNT', 'balance': Decimal('1000000'), 'count': 12},
            ],
        }

    def test_happy_path_emits_five_sections(self):
        """Structured ``rows`` carries the five MFR sections."""
        from accounting.statutory.oagf import export_oagf_mfr

        with patch(
            'accounting.services.ipsas_reports.IPSASReportService.statement_of_financial_performance',
            return_value=self._ipsas_performance_stub(),
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService.tsa_cash_position',
            return_value=self._tsa_stub(),
        ), patch(
            'accounting.models.advanced.FiscalYear.objects.filter'
        ) as fy_filter:
            fy_filter.return_value.first.return_value = None  # skip budget section
            result = export_oagf_mfr(year=2026, month=4, tenant_name='Delta State')

        assert result.regulator == 'OAGF'
        assert result.period_label == '2026-04'
        section_names = [r['section'] for r in result.rows]
        assert section_names == [
            'revenue', 'expenditure', 'surplus_deficit',
            'budget_execution', 'fund_position',
        ]

    def test_totals_match_ipsas_values(self):
        from accounting.statutory.oagf import export_oagf_mfr

        with patch(
            'accounting.services.ipsas_reports.IPSASReportService.statement_of_financial_performance',
            return_value=self._ipsas_performance_stub(),
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService.tsa_cash_position',
            return_value=self._tsa_stub(),
        ), patch(
            'accounting.models.advanced.FiscalYear.objects.filter'
        ) as fy_filter:
            fy_filter.return_value.first.return_value = None
            result = export_oagf_mfr(year=2026, month=4)

        assert result.totals['total_revenue']     == Decimal('1700000')
        assert result.totals['total_expenditure'] == Decimal('800000')
        assert result.totals['surplus_deficit']   == Decimal('900000')
        assert result.totals['tsa_cash_balance']  == Decimal('5000000')

    def test_csv_has_long_format_with_section_column(self):
        """OAGF CSV uses (Section, Code, Label, Amount) long format."""
        from accounting.statutory.oagf import export_oagf_mfr, OAGF_CSV_COLUMNS

        with patch(
            'accounting.services.ipsas_reports.IPSASReportService.statement_of_financial_performance',
            return_value=self._ipsas_performance_stub(),
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService.tsa_cash_position',
            return_value=self._tsa_stub(),
        ), patch(
            'accounting.models.advanced.FiscalYear.objects.filter'
        ) as fy_filter:
            fy_filter.return_value.first.return_value = None
            result = export_oagf_mfr(year=2026, month=4)

        header_line = result.csv.splitlines()[0]
        assert header_line == ','.join(OAGF_CSV_COLUMNS)

        # Every data line should have exactly 4 fields.
        for line in result.csv.splitlines()[1:]:
            # Use csv.reader because fields may contain commas within quotes.
            import csv
            parsed = next(csv.reader([line]))
            assert len(parsed) == 4

    def test_missing_fiscal_year_adds_placeholder_note(self):
        """Budget execution rows degrade gracefully when the FiscalYear
        row doesn't exist."""
        from accounting.statutory.oagf import export_oagf_mfr

        with patch(
            'accounting.services.ipsas_reports.IPSASReportService.statement_of_financial_performance',
            return_value=self._ipsas_performance_stub(),
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService.tsa_cash_position',
            return_value=self._tsa_stub(),
        ), patch(
            'accounting.models.advanced.FiscalYear.objects.filter'
        ) as fy_filter:
            fy_filter.return_value.first.return_value = None
            result = export_oagf_mfr(year=2099, month=1)

        budget_section = next(
            r for r in result.rows if r['section'] == 'budget_execution'
        )
        assert len(budget_section['items']) == 1
        assert 'unavailable' in budget_section['items'][0]['label'].lower()

    def test_to_decimal_coerces_various_inputs(self):
        """_to_decimal handles Decimal, int, float, str, and None."""
        from accounting.statutory.oagf import _to_decimal
        assert _to_decimal(Decimal('5.5')) == Decimal('5.5')
        assert _to_decimal(5) == Decimal('5')
        assert _to_decimal(5.25) == Decimal('5.25')
        assert _to_decimal('100.50') == Decimal('100.50')
        assert _to_decimal(None) == Decimal('0')
        assert _to_decimal('') == Decimal('0')
        # Non-parseable falls through to zero, not a raise.
        assert _to_decimal('not a number') == Decimal('0')


# =============================================================================
# FIRS VAT return
# =============================================================================

class TestVATReturnExporter:

    def _output_vat_txns(self):
        return [
            {
                'document_type': 'CI', 'document_id': 1,
                'document_number': 'CI-001',
                'document_date': date(2026, 4, 5),
                'customer_name': 'Alpha Ltd',
                'taxable_amount': Decimal('100000'),
                'vat_amount':     Decimal('7500'),
                'vat_rate':       Decimal('7.5'),
            },
        ]

    def _input_vat_txns(self):
        return [
            {
                'document_type': 'VI', 'document_id': 10,
                'document_number': 'VI-010',
                'document_date': date(2026, 4, 12),
                'vendor_name': 'Beta Supplies',
                'taxable_amount': Decimal('40000'),
                'vat_amount':     Decimal('3000'),
                'vat_rate':       Decimal('7.5'),
            },
        ]

    def test_output_and_input_rows_emitted(self):
        from accounting.statutory.vat import export_vat_return

        with patch(
            'accounting.services.vat_returns.VATReturnService.get_output_vat',
            return_value=self._output_vat_txns(),
        ), patch(
            'accounting.services.vat_returns.VATReturnService.get_input_vat',
            return_value=self._input_vat_txns(),
        ):
            result = export_vat_return(year=2026, month=4)

        sections = {r['Section'] for r in result.rows}
        assert sections == {'Output VAT', 'Input VAT'}
        assert len(result.rows) == 2

    def test_net_vat_payable_is_output_minus_input(self):
        from accounting.statutory.vat import export_vat_return

        with patch(
            'accounting.services.vat_returns.VATReturnService.get_output_vat',
            return_value=self._output_vat_txns(),
        ), patch(
            'accounting.services.vat_returns.VATReturnService.get_input_vat',
            return_value=self._input_vat_txns(),
        ):
            result = export_vat_return(year=2026, month=4)

        # 7500 - 3000 = 4500
        assert result.totals['total_output_vat'] == Decimal('7500')
        assert result.totals['total_input_vat']  == Decimal('3000')
        assert result.totals['net_vat_payable']  == Decimal('4500')

    def test_negative_net_means_carry_forward(self):
        """When input VAT exceeds output VAT the net is negative — FIRS
        carries this forward to the next period."""
        from accounting.statutory.vat import export_vat_return

        with patch(
            'accounting.services.vat_returns.VATReturnService.get_output_vat',
            return_value=[{
                'document_type': 'CI', 'document_number': 'CI-1',
                'document_date': date(2026, 4, 1),
                'customer_name': 'X', 'taxable_amount': Decimal('10000'),
                'vat_amount': Decimal('750'), 'vat_rate': Decimal('7.5'),
            }],
        ), patch(
            'accounting.services.vat_returns.VATReturnService.get_input_vat',
            return_value=[{
                'document_type': 'VI', 'document_number': 'VI-1',
                'document_date': date(2026, 4, 1),
                'vendor_name': 'Y', 'taxable_amount': Decimal('50000'),
                'vat_amount': Decimal('3750'), 'vat_rate': Decimal('7.5'),
            }],
        ):
            result = export_vat_return(year=2026, month=4)

        # 750 - 3750 = -3000 (carry forward)
        assert result.totals['net_vat_payable'] == Decimal('-3000')

    def test_empty_period(self):
        from accounting.statutory.vat import export_vat_return

        with patch(
            'accounting.services.vat_returns.VATReturnService.get_output_vat',
            return_value=[],
        ), patch(
            'accounting.services.vat_returns.VATReturnService.get_input_vat',
            return_value=[],
        ):
            result = export_vat_return(year=2026, month=4)

        assert result.rows == []
        assert result.totals['net_vat_payable'] == Decimal('0')


# =============================================================================
# Statutory Index — catalogue structure
# =============================================================================

class TestStatutoryIndex:
    """The /statutory/ index returns a self-describing catalogue of all
    available exporters. This test locks the catalogue shape so new
    exporters can be added without silently breaking the index."""

    def test_index_returns_all_sprint_7_8_9_exporters(self):
        from accounting.views.statutory_reports import StatutoryIndexView

        view = StatutoryIndexView()
        view.kwargs = {}
        view.request = MagicMock()
        view.format_kwarg = None

        response = view.get(view.request)
        data = response.data

        regulators = {e['regulator'] for e in data['exporters']}
        # Sprint 7: FIRS (WHT), State IRS (PAYE)
        # Sprint 8: PENCOM, NSITF, NHIA, ITF
        # Sprint 9: OAGF, FIRS (VAT — dupes FIRS)
        assert 'FIRS' in regulators
        assert 'State IRS' in regulators
        assert 'PENCOM' in regulators
        assert 'NSITF' in regulators
        assert 'NHIA' in regulators
        assert 'ITF' in regulators
        assert 'OAGF' in regulators
        # FIRS has two reports (WHT + VAT).
        firs_reports = [e for e in data['exporters'] if e['regulator'] == 'FIRS']
        assert len(firs_reports) >= 2

    def test_every_exporter_has_required_fields(self):
        """Each entry must carry: regulator, report_name, endpoint,
        cadence, params, formats."""
        from accounting.views.statutory_reports import StatutoryIndexView

        view = StatutoryIndexView()
        view.kwargs = {}
        view.request = MagicMock()
        view.format_kwarg = None

        response = view.get(view.request)
        required = {'regulator', 'report_name', 'endpoint', 'cadence', 'params', 'formats'}
        for entry in response.data['exporters']:
            missing = required - set(entry.keys())
            assert not missing, f'Entry missing keys: {missing} in {entry}'
        # Count must match listed exporters.
        assert response.data['count'] == len(response.data['exporters'])
