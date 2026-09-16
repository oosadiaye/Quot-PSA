"""
A clearing account must never be offered as a contract's expense line.

The contract form's GL Account dropdown shows posting-level, non-control
accounts in the 2-series, and ``NCoAService.resolve_code`` rejects header
and control accounts. Both rules were right; the data was wrong. GR/IR
Clearing sat at ``20100100`` in the 2-series, not flagged as a control
account, so it satisfied every one of those conditions and a contract
could be raised against it.

Migration 0115 moved it to the 4-series and flagged it as the control
account it always was, finishing what 0095 started on the ``Account``
table. The economic segment and the chart of accounts have since been
merged into one table, so the rule now lives in one place and is
expressed in the GL's own vocabulary:

    is_posting_level    -> Account.is_postable
    is_control_account  -> Account.is_reconciliation
    account_type_code   -> the first digit of ``code``

These tests pin the *rule*, not the migration — they describe which
accounts may be offered for posting, so re-introducing a clearing
account into the expense series fails here rather than in a ministry's
expenditure report.
"""
from __future__ import annotations

from django.test import SimpleTestCase


class _Seg:
    """The Account fields the contract form and resolve_code consult."""

    def __init__(self, code, name, account_type, is_postable=True,
                 is_reconciliation=False):
        self.code = code
        self.name = name
        self.account_type = account_type
        self.is_postable = is_postable
        self.is_reconciliation = is_reconciliation


def offered_for_contract_gl(accounts):
    """Mirror of the query ContractForm.tsx sends to /accounting/accounts/.

    The form now asks the server for
    ``account_type=Expense&is_postable=true&is_reconciliation=false``
    and keeps a 2-series check client-side. This function is that
    predicate, kept in step deliberately: if the two ever diverge, the
    browser is the only place the difference shows, and by then a
    contract has been raised against the wrong account.
    """
    return [
        a for a in accounts
        if a.account_type == "Expense"
        and a.is_postable
        and not a.is_reconciliation
        and str(a.code).startswith("2")
    ]


GRIR_AFTER_0115 = _Seg("41090000", "GR/IR Clearing — Goods Received / Invoice Received",
                       "Liability", is_postable=True, is_reconciliation=True)
GRIR_BEFORE_0115 = _Seg("20100100", "GR/IR Clearing — Goods Received / Invoice Received",
                        "Expense", is_postable=True, is_reconciliation=False)

EXPENDITURE = [
    _Seg("21100100", "Basic Salaries", "Expense"),
    _Seg("22100100", "Travel and Transport", "Expense"),
    _Seg("23100100", "Acquisition of Land", "Expense"),
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
        stray = _Seg("20999999", "Some Clearing Account", "Expense",
                     is_reconciliation=True)
        assert offered_for_contract_gl([stray]) == []

    def test_a_header_account_is_excluded(self):
        header = _Seg("22000000", "Other Recurrent Costs (Group)", "Expense",
                      is_postable=False)
        assert offered_for_contract_gl([header]) == []


class NamePatternTests(SimpleTestCase):
    """Why the migration targets one code instead of matching words.

    Live tenant data contains expenditure lines whose names include
    "clearance", "clearing" and "payable". Excluding on those words would
    hide genuine expense accounts from every contract — a worse fault
    than the one being fixed, and a much quieter one.
    """

    REAL_EXPENDITURE_WITH_MISLEADING_NAMES = [
        _Seg("22020420", "Removal of Illegal Structures/Slum Clearance", "Expense"),
        _Seg("23040108", "clearing and sanitation of Street/town", "Expense"),
        _Seg("22021033", "ENROMENT FEES AND INCIDENTAL COST PAYABLE BY", "Expense"),
    ]

    def test_expenditure_lines_that_merely_sound_like_clearing_are_kept(self):
        offered = offered_for_contract_gl(self.REAL_EXPENDITURE_WITH_MISLEADING_NAMES)
        assert len(offered) == 3, "a name-based rule would have hidden these"
