"""
debt.gl — the debt module on the general ledger, the chart of accounts and the bank accounts.

How a public loan or bond reaches the books (IPSAS 28/29 presentation, accrual basis):

    drawdown                 Dr  Bank account (its GL)          Cr  Non-current liability (long-term borrowings)
    reclassify, at a date    Dr  Non-current liability         Cr  Current portion of long-term borrowings
                             (principal due within 12 months moves to current liabilities; Financial Position
                              reads NCoA 41xx as current and 42xx as non-current, so the statement follows)
    pay a coupon             Dr  Current portion (then non-current, for any principal not yet reclassified)
                             Dr  Interest expense, Dr Fee expense
                                                               Cr  Bank account (its GL)

Principal repayment reduces the liability; it is never an expense. Only interest and fees are expenses, and so they are
the only legs that meet the appropriation gate.

Each instrument carries its own account mapping. "Use standard accounts" fills it from the NCoA chart (42100100 bonds,
42100200 domestic loans, 42200100 foreign loans, 41400100 current portion, 24100100 interest). An instrument with no
mapping keeps the older behaviour (see ``DebtServiceGLService.pay_coupon``).
"""
from __future__ import annotations

from collections import namedtuple
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from accounting.models import Account, BankAccount, JournalHeader, JournalLine
from accounting.services.base_posting import TransactionPostingError
from accounting.services.ipsas_journal_service import IPSASJournalService

ZERO = Decimal("0.00")
TWO = Decimal("0.01")

BOND_CODE = "42100100"
DOMESTIC_LOAN_CODE = "42100200"
FOREIGN_LOAN_CODE = "42200100"
CURRENT_PORTION_CODE = "41400100"
CURRENT_PORTION_NAME = "Current Portion of Long-Term Borrowings"
INTEREST_CODE = "24100100"
CURRENT_LIABILITIES_PARENT = "41000000"

Accounts = namedtuple("Accounts", "liability current_portion interest fee")


class DebtGLConfigError(TransactionPostingError):
    """The instrument's accounts or bank account are not set up; the message says what to do."""


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(TWO)


def _active(account: Optional[Account], what: str, instrument) -> Account:
    if account is None:
        raise DebtGLConfigError(
            f"{instrument.instrument_number}: no {what} account is set. Use \"Use standard accounts\" or choose one in the "
            f"instrument's GL mapping.")
    if not account.is_active or not account.is_postable:
        raise DebtGLConfigError(f"{instrument.instrument_number}: the {what} account {account.code} is not an active, postable account.")
    return account


def resolve_accounts(instrument, *, need_expense: bool = True) -> Accounts:
    """The four accounts of an instrument, validated. Fee expense falls back to interest expense."""
    liability = _active(instrument.liability_account, "non-current liability", instrument)
    current = _active(instrument.current_portion_account, "current-portion liability", instrument)
    if liability.account_type != "Liability" or current.account_type != "Liability":
        raise DebtGLConfigError(f"{instrument.instrument_number}: the liability accounts must be Liability accounts.")
    interest = fee = None
    if need_expense:
        interest = _active(instrument.interest_expense_account, "interest expense", instrument)
        fee = instrument.fee_expense_account or interest
        _active(fee, "fee expense", instrument)
    return Accounts(liability, current, interest, fee)


def _bank(bank: Optional[BankAccount], instrument) -> BankAccount:
    bank = bank or instrument.bank_account
    if bank is None:
        raise DebtGLConfigError(f"{instrument.instrument_number}: choose the bank account for this transaction.")
    if not bank.is_active or not bank.gl_account_id:
        raise DebtGLConfigError(f"The bank account \"{bank.name}\" is inactive or has no GL account.")
    return bank


def _move_bank(bank_id: int, delta: Decimal) -> None:
    BankAccount.objects.filter(pk=bank_id).update(current_balance=F("current_balance") + delta, updated_at=timezone.now())


def _post(reference: str, description: str, posting_date: date, source: tuple, lines: list, actor) -> JournalHeader:
    """One balanced journal through the canonical posting pipeline (period gate, balance check, GL balances, audit).

    ``source`` is (module, document id): the ledger allows one posted journal per source document, so a drawdown, a
    reclassification and a coupon payment each name their own record rather than sharing the instrument.
    """
    journal = JournalHeader.objects.create(
        posting_date=posting_date, reference_number=reference[:50], description=description[:255], status="Draft",
        source_module=source[0], source_document_id=source[1], posted_by=actor if getattr(actor, "pk", None) else None,
    )
    for account, debit, credit, memo in lines:
        JournalLine.objects.create(header=journal, account=account, debit=debit, credit=credit, memo=memo[:255])
    IPSASJournalService.post_journal(journal, actor)
    return journal


# -- the standard accounts ------------------------------------------------------------------------------------------
def _account(code: str) -> Optional[Account]:
    return Account.objects.filter(code=code, is_active=True).first()


def _ensure_economic_segment(account: Account, parent_code: str) -> None:
    """Give a new liability account its NCoA economic segment.

    The Statement of Financial Position is built from NCoA economic segments (41xx current, 42xx non-current) bridged to GL
    accounts, so an account without a segment would post correctly yet never appear on the statement.
    """
    try:
        from accounting.models import EconomicSegment
    except ImportError:          # a ledger where the account itself is the economic classifier
        return
    segment = EconomicSegment.objects.filter(code=account.code).first()
    if segment is not None:
        if segment.legacy_account_id is None:
            segment.legacy_account = account
            segment.save(update_fields=["legacy_account", "updated_at"])
        return
    parent = EconomicSegment.objects.filter(code=parent_code).first()
    EconomicSegment.objects.create(
        code=account.code, name=account.name, account_type_code=account.code[:1], parent=parent, is_active=True,
        is_posting_level=True, normal_balance="CREDIT", legacy_account=account, legacy_account_type="Liability",
    )


@transaction.atomic
def apply_standard_accounts(instrument) -> dict:
    """Fill the instrument's mapping from the chart of accounts, creating the current-portion account when the chart has none."""
    if instrument.instrument_type == "bond":
        liability_code = BOND_CODE
    elif instrument.currency_id and not getattr(instrument.currency, "is_base_currency", True):
        liability_code = FOREIGN_LOAN_CODE
    else:
        liability_code = DOMESTIC_LOAN_CODE
    liability = _account(liability_code)
    interest = _account(INTEREST_CODE)
    missing = [c for c, a in ((liability_code, liability), (INTEREST_CODE, interest)) if a is None]
    if missing:
        raise DebtGLConfigError(
            f"The chart of accounts has no account {', '.join(missing)}. Add it, or choose the accounts by hand.")
    current = Account.objects.filter(code=CURRENT_PORTION_CODE).first()
    if current is None:
        parent = Account.objects.filter(code=CURRENT_LIABILITIES_PARENT).first()
        current = Account.objects.create(
            code=CURRENT_PORTION_CODE, name=CURRENT_PORTION_NAME, account_type="Liability", parent=parent, is_active=True,
        )
    _ensure_economic_segment(current, CURRENT_LIABILITIES_PARENT)
    instrument.liability_account = liability
    instrument.current_portion_account = current
    instrument.interest_expense_account = interest
    instrument.fee_expense_account = interest
    instrument.save(update_fields=["liability_account", "current_portion_account", "interest_expense_account",
                                   "fee_expense_account", "updated_at"])
    return {"liability": liability.code, "current_portion": current.code, "interest": interest.code}


# -- drawdown --------------------------------------------------------------------------------------------------------
@transaction.atomic
def record_drawdown(instrument, *, amount, bank_account=None, drawdown_date: Optional[date] = None, actor=None,
                    reference: str = ""):
    """Money received against the facility: Dr Bank / Cr Non-current liability."""
    from .models import DebtDrawdown, DebtInstrument

    instrument = DebtInstrument.objects.select_for_update(of=("self",)).select_related(
        "liability_account", "current_portion_account", "bank_account").get(pk=instrument.pk)
    amount = _money(amount)
    if amount <= ZERO:
        raise DebtGLConfigError("The drawdown amount must be greater than zero.")
    if instrument.status == "closed":
        raise DebtGLConfigError(f"{instrument.instrument_number} is closed.")
    accounts = resolve_accounts(instrument, need_expense=False)
    bank = _bank(bank_account, instrument)
    already = _money(instrument.drawn_amount)
    if already + amount > _money(instrument.principal_amount):
        raise DebtGLConfigError(
            f"{instrument.instrument_number}: this drawdown would take the amount drawn to {already + amount:,.2f}, above the "
            f"facility of {_money(instrument.principal_amount):,.2f}.")
    when = drawdown_date or timezone.now().date()
    ref = reference or f"DD-{instrument.instrument_number}-{instrument.drawdowns.count() + 1:03d}"
    drawdown = DebtDrawdown.objects.create(
        instrument=instrument, drawdown_date=when, amount=amount, bank_account=bank, reference=ref,
        created_by=actor if getattr(actor, "pk", None) else None)
    drawdown.journal = _post(ref, f"Debt drawdown - {instrument.instrument_number} ({instrument.creditor})", when,
                             ("debt_drawdown", drawdown.pk), [
        (bank.gl_account, amount, ZERO, f"Loan proceeds {ref}"),
        (accounts.liability, ZERO, amount, f"Long-term borrowing {ref}"),
    ], actor)
    drawdown.save(update_fields=["journal", "updated_at"])
    _move_bank(bank.pk, amount)
    if instrument.status == "draft":
        instrument.status = "active"
        instrument.save(update_fields=["status", "updated_at"])
    return drawdown


# -- current / non-current ----------------------------------------------------------------------------------------------
def _principal_due(instrument, as_of: date) -> Decimal:
    """Principal of unpaid coupons falling due on or before ``as_of`` plus twelve months."""
    from .models import AmortisationCoupon

    horizon = as_of.replace(year=as_of.year + 1) if not (as_of.month == 2 and as_of.day == 29) else as_of + timedelta(days=365)
    total = AmortisationCoupon.objects.filter(
        schedule__instrument=instrument, schedule__coupon_date__lte=horizon,
    ).exclude(status__in=["paid", "closed"]).aggregate(t=Sum("principal_amount"))["t"]
    return _money(total)


def position(instrument, as_of: Optional[date] = None) -> dict:
    """Where the instrument stands: owed, split current / non-current, and what a reclassification would move."""
    as_of = as_of or timezone.now().date()
    outstanding = _money(instrument.outstanding_principal)
    due = _principal_due(instrument, as_of)
    target = min(due, outstanding) if outstanding > ZERO else ZERO
    booked = _money(instrument.current_portion_booked)
    return {
        "as_of": as_of, "facility": _money(instrument.principal_amount), "drawn": _money(instrument.drawn_amount),
        "principal_repaid": _money(instrument.principal_repaid), "outstanding_principal": outstanding,
        "current_portion": booked, "non_current_portion": outstanding - booked,
        "due_within_12_months": due, "suggested_current_portion": target, "reclassification_needed": target - booked,
    }


@transaction.atomic
def reclassify_current_portion(instrument, *, as_of: Optional[date] = None, actor=None):
    """Move the principal due within twelve months from non-current to current liabilities (or back, if less is now due)."""
    from .models import DebtClassification, DebtInstrument

    instrument = DebtInstrument.objects.select_for_update(of=("self",)).select_related(
        "liability_account", "current_portion_account").get(pk=instrument.pk)
    as_of = as_of or timezone.now().date()
    if DebtClassification.objects.filter(instrument=instrument, as_of=as_of).exists():
        raise DebtGLConfigError(f"{instrument.instrument_number} was already classified at {as_of:%d/%m/%Y}.")
    accounts = resolve_accounts(instrument, need_expense=False)
    pos = position(instrument, as_of)
    target, delta = pos["suggested_current_portion"], pos["reclassification_needed"]
    row = DebtClassification.objects.create(
        instrument=instrument, as_of=as_of, current_portion=target, adjustment=delta,
        created_by=actor if getattr(actor, "pk", None) else None)
    if delta != ZERO:
        amount = abs(delta)
        ref = f"CL-{instrument.instrument_number}-{as_of:%Y%m%d}"
        if delta > ZERO:
            lines = [(accounts.liability, amount, ZERO, f"Reclassify to current {ref}"),
                     (accounts.current_portion, ZERO, amount, f"Current portion {ref}")]
        else:
            lines = [(accounts.current_portion, amount, ZERO, f"Reclassify to non-current {ref}"),
                     (accounts.liability, ZERO, amount, f"Non-current {ref}")]
        row.journal = _post(ref, f"Current portion of long-term debt - {instrument.instrument_number}", as_of,
                            ("debt_reclass", row.pk), lines, actor)
        row.save(update_fields=["journal", "updated_at"])
        instrument.current_portion_booked = target
        instrument.save(update_fields=["current_portion_booked", "updated_at"])
    return row


# -- paying a coupon ----------------------------------------------------------------------------------------------------
@transaction.atomic
def pay_coupon_from_bank(*, coupon, actor, bank_account=None, warrant=None, paid_date: Optional[date] = None,
                         description: str = "") -> JournalHeader:
    """Pay a coupon out of a bank account: principal reduces the liability, interest and fees are expense."""
    from .models import AmortisationCoupon, AmortisationLedger, DebtInstrument
    from .services import DebtServiceGLService

    coupon = AmortisationCoupon.objects.select_for_update(of=("self",)).select_related("schedule__instrument").get(pk=coupon.pk)
    instrument = DebtInstrument.objects.select_for_update(of=("self",)).select_related(
        "liability_account", "current_portion_account", "interest_expense_account", "fee_expense_account", "bank_account",
    ).get(pk=coupon.schedule.instrument_id)
    if coupon.status == "paid" or AmortisationLedger.objects.filter(coupon=coupon, event="paid").exists():
        raise TransactionPostingError(f"Amortisation coupon {coupon.pk} is already paid.")
    principal, interest, fees = _money(coupon.principal_amount), _money(coupon.interest_amount), _money(coupon.commitment_fee)
    total = principal + interest + fees
    if total <= ZERO:
        raise TransactionPostingError(f"Amortisation coupon {coupon.pk} has no payable amount.")
    accounts = resolve_accounts(instrument, need_expense=bool(interest or fees))
    bank = _bank(bank_account, instrument)
    owed = _money(instrument.drawn_amount) - _money(instrument.principal_repaid)
    if principal > owed:
        raise DebtGLConfigError(
            f"{instrument.instrument_number}: the coupon repays {principal:,.2f} of principal but only {owed:,.2f} has been "
            f"drawn and is outstanding. Record the drawdown first.")

    take_current = min(principal, _money(instrument.current_portion_booked))
    take_noncurrent = principal - take_current
    ref = f"DS-{instrument.instrument_number}-{coupon.pk:04d}"
    memo = f"Debt service {ref}"
    lines = []
    if take_current:
        lines.append((accounts.current_portion, take_current, ZERO, f"Principal (current portion) {ref}"))
    if take_noncurrent:
        lines.append((accounts.liability, take_noncurrent, ZERO, f"Principal (non-current) {ref}"))
    if interest:
        lines.append((accounts.interest, interest, ZERO, f"Interest {ref}"))
    if fees:
        lines.append((accounts.fee, fees, ZERO, f"Fees {ref}"))
    lines.append((bank.gl_account, ZERO, total, f"Paid from {bank.name} {ref}"))
    posting_date = paid_date or timezone.now().date()
    journal = _post(ref, description or f"Debt service - {instrument.instrument_number}", posting_date, ("debt_gl", coupon.pk), lines, actor)

    _move_bank(bank.pk, -total)
    if take_current:
        instrument.current_portion_booked = _money(instrument.current_portion_booked) - take_current
        instrument.save(update_fields=["current_portion_booked", "updated_at"])
    coupon.warrant = warrant
    coupon.status = "paid"
    coupon.paid_at = timezone.now()
    coupon.bank_account = bank
    coupon.journal = journal
    coupon.save(update_fields=["warrant", "status", "paid_at", "bank_account", "journal", "updated_at"])
    DebtServiceGLService.record_actuals(instrument, posting_date, principal, interest, fees)
    AmortisationLedger.objects.create(
        coupon=coupon, event="paid", amount=total, warrant=warrant, description=f"Paid from {bank.name} via {journal.reference_number}",
        recorded_by=actor if getattr(actor, "pk", None) else None)
    return journal
