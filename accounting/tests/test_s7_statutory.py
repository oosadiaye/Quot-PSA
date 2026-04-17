"""
Sprint-7 regression tests: statutory exporters.

Covers:
  * FIRS WHT schedule — row shape + CSV rendering + totals
  * PAYE schedule — row shape + CRA derivation + totals
  * Shared helpers — ``format_csv``, ``stringify``, CRA math

All tests run in the fast (no-DB) tier by mocking the querysets that
the exporters iterate. The exporters themselves are pure functions
over model iterables, so this works cleanly.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch



# =============================================================================
# Shared helpers
# =============================================================================

class TestStringifyAndCSV:

    def test_stringify_decimal_uses_2dp(self):
        from accounting.statutory import stringify
        assert stringify(Decimal('1234.5')) == '1234.50'

    def test_stringify_none_is_blank(self):
        from accounting.statutory import stringify
        assert stringify(None) == ''

    def test_stringify_date_iso(self):
        from accounting.statutory import stringify
        assert stringify(date(2026, 4, 17)) == '2026-04-17'

    def test_format_csv_emits_header_first(self):
        from accounting.statutory import format_csv
        csv = format_csv(['A', 'B'], [{'A': 1, 'B': 2}])
        lines = csv.strip().split('\n')
        assert lines[0] == 'A,B'
        assert lines[1] == '1,2'

    def test_format_csv_ignores_extra_keys(self):
        """``extrasaction='ignore'`` — rows with extra keys don't raise."""
        from accounting.statutory import format_csv
        csv = format_csv(
            ['A'], [{'A': 1, 'junk': 'skip-me'}],
        )
        assert 'junk' not in csv
        assert 'skip-me' not in csv

    def test_format_csv_empty_rows_still_has_header(self):
        from accounting.statutory import format_csv
        csv = format_csv(['A', 'B'], [])
        assert csv.strip() == 'A,B'


# =============================================================================
# FIRS WHT exporter
# =============================================================================

class TestFIRSWHTExporter:

    def _pv_stub(
        self, *, gross, wht, payee='Acme Ltd',
        econ_name='Professional Fees',
        invoice='INV-001', created=datetime(2026, 4, 10),
        payment_type='Vendor Payment',
    ):
        """Build a MagicMock that looks like a PaymentVoucherGov."""
        pv = MagicMock()
        pv.gross_amount = Decimal(str(gross))
        pv.wht_amount = Decimal(str(wht))
        pv.payee_name = payee
        pv.payee_tin = ''
        pv.payee_address = ''
        pv.invoice_number = invoice
        pv.source_document = ''
        pv.created_at = created
        pv.invoice_date = created.date() if created else None
        pv.get_payment_type_display = MagicMock(return_value=payment_type)
        # NCoA chain
        pv.ncoa_code = MagicMock()
        pv.ncoa_code.economic = MagicMock(name=econ_name)
        # MagicMock auto-creates attribute `name`, but it's a MagicMock
        # object, not a string. Explicit assignment forces a string.
        pv.ncoa_code.economic.name = econ_name
        return pv

    def test_empty_period_produces_header_only(self):
        """No PVs → CSV has header + no data rows, totals are zero."""
        from accounting.statutory.firs import export_wht_schedule

        with patch(
            'accounting.models.treasury.PaymentVoucherGov.objects.filter'
        ) as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = []
            filt.return_value = qs

            result = export_wht_schedule(
                year=2026, month=4, tenant_name='Delta State',
            )

        assert result.regulator == 'FIRS'
        assert result.period_label == '2026-04'
        assert result.rows == []
        assert result.totals['total_gross_amount'] == Decimal('0')
        assert result.totals['total_wht_amount'] == Decimal('0')
        # Header still present.
        first_line = result.csv.splitlines()[0]
        assert 'Beneficiary Name' in first_line

    def test_populates_rows_and_totals(self):
        from accounting.statutory.firs import export_wht_schedule

        pvs = [
            self._pv_stub(gross=100_000, wht=5_000,  payee='Alpha Ltd'),
            self._pv_stub(gross=250_000, wht=12_500, payee='Beta Ltd'),
        ]
        with patch(
            'accounting.models.treasury.PaymentVoucherGov.objects.filter'
        ) as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = pvs
            filt.return_value = qs

            result = export_wht_schedule(year=2026, month=4)

        assert len(result.rows) == 2
        assert result.totals['total_gross_amount'] == Decimal('350000')
        assert result.totals['total_wht_amount'] == Decimal('17500')
        # Rate should be 5% on both (5k/100k, 12.5k/250k).
        assert result.rows[0]['WHT Rate (%)'] == Decimal('5.00')
        assert result.rows[1]['WHT Rate (%)'] == Decimal('5.00')
        # SN is 1-based and sequential.
        assert result.rows[0]['SN'] == 1
        assert result.rows[1]['SN'] == 2

    def test_missing_tin_adds_remark(self):
        """Rows without a TIN get 'TIN pending' in Remarks so FIRS
        accepts them with a mitigation note."""
        from accounting.statutory.firs import export_wht_schedule

        pvs = [self._pv_stub(gross=50_000, wht=2_500)]
        with patch(
            'accounting.models.treasury.PaymentVoucherGov.objects.filter'
        ) as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = pvs
            filt.return_value = qs

            result = export_wht_schedule(year=2026, month=4)

        assert result.rows[0]['Remarks'] == 'TIN pending'

    def test_zero_gross_does_not_divide_by_zero(self):
        """Defensive: if gross is 0 we return 0% rate without crashing."""
        from accounting.statutory.firs import export_wht_schedule

        pv = self._pv_stub(gross=0, wht=0)
        with patch(
            'accounting.models.treasury.PaymentVoucherGov.objects.filter'
        ) as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = [pv]
            filt.return_value = qs

            result = export_wht_schedule(year=2026, month=4)

        assert result.rows[0]['WHT Rate (%)'] == Decimal('0.00')


# =============================================================================
# PAYE exporter
# =============================================================================

class TestPAYEExporter:

    def _line_stub(
        self, *, gross, tax, pension=0, net=None, first='Aisha',
        last='Bello', tin='T-123', position='Director',
    ):
        line = MagicMock()
        line.gross_salary = Decimal(str(gross))
        line.tax_deduction = Decimal(str(tax))
        line.pension_deduction = Decimal(str(pension))
        line.net_salary = (
            Decimal(str(net)) if net is not None
            else Decimal(str(gross)) - Decimal(str(tax)) - Decimal(str(pension))
        )
        line.bank_name = 'Access Bank'
        line.bank_account = '0123456789'

        emp = MagicMock()
        emp.first_name = first
        emp.middle_name = ''
        emp.last_name = last
        emp.tin = tin
        emp.employee_id = 'EMP-001'
        pos = MagicMock()
        pos.title = position
        emp.position = pos
        line.employee = emp
        return line

    def test_cra_derivation_hits_pitam_floor(self):
        """For very low gross salary CRA should hit the NGN 200k/year
        floor (≈ NGN 16,666.67/month)."""
        from accounting.statutory.paye import _derive_cra
        # 50k monthly gross: 1% would be 500; floor kicks in.
        cra = _derive_cra(Decimal('50000'))
        # CRA = 16666.67 (floor) + 20% of 50000 = 10000 → 26666.67
        assert cra == Decimal('26666.67')

    def test_cra_derivation_scales_with_gross(self):
        """When annual gross > NGN 20M, the 1% branch beats the 200k
        floor: CRA = 1% of gross + 20% of gross = 21% of gross."""
        from accounting.statutory.paye import _derive_cra
        # 2M monthly = 24M annual. 1% annual = 240k > 200k floor.
        # Monthly CRA = (1% + 20%) × 2M = 420k.
        cra = _derive_cra(Decimal('2000000'))
        assert cra == Decimal('420000.00')

    def test_cra_mid_range_uses_floor(self):
        """At 1M monthly (12M annual), 1% = 120k < 200k floor → floor wins."""
        from accounting.statutory.paye import _derive_cra
        # Monthly floor ≈ 200k/12 = 16666.67; + 20% × 1M = 200k → 216666.67.
        cra = _derive_cra(Decimal('1000000'))
        assert cra == Decimal('216666.67')

    def test_cra_zero_gross_is_zero(self):
        from accounting.statutory.paye import _derive_cra
        assert _derive_cra(Decimal('0')) == Decimal('0')

    def test_empty_period_produces_header_only(self):
        from accounting.statutory.paye import export_paye_schedule

        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = []
            filt.return_value = qs

            result = export_paye_schedule(year=2026, month=4)

        assert result.regulator == 'State IRS'
        assert result.period_label == '2026-04'
        assert result.rows == []
        assert result.totals['total_paye'] == Decimal('0')

    def test_full_name_assembly(self):
        from accounting.statutory.paye import export_paye_schedule

        lines = [self._line_stub(
            gross=500_000, tax=75_000, pension=40_000,
            first='Kemi', last='Oluwole',
        )]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_paye_schedule(year=2026, month=4)

        assert result.rows[0]['Employee Name'] == 'Kemi Oluwole'
        assert result.rows[0]['TIN'] == 'T-123'
        assert result.rows[0]['Designation'] == 'Director'
        assert result.rows[0]['PAYE Amount (NGN)'] == Decimal('75000')

    def test_totals_accumulate_across_lines(self):
        from accounting.statutory.paye import export_paye_schedule

        lines = [
            self._line_stub(gross=300_000, tax=30_000, pension=24_000),
            self._line_stub(gross=400_000, tax=60_000, pension=32_000),
            self._line_stub(gross=500_000, tax=90_000, pension=40_000),
        ]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_paye_schedule(year=2026, month=4)

        assert result.totals['total_gross'] == Decimal('1200000')
        assert result.totals['total_paye'] == Decimal('180000')
        assert result.totals['total_pension'] == Decimal('96000')
        assert result.totals['line_count'] == Decimal('3')


# =============================================================================
# CSV round-trip
# =============================================================================

class TestCSVRoundTrip:

    def test_csv_has_one_data_line_per_row(self):
        """CSV output must have exactly (rows + 1) lines (header + data)."""
        from accounting.statutory.paye import export_paye_schedule, PAYE_COLUMNS

        lines = [MagicMock() for _ in range(5)]
        for i, line in enumerate(lines):
            line.gross_salary = Decimal('100000')
            line.tax_deduction = Decimal('10000')
            line.pension_deduction = Decimal('8000')
            line.net_salary = Decimal('82000')
            line.bank_name = ''
            line.bank_account = ''
            line.employee = MagicMock(
                first_name=f'Emp{i}', middle_name='', last_name='X',
                tin=f'T{i}', employee_id=f'E{i}',
            )
            line.employee.position = None  # no designation

        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_paye_schedule(year=2026, month=4)

        csv_lines = result.csv.strip().split('\n')
        assert len(csv_lines) == 1 + 5
        assert csv_lines[0] == ','.join(PAYE_COLUMNS)
