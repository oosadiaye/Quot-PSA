"""
Sprint-15 regression tests — no-DB fast tier.

Covers:
  * PensionAccrualService — month validation, month-end helper,
    settings resolver behaviour.
  * SocialBenefitBatchPayService — missing bank code rejection,
    settings resolver, result dataclass defaults.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


# =============================================================================
# PensionAccrualService
# =============================================================================

class TestPensionMonthEnd:

    def test_jan(self):
        from accounting.services.pension_accrual import PensionAccrualService
        assert PensionAccrualService._month_end(2026, 1) == date(2026, 1, 31)

    def test_feb_non_leap(self):
        from accounting.services.pension_accrual import PensionAccrualService
        assert PensionAccrualService._month_end(2026, 2) == date(2026, 2, 28)

    def test_feb_leap(self):
        from accounting.services.pension_accrual import PensionAccrualService
        assert PensionAccrualService._month_end(2024, 2) == date(2024, 2, 29)

    def test_dec(self):
        from accounting.services.pension_accrual import PensionAccrualService
        assert PensionAccrualService._month_end(2026, 12) == date(2026, 12, 31)


class TestPensionMonthValidation:

    def test_month_too_low(self):
        from accounting.services.pension_accrual import (
            PensionAccrualService, PensionAccrualError,
        )
        with pytest.raises(PensionAccrualError, match='month must be 1-12'):
            PensionAccrualService.run_monthly(year=2026, month=0)

    def test_month_too_high(self):
        from accounting.services.pension_accrual import (
            PensionAccrualService, PensionAccrualError,
        )
        with pytest.raises(PensionAccrualError, match='month must be 1-12'):
            PensionAccrualService.run_monthly(year=2026, month=13)


class TestPensionResolve:

    def test_none_settings_returns_default(self):
        from accounting.services.pension_accrual import _resolve
        assert _resolve(None, 'any_field', 'DEFAULT') == 'DEFAULT'

    def test_blank_value_returns_default(self):
        from accounting.services.pension_accrual import _resolve

        class Obj:
            any_field = '   '
        assert _resolve(Obj(), 'any_field', 'DEFAULT') == 'DEFAULT'

    def test_set_value_returns_stripped(self):
        from accounting.services.pension_accrual import _resolve

        class Obj:
            any_field = '  12345  '
        assert _resolve(Obj(), 'any_field', 'DEFAULT') == '12345'


# =============================================================================
# SocialBenefitBatchPayService
# =============================================================================

class TestBatchPayBankCodeRequired:

    def test_missing_bank_code_rejected(self):
        from accounting.services.social_benefit_batch_pay import (
            SocialBenefitBatchPayService, SocialBenefitBatchPayError,
        )
        with pytest.raises(SocialBenefitBatchPayError, match='bank_account_code is required'):
            SocialBenefitBatchPayService.run_batch(bank_account_code='')

    def test_whitespace_bank_code_rejected(self):
        from accounting.services.social_benefit_batch_pay import (
            SocialBenefitBatchPayService, SocialBenefitBatchPayError,
        )
        with pytest.raises(SocialBenefitBatchPayError, match='bank_account_code is required'):
            SocialBenefitBatchPayService.run_batch(bank_account_code='   ')


class TestBatchPayResultDefaults:

    def test_result_dataclass_defaults(self):
        from accounting.services.social_benefit_batch_pay import BatchPayResult
        r = BatchPayResult(
            posting_date=date(2026, 4, 17),
            bank_account_code='11101001',
        )
        assert r.journal_id is None
        assert r.journal_reference == ''
        assert r.claims_paid == 0
        assert r.claims_skipped == 0
        assert r.total_paid == Decimal('0')
        assert r.skipped_details == []
        assert r.paid_claim_ids == []


class TestBatchPayResolve:

    def test_none_settings_returns_default(self):
        from accounting.services.social_benefit_batch_pay import _resolve
        assert _resolve(None, 'social_benefit_expense_code', '25100000') == '25100000'

    def test_blank_value_returns_default(self):
        from accounting.services.social_benefit_batch_pay import _resolve

        class Obj:
            social_benefit_expense_code = ''
        assert _resolve(Obj(), 'social_benefit_expense_code', '25100000') == '25100000'

    def test_set_value_returns_stripped(self):
        from accounting.services.social_benefit_batch_pay import _resolve

        class Obj:
            social_benefit_expense_code = '  25199999  '
        assert _resolve(Obj(), 'social_benefit_expense_code', '25100000') == '25199999'
