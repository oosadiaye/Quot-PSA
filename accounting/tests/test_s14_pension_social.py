"""
Sprint-14 regression tests: IPSAS 39 pension models + IPSAS 42 social
benefits + their IPSAS Notes integration.

Fast-tier (no DB) coverage:
  * ``PensionScheme.is_defined_benefit`` property
  * ``ActuarialValuation.net_defined_benefit_liability`` +
    ``total_period_expense`` math
  * ``SocialBenefitClaim.is_recognisable`` IPSAS 42 ¶31 gate
  * Note 8 (pension) + Note 9 (social benefits) degraded + populated
    paths via mocked querysets
  * ``ActuarialValuationSerializer`` rejects DB-only valuations on DC
    schemes (IPSAS 39 ¶30)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# PensionScheme property
# =============================================================================

class TestPensionSchemeIsDefinedBenefit:

    def _scheme(self, scheme_type='DEFINED_BENEFIT'):
        from accounting.models import PensionScheme
        return PensionScheme(
            code='TEST', name='Test', scheme_type=scheme_type,
        )

    def test_defined_benefit_true(self):
        assert self._scheme('DEFINED_BENEFIT').is_defined_benefit is True

    def test_defined_contribution_false(self):
        assert self._scheme('DEFINED_CONTRIBUTION').is_defined_benefit is False


# =============================================================================
# ActuarialValuation — math properties
# =============================================================================

class TestActuarialValuationMath:

    def _val(self, **overrides):
        from accounting.models import ActuarialValuation
        defaults = dict(
            valuation_date=date(2026, 12, 31),
            dbo=Decimal('0'),
            plan_assets=Decimal('0'),
            service_cost=Decimal('0'),
            interest_cost=Decimal('0'),
            past_service_cost=Decimal('0'),
            gain_on_settlement=Decimal('0'),
            actuarial_gains_losses=Decimal('0'),
            return_on_plan_assets=Decimal('0'),
        )
        defaults.update(overrides)
        return ActuarialValuation(**defaults)

    def test_net_liability_unfunded_scheme(self):
        """Unfunded DB scheme: net liability = DBO."""
        v = self._val(dbo=Decimal('100000000'), plan_assets=Decimal('0'))
        assert v.net_defined_benefit_liability == Decimal('100000000')

    def test_net_liability_funded_scheme(self):
        """Funded DB scheme: net liability = DBO − plan assets."""
        v = self._val(
            dbo=Decimal('100000000'),
            plan_assets=Decimal('60000000'),
        )
        assert v.net_defined_benefit_liability == Decimal('40000000')

    def test_net_liability_overfunded_is_negative(self):
        """Overfunded (rare): negative liability = asset."""
        v = self._val(
            dbo=Decimal('40000000'),
            plan_assets=Decimal('50000000'),
        )
        assert v.net_defined_benefit_liability == Decimal('-10000000')

    def test_total_period_expense_sum(self):
        """IPSAS 39 ¶64: service + interest + past-service − settlement gain."""
        v = self._val(
            service_cost=Decimal('5000000'),
            interest_cost=Decimal('15000000'),
            past_service_cost=Decimal('2000000'),
            gain_on_settlement=Decimal('1000000'),
        )
        # 5M + 15M + 2M - 1M = 21M
        assert v.total_period_expense == Decimal('21000000')

    def test_total_period_expense_defaults_to_zero(self):
        v = self._val()
        assert v.total_period_expense == Decimal('0')


# =============================================================================
# PensionContribution.total_amount
# =============================================================================

class TestPensionContributionTotal:

    def test_sums_employee_and_employer(self):
        from accounting.models import PensionContribution
        c = PensionContribution(
            scheme_id=1, period_year=2026, period_month=4,
            employee_amount=Decimal('80000'),
            employer_amount=Decimal('100000'),
        )
        assert c.total_amount == Decimal('180000')

    def test_handles_zero_inputs(self):
        from accounting.models import PensionContribution
        c = PensionContribution(
            scheme_id=1, period_year=2026, period_month=4,
            employee_amount=Decimal('0'),
            employer_amount=Decimal('0'),
        )
        assert c.total_amount == Decimal('0')


# =============================================================================
# SocialBenefitClaim — recognition gate
# =============================================================================

class TestSocialBenefitClaimIsRecognisable:

    def _claim(self, **overrides):
        from accounting.models import SocialBenefitClaim
        defaults = dict(
            claim_reference='X-001',
            beneficiary_name='Test',
            period_year=2026, period_month=4,
            amount=Decimal('10000'),
            eligible_date=date(2026, 4, 1),
        )
        defaults.update(overrides)
        return SocialBenefitClaim(**defaults)

    def test_eligible_with_positive_amount_is_recognisable(self):
        assert self._claim().is_recognisable is True

    def test_no_eligible_date_not_recognisable(self):
        """IPSAS 42 ¶31: recognition starts at the eligibility date."""
        assert self._claim(eligible_date=None).is_recognisable is False

    def test_zero_amount_not_recognisable(self):
        assert self._claim(amount=Decimal('0')).is_recognisable is False

    def test_negative_amount_not_recognisable(self):
        """Defensive: a negative payment is never recognisable."""
        assert self._claim(amount=Decimal('-100')).is_recognisable is False


# =============================================================================
# ActuarialValuationSerializer — DC scheme rejection
# =============================================================================

class TestActuarialValuationSerializerScopeGuard:

    def test_rejects_valuation_on_dc_scheme(self):
        """IPSAS 39 ¶30: actuarial valuations apply only to DB schemes.
        Recording one against a DC scheme is a user error and the
        serializer must flag it."""
        from accounting.views.pension_social import ActuarialValuationSerializer
        from rest_framework.exceptions import ValidationError

        scheme = MagicMock()
        scheme.code = 'DELTA-CPS'
        scheme.is_defined_benefit = False
        serializer = ActuarialValuationSerializer()
        with pytest.raises(ValidationError, match='Defined Contribution'):
            serializer.validate({'scheme': scheme})

    def test_accepts_valuation_on_db_scheme(self):
        from accounting.views.pension_social import ActuarialValuationSerializer

        scheme = MagicMock()
        scheme.code = 'DELTA-LEGACY-DB'
        scheme.is_defined_benefit = True
        serializer = ActuarialValuationSerializer()
        attrs = {'scheme': scheme}
        result = serializer.validate(attrs)
        assert result is attrs  # pass-through


# =============================================================================
# IPSAS Notes — degraded paths
# =============================================================================

_STUB_GL = {
    'fiscal_year': 2026,
    'filter': {'prefixes': [], 'exact': []},
    'lines': [], 'total_debit': 0, 'total_credit': 0, 'total_net': 0,
}


class TestNotePensionDegraded:
    """After S21 the degraded-mode note embeds a ``gl_balances`` section
    (still empty when the ledger is empty) so the reconciliation surface
    is present regardless of register state. ``data`` is therefore a dict
    rather than None once S21 shipped — these tests assert that shape."""

    def test_no_schemes_returns_note_with_gl_section(self):
        from accounting.services.ipsas_reports import IPSASReportService
        with patch(
            'accounting.services.ipsas_reports.IPSASReportService._gl_balances_for_note',
            return_value=_STUB_GL,
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._pension_gl_codes',
            return_value=['42201000'],
        ), patch(
            'accounting.models.PensionScheme.objects.all',
        ) as all_mock:
            all_mock.return_value.order_by.return_value = []
            note = IPSASReportService._note_pension_ipsas_39(2026)
        assert note['number'] == 8
        assert isinstance(note['data'], dict)
        assert 'gl_balances' in note['data']
        assert 'No pension schemes' in note['body']

    def test_model_import_raises_returns_degraded(self):
        """Defensive path — if the PensionScheme table isn't available
        (very early deployments), the note still returns with its GL
        section so the financial-statement reconciliation is visible."""
        from accounting.services.ipsas_reports import IPSASReportService
        with patch(
            'accounting.services.ipsas_reports.IPSASReportService._gl_balances_for_note',
            return_value=_STUB_GL,
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._pension_gl_codes',
            return_value=['42201000'],
        ), patch(
            'accounting.models.PensionScheme.objects.all',
            side_effect=Exception('table missing'),
        ):
            note = IPSASReportService._note_pension_ipsas_39(2026)
        assert note['number'] == 8
        assert isinstance(note['data'], dict)
        assert 'gl_balances' in note['data']


class TestNoteSocialBenefitsDegraded:

    def test_no_active_schemes_returns_note_with_gl_section(self):
        from accounting.services.ipsas_reports import IPSASReportService
        with patch(
            'accounting.services.ipsas_reports.IPSASReportService._gl_balances_for_note',
            return_value=_STUB_GL,
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._social_benefit_gl_codes',
            return_value=['25100000'],
        ), patch(
            'accounting.models.SocialBenefitScheme.objects.filter',
        ) as filt_mock:
            filt_mock.return_value.order_by.return_value = []
            note = IPSASReportService._note_social_benefits_ipsas_42(2026)
        assert note['number'] == 9
        assert isinstance(note['data'], dict)
        assert 'gl_balances' in note['data']
        assert 'no active social-benefit schemes' in note['body'].lower()

    def test_model_raises_returns_degraded(self):
        from accounting.services.ipsas_reports import IPSASReportService
        with patch(
            'accounting.services.ipsas_reports.IPSASReportService._gl_balances_for_note',
            return_value=_STUB_GL,
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._social_benefit_gl_codes',
            return_value=['25100000'],
        ), patch(
            'accounting.models.SocialBenefitScheme.objects.filter',
            side_effect=Exception('table missing'),
        ):
            note = IPSASReportService._note_social_benefits_ipsas_42(2026)
        assert note['number'] == 9
        assert isinstance(note['data'], dict)
        assert 'gl_balances' in note['data']


# =============================================================================
# Empty-note helper
# =============================================================================

class TestEmptyNoteHelper:

    def test_shape(self):
        from accounting.services.ipsas_reports import _empty_note
        note = _empty_note(99, 'Test Title', 'Test body')
        assert note == {
            'number': 99, 'title': 'Test Title',
            'body': 'Test body', 'data': None,
        }


# =============================================================================
# Notes output includes Note 8 + Note 9
# =============================================================================

class TestNotesPackCoverage:
    """The notes_to_financial_statements output must include both new
    IPSAS 39 and IPSAS 42 notes so auditors see the complete 9-note pack.
    """

    def test_notes_pack_includes_notes_8_and_9(self):
        from accounting.services.ipsas_reports import IPSASReportService

        # Mock every register query + the S21 GL helper so we only test
        # the NOTE STRUCTURE, not the content.
        with patch(
            'accounting.services.ipsas_reports.IPSASReportService._gl_balances_for_note',
            return_value=_STUB_GL,
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._pension_gl_codes',
            return_value=['42201000'],
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._social_benefit_gl_codes',
            return_value=['25100000'],
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._note_ppe_movement',
            return_value={'number': 2, 'title': 'PPE', 'body': '', 'data': None},
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._note_receivables_aging',
            return_value={'number': 3, 'title': 'R', 'body': '', 'data': None},
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._note_payables_aging',
            return_value={'number': 4, 'title': 'P', 'body': '', 'data': None},
        ), patch(
            'accounting.services.ipsas_reports.IPSASReportService._note_borrowings',
            return_value=None,
        ), patch(
            'accounting.models.PensionScheme.objects.all',
        ) as pens, patch(
            'accounting.models.SocialBenefitScheme.objects.filter',
        ) as social, patch(
            'accounting.models.OpeningBalanceSheet.objects.filter',
        ) as obs, patch(
            'accounting.models.Provision.objects.filter',
        ) as prov, patch(
            'accounting.models.ContingentLiability.objects.filter',
        ) as cl, patch(
            'accounting.models.ContingentAsset.objects.filter',
        ) as ca:
            pens.return_value.order_by.return_value = []
            social.return_value.order_by.return_value = []
            obs.return_value.order_by.return_value.first.return_value = None
            prov.return_value.values.return_value.annotate.return_value.order_by.return_value = []
            cl.return_value.values.return_value.annotate.return_value = []
            ca.return_value.values.return_value.annotate.return_value = []

            pack = IPSASReportService.notes_to_financial_statements(2026)

        note_numbers = [n['number'] for n in pack['notes']]
        # Every note number 1..9 should be present.
        for expected in range(1, 10):
            assert expected in note_numbers, (
                f'Note {expected} missing from notes pack. '
                f'Got: {note_numbers}'
            )
