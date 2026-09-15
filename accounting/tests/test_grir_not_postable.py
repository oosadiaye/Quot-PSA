"""
A clearing account must never be offered as a contract's expense line.

The contract form's GL Account dropdown shows posting-level, non-control
accounts in the 2-series, and ``NCoAService.resolve_code`` rejects header
and control accounts. Both rules were right; the data was wrong. GR/IR
Clearing sat at ``20100100`` with ``account_type_code '2'`` and
``is_control_account False``, so it satisfied every one of those
conditions and a contract could be raised against it.

Migration 0115 moved it to the 4-series and flagged it as the control
account it always was, finishing for ``EconomicSegment`` what 0095 did
for the legacy ``Account`` table.

These tests pin the *rule*, not the migration — they describe which
segments may be offered for posting, so re-introducing a clearing
account into the expense series fails here rather than in a ministry's
expenditure report.
"""
from __future__ import annotations

from django.test import SimpleTestCase


class _Seg:
    """The fields the contract form and resolve_code actually consult."""

    def __init__(self, code, name, account_type_code, is_posting_level=True,
                 is_control_account=False):
        self.code = code
        self.name = name
        self.account_type_code = account_type_code
        self.is_posting_level = is_posting_level
        self.is_control_account = is_control_account


def offered_for_contract_gl(segments):
    """Mirror of the filter in ContractForm.tsx.

    Kept in step deliberately: if the two ever diverge, the browser is
    the only place the difference shows, and by then a contract has been
    raised against the wrong account.
    """
    return [
        s for s in segments
        if (s.account_type_code == "2" or str(s.code).startswith("2"))
        and s.is_posting_level
        and not s.is_control_account
    ]


GRIR_AFTER_0115 = _Seg("41090000", "GR/IR Clearing — Goods Received / Invoice Received",
                       "4", is_posting_level=True, is_control_account=True)
GRIR_BEFORE_0115 = _Seg("20100100", "GR/IR Clearing — Goods Received / Invoice Received",
                        "2", is_posting_level=True, is_control_account=False)

EXPENDITURE = [
    _Seg("21100100", "Basic Salaries", "2"),
    _Seg("22100100", "Travel and Transport", "2"),
    _Seg("23100100", "Acquisition of Land", "2"),
]


class GrIrExclusionTests(SimpleTestCase):

    def test_grir_is_not_offered_after_the_relocation(self):
        offered = offered_for_contract_gl([GRIR_AFTER_0115, *EXPENDITURE])
        assert all("GR/IR" not in s.name for s in offered)

    def test_the_old_shape_is_exactly_what_slipped_through(self):
        # Documents the bug: every condition was satisfied, which is why
        # neither the dropdown nor resolve_code caught it. If this ever
        # stops being true the fix above has become unnecessary.
        offered = offered_for_contract_gl([GRIR_BEFORE_0115])
        assert len(offered) == 1

    def test_real_expenditure_lines_are_still_offered(self):
        offered = offered_for_contract_gl([GRIR_AFTER_0115, *EXPENDITURE])
        assert {s.code for s in offered} == {"21100100", "22100100", "23100100"}

    def test_a_control_account_in_the_expense_series_is_excluded(self):
        # The flag is the primary guard; the series is defence in depth.
        # A clearing account mis-coded into the 2-series must still be
        # kept out on the strength of the flag alone.
        stray = _Seg("20999999", "Some Clearing Account", "2", is_control_account=True)
        assert offered_for_contract_gl([stray]) == []

    def test_a_header_account_is_excluded(self):
        header = _Seg("22000000", "Other Recurrent Costs (Group)", "2",
                      is_posting_level=False)
        assert offered_for_contract_gl([header]) == []


class NamePatternTests(SimpleTestCase):
    """Why the migration targets one code instead of matching words.

    Live tenant data contains expenditure lines whose names include
    "clearance", "clearing" and "payable". Excluding on those words would
    hide genuine expense accounts from every contract — a worse fault
    than the one being fixed, and a much quieter one.
    """

    REAL_EXPENDITURE_WITH_MISLEADING_NAMES = [
        _Seg("22020420", "Removal of Illegal Structures/Slum Clearance", "2"),
        _Seg("23040108", "clearing and sanitation of Street/town", "2"),
        _Seg("22021033", "ENROMENT FEES AND INCIDENTAL COST PAYABLE BY", "2"),
    ]

    def test_expenditure_lines_that_merely_sound_like_clearing_are_kept(self):
        offered = offered_for_contract_gl(self.REAL_EXPENDITURE_WITH_MISLEADING_NAMES)
        assert len(offered) == 3, "a name-based rule would have hidden these"
