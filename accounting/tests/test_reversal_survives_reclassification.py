"""A posted journal stays reversible after its account is re-classified.

IPSAS does not allow deleting a journal; the only remedy for a mistake
is a reversal. That makes reversibility a property the chart of accounts
must never be able to take away.

It could. ``post_journal`` applies the header / posting-level / control
account gates to every journal it posts, and a reversal goes through
``post_journal`` like anything else. So flagging an account as a header
— which migration 0121 does for NCoA group roots such as 20000000
Expenditure — would have stranded every journal that had ever posted to
it: the error could no longer be reversed, only compounded.

The gates describe which account an operator may *choose* today. A
reversal chooses nothing: its lines are copied from the original, whose
choice was legal when it was made. So the classification gates do not
apply to it, while balance, sign and double-entry rules — properties of
the journal itself rather than of the chart — still do.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.services.ipsas_journal_service import (
    IPSASJournalService, JournalPostingError,
)


@pytest.fixture
def posted_journal(db, raw_journal, expense_account, cash_account,
                   open_fiscal_period, maker_user):
    """A balanced, posted journal: DR expense 500 / CR cash 500."""
    journal = raw_journal([
        (expense_account, Decimal('500.00'), Decimal('0.00')),
        (cash_account, Decimal('0.00'), Decimal('500.00')),
    ])
    return IPSASJournalService.post_journal(journal, maker_user)


@pytest.mark.django_db
def test_reversal_succeeds_after_the_account_becomes_a_header(
    posted_journal, expense_account, maker_user,
):
    # The account is re-classified as a group / header account *after*
    # the journal legitimately posted to it — exactly what 0121 does to
    # NCoA group roots.
    expense_account.is_postable = False
    expense_account.save(update_fields=['is_postable'])

    reversal = IPSASJournalService.reverse_journal(
        posted_journal, maker_user, reason='account re-classified',
    )

    assert reversal.status == IPSASJournalService.STATUS_POSTED
    assert reversal.source_module == 'reversal'
    posted_journal.refresh_from_db()
    assert posted_journal.is_reversed is True


@pytest.mark.django_db
def test_the_reversal_actually_unwinds_the_original(
    posted_journal, expense_account, cash_account, maker_user,
):
    """Exempting the gate must not also exempt the arithmetic."""
    expense_account.is_postable = False
    expense_account.save(update_fields=['is_postable'])

    reversal = IPSASJournalService.reverse_journal(
        posted_journal, maker_user, reason='account re-classified',
    )

    by_account = {ln.account_id: ln for ln in reversal.lines.all()}
    assert by_account[expense_account.pk].credit == Decimal('500.00')
    assert by_account[expense_account.pk].debit == Decimal('0.00')
    assert by_account[cash_account.pk].debit == Decimal('500.00')
    assert by_account[cash_account.pk].credit == Decimal('0.00')


@pytest.mark.django_db
def test_a_new_journal_on_the_header_account_is_still_refused(
    db, raw_journal, expense_account, cash_account, open_fiscal_period, maker_user,
):
    """The exemption is for reversals only — the guard itself still bites.

    If this ever passes, the header guard has been disabled for ordinary
    postings too, and the trial-balance invariant "header balance = sum
    of children" is no longer defended.
    """
    expense_account.is_postable = False
    expense_account.save(update_fields=['is_postable'])

    journal = raw_journal([
        (expense_account, Decimal('500.00'), Decimal('0.00')),
        (cash_account, Decimal('0.00'), Decimal('500.00')),
    ])

    with pytest.raises(JournalPostingError) as exc:
        IPSASJournalService.post_journal(journal, maker_user)
    assert 'header / group account' in str(exc.value)


@pytest.mark.django_db
def test_a_reversal_must_still_balance(
    db, raw_journal, expense_account, cash_account, open_fiscal_period, maker_user,
):
    """Balance is a property of the journal, not of the chart.

    Exempting reversals from the *classification* gates must not exempt
    them from double-entry. Constructed directly rather than through
    ``reverse_journal`` (which cannot produce an unbalanced journal) so
    the gate itself is what is under test.
    """
    journal = raw_journal([
        (expense_account, Decimal('500.00'), Decimal('0.00')),
        (cash_account, Decimal('0.00'), Decimal('400.00')),
    ])
    journal.source_module = 'reversal'
    journal.save(update_fields=['source_module'])

    with pytest.raises(JournalPostingError) as exc:
        IPSASJournalService.post_journal(journal, maker_user)
    assert 'not balanced' in str(exc.value)
