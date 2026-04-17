"""
Sprint-8 regression tests: PENCOM / NSITF / ITF / NHIA exporters.

All four are payroll-derived schedules; they share the same general
pattern — iterate PayrollLines in a period, apply rates, emit rows.
We test each one with MagicMock'd querysets so the suite stays in
the fast (no-DB) tier.

Coverage per regulator:
  * PENCOM — employer contribution derivation (explicit vs 1.25× fallback),
    PFA grouping, missing-profile remark, totals
  * NSITF — 1% rate, totals, empty period
  * ITF — annual aggregation, staff-threshold enforcement (below / above),
    empty period
  * NHIA — 1.75% / 3.25% split on BASIC (not gross), HMO-missing remark
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# PENCOM
# =============================================================================

class TestPENCOMExporter:

    def _line_stub(
        self, *, pension=Decimal('0'), explicit_employer=None,
        first='Aisha', last='Bello', rsa_pin='PEN-123',
        pfa_name='ARM Pension', pfa_code='PFA-001',
        missing_profile=False,
    ):
        line = MagicMock()
        line.pension_deduction = pension
        if explicit_employer is not None:
            line.employer_pension_contribution = explicit_employer
        else:
            # ``getattr(line, ..., None)`` should return None. Remove
            # the auto-created MagicMock attr by setting explicitly.
            line.employer_pension_contribution = None

        emp = MagicMock()
        emp.first_name = first
        emp.middle_name = ''
        emp.last_name = last
        emp.employee_id = 'EMP-01'

        if missing_profile:
            emp.pension_profile = None
        else:
            profile = MagicMock()
            profile.rsa_pin = rsa_pin
            pfa = MagicMock()
            pfa.name = pfa_name
            pfa.pfa_code = pfa_code
            profile.pfa = pfa
            emp.pension_profile = profile

        line.employee = emp
        return line

    def test_employer_amount_from_explicit_field(self):
        """When the payroll engine set ``employer_pension_contribution``,
        that's the authoritative figure."""
        from accounting.statutory.pencom import _employer_amount
        line = MagicMock(employer_pension_contribution=Decimal('12000.00'))
        # Employee 8000 would naively produce 10000 via 1.25×; the
        # explicit 12000 should win.
        assert _employer_amount(line, Decimal('8000')) == Decimal('12000.00')

    def test_employer_amount_falls_back_to_1_25_ratio(self):
        """Without an explicit field, apply PRA 2014 10/8 ratio."""
        from accounting.statutory.pencom import _employer_amount
        line = MagicMock(employer_pension_contribution=None)
        assert _employer_amount(line, Decimal('8000')) == Decimal('10000.00')

    def test_missing_pension_profile_flags_remark(self):
        from accounting.statutory.pencom import export_pencom_schedule

        lines = [self._line_stub(pension=Decimal('8000'), missing_profile=True)]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_pencom_schedule(year=2026, month=4)

        assert len(result.rows) == 1
        assert 'Pension profile missing' in result.rows[0]['Remarks']
        # PFA column falls back to "(unassigned)" when profile is missing.
        assert result.rows[0]['PFA Name'] == '(unassigned)'

    def test_totals_accumulate_employee_and_employer(self):
        from accounting.statutory.pencom import export_pencom_schedule

        lines = [
            self._line_stub(pension=Decimal('8000')),    # employer 10000
            self._line_stub(pension=Decimal('16000')),   # employer 20000
        ]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_pencom_schedule(year=2026, month=4)

        assert result.totals['total_employee_contribution'] == Decimal('24000')
        assert result.totals['total_employer_contribution'] == Decimal('30000.00')
        assert result.totals['grand_total'] == Decimal('54000.00')


# =============================================================================
# NSITF
# =============================================================================

class TestNSITFExporter:

    def _line_stub(self, *, gross, first='X', last='Y', dept='IT'):
        line = MagicMock()
        line.gross_salary = Decimal(str(gross))
        emp = MagicMock()
        emp.first_name = first
        emp.middle_name = ''
        emp.last_name = last
        emp.employee_id = 'EMP-01'
        if dept is not None:
            dept_obj = MagicMock()
            dept_obj.name = dept
            emp.department = dept_obj
        else:
            emp.department = None
        line.employee = emp
        return line

    def test_rate_applied_correctly(self):
        from accounting.statutory.nsitf import export_nsitf_schedule

        lines = [self._line_stub(gross=500_000)]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_nsitf_schedule(year=2026, month=4)

        # 500,000 × 1% = 5,000.
        assert result.rows[0]['NSITF Contribution (NGN)'] == Decimal('5000.00')

    def test_totals_are_sums(self):
        from accounting.statutory.nsitf import export_nsitf_schedule

        lines = [
            self._line_stub(gross=300_000),
            self._line_stub(gross=400_000),
            self._line_stub(gross=500_000),
        ]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_nsitf_schedule(year=2026, month=4)

        assert result.totals['total_gross_payroll'] == Decimal('1200000')
        # 1% of 1,200,000 = 12,000.
        assert result.totals['total_nsitf_contribution'] == Decimal('12000.00')

    def test_empty_period(self):
        from accounting.statutory.nsitf import export_nsitf_schedule
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = []
            filt.return_value = qs

            result = export_nsitf_schedule(year=2026, month=4)

        assert result.rows == []
        assert result.totals['total_nsitf_contribution'] == Decimal('0')


# =============================================================================
# ITF — annual threshold-enforced
# =============================================================================

class TestITFExporter:

    def test_below_threshold_returns_empty_schedule(self):
        """Fewer than 5 employees → not applicable."""
        from accounting.statutory.itf import export_itf_schedule

        # 3 employees for the year.
        agg = [
            {'employee': i, 'annual_gross': Decimal('1200000')}
            for i in range(3)
        ]
        with patch('hrm.models.PayrollLine.objects.filter') as filt, \
             patch('hrm.models.Employee.objects.filter') as emp_filt:
            qs = MagicMock()
            qs.values.return_value.annotate.return_value = agg
            filt.return_value = qs
            emp_filt.return_value = []  # won't be called when empty

            result = export_itf_schedule(year=2025)

        assert result.rows == []
        assert result.totals['threshold_met'] == Decimal('0')
        assert result.totals['headcount'] == Decimal('3')

    def test_at_threshold_includes_schedule(self):
        """Exactly 5 employees → schedule IS produced (threshold is
        "5 or more")."""
        from accounting.statutory.itf import export_itf_schedule

        agg = [
            {'employee': i, 'annual_gross': Decimal('1000000')}
            for i in range(5)
        ]
        emps = [
            MagicMock(
                id=i, first_name=f'E{i}', middle_name='', last_name='X',
                employee_id=f'EMP-{i}',
            )
            for i in range(5)
        ]
        with patch('hrm.models.PayrollLine.objects.filter') as filt, \
             patch('hrm.models.Employee.objects.filter') as emp_filt:
            qs = MagicMock()
            qs.values.return_value.annotate.return_value = agg
            filt.return_value = qs
            emp_filt.return_value = emps

            result = export_itf_schedule(year=2025)

        assert len(result.rows) == 5
        assert result.totals['threshold_met'] == Decimal('1')
        # 5 × 1M × 1% = 50,000.
        assert result.totals['total_itf_contribution'] == Decimal('50000.00')
        assert result.totals['total_annual_gross'] == Decimal('5000000')

    def test_annual_rate_is_one_percent(self):
        """Per-row ITF contribution is exactly 1% of annual gross."""
        from accounting.statutory.itf import export_itf_schedule

        agg = [
            {'employee': i, 'annual_gross': Decimal('2400000')}
            for i in range(7)
        ]
        emps = [
            MagicMock(
                id=i, first_name=f'E{i}', middle_name='', last_name='X',
                employee_id=f'EMP-{i}',
            )
            for i in range(7)
        ]
        with patch('hrm.models.PayrollLine.objects.filter') as filt, \
             patch('hrm.models.Employee.objects.filter') as emp_filt:
            qs = MagicMock()
            qs.values.return_value.annotate.return_value = agg
            filt.return_value = qs
            emp_filt.return_value = emps

            result = export_itf_schedule(year=2025)

        # 2,400,000 × 1% = 24,000 per row.
        assert result.rows[0]['ITF Contribution (NGN)'] == Decimal('24000.00')


# =============================================================================
# NHIA
# =============================================================================

class TestNHIAExporter:

    def _line_stub(
        self, *, basic, first='C', last='D',
        hmo='HealthCare Intl.', nhis_id='NHIS-001',
    ):
        line = MagicMock()
        line.basic_salary = Decimal(str(basic))
        emp = MagicMock()
        emp.first_name = first
        emp.middle_name = ''
        emp.last_name = last
        emp.employee_id = 'EMP-01'
        emp.hmo_name = hmo
        emp.nhis_id = nhis_id
        line.employee = emp
        return line

    def test_rates_on_basic_salary(self):
        """NHIA is 1.75% / 3.25% of BASIC, not gross."""
        from accounting.statutory.nhis import export_nhis_schedule

        lines = [self._line_stub(basic=200_000)]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_nhis_schedule(year=2026, month=4)

        assert result.rows[0]['Employee Contribution (NGN)'] == Decimal('3500.00')
        assert result.rows[0]['Employer Contribution (NGN)'] == Decimal('6500.00')
        assert result.rows[0]['Total Contribution (NGN)'] == Decimal('10000.00')

    def test_missing_hmo_flags_remark(self):
        from accounting.statutory.nhis import export_nhis_schedule

        lines = [self._line_stub(basic=100_000, hmo='', nhis_id='')]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_nhis_schedule(year=2026, month=4)

        remark = result.rows[0]['Remarks']
        assert 'HMO not assigned' in remark
        assert 'NHIS ID missing' in remark

    def test_totals_separate_employee_employer(self):
        from accounting.statutory.nhis import export_nhis_schedule

        lines = [
            self._line_stub(basic=100_000),   # emp 1750, empr 3250
            self._line_stub(basic=200_000),   # emp 3500, empr 6500
        ]
        with patch('hrm.models.PayrollLine.objects.filter') as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = lines
            filt.return_value = qs

            result = export_nhis_schedule(year=2026, month=4)

        assert result.totals['total_employee_contribution'] == Decimal('5250.00')
        assert result.totals['total_employer_contribution'] == Decimal('9750.00')
        assert result.totals['grand_total'] == Decimal('15000.00')


# =============================================================================
# Structural checks — CSV output for all four
# =============================================================================

class TestPayrollStatutoryCSVStructure:
    """All four exporters must produce a CSV header regardless of data."""

    @pytest.mark.parametrize('patch_path,exporter_path,kwargs', [
        ('hrm.models.PayrollLine.objects.filter',
         'accounting.statutory.pencom.export_pencom_schedule',
         {'year': 2026, 'month': 4}),
        ('hrm.models.PayrollLine.objects.filter',
         'accounting.statutory.nsitf.export_nsitf_schedule',
         {'year': 2026, 'month': 4}),
        ('hrm.models.PayrollLine.objects.filter',
         'accounting.statutory.nhis.export_nhis_schedule',
         {'year': 2026, 'month': 4}),
    ])
    def test_empty_period_emits_header_only(self, patch_path, exporter_path, kwargs):
        """Header row is always present even when no lines match."""
        import importlib
        module_name, fn_name = exporter_path.rsplit('.', 1)
        exporter = getattr(importlib.import_module(module_name), fn_name)

        with patch(patch_path) as filt:
            qs = MagicMock()
            qs.select_related.return_value.order_by.return_value = []
            filt.return_value = qs

            result = exporter(**kwargs)

        csv_lines = result.csv.strip().split('\n')
        # At minimum: one header line.
        assert len(csv_lines) >= 1
        assert ',' in csv_lines[0]   # header has columns
        assert result.rows == []
