"""
Sprint-11 regression tests.

Coverage:
  * ``serve_report`` helper — dict coercion, format negotiation,
    persist flag, ExportResult dataclass support.
  * ``MDAImporter`` CSV parse, XLSX parse, header normalisation,
    required-column check, numeric/date coercion.
  * ``ImportSpec`` catalogue contains the documented data types.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# serve_report helper
# =============================================================================

class TestServeReportDictCoercion:
    """_to_dict handles dicts, dataclasses, and objects with .as_dict()."""

    def test_dict_passes_through(self):
        from accounting.views.reporting_helpers import _to_dict
        payload = {'a': 1, 'b': [2, 3]}
        assert _to_dict(payload) is payload

    def test_dataclass_converted(self):
        from accounting.statutory import ExportResult
        from accounting.views.reporting_helpers import _to_dict
        from datetime import date
        result = ExportResult(
            regulator='X', report_name='Test', tenant_name='T',
            period_label='2026-01', rows=[], csv='', totals={},
            generated_at=date(2026, 1, 1),
        )
        d = _to_dict(result)
        assert d['regulator'] == 'X'
        assert d['period_label'] == '2026-01'

    def test_object_with_as_dict(self):
        from accounting.views.reporting_helpers import _to_dict

        class Foo:
            def as_dict(self):
                return {'ok': True}
        assert _to_dict(Foo()) == {'ok': True}

    def test_unsupported_type_raises_type_error(self):
        from accounting.views.reporting_helpers import _to_dict
        with pytest.raises(TypeError, match='cannot coerce'):
            _to_dict(12345)


class TestTruthyParser:

    @pytest.mark.parametrize('value,expected', [
        ('true', True), ('True', True), ('1', True),
        ('yes', True), ('y', True), ('t', True),
        ('false', False), ('0', False), ('no', False),
        ('', False), (None, False),
        ('anything_else', False),
    ])
    def test_truthy(self, value, expected):
        from accounting.views.reporting_helpers import _truthy
        assert _truthy(value) is expected


class TestServeReportFormatRouting:
    """serve_report picks the right rendering path per ?format=."""

    def _request(self, fmt='json', persist=False):
        req = MagicMock()
        params = {'format': fmt}
        if persist:
            params['persist'] = 'true'
        req.query_params = params
        req.user = MagicMock(is_authenticated=True)
        return req

    def test_json_default_returns_drf_response(self):
        from accounting.views.reporting_helpers import serve_report
        resp = serve_report(
            self._request('json'), {'title': 'X'},
            filename_stem='x',
        )
        # DRF Response — has .data
        assert hasattr(resp, 'data')
        assert resp.data['title'] == 'X'

    def test_html_returns_http_response_with_attachment(self):
        from accounting.views.reporting_helpers import serve_report
        resp = serve_report(
            self._request('html'), {'title': 'Test', 'totals': {}},
            filename_stem='test',
        )
        assert resp['Content-Type'].startswith('text/html')
        assert 'attachment' in resp['Content-Disposition']
        assert '.html' in resp['Content-Disposition']

    def test_xlsx_returns_spreadsheet_bytes(self):
        from accounting.views.reporting_helpers import serve_report
        resp = serve_report(
            self._request('xlsx'), {
                'title': 'Test', 'totals': {'x': Decimal('100')},
            },
            filename_stem='test',
        )
        assert resp['Content-Type'].endswith('spreadsheetml.sheet')
        assert resp.content[:2] == b'PK'  # zip magic

    def test_unsupported_format_returns_400(self):
        from accounting.views.reporting_helpers import serve_report
        resp = serve_report(
            self._request('docx'), {'title': 'X'},
            filename_stem='x',
        )
        assert resp.status_code == 400


class TestServeReportPersistFlag:
    """?persist=true routes through ReportSnapshotService and attaches
    snapshot metadata to the JSON response."""

    def _request(self, persist=True):
        req = MagicMock()
        params = {'format': 'json'}
        if persist:
            params['persist'] = 'true'
        req.query_params = params
        req.user = MagicMock(is_authenticated=True)
        return req

    def test_persist_attaches_snapshot_meta_to_json(self):
        from accounting.views.reporting_helpers import serve_report

        snap_mock = MagicMock(
            id=42,
            content_hash='a' * 64,
            generated_at=MagicMock(isoformat=lambda: '2026-04-17T10:00:00'),
            report_type='ipsas.sofp',
            fiscal_year=2026,
            period=4,
        )
        with patch(
            'accounting.services.report_snapshot.ReportSnapshotService.persist',
            return_value=snap_mock,
        ):
            resp = serve_report(
                self._request(persist=True),
                {'title': 'SoFP'},
                filename_stem='sofp',
                report_type='ipsas.sofp',
                fiscal_year=2026, period=4,
            )

        assert '_snapshot' in resp.data
        assert resp.data['_snapshot']['id'] == 42
        assert resp.data['_snapshot']['content_hash'] == 'a' * 64

    def test_no_persist_without_flag(self):
        from accounting.views.reporting_helpers import serve_report
        with patch(
            'accounting.services.report_snapshot.ReportSnapshotService.persist',
        ) as persist:
            serve_report(
                self._request(persist=False),
                {'title': 'SoFP'},
                filename_stem='sofp',
                report_type='ipsas.sofp',
                fiscal_year=2026, period=4,
            )
            persist.assert_not_called()

    def test_persist_without_report_type_is_silent_noop(self):
        """If the view forgot to pass report_type, the flag silently
        skips persistence instead of raising."""
        from accounting.views.reporting_helpers import serve_report
        with patch(
            'accounting.services.report_snapshot.ReportSnapshotService.persist',
        ) as persist:
            resp = serve_report(
                self._request(persist=True),
                {'title': 'X'},
                filename_stem='x',
            )
            persist.assert_not_called()
        assert '_snapshot' not in resp.data

    def test_persist_failure_is_swallowed(self):
        """Snapshot failure must not block the report download."""
        from accounting.views.reporting_helpers import serve_report
        with patch(
            'accounting.services.report_snapshot.ReportSnapshotService.persist',
            side_effect=RuntimeError('DB down'),
        ):
            resp = serve_report(
                self._request(persist=True),
                {'title': 'X'},
                filename_stem='x',
                report_type='ipsas.sofp',
                fiscal_year=2026, period=4,
            )
        assert resp.data['title'] == 'X'
        assert '_snapshot' not in resp.data


# =============================================================================
# MDAImporter
# =============================================================================

class TestMDAImporterCSVParse:

    def _csv_upload(self, text: str, name='upload.csv'):
        """Build a django-style upload stub from CSV text."""
        f = MagicMock()
        f.name = name
        f.read = MagicMock(return_value=text.encode('utf-8'))
        f.seek = MagicMock()
        return f

    def test_happy_path(self):
        from accounting.services.mda_data_import import MDAImporter, ImportSpec
        csv_text = (
            'mda_code,account_code,debit,credit\n'
            '011,50100000,1000,0\n'
            '011,10100000,0,1000\n'
        )
        spec = ImportSpec(
            required_columns=['mda_code', 'account_code', 'debit', 'credit'],
            numeric_columns=['debit', 'credit'],
        )
        result = MDAImporter.parse(self._csv_upload(csv_text), spec)
        assert result.is_valid() is True
        assert len(result.rows) == 2
        assert result.rows[0]['debit'] == Decimal('1000')
        assert result.rows[1]['credit'] == Decimal('1000')

    def test_missing_required_column_errors(self):
        from accounting.services.mda_data_import import MDAImporter, ImportSpec
        csv_text = 'mda_code,debit\n011,1000\n'
        spec = ImportSpec(
            required_columns=['mda_code', 'account_code', 'debit'],
            numeric_columns=['debit'],
        )
        result = MDAImporter.parse(self._csv_upload(csv_text), spec)
        assert result.is_valid() is False
        assert any('Missing required column' in e['error'] for e in result.errors)

    def test_header_normalisation(self):
        """Headers get lowercased + spaces→underscores, so 'MDA Code'
        matches ``mda_code`` in the spec."""
        from accounting.services.mda_data_import import MDAImporter, ImportSpec
        csv_text = (
            'MDA Code,Account-Code,Debit,Credit\n'
            '011,50100000,1000,0\n'
        )
        spec = ImportSpec(
            required_columns=['mda_code', 'account_code', 'debit', 'credit'],
            numeric_columns=['debit', 'credit'],
        )
        result = MDAImporter.parse(self._csv_upload(csv_text), spec)
        assert result.is_valid() is True
        assert 'mda_code' in result.columns
        assert 'account_code' in result.columns

    def test_currency_symbols_stripped_from_numeric(self):
        from accounting.services.mda_data_import import MDAImporter, ImportSpec
        csv_text = (
            'mda_code,account_code,debit,credit\n'
            '011,50100000,"₦1,500.00",0\n'
        )
        spec = ImportSpec(
            required_columns=['mda_code', 'account_code', 'debit', 'credit'],
            numeric_columns=['debit', 'credit'],
        )
        result = MDAImporter.parse(self._csv_upload(csv_text), spec)
        assert result.is_valid() is True
        assert result.rows[0]['debit'] == Decimal('1500.00')

    def test_parenthesised_negative(self):
        from accounting.services.mda_data_import import MDAImporter, ImportSpec
        csv_text = (
            'mda_code,account_code,debit,credit\n'
            '011,50100000,(500),0\n'
        )
        spec = ImportSpec(
            required_columns=['mda_code', 'account_code', 'debit', 'credit'],
            numeric_columns=['debit', 'credit'],
        )
        result = MDAImporter.parse(self._csv_upload(csv_text), spec)
        assert result.rows[0]['debit'] == Decimal('-500')

    def test_empty_cells_in_required_column(self):
        from accounting.services.mda_data_import import MDAImporter, ImportSpec
        csv_text = (
            'mda_code,account_code,debit,credit\n'
            ',50100000,1000,0\n'   # missing mda_code
        )
        spec = ImportSpec(
            required_columns=['mda_code', 'account_code', 'debit', 'credit'],
            numeric_columns=['debit', 'credit'],
        )
        result = MDAImporter.parse(self._csv_upload(csv_text), spec)
        assert result.rejected_rows == 1
        assert any('mda_code' in (e.get('column') or '') for e in result.errors)

    def test_date_column_parsing(self):
        from accounting.services.mda_data_import import MDAImporter, ImportSpec
        csv_text = (
            'collection_date,amount\n'
            '2026-04-17,1000\n'
            '15/05/2026,2000\n'
            'not-a-date,3000\n'
        )
        spec = ImportSpec(
            required_columns=['collection_date', 'amount'],
            numeric_columns=['amount'],
            date_columns=['collection_date'],
        )
        result = MDAImporter.parse(self._csv_upload(csv_text), spec)
        # First two rows parse; third rejects with a date error.
        assert result.accepted_rows == 2
        assert result.rejected_rows == 1
        assert result.rows[0]['collection_date'] == date(2026, 4, 17)
        assert result.rows[1]['collection_date'] == date(2026, 5, 15)
        assert any('date' in e['error'].lower() for e in result.errors)

    def test_max_rows_cap(self):
        """Importer refuses to load beyond spec.max_rows to protect memory."""
        from accounting.services.mda_data_import import MDAImporter, ImportSpec
        rows = ['mda_code,account_code,debit,credit']
        for i in range(15):
            rows.append(f'011,50100000,{i},0')
        csv_text = '\n'.join(rows) + '\n'
        spec = ImportSpec(
            required_columns=['mda_code', 'account_code', 'debit', 'credit'],
            numeric_columns=['debit', 'credit'],
            max_rows=10,
        )
        result = MDAImporter.parse(self._csv_upload(csv_text), spec)
        # 10 accepted + 1 error noting the cap. (The importer stops on
        # the first over-cap row and records an error.)
        assert result.accepted_rows == 10
        assert any('cap' in e['error'].lower() for e in result.errors)


class TestImportCatalogue:

    def test_catalogue_lists_all_data_types(self):
        from accounting.views.mda_data_import import IMPORT_SPECS
        expected = {'journal_summary', 'revenue_collection',
                    'payroll_summary', 'provisions'}
        assert set(IMPORT_SPECS.keys()) >= expected

    def test_every_spec_has_required_columns(self):
        from accounting.views.mda_data_import import IMPORT_SPECS
        for key, spec in IMPORT_SPECS.items():
            assert len(spec.required_columns) >= 1, (
                f'Spec {key!r} has no required columns.'
            )
