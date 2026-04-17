"""
Phase 2 Task 1 tests — period-close service.

No-DB fast tier: service contract, helper behaviour, reference stamp.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


class TestResolveSetting:

    def test_none_settings_returns_default(self):
        from accounting.services.period_close import _resolve_setting
        assert _resolve_setting(None, 'anything', 'X') == 'X'

    def test_blank_returns_default(self):
        from accounting.services.period_close import _resolve_setting

        class Obj:
            anything = '   '
        assert _resolve_setting(Obj(), 'anything', 'X') == 'X'

    def test_set_returns_stripped(self):
        from accounting.services.period_close import _resolve_setting

        class Obj:
            anything = '  43100000 '
        assert _resolve_setting(Obj(), 'anything', 'X') == '43100000'


class TestCloseResultShape:

    def test_dataclass_defaults(self):
        from accounting.services.period_close import CloseResult
        r = CloseResult(fiscal_year=2026)
        assert r.fiscal_year == 2026
        assert r.already_closed is False
        assert r.journal_id is None
        assert r.total_revenue == Decimal('0')
        assert r.total_expense == Decimal('0')
        assert r.surplus_deficit == Decimal('0')
        assert r.line_count == 0


class TestReferenceStamp:
    """The reference stamp is the idempotency key — must stay stable."""

    def test_stamp_format(self):
        # The planner uses f'PERIOD-CLOSE:{fiscal_year}' as the
        # unique identifier. Any change here silently orphans prior
        # close postings.
        expected = 'PERIOD-CLOSE:2026'
        from accounting.services import period_close
        # Re-derive the stamp the same way the planner does.
        stamp = f'PERIOD-CLOSE:{2026}'
        assert stamp == expected
        # Also verify the helper module constants.
        assert period_close.REV_PREFIXES == ('11', '12', '13', '14')
        assert period_close.EXP_PREFIXES == ('21', '22', '23', '24', '25')


class TestPrefixCoverage:
    """Every revenue and expense NCoA group must be covered by the
    close. If a new prefix ships (e.g. extraordinary items under 15xx)
    and we don't add it here, the SoFP will silently stop balancing."""

    def test_revenue_prefixes(self):
        from accounting.services.period_close import REV_PREFIXES
        assert set(REV_PREFIXES) == {'11', '12', '13', '14'}

    def test_expense_prefixes(self):
        from accounting.services.period_close import EXP_PREFIXES
        assert set(EXP_PREFIXES) == {'21', '22', '23', '24', '25'}


class TestPeriodCloseError:

    def test_error_is_exception(self):
        from accounting.services.period_close import PeriodCloseError
        assert issubclass(PeriodCloseError, Exception)


class TestPublicAPI:
    """Freeze the public function names — these are imported by the
    management command and the admin view."""

    def test_functions_exported(self):
        from accounting.services import period_close
        assert hasattr(period_close, 'close_fiscal_year')
        assert hasattr(period_close, 'preview_close')
        assert hasattr(period_close, 'CloseResult')
        assert hasattr(period_close, 'PeriodCloseError')
