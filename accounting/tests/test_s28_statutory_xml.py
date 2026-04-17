"""
Phase 5 — Statutory XML exporter + XSD validator tests.

Round-trip: call each ``build_*_xml`` function, feed the result
straight into ``validate_xml`` against the appropriate XSD, and
assert the result is valid.

No DB dependency — exporters take plain dataclasses so they're
unit-testable.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest


class TestValidatorContract:

    def test_validation_result_dataclass(self):
        from accounting.services.statutory_xml import ValidationResult
        r = ValidationResult(is_valid=True)
        assert r.is_valid is True
        assert r.errors == []
        assert r.warnings == []

    def test_assert_valid_raises_on_invalid(self):
        from accounting.services.statutory_xml import (
            ValidationResult, XSDValidationError,
        )
        r = ValidationResult(
            is_valid=False,
            schema_path='/x.xsd',
            errors=['missing element Header'],
        )
        with pytest.raises(XSDValidationError) as exc:
            r.assert_valid()
        assert 'missing element Header' in str(exc.value)

    def test_missing_schema_returns_invalid(self):
        from accounting.services.statutory_xml import validate_xml
        r = validate_xml(b'<x/>', 'nonexistent_schema.xsd')
        assert not r.is_valid
        assert any('not found' in e for e in r.errors)

    def test_malformed_xml_caught_before_xsd(self):
        from accounting.services.statutory_xml import validate_xml
        r = validate_xml(b'<unclosed>', 'firs_wht.xsd')
        assert not r.is_valid
        assert any('well-formed' in e for e in r.errors)


class TestFIRSWHTExporter:

    def _sample_lines(self):
        from accounting.services.statutory_xml import WHTLine
        return [
            WHTLine(
                payee_name='Acme Contracts Ltd',
                payee_tin='12345678',
                payee_type='COMPANY',
                invoice_number='INV-2026-001',
                invoice_date='2026-04-05',
                gross_amount=Decimal('1000000.00'),
                wht_rate=Decimal('5.00'),
                wht_amount=Decimal('50000.00'),
                nature_of_payment='CONTRACT',
            ),
            WHTLine(
                payee_name='John Doe',
                payee_tin=None,
                payee_type='INDIVIDUAL',
                invoice_number='CONS-042',
                invoice_date='2026-04-15',
                gross_amount=Decimal('250000.00'),
                wht_rate=Decimal('10.00'),
                wht_amount=Decimal('25000.00'),
                nature_of_payment='CONSULTANCY',
            ),
        ]

    def test_exporter_produces_bytes(self):
        from accounting.services.statutory_xml import build_firs_wht_xml
        out = build_firs_wht_xml(
            taxpayer_tin='10203040', taxpayer_name='Delta State Government',
            year=2026, month=4, return_type='ORIGINAL',
            prepared_by='aminu@delta.gov.ng',
            prepared_at_iso='2026-04-17T10:00:00+01:00',
            lines=self._sample_lines(),
        )
        assert isinstance(out, bytes)
        assert out.startswith(b'<?xml')
        assert b'<WHTReturn>' in out
        assert b'<TotalWHT>75000.00</TotalWHT>' in out
        assert b'<LineCount>2</LineCount>' in out

    def test_roundtrip_through_validator(self):
        from accounting.services.statutory_xml import (
            build_firs_wht_xml, validate_xml,
        )
        out = build_firs_wht_xml(
            taxpayer_tin='10203040', taxpayer_name='Delta State Government',
            year=2026, month=4, return_type='ORIGINAL',
            prepared_by='aminu@delta.gov.ng',
            prepared_at_iso='2026-04-17T10:00:00+01:00',
            lines=self._sample_lines(),
        )
        r = validate_xml(out, 'firs_wht.xsd')
        # Well-formedness always passes; XSD passes only when lxml is
        # installed. Either outcome is acceptable — we just must not
        # report is_valid=False with errors for this known-good input.
        assert r.is_valid, f'Unexpected errors: {r.errors[:3]}'

    def test_totals_computed_correctly(self):
        from accounting.services.statutory_xml import build_firs_wht_xml
        out = build_firs_wht_xml(
            taxpayer_tin='10203040', taxpayer_name='X', year=2026, month=4,
            return_type='ORIGINAL', prepared_by='x',
            prepared_at_iso='2026-04-17T10:00:00+01:00',
            lines=self._sample_lines(),
        )
        # 1,000,000 + 250,000 = 1,250,000
        assert b'<TotalGross>1250000.00</TotalGross>' in out


class TestFIRSVATExporter:

    def test_vat_exporter_produces_valid_xml(self):
        from accounting.services.statutory_xml import build_firs_vat_xml
        out = build_firs_vat_xml(
            taxpayer_tin='10203040', taxpayer_name='Delta State',
            year=2026, month=4, return_type='ORIGINAL',
            output_standard=Decimal('10000000'),
            output_zero=Decimal('500000'),
            output_exempt=Decimal('200000'),
            output_vat_collected=Decimal('750000'),
            input_standard=Decimal('4000000'),
            input_zero=Decimal('0'),
            input_exempt=Decimal('100000'),
            input_vat_paid=Decimal('300000'),
        )
        assert b'<VATReturn>' in out
        assert b'<VATPayable>450000.00</VATPayable>' in out  # 750k - 300k

    def test_refund_position_is_negative(self):
        from accounting.services.statutory_xml import build_firs_vat_xml
        out = build_firs_vat_xml(
            taxpayer_tin='10203040', taxpayer_name='X',
            year=2026, month=4, return_type='ORIGINAL',
            output_standard=Decimal('1000000'),
            output_zero=Decimal('0'), output_exempt=Decimal('0'),
            output_vat_collected=Decimal('75000'),
            input_standard=Decimal('5000000'),
            input_zero=Decimal('0'), input_exempt=Decimal('0'),
            input_vat_paid=Decimal('375000'),
        )
        # 75k output - 375k input = -300k (refund position)
        assert b'<VATPayable>-300000.00</VATPayable>' in out

    def test_roundtrip_through_validator(self):
        from accounting.services.statutory_xml import (
            build_firs_vat_xml, validate_xml,
        )
        out = build_firs_vat_xml(
            taxpayer_tin='10203040', taxpayer_name='X',
            year=2026, month=4, return_type='ORIGINAL',
            output_standard=Decimal('1000000'),
            output_zero=Decimal('0'), output_exempt=Decimal('0'),
            output_vat_collected=Decimal('75000'),
            input_standard=Decimal('500000'),
            input_zero=Decimal('0'), input_exempt=Decimal('0'),
            input_vat_paid=Decimal('37500'),
        )
        r = validate_xml(out, 'firs_vat.xsd')
        assert r.is_valid, f'Unexpected errors: {r.errors[:3]}'


class TestPENCOMExporter:

    def _sample_rows(self):
        from accounting.services.statutory_xml import PENCOMContribution
        return [
            PENCOMContribution(
                employee_pin='PEN123456789012',
                surname='Okoro', first_name='Ifeoma', other_names='Chinwe',
                date_of_birth='1985-03-14',
                employer_contribution=Decimal('50000.00'),
                employee_contribution=Decimal('40000.00'),
                month=4, year=2026,
            ),
            PENCOMContribution(
                employee_pin='PEN987654321098',
                surname='Bello', first_name='Musa', other_names='',
                date_of_birth='1990-07-22',
                employer_contribution=Decimal('30000.00'),
                employee_contribution=Decimal('24000.00'),
                month=4, year=2026,
            ),
        ]

    def test_exporter_totals(self):
        from accounting.services.statutory_xml import build_pencom_schedule_xml
        out = build_pencom_schedule_xml(
            employer_rc_number='RC123456',
            employer_name='Delta State',
            pfa_code='STANBIC',
            period_year=2026, period_month=4,
            rows=self._sample_rows(),
        )
        # 50k + 30k = 80k employer
        assert b'<TotalEmployer>80000.00</TotalEmployer>' in out
        # 40k + 24k = 64k employee
        assert b'<TotalEmployee>64000.00</TotalEmployee>' in out
        # Grand total = 144k
        assert b'<GrandTotal>144000.00</GrandTotal>' in out
        assert b'<EmployeeCount>2</EmployeeCount>' in out

    def test_roundtrip_through_validator(self):
        from accounting.services.statutory_xml import (
            build_pencom_schedule_xml, validate_xml,
        )
        out = build_pencom_schedule_xml(
            employer_rc_number='RC123456',
            employer_name='Delta State',
            pfa_code='STANBIC',
            period_year=2026, period_month=4,
            rows=self._sample_rows(),
        )
        r = validate_xml(out, 'pencom_pension.xsd')
        assert r.is_valid, f'Unexpected errors: {r.errors[:3]}'

    def test_invalid_pin_caught_by_xsd(self):
        """Short PIN fails the XSD pattern. Only runs when lxml installed —
        without lxml we skip (documented in ValidationResult.warnings)."""
        try:
            import lxml  # noqa
        except ImportError:
            pytest.skip('lxml not installed — XSD content validation skipped')

        from accounting.services.statutory_xml import (
            build_pencom_schedule_xml, validate_xml, PENCOMContribution,
        )
        bad = [PENCOMContribution(
            employee_pin='BAD',  # not PEN-prefixed, wrong length
            surname='X', first_name='Y', other_names='',
            date_of_birth='1990-01-01',
            employer_contribution=Decimal('0'), employee_contribution=Decimal('0'),
            month=4, year=2026,
        )]
        out = build_pencom_schedule_xml(
            employer_rc_number='RC123456', employer_name='X',
            pfa_code='STAN', period_year=2026, period_month=4, rows=bad,
        )
        r = validate_xml(out, 'pencom_pension.xsd')
        assert not r.is_valid
        assert any('PIN' in e for e in r.errors)


class TestSchemaFilesShipped:
    """Freeze the schema-file inventory. A refactor that renames or
    removes an XSD would silently break exports."""

    def test_schema_directory_exists(self):
        from accounting.services.statutory_xml import SCHEMA_DIR
        assert SCHEMA_DIR.is_dir()

    def test_firs_wht_xsd_present(self):
        from accounting.services.statutory_xml import SCHEMA_DIR
        assert (SCHEMA_DIR / 'firs_wht.xsd').is_file()

    def test_firs_vat_xsd_present(self):
        from accounting.services.statutory_xml import SCHEMA_DIR
        assert (SCHEMA_DIR / 'firs_vat.xsd').is_file()

    def test_pencom_xsd_present(self):
        from accounting.services.statutory_xml import SCHEMA_DIR
        assert (SCHEMA_DIR / 'pencom_pension.xsd').is_file()
