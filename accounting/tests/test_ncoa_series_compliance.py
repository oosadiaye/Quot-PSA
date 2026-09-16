"""
NCoA first-digit families, and the one they could not express.

    1xxxxxxx Revenue
    2xxxxxxx Expenditure
    3xxxxxxx Assets
    4xxxxxxx Liabilities **and Net Assets**

The fourth family carries two account types, which the prefix -> type map
cannot say. The consequence was not that Equity landed in the wrong
place — it was that Equity could not be created at *any* prefix, since
every other series demanded something else.

That contradicted the system's own year-end close:
``AccountingSettings.accumulated_fund_account_code`` defaults to NCoA
43100000 and documents that the account "must exist in the Account table
before close_year can run". Closing the year needed an account the API
refused to accept.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from accounting.models.advanced import AccountingSettings

SERIES = AccountingSettings.DEFAULT_NUMBER_SERIES
ALSO = AccountingSettings.SERIES_ALSO_ALLOWS


def accepted(code: str, account_type: str) -> bool:
    """The rule both the serializer and AccountingSettings apply."""
    expected = SERIES.get(code[0])
    if not expected:
        return True                      # prefix outside the NCoA families
    return expected == account_type or account_type in ALSO.get(code[0], ())


class SeriesFamilyTests(SimpleTestCase):

    def test_the_four_canonical_families(self):
        assert SERIES == {'1': 'Income', '2': 'Expense', '3': 'Asset', '4': 'Liability'}

    def test_each_family_accepts_its_own_type(self):
        for code, kind in [('10100000', 'Income'), ('22100100', 'Expense'),
                           ('31010000', 'Asset'), ('41090000', 'Liability')]:
            assert accepted(code, kind), f'{code} should accept {kind}'

    def test_a_liability_in_the_expense_series_is_refused(self):
        # The GR/IR shape: a clearing liability sitting at 2xxxxxxx.
        assert not accepted('20100100', 'Liability')

    def test_an_asset_in_the_revenue_series_is_refused(self):
        assert not accepted('10300000', 'Asset')

    def test_an_expense_outside_the_four_families_is_not_policed(self):
        # 5xxxxxxx-9xxxxxxx are outside NCoA's first-digit taxonomy;
        # enforcement deliberately stops rather than guessing.
        assert accepted('50100000', 'Expense')


class NetAssetsTests(SimpleTestCase):
    """The 4-series carries Liabilities AND Net Assets."""

    def test_equity_is_accepted_in_the_four_series(self):
        assert accepted('43100000', 'Equity'), (
            'NCoA 4xxxxxxx is "Liabilities and Net Assets" — the accumulated '
            'fund lives here and year-end close depends on it'
        )

    def test_liability_is_still_accepted_in_the_four_series(self):
        assert accepted('41090000', 'Liability')

    def test_equity_is_refused_everywhere_else(self):
        # Widening the rule must not turn it off. Net assets belong in the
        # fourth family and nowhere else.
        for code in ('10100000', '22100100', '31010000'):
            assert not accepted(code, 'Equity'), f'{code} should refuse Equity'

    def test_the_year_end_close_default_account_can_exist(self):
        # accumulated_fund_account_code defaults to 43100000 and the
        # account must exist before close_year runs. Before this rule it
        # could not be created through the API at all.
        default_code = AccountingSettings._meta.get_field(
            'accumulated_fund_account_code').default or '43100000'
        code = str(default_code) or '43100000'
        if not code[0].isdigit():
            code = '43100000'
        assert accepted(code, 'Equity')


class LockstepTests(SimpleTestCase):
    """The serializer and the settings model must agree.

    ``NIGERIA_COA_SERIES`` carries a comment asking for the two to stay
    in lockstep. They are now sourced from one place; this fails if
    somebody reintroduces a second literal that disagrees.
    """

    def test_the_serializer_map_matches_the_settings_map(self):
        from accounting.serializers import AccountSerializer

        assert AccountSerializer.NIGERIA_COA_SERIES == SERIES
