"""Post a Payment Document as one balanced journal (see the design spec).

NEW model: the document is a FULL balanced journal. The bank credit (cash out)
is an EXPLICIT line in the document — the frontend adds a line crediting the
bank's GL account. Posting therefore writes the lines AS ENTERED and requires
``Σ debit == Σ credit``; it no longer derives / appends a bank credit leg.
An MDA is now mandatory on the document.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone


class PaymentDocumentError(Exception):
    """A payment document could not be posted for a domain reason."""


def compute_net(lines) -> Decimal:
    """Net = Σ debits − Σ credits across the document's lines.

    Retained so existing callers/imports don't break, but for a BALANCED
    document (the new model) this is ~0. It is NO LONGER the ``net_amount``
    (cash out) — that figure is the bank credit; see ``_bank_credit``.
    """
    total_debit = sum((ln.debit or Decimal("0.00")) for ln in lines)
    total_credit = sum((ln.credit or Decimal("0.00")) for ln in lines)
    return Decimal(total_debit) - Decimal(total_credit)


def _bank_credit(lines, bank_gl_account_id) -> Decimal:
    """Cash actually leaving the bank = Σ credits on the bank's GL line(s).

    This is the document's real cash-out figure under the explicit-bank-line
    model: the amount the frontend entered as a credit against the bank's GL
    account. Returns ``Decimal("0.00")`` when no line credits the bank GL.
    """
    return sum(
        ((ln.credit or Decimal("0.00")) for ln in lines if ln.account_id == bank_gl_account_id),
        Decimal("0.00"),
    )


def _lines(doc):
    return list(doc.lines.select_related("account", "vendor").all())


def _validate_lines_and_bank(doc, lines):
    """Validate the document's lines + bank account; return ``(bank, cash_out)``.

    Raises :class:`PaymentDocumentError` on any domain violation. This is the
    ONLY validation layer for a payment document — ``PaymentDocumentLine`` has
    no DB constraint / validator against negative or both-sided amounts, so the
    guards below are what keep a corrupted line out of the GL.

    Under the new model the document is a full balanced journal: the bank
    credit is one of ``lines`` (not derived), so we require ``Σ debit == Σ
    credit`` and at least one line crediting the bank's GL account.
    """
    if doc.status == "Posted":
        raise PaymentDocumentError("Payment document is already posted.")
    if doc.journal_id:
        raise PaymentDocumentError("Payment document already has a journal.")
    if doc.mda_id is None:
        raise PaymentDocumentError("An MDA is required for a payment document.")
    if not lines:
        raise PaymentDocumentError("A payment document needs at least one line.")
    if len(lines) < 2:
        raise PaymentDocumentError(
            "A payment document needs at least two lines "
            "(a bank credit and at least one settlement debit)."
        )
    for ln in lines:
        d, c = (ln.debit or Decimal("0.00")), (ln.credit or Decimal("0.00"))
        if d < 0 or c < 0:
            raise PaymentDocumentError("A line's debit and credit amounts must not be negative.")
        if d > 0 and c > 0:
            raise PaymentDocumentError("A line cannot carry both a debit and a credit.")
        if d <= 0 and c <= 0:
            raise PaymentDocumentError("Each line must carry a debit or a credit amount.")

    bank = doc.bank_account
    if not bank or not bank.gl_account_id:
        raise PaymentDocumentError("The document's bank account has no GL account configured.")

    total_debit = sum((ln.debit or Decimal("0.00")) for ln in lines)
    total_credit = sum((ln.credit or Decimal("0.00")) for ln in lines)
    if total_debit != total_credit:
        raise PaymentDocumentError(
            f"Document is not balanced: debits {total_debit} ≠ credits {total_credit}."
        )
    if total_debit <= 0:
        raise PaymentDocumentError("The document total must be positive.")

    cash_out = _bank_credit(lines, bank.gl_account_id)
    if cash_out <= 0:
        raise PaymentDocumentError("The document must credit the bank account (cash out).")
    return bank, cash_out


def _enforce_expense_budget_gates(doc, lines, *, actor=None):
    """Fiscal-period gate + expense-only appropriation / warrant gates.

    Design principle: budget/appropriation is consumed UPSTREAM at expense
    recognition; a payment document merely settles the resulting obligation.
    So ONLY genuine expense-consumption lines (Expense-type debits) are
    budget-gated here — liability, vendor and asset settlement debits post
    with no budget check.

    SIGNATURE / BEHAVIOUR ADAPTATION: the shared budget_enforcement pre-save
    signal gates EVERY debit line whose GL falls under a BudgetCheckRule —
    including liability GLs that happen to sit inside the expenditure code
    range (e.g. 21050000 Payroll Liability under a STRICT rule covering
    20000000-29999999). That would wrongly block obligation settlements,
    contradicting this feature's principle. We therefore run these expense-only
    gates ourselves and set the signal's documented ``_budget_checked``
    sentinel on the journal (see ``_build_and_post_journal``) so the safety-net
    signal does not re-evaluate (and over-gate) the settlement debits.
    """
    from accounting.services.base_posting import BasePostingService
    from accounting.budget_logic import check_warrant_availability, warrant_enforcement_enabled
    from accounting.services.budget_check_rules import check_policy, find_matching_appropriation

    BasePostingService._validate_fiscal_period(doc.document_date, user=actor)

    warrant_on = warrant_enforcement_enabled()
    fiscal_year = doc.document_date.year if doc.document_date else None
    for ln in lines:
        if not (ln.debit and ln.debit > 0 and ln.account.account_type == "Expense"):
            continue
        # Annual appropriation gate (unconditional — mirrors the signal's
        # check_policy branch), so an over-spend on a direct expense payment
        # is blocked even when the quarterly-warrant control is off.
        appropriation = find_matching_appropriation(
            mda=doc.mda, fund=doc.fund, account=ln.account, fiscal_year=fiscal_year,
        )
        policy = check_policy(
            account_code=ln.account.code, appropriation=appropriation,
            requested_amount=ln.debit, transaction_label="payment",
            account_name=ln.account.name,
        )
        if policy.blocked:
            raise PaymentDocumentError(policy.reason)
        # Quarterly warrant / AIE ceiling gate (only when the tenant enforces
        # warrants before payment).
        if warrant_on:
            allowed, warrant_msg, _info = check_warrant_availability(
                dimensions={"mda": doc.mda, "fund": doc.fund},
                account=ln.account, amount=ln.debit,
            )
            if not allowed:
                raise PaymentDocumentError(
                    warrant_msg or "No warrant (AIE) available for an expense line."
                )


def _build_and_post_journal(doc, lines, bank, cash_out):
    """Create and post ONE journal from the document's lines AS ENTERED.

    The bank credit is already one of ``lines`` (an explicit line crediting the
    bank's GL account), so NO derived bank leg is appended. Returns the posted
    ``JournalHeader``.
    """
    from accounting.models import JournalHeader, JournalLine
    from accounting.services.base_posting import BasePostingService

    BasePostingService._check_duplicate_posting(doc.document_number)
    journal = JournalHeader.objects.create(
        posting_date=doc.document_date,
        description=doc.description or f"Payment Document {doc.document_number}",
        reference_number=doc.document_number,
        status="Draft",  # _update_gl_balances flips this to Posted
        source_module="payment_document",
        source_document_id=doc.pk,
        mda=doc.mda, fund=doc.fund, function=doc.function, program=doc.program, geo=doc.geo,
    )
    # Expense budget gates already ran (see _enforce_expense_budget_gates); tell
    # the safety-net signal not to re-evaluate so obligation-settlement debits
    # (liability / vendor / asset) are not over-gated when their GL falls in a
    # BudgetCheckRule range. Set BEFORE _update_gl_balances flips to Posted.
    journal._budget_checked = True
    for ln in lines:
        JournalLine.objects.create(
            header=journal, account=ln.account,
            debit=ln.debit or Decimal("0.00"), credit=ln.credit or Decimal("0.00"),
            memo=doc.document_number[:255],
        )
    BasePostingService._validate_journal_balanced(journal)
    BasePostingService._update_gl_balances(journal)  # runs budget signal, flips to Posted
    return journal


def _settle_vendor_and_bank(lines, bank, cash_out):
    """Decrement the vendor sub-ledger + bank balance after the journal posts.

    ``.update()`` does not fire ``auto_now`` fields, so ``updated_at`` is set
    explicitly on both writes. The bank is decremented by ``cash_out`` — the
    explicit bank credit line — not by ``compute_net``.
    """
    from accounting.models import BankAccount

    for ln in lines:
        if ln.vendor_id and ln.debit and ln.debit > 0 and ln.account.account_type in ("Liability", "Asset"):
            type(ln.vendor).objects.filter(pk=ln.vendor_id).update(
                balance=F("balance") - ln.debit, updated_at=timezone.now(),
            )
    BankAccount.objects.filter(pk=bank.pk).update(
        current_balance=F("current_balance") - cash_out, updated_at=timezone.now(),
    )


@transaction.atomic
def post_payment_document(doc, *, actor=None):
    """Post ``doc`` as one balanced journal from its lines AS ENTERED.

    The document already carries an explicit bank credit line, so posting does
    not append a derived bank leg. Orchestrates: validate (balanced, MDA
    present, bank credited) → enforce expense budget gates → build + post the
    journal → settle vendor/bank sub-ledgers → link the document.

    Returns the ``JournalHeader``. Raises :class:`PaymentDocumentError` for a
    domain problem, or ``ValidationError``/``TransactionPostingError`` if the
    budget signal / balance validation rejects the journal.
    """
    lines = _lines(doc)
    bank, cash_out = _validate_lines_and_bank(doc, lines)
    _enforce_expense_budget_gates(doc, lines, actor=actor)
    journal = _build_and_post_journal(doc, lines, bank, cash_out)
    _settle_vendor_and_bank(lines, bank, cash_out)

    doc.journal = journal
    doc.net_amount = cash_out
    doc.status = "Posted"
    doc.save(update_fields=["journal", "net_amount", "status", "updated_at"], _allow_status_change=True)
    return journal
