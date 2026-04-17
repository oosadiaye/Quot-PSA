"""
Sprint-13 regression tests:

  * IntangibleAmortisationService — period-stamp skip, residual cap,
    month-end posting date, AmortisationRunError on bad config.
  * IPSAS 33 transition note generator — degraded mode when no
    FINALISED opening balance sheet exists; full disclosures when one
    does.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# IntangibleAmortisationService — skip / cap / config logic (no DB)
# =============================================================================

class TestShouldSkip:

    def _asset(self, **overrides):
        from accounting.models import IntangibleAsset
        defaults = dict(
            asset_number='INTAN-001',
            name='Test', category='SOFTWARE_LICENCE',
            acquisition_cost=Decimal('1000000'),
            acquisition_date=date(2026, 1, 1),
            useful_life_months=60,
            amortisation_method='STRAIGHT_LINE',
            accumulated_amortisation=Decimal('0'),
            residual_value=Decimal('0'),
            impairment_loss=Decimal('0'),
            notes='',
            status='ACTIVE',
        )
        defaults.update(overrides)
        return IntangibleAsset(**defaults)

    def test_active_unstamped_not_fully_amortised_is_eligible(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        asset = self._asset()
        assert IntangibleAmortisationService._should_skip(
            asset, 'AMORT:2026-04',
        ) is None

    def test_already_stamped_skips(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        asset = self._asset(notes='AMORT:2026-04')
        reason = IntangibleAmortisationService._should_skip(
            asset, 'AMORT:2026-04',
        )
        assert reason is not None
        assert 'already stamped' in reason.lower()

    def test_fully_amortised_skips(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        asset = self._asset(
            accumulated_amortisation=Decimal('1000000'),  # 100% amortised
        )
        reason = IntangibleAmortisationService._should_skip(
            asset, 'AMORT:2026-04',
        )
        assert reason is not None
        assert 'fully amortised' in reason.lower()

    def test_earlier_period_stamp_does_not_skip_later_period(self):
        """Stamp `AMORT:2026-03` should not block running `AMORT:2026-04`."""
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        asset = self._asset(notes='AMORT:2026-03')
        assert IntangibleAmortisationService._should_skip(
            asset, 'AMORT:2026-04',
        ) is None


class TestCapToRemaining:

    def _asset(self, **overrides):
        from accounting.models import IntangibleAsset
        defaults = dict(
            asset_number='INTAN-001', name='Test',
            category='SOFTWARE_LICENCE',
            acquisition_cost=Decimal('1000000'),
            acquisition_date=date(2026, 1, 1),
            useful_life_months=60,
            amortisation_method='STRAIGHT_LINE',
            accumulated_amortisation=Decimal('0'),
            residual_value=Decimal('0'),
            impairment_loss=Decimal('0'),
        )
        defaults.update(overrides)
        return IntangibleAsset(**defaults)

    def test_normal_charge_uncapped(self):
        """Typical month: charge well below carrying amount — uncapped."""
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        asset = self._asset()
        capped = IntangibleAmortisationService._cap_to_remaining(
            asset, Decimal('16666.67'),
        )
        assert capped == Decimal('16666.67')

    def test_final_month_capped_to_remaining(self):
        """Last month: normal charge would overshoot — cap to remaining."""
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        asset = self._asset(
            accumulated_amortisation=Decimal('990000'),  # 10k left
        )
        # Normal charge 16.67k, remaining 10k → capped to 10k.
        capped = IntangibleAmortisationService._cap_to_remaining(
            asset, Decimal('16666.67'),
        )
        assert capped == Decimal('10000')

    def test_already_at_residual_returns_zero(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        asset = self._asset(
            accumulated_amortisation=Decimal('1000000'),
            residual_value=Decimal('0'),
        )
        capped = IntangibleAmortisationService._cap_to_remaining(
            asset, Decimal('1000'),
        )
        assert capped == Decimal('0')

    def test_cap_respects_residual_value(self):
        """Cap down to (carrying_amount - residual), not carrying_amount."""
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        asset = self._asset(
            acquisition_cost=Decimal('100000'),
            residual_value=Decimal('10000'),
            accumulated_amortisation=Decimal('85000'),
        )
        # carrying = 100 - 85 = 15k, remaining over residual = 15 - 10 = 5k.
        capped = IntangibleAmortisationService._cap_to_remaining(
            asset, Decimal('1666.67'),
        )
        # Normal monthly charge (1.67k) is below the remaining 5k, so uncapped.
        assert capped == Decimal('1666.67')


class TestMonthEndDate:

    def test_january(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        assert IntangibleAmortisationService._month_end(2026, 1) == date(2026, 1, 31)

    def test_february_non_leap(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        assert IntangibleAmortisationService._month_end(2026, 2) == date(2026, 2, 28)

    def test_february_leap(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        assert IntangibleAmortisationService._month_end(2024, 2) == date(2024, 2, 29)

    def test_december(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService,
        )
        assert IntangibleAmortisationService._month_end(2026, 12) == date(2026, 12, 31)


class TestResolveSettingCode:

    def test_uses_default_when_settings_is_none(self):
        from accounting.services.intangible_amortisation import _resolve_setting_code
        assert _resolve_setting_code(None, 'x', 'DEFAULT') == 'DEFAULT'

    def test_uses_default_when_attribute_missing(self):
        from accounting.services.intangible_amortisation import _resolve_setting_code
        s = MagicMock(spec=[])  # no attributes
        assert _resolve_setting_code(s, 'nonexistent', 'DEFAULT') == 'DEFAULT'

    def test_strips_whitespace_from_configured_value(self):
        from accounting.services.intangible_amortisation import _resolve_setting_code
        s = MagicMock()
        s.code = '   22301000   '
        assert _resolve_setting_code(s, 'code', 'DEFAULT') == '22301000'

    def test_empty_string_falls_back_to_default(self):
        from accounting.services.intangible_amortisation import _resolve_setting_code
        s = MagicMock()
        s.code = ''
        assert _resolve_setting_code(s, 'code', 'DEFAULT') == 'DEFAULT'


class TestAmortisationRunErrorOnBadConfig:

    def test_invalid_month_raises(self):
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService, AmortisationRunError,
        )
        with pytest.raises(AmortisationRunError, match='month must be 1-12'):
            IntangibleAmortisationService.run_monthly(year=2026, month=13)

    def test_missing_expense_account_raises(self):
        """When the configured expense account code doesn't exist in the
        CoA, the service raises AmortisationRunError (not a 500)."""
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService, AmortisationRunError,
        )
        with patch(
            'accounting.models.AccountingSettings.objects.first',
            return_value=None,
        ), patch(
            'accounting.models.Account.objects.filter'
        ) as filt:
            filt.return_value.first.return_value = None  # no account found
            with pytest.raises(AmortisationRunError,
                               match='expense account.*not in the chart'):
                IntangibleAmortisationService.run_monthly(year=2026, month=4)


# =============================================================================
# IPSAS 33 transition note generator
# =============================================================================

class TestTransitionNoteDegraded:
    """When no FINALISED opening balance sheet exists, the note is
    emitted with ``data=None`` and a "not a first-time adopter" body."""

    def test_returns_degraded_note_when_no_obs(self):
        from accounting.services.ipsas_reports import IPSASReportService

        with patch(
            'accounting.models.OpeningBalanceSheet.objects.filter'
        ) as filt:
            filt.return_value.order_by.return_value.first.return_value = None
            note = IPSASReportService._note_ipsas_33_transition(2026)

        assert note['number'] == 7
        assert 'IPSAS 33' in note['title']
        assert note['data'] is None
        assert 'not in a first-time-adoption year' in note['body']

    def test_returns_degraded_note_when_model_raises(self):
        """Defensive path — if OpeningBalanceSheet can't be queried (e.g.
        pre-S10 deployment), we still return a valid note shape."""
        from accounting.services.ipsas_reports import IPSASReportService
        with patch(
            'accounting.models.OpeningBalanceSheet.objects.filter',
            side_effect=Exception('table missing'),
        ):
            note = IPSASReportService._note_ipsas_33_transition(2026)
        assert note['number'] == 7
        assert note['data'] is None


class TestTransitionNoteFinalised:
    """Integration-style: OBS exists, note emits full ¶142 disclosures."""

    def _build_obs_stub(self, items: list[dict]):
        """Build a MagicMock that looks like a FINALISED OpeningBalanceSheet."""
        sheet = MagicMock()
        sheet.transition_date = date(2026, 1, 1)
        sheet.status = 'FINALISED'
        sheet.finalised_at = MagicMock(
            isoformat=lambda: '2026-02-15T10:00:00',
            date=lambda: date(2026, 2, 15),
        )
        sheet.finalised_by = MagicMock(username='ag_accountant')
        jnl = MagicMock()
        jnl.reference_number = 'OBS-2026-01-01'
        sheet.finalisation_journal = jnl
        sheet.total_assets = Decimal('10000000')
        sheet.total_liabilities = Decimal('4000000')
        sheet.total_net_assets = Decimal('6000000')
        sheet.is_balanced = True
        sheet.transition_notes = 'Test transition'

        # Build item stubs.
        items_qs = MagicMock()
        item_objs = []
        for spec in items:
            item = MagicMock()
            account = MagicMock()
            account.code = spec['account_code']
            account.name = spec['account_name']
            item.account = account
            item.debit = spec.get('debit', Decimal('0'))
            item.credit = spec.get('credit', Decimal('0'))
            item.deemed_cost_basis = spec.get('basis', 'HISTORICAL')
            item.deemed_cost_rationale = spec.get('rationale', '')
            item.supporting_document_ref = spec.get('ref', '')
            item_objs.append(item)
        items_qs.select_related.return_value.all.return_value = item_objs
        sheet.items = items_qs
        return sheet

    def test_full_disclosures_when_sheet_finalised(self):
        from accounting.services.ipsas_reports import IPSASReportService

        sheet = self._build_obs_stub([
            # Historical cost items
            {'account_code': '31100000', 'account_name': 'Cash',
             'debit': Decimal('500000'), 'basis': 'HISTORICAL'},
            # Fair-value elected items
            {'account_code': '32100000', 'account_name': 'Buildings',
             'debit': Decimal('9000000'), 'basis': 'FAIR_VALUE',
             'rationale': 'Independent valuer report dated 2025-12-20',
             'ref': 'VAL-RPT-2025-034'},
            {'account_code': '32200000', 'account_name': 'Plant & Equipment',
             'debit': Decimal('500000'), 'basis': 'FAIR_VALUE',
             'rationale': 'Same valuer; schedule attached',
             'ref': 'VAL-RPT-2025-034-APPX'},
            # Liability (credit-normal)
            {'account_code': '41100000', 'account_name': 'Payables',
             'credit': Decimal('4000000'), 'basis': 'HISTORICAL'},
        ])

        with patch(
            'accounting.models.OpeningBalanceSheet.objects.filter'
        ) as filt:
            filt.return_value.order_by.return_value.first.return_value = sheet
            note = IPSASReportService._note_ipsas_33_transition(2026)

        assert note['number'] == 7
        assert note['data'] is not None
        data = note['data']
        assert data['transition_date'] == '2026-01-01'
        assert data['journal_reference'] == 'OBS-2026-01-01'
        assert data['opening_totals']['total_assets'] == Decimal('10000000')
        assert data['opening_totals']['is_balanced'] is True

        # Elections — should have at least HISTORICAL + FAIR_VALUE groups.
        elections_by_basis = {e['basis']: e for e in data['deemed_cost_elections']}
        assert 'HISTORICAL' in elections_by_basis
        assert 'FAIR_VALUE' in elections_by_basis

        # FAIR_VALUE grouping: 2 items, 9.5M total, rationale_required=True.
        fv = elections_by_basis['FAIR_VALUE']
        assert fv['item_count'] == 2
        assert fv['total'] == Decimal('9500000')
        assert fv['rationale_required'] is True
        assert 'items' in fv
        # Each item carries rationale + evidence_ref for ¶142(c).
        for item in fv['items']:
            assert item['rationale'], 'Fair-value items must document rationale'
            assert item['evidence_ref'], 'Fair-value items must cite evidence'

        # HISTORICAL grouping: rationale_required=False; no per-item
        # list needed.
        hist = elections_by_basis['HISTORICAL']
        assert hist['rationale_required'] is False

    def test_body_references_transition_journal_reference(self):
        from accounting.services.ipsas_reports import IPSASReportService
        sheet = self._build_obs_stub([
            {'account_code': '31100000', 'account_name': 'Cash',
             'debit': Decimal('1000000'), 'basis': 'HISTORICAL'},
        ])
        with patch(
            'accounting.models.OpeningBalanceSheet.objects.filter'
        ) as filt:
            filt.return_value.order_by.return_value.first.return_value = sheet
            note = IPSASReportService._note_ipsas_33_transition(2026)
        assert 'OBS-2026-01-01' in note['body']


# =============================================================================
# Amortisation result dataclass
# =============================================================================

class TestAmortisationRunResult:

    def test_defaults(self):
        from accounting.services.intangible_amortisation import (
            AmortisationRunResult,
        )
        r = AmortisationRunResult(year=2026, month=4)
        assert r.year == 2026
        assert r.month == 4
        assert r.journal_id is None
        assert r.assets_posted == 0
        assert r.assets_skipped == 0
        assert r.total_amortisation == Decimal('0')
        assert r.skipped_details == []
