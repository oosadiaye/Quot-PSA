"""
The renumbering rules behind migrations 0116 and 0117.

Both migrations move accounts onto their NCoA family digit. The parts
worth pinning are the ones an obvious implementation gets wrong:

  * ordering — 20100000 is occupied by Accounts Payable and only frees
    once Accounts Payable has moved, so a single sorted pass cannot
    place Purchase Expense;
  * equity — 4xxxxxxx is "Liabilities and Net Assets", and moving an
    equity account by family digit alone drops it into the payables
    band, which is compliant and still wrong to an auditor;
  * allocation — a fallback that increments by one turns a chart into a
    sequence.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m0116 = _load("m0116", "accounting/migrations/0116_ncoa_series_compliance.py")


class ComplianceRuleTests(SimpleTestCase):

    def test_each_family_accepts_its_own_type(self):
        for code, kind in [("10100000", "Income"), ("22100100", "Expense"),
                           ("30100000", "Asset"), ("41090000", "Liability")]:
            assert m0116._is_compliant(code, kind)

    def test_equity_is_compliant_in_the_fourth_family(self):
        assert m0116._is_compliant("43100100", "Equity")

    def test_the_commercial_convention_is_not_compliant(self):
        # 1 Asset / 2 Liability / 5 Expense — what seed_coa.py produced.
        assert not m0116._is_compliant("10100000", "Asset")
        assert not m0116._is_compliant("20100000", "Liability")
        assert not m0116._is_compliant("50100000", "Expense")

    def test_a_fifth_family_does_not_exist(self):
        for kind in ("Income", "Expense", "Asset", "Liability", "Equity"):
            assert not m0116._is_compliant("50000000", kind)


class PreferredCodeTests(SimpleTestCase):

    def test_the_family_digit_moves_and_the_rest_is_kept(self):
        assert m0116._preferred_code("20100000", "Liability", "4") == "40100000"
        assert m0116._preferred_code("50100000", "Expense", "2") == "20100000"

    def test_equity_keeps_the_net_assets_band(self):
        # Not 40100000 — that is the payables band. Net assets live at
        # 43xxxxxx alongside the accumulated fund and the reserves.
        assert m0116._preferred_code("30100000", "Equity", "4").startswith("43")


class AllocationTests(SimpleTestCase):

    def test_a_free_preference_is_used_as_is(self):
        assert m0116._allocate("40100000", "4", set()) == "40100000"

    def test_a_taken_preference_steps_by_a_hundred(self):
        # Sequence numbers make a chart unreadable; 100 keeps the shape.
        assert m0116._allocate("40100000", "4", {"40100000"}) == "40100100"

    def test_it_keeps_stepping_past_a_run_of_taken_codes(self):
        taken = {"40100000", "40100100", "40100200"}
        assert m0116._allocate("40100000", "4", taken) == "40100300"

    def test_allocation_never_leaves_the_family(self):
        out = m0116._allocate("49999900", "4", {"49999900"})
        assert out.startswith("4"), out


class OrderingTests(SimpleTestCase):
    """The collision that a single sorted pass cannot resolve."""

    def test_purchase_expense_can_take_the_code_accounts_payable_vacates(self):
        # Accounts Payable 20100000 -> 40100000 frees 20100000, which is
        # exactly where Purchase Expense 50100000 belongs. Both are
        # movers, so neither blocks the other: only codes held by
        # accounts that stay put are treated as occupied.
        staying = {"20000000"}          # the compliant "Expenditure" group
        ap_target = m0116._allocate(
            m0116._preferred_code("20100000", "Liability", "4"), "4", staying)
        assert ap_target == "40100000"

        staying.add(ap_target)
        pe_target = m0116._allocate(
            m0116._preferred_code("50100000", "Expense", "2"), "2", staying)
        assert pe_target == "20100000", (
            "Purchase Expense should take the code Accounts Payable vacated"
        )
