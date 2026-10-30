"""Post, reverse and close a cash journal (Cash Posting, the FBCJ equivalent).

The models and the shape of each document are in ``accounting.models.cash_posting``. The rules that matter, in one place:

* Every cash line carries the ``bank_account`` it belongs to, so the cash book sees exactly this desk's money even when
  several cash accounts share one control GL account.
* Cash cannot be paid out that is not there: a payment is refused when it would take the cash book below its floor, at the
  document's date or today, unless the journal allows a negative balance.
* A closed day is closed: nothing dated on or before the closing date can be posted or reversed.
* A payment to an expense account passes the same appropriation and warrant gates as any other expenditure.
* Reversing posts the mirror of the original journal and puts the cash line back on this desk's book.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

TWO = Decimal('0.01')
ZERO = Decimal('0.00')


class CashPostingError(Exception):
    """A cash document or closing that cannot be accepted; the message is fit to show the cashier."""


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(TWO, rounding=ROUND_HALF_UP)


def _user(user):
    return user if getattr(user, 'pk', None) else None


# -- the cash book ------------------------------------------------------------------------------------------------------
def _lines(cash_account):
    from accounting.models import JournalLine
    return JournalLine.objects.filter(bank_account_id=cash_account.pk, header__status='Posted')


def balance_as_of(cash_account, as_of: Optional[date] = None) -> Decimal:
    """The cash on the book at the END of ``as_of`` (today when omitted): the opening balance plus posted lines up to then."""
    qs = _lines(cash_account)
    if as_of is not None:
        qs = qs.filter(header__posting_date__lte=as_of)
    agg = qs.aggregate(debit=Sum('debit'), credit=Sum('credit'))
    return (cash_account.opening_balance or ZERO) + (agg['debit'] or ZERO) - (agg['credit'] or ZERO)


def movement(cash_account, date_from: date, date_to: date) -> dict:
    """Cash in and out between two dates (inclusive), straight from the posted lines on this desk."""
    agg = _lines(cash_account).filter(header__posting_date__gte=date_from, header__posting_date__lte=date_to).aggregate(
        debit=Sum('debit'), credit=Sum('credit'))
    return {'receipts': agg['debit'] or ZERO, 'payments': agg['credit'] or ZERO}


def pending_drafts(journal, up_to: date) -> dict:
    """The cash in and out of this journal's Draft documents dated on or before ``up_to`` (not yet on the book)."""
    from accounting.models import CashDocument as D
    drafts = D.objects.filter(cash_journal=journal, status=D.DRAFT, posting_date__lte=up_to)
    cash_in = drafts.filter(transaction_type__in=D.RECEIPT_TYPES).aggregate(total=Sum('amount'))['total'] or ZERO
    cash_out = drafts.exclude(transaction_type__in=D.RECEIPT_TYPES).aggregate(total=Sum('amount'))['total'] or ZERO
    return {'receipts': cash_in, 'payments': cash_out}


def cash_book(journal, date_from: date, date_to: date) -> dict:
    """Opening balance, receipts, payments and closing balance for a period, as the cash book shows them."""
    account = journal.cash_account
    opening = balance_as_of(account, date_from - timedelta(days=1))
    flow = movement(account, date_from, date_to)
    closing = opening + flow['receipts'] - flow['payments']
    drafts = pending_drafts(journal, date_to)
    return {
        'opening_balance': opening, 'receipts': flow['receipts'], 'payments': flow['payments'],
        'closing_balance': closing,
        # The balance if every Draft dated up to the To date were posted: what the book will read once the captured documents go through.
        'draft_receipts': drafts['receipts'], 'draft_payments': drafts['payments'],
        'balance_including_drafts': closing + drafts['receipts'] - drafts['payments'],
        'current_balance': balance_as_of(account),
        'last_closed_date': journal.last_closed_date,
    }


def replenishment(journal, as_of: Optional[date] = None) -> dict:
    """How much brings an imprest fund back to its float, as at ``as_of`` (today when omitted). ``amount`` is 0 for a desk with no float
    or one already full."""
    balance = balance_as_of(journal.cash_account, as_of)
    float_amount = journal.float_amount or ZERO
    amount = max(float_amount - balance, ZERO) if float_amount > 0 else ZERO
    return {'float_amount': float_amount, 'balance': balance, 'amount': amount}


# -- numbering ----------------------------------------------------------------------------------------------------------
def assign_number(doc):
    from accounting.models import TransactionSequence
    if not doc.document_number:
        doc.document_number = TransactionSequence.get_next('cash_document', doc.cash_journal.number_prefix)
    return doc


# -- validation ---------------------------------------------------------------------------------------------------------
def _check_journal(journal):
    from accounting.models.cash_posting import CASH_ACCOUNT_TYPES
    account = journal.cash_account
    if not journal.is_active:
        raise CashPostingError(f'Cash journal "{journal.name}" is not active.')
    if not account.is_active:
        raise CashPostingError(f'The cash account "{account.name}" is inactive.')
    if not account.gl_account_id:
        raise CashPostingError(f'The cash account "{account.name}" is not linked to a GL account.')
    if account.account_type not in CASH_ACCOUNT_TYPES:
        raise CashPostingError(f'"{account.name}" is a {account.account_type or "bank"} account, not a cash account.')


def _check_open_day(journal, when: date, what: str):
    if journal.last_closed_date and when <= journal.last_closed_date:
        raise CashPostingError(
            f'{journal.name} was closed on {journal.last_closed_date:%d/%m/%Y}: {what} dated {when:%d/%m/%Y} cannot be '
            f'posted into a closed day.')


def _check_gl_account(account, journal, where=''):
    """The rules for a GL account a cash document debits or credits: postable, not the cash itself, not a control account."""
    if not (account.is_active and account.is_postable):
        raise CashPostingError(f'{where}GL account {account.code} is not an active, postable account.')
    if account.pk == journal.cash_account.gl_account_id:
        raise CashPostingError(f'{where}The GL account cannot be the cash account itself.')
    if getattr(account, 'is_reconciliation', False):
        raise CashPostingError(
            f'{where}GL account {account.code} is a control account. Pay suppliers through Outgoing Payments, '
            f'which post to the sub-ledger.')


def validate_document(doc):
    """Everything about a Draft that can be checked before posting. Raises ``CashPostingError`` in words."""
    from accounting.models import CashDocument as D
    journal = doc.cash_journal
    _check_journal(journal)
    if doc.amount is None or _money(doc.amount) <= 0:
        raise CashPostingError('The amount must be greater than zero.')

    kind = doc.transaction_type
    if kind == D.EXPENSE and doc.pk and doc.lines.exists():
        lines = list(doc.lines.select_related('account'))
        for number, item in enumerate(lines, start=1):
            _check_gl_account(item.account, journal, where=f'Line {number}: ')
        if _money(sum((i.amount for i in lines), ZERO)) != _money(doc.amount):
            raise CashPostingError('The line items do not add up to the document amount. Open the document and save it again.')
    elif kind in (D.EXPENSE, D.REVENUE):
        if doc.offset_account is None:
            raise CashPostingError('Choose the GL account for this cash document.')
        _check_gl_account(doc.offset_account, journal)
    elif kind in (D.BANK_WITHDRAWAL, D.BANK_DEPOSIT):
        bank = doc.bank_account
        if bank is None:
            raise CashPostingError('Choose the bank account for this cash document.')
        if bank.pk == journal.cash_account_id:
            raise CashPostingError('Choose a different account from the cash account itself.')
        if not bank.is_active or not bank.gl_account_id:
            raise CashPostingError(f'The bank account "{bank.name}" is inactive or has no GL account.')
    else:
        raise CashPostingError(f'Unknown cash transaction "{kind}".')


def first_date_with_cash(cash_account, after: date, amount: Decimal, floor: Decimal = ZERO) -> Optional[date]:
    """The first date after ``after`` on which the cash book holds at least ``amount`` (end of that day), or ``None``."""
    days = (_lines(cash_account).filter(header__posting_date__gt=after)
            .values_list('header__posting_date', flat=True).distinct().order_by('header__posting_date'))
    for day in days:
        if balance_as_of(cash_account, day) - amount >= floor:
            return day
    return None


def _funds_check(journal, doc):
    """A payment may not take the book below its floor (at its own date, or now): zero, or minus the overdraft limit when the
    journal allows an overdraft; no floor at all when the overdraft has no limit."""
    floor = journal.lowest_balance()
    if doc.is_receipt or floor is None:
        return
    for label, when in (('on that date', doc.posting_date), ('now', None)):
        held = balance_as_of(journal.cash_account, when)
        if held - doc.amount < floor:
            message = (f'{journal.name} holds {held:,.2f} {label}, less than the {doc.amount:,.2f} to pay out. '
                       f'Replenish the cash first, or allow a negative balance on the journal.')
            if when is not None:
                # The usual cause: the payment is dated BEFORE the cash came in, so today's balance looks fine but the book
                # was empty on the payment's own date. Say when the cash was there.
                available = first_date_with_cash(journal.cash_account, doc.posting_date, doc.amount, floor)
                if available is not None:
                    message += (f' The cash is available from {available:%d/%m/%Y}: date this payment on or after then, '
                                f'or re-date the receipt that brought the cash in if it arrived earlier.')
            raise CashPostingError(message)


def _budget_gates(doc, items):
    """Appropriation and warrant gates for the expense lines of a cash payment, the same as any other expenditure.

    The shared ``budget_enforcement`` signal gates every debit whose GL sits in a budget-check range; the journal is flagged
    ``_budget_checked`` after this runs so a payment that is not an expense is not over-gated.
    """
    from accounting.budget_logic import check_warrant_availability, warrant_enforcement_enabled
    from accounting.services.budget_check_rules import check_policy, find_matching_appropriation

    warrant_on = warrant_enforcement_enabled()
    fiscal_year = doc.posting_date.year
    for item in items:
        if not (item['debit'] > 0 and item['account'].account_type == 'Expense'):
            continue
        appropriation = find_matching_appropriation(mda=doc.mda, fund=doc.fund, account=item['account'], fiscal_year=fiscal_year)
        policy = check_policy(account_code=item['account'].code, appropriation=appropriation, requested_amount=item['debit'],
                              transaction_label='payment', account_name=item['account'].name)
        if policy.blocked:
            raise CashPostingError(policy.reason)
        if warrant_on and doc.mda_id is not None:
            allowed, message, _info = check_warrant_availability(
                dimensions={'mda': doc.mda, 'fund': doc.fund}, account=item['account'], amount=item['debit'])
            if not allowed:
                raise CashPostingError(message or 'No warrant (AIE) is available for this expense.')


# -- posting ------------------------------------------------------------------------------------------------------------
def recipient_suffix(doc) -> str:
    """``' - Received by <name>'``, or nothing when the cashier named no recipient."""
    name = (doc.recipient or '').strip()
    return f' - Received by {name}' if name else ''


def gl_lines_for(doc) -> list:
    """The journal lines a cash document makes, as plain dicts.

    One place builds them, so what the View screen previews for a Draft is exactly what posting writes.
    """
    from accounting.models import CashDocument as D
    journal = doc.cash_journal
    cash = journal.cash_account
    text = doc.description or doc.get_transaction_type_display()
    amount = _money(doc.amount)
    memo = f'{doc.document_number}: {text}{recipient_suffix(doc)}'
    lines = []

    def line(account, *, debit=ZERO, credit=ZERO, memo, bank=None):
        lines.append({'account': account, 'debit': debit, 'credit': credit, 'memo': memo[:255], 'bank': bank})

    if doc.transaction_type == D.EXPENSE:
        items = list(doc.lines.select_related('account')) if doc.pk else []
        for item in items:
            detail = f'{memo} - {item.description}' if item.description else memo
            line(item.account, debit=_money(item.amount), memo=detail)
        if not items:
            line(doc.offset_account, debit=amount, memo=memo)
        line(cash.gl_account, credit=amount, memo=memo, bank=cash)
    elif doc.transaction_type == D.REVENUE:
        line(cash.gl_account, debit=amount, memo=memo, bank=cash)
        line(doc.offset_account, credit=amount, memo=memo)
    elif doc.transaction_type == D.BANK_WITHDRAWAL:
        line(cash.gl_account, debit=amount, memo=f'{memo} (from {doc.bank_account.name})', bank=cash)
        line(doc.bank_account.gl_account, credit=amount, memo=f'{memo} (to {journal.name})', bank=doc.bank_account)
    elif doc.transaction_type == D.BANK_DEPOSIT:
        line(doc.bank_account.gl_account, debit=amount, memo=f'{memo} (from {journal.name})', bank=doc.bank_account)
        line(cash.gl_account, credit=amount, memo=f'{memo} (to {doc.bank_account.name})', bank=cash)
    return lines


def _post_journal(*, reference, source_id, posting_date, description, items, dims, user, budget_checked):
    """Create and post ONE balanced journal from ``items`` (dicts as in ``gl_lines_for``)."""
    from accounting.models import JournalHeader, JournalLine, TransactionSequence
    from accounting.services.base_posting import BasePostingService

    BasePostingService._check_duplicate_posting(reference)
    header = JournalHeader.objects.create(
        reference_number=reference, description=description[:255], posting_date=posting_date, status='Draft',
        source_module='cash_posting', source_document_id=source_id, posted_by=_user(user), posted_at=timezone.now(),
        **dims,
    )
    header.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
    header.save(update_fields=['document_number'], _allow_status_change=True)
    if budget_checked:
        # The expense gates already ran; the safety-net signal must not re-evaluate and over-gate the cash leg.
        header._budget_checked = True
    for item in items:
        JournalLine.objects.create(header=header, account=item['account'], debit=item['debit'], credit=item['credit'],
                                   memo=item['memo'], bank_account=item['bank'])
    BasePostingService._validate_journal_balanced(header)
    BasePostingService._update_gl_balances(header)   # runs the budget signal, flips the header to Posted
    return header


def _move_balance(bank_account_id, delta):
    from accounting.models import BankAccount
    BankAccount.objects.filter(pk=bank_account_id).update(current_balance=F('current_balance') + delta, updated_at=timezone.now())


def _dims(doc) -> dict:
    return {name: getattr(doc, name) for name in ('mda', 'fund', 'function', 'program', 'geo')}


@transaction.atomic
def post_document(doc, *, user=None):
    """Post a Draft cash document and return it."""
    from accounting.models import BankAccount, CashDocument as D, CashJournal
    from accounting.services.base_posting import BasePostingService

    doc = D.objects.select_for_update(of=('self',)).select_related('cash_journal__cash_account', 'bank_account').get(pk=doc.pk)
    if doc.status != D.DRAFT:
        raise CashPostingError(f'{doc.document_number} is {doc.status}; only a Draft can be posted.')
    journal = CashJournal.objects.select_for_update(of=('self',)).select_related('cash_account').get(pk=doc.cash_journal_id)
    list(BankAccount.objects.select_for_update().filter(
        pk__in=[journal.cash_account_id] + ([doc.bank_account_id] if doc.bank_account_id else [])).order_by('pk'))
    doc.cash_journal = journal
    validate_document(doc)
    _check_open_day(journal, doc.posting_date, 'a document')
    try:
        BasePostingService._validate_fiscal_period(doc.posting_date, user=_user(user))
    except Exception as exc:  # noqa: BLE001 - PeriodClosedError and friends carry a sentence for the user
        raise CashPostingError(str(exc))
    _funds_check(journal, doc)

    items = gl_lines_for(doc)
    expense = doc.transaction_type == D.EXPENSE
    if expense:
        _budget_gates(doc, items)
    text = doc.description or doc.get_transaction_type_display()
    try:
        header = _post_journal(
            reference=doc.document_number, source_id=doc.pk, posting_date=doc.posting_date,
            description=f'Cash journal {journal.code} {doc.document_number}: {text}{recipient_suffix(doc)}',
            items=items, dims=_dims(doc), user=user, budget_checked=expense)
    except ValidationError as exc:
        raise CashPostingError(' '.join(getattr(exc, 'messages', None) or [str(exc)]))

    _move_balance(journal.cash_account_id, doc.signed_amount)
    if doc.bank_account_id:
        _move_balance(doc.bank_account_id, -doc.signed_amount)
    doc.journal_entry = header
    doc.status = D.POSTED
    doc.posted_at = timezone.now()
    doc.posted_by = _user(user)
    doc.save()
    return doc


@transaction.atomic
def reverse_document(doc, *, user=None, reason: str = ''):
    """Reverse a posted cash document: post the mirror journal and put its lines back on the right desk's book."""
    from accounting.models import CashDocument as D, JournalLine
    from accounting.services.ipsas_journal_service import IPSASJournalService, JournalPostingError

    doc = D.objects.select_for_update(of=('self',)).select_related('cash_journal__cash_account', 'journal_entry', 'bank_account').get(pk=doc.pk)
    if doc.status != D.POSTED or doc.journal_entry_id is None:
        raise CashPostingError(f'{doc.document_number} is {doc.status}; only a posted document can be reversed.')
    journal = doc.cash_journal
    when = timezone.now().date()
    _check_open_day(journal, when, 'a reversal')
    if journal.last_closed_date and doc.posting_date <= journal.last_closed_date:
        raise CashPostingError(
            f'{doc.document_number} is in a day closed on {journal.last_closed_date:%d/%m/%Y}; it cannot be reversed. '
            f'Post a correcting cash document instead.')
    floor = journal.lowest_balance()
    if doc.is_receipt and floor is not None:
        # Reversing money received takes that cash out again (reversing a payment puts cash back, so needs no check).
        held = balance_as_of(journal.cash_account)
        if held - doc.amount < floor:
            raise CashPostingError(f'{journal.name} holds {held:,.2f}, less than the {doc.amount:,.2f} this reversal takes back out.')

    original = doc.journal_entry
    try:
        reversal = IPSASJournalService.reverse_journal(
            original, user, (reason or f'Cash document {doc.document_number} reversed').strip())
    except (JournalPostingError, ValidationError) as exc:
        raise CashPostingError(' '.join(getattr(exc, 'messages', None) or [str(exc)]) or 'The journal could not be reversed.')

    # The central reversal swaps debit and credit but does not copy which cash / bank account a line belongs to; without
    # that the cash book would not move. Put each line back on the account it was on.
    attribution = {}
    for line in original.lines.all():
        if line.bank_account_id:
            attribution.setdefault(line.account_id, line.bank_account_id)
    for account_id, bank_id in attribution.items():
        JournalLine.objects.filter(header=reversal, account_id=account_id, bank_account__isnull=True).update(bank_account_id=bank_id)

    _move_balance(journal.cash_account_id, -doc.signed_amount)
    if doc.bank_account_id:
        _move_balance(doc.bank_account_id, doc.signed_amount)
    doc.status = D.REVERSED
    doc.reversal_journal = reversal
    doc.reversed_by = _user(user)
    doc.reversed_at = timezone.now()
    doc.save(update_fields=['status', 'reversal_journal', 'reversed_by', 'reversed_at', 'updated_at'])
    return reversal


# -- the day-end count --------------------------------------------------------------------------------------------------
@transaction.atomic
def close_journal(journal, *, closing_date: date, counted_amount, user=None, note: str = ''):
    """Count the cash for ``closing_date``: compare with the book, post any difference, and close the day."""
    from accounting.models import BankAccount, CashClosing, CashDocument as D, CashJournal
    from accounting.services.base_posting import BasePostingService

    journal = CashJournal.objects.select_for_update(of=('self',)).select_related('cash_account', 'difference_account').get(pk=journal.pk)
    _check_journal(journal)
    list(BankAccount.objects.select_for_update().filter(pk=journal.cash_account_id))
    if closing_date > timezone.now().date():
        raise CashPostingError('A day cannot be closed before it has happened.')
    if journal.last_closed_date and closing_date <= journal.last_closed_date:
        raise CashPostingError(f'{journal.name} is already closed up to {journal.last_closed_date:%d/%m/%Y}.')
    counted = _money(counted_amount)
    if counted < 0:
        raise CashPostingError('The counted cash cannot be negative.')
    open_drafts = D.objects.filter(cash_journal=journal, status=D.DRAFT, posting_date__lte=closing_date).count()
    if open_drafts:
        raise CashPostingError(
            f'{open_drafts} cash document(s) dated on or before {closing_date:%d/%m/%Y} are still Drafts. '
            f'Post or delete them before closing.')

    book = balance_as_of(journal.cash_account, closing_date)
    difference = counted - book
    difference_journal = None
    if difference != 0:
        if journal.difference_account_id is None:
            raise CashPostingError(
                f'The count is {abs(difference):,.2f} {"short" if difference < 0 else "over"}. Set a cash difference '
                f'account on the journal so it can be posted, or recount.')
        BasePostingService._validate_fiscal_period(closing_date, user=_user(user))
        shortage = difference < 0
        amount = abs(difference)
        memo = f'Cash {"short" if shortage else "over"} at close {closing_date:%d/%m/%Y}'
        cash, other = journal.cash_account, journal.difference_account
        items = [
            {'account': other if shortage else cash.gl_account, 'debit': amount, 'credit': ZERO, 'memo': memo,
             'bank': None if shortage else cash},
            {'account': cash.gl_account if shortage else other, 'debit': ZERO, 'credit': amount, 'memo': memo,
             'bank': cash if shortage else None},
        ]
        difference_journal = _post_journal(
            reference=f'{journal.code}-DIFF-{closing_date:%Y%m%d}', source_id=journal.pk, posting_date=closing_date,
            description=f'Cash count difference {journal.code} {closing_date:%d/%m/%Y}: {"short" if shortage else "over"} {amount:,.2f}',
            items=items, dims={'mda': journal.mda}, user=user, budget_checked=True)
        _move_balance(cash.pk, difference)

    closing = CashClosing.objects.create(
        cash_journal=journal, closing_date=closing_date, book_balance=book, counted_amount=counted, difference=difference,
        difference_journal=difference_journal, note=(note or '')[:255], created_by=_user(user))
    journal.last_closed_date = closing_date
    journal.save(update_fields=['last_closed_date', 'updated_at'])
    return closing
