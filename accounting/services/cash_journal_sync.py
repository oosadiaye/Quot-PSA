"""A cash journal follows its Bank & Cash account.

There is no separate "set up a cash journal" step: the moment a Cash, Petty Cash or Imprest account exists in Bank & Cash it
has a cash journal, named after it, active while it is. Renaming or deactivating the account carries over.

An account that stops being a cash account (changed to Bank) keeps its journal and its history but the journal is
deactivated: documents already posted in it must stay readable and reversible.
"""
from __future__ import annotations

from accounting.models.cash_posting import CASH_ACCOUNT_TYPES, CashJournal

_CODE_MAX = 20


def is_cash_account(account) -> bool:
    return account.account_type in CASH_ACCOUNT_TYPES


def _free_code(account) -> str:
    """The account number if it is free, else ``CJ-<pk>`` (the pk is unique, so this always is)."""
    wanted = (account.account_number or '').strip()[:_CODE_MAX]
    if wanted and not CashJournal.objects.filter(code__iexact=wanted).exists():
        return wanted
    return f'{CashJournal.number_prefix}{account.pk}'[:_CODE_MAX]


def ensure_cash_journal(account) -> CashJournal | None:
    """Create or bring up to date the journal of a bank account; ``None`` for an account that never had one and is not cash."""
    journal = CashJournal.objects.filter(cash_account=account).first()
    if is_cash_account(account):
        if journal is None:
            return CashJournal.objects.create(
                code=_free_code(account), name=account.name[:100], cash_account=account, is_active=account.is_active)
        changes = {}
        if journal.name != account.name[:100]:
            changes['name'] = account.name[:100]
        if journal.is_active != account.is_active:
            changes['is_active'] = account.is_active
        if changes:
            for field, value in changes.items():
                setattr(journal, field, value)
            journal.save(update_fields=list(changes))
        return journal
    if journal is not None and journal.is_active:
        journal.is_active = False                  # no longer a cash account: keep the history, close the desk
        journal.save(update_fields=['is_active'])
    return journal
