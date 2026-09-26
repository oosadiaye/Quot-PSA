"""
Gateway disbursement — the clearing-account path (Option 1).

Parallel to ``ProcurementPostingService.post_payment`` (DR AP / CR Bank),
which is left untouched. A gateway payout instead posts

    DR Accounts Payable (gross)
    CR each deduction G/L
    CR Gateway Settlement Clearing (net)

and dispatches the net to the PSP through the fail-closed
:func:`superadmin.gateway_client.disburse` seam. The cash has NOT left yet
— the clearing account holds it. Settlement, driven by the PSP webhook
(or a status poll), then:

    success →  DR Gateway Settlement Clearing / CR Bank   (cash out)
    failure →  reverse the clearing journal               (payable reinstated)

The failure reversal is automatic — no operator posts a correcting entry.

The same pre-disbursement controls the normal post enforces run here too,
via :mod:`accounting.services.disbursement_controls`, so a gateway payout
can never slip past a fiscal-period lock or a warrant ceiling.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from accounting.models import JournalHeader, JournalLine
from accounting.services.base_posting import BasePostingService, get_gl_account
from accounting.services.disbursement_controls import (
    enforce_fiscal_period,
    enforce_payment_warrant,
)
from accounting.services.procurement_posting import get_vendor_ap_account
from superadmin.gateway_client import GatewayRefused, disburse
from superadmin.gateway_connectors.base import DisburseRequest
from superadmin.gateway_models import GatewayTransaction

CLEARING_KEY = "GATEWAY_SETTLEMENT_CLEARING"


class GatewayDisbursementError(Exception):
    """A gateway payout could not be posted/dispatched for a domain reason."""


def _clearing_account():
    acc = get_gl_account(CLEARING_KEY, "Liability", "Gateway Clearing")
    if not acc:
        raise GatewayDisbursementError(
            "No Gateway Settlement Clearing GL account is configured. Map the "
            f"'{CLEARING_KEY}' key to a liability account."
        )
    return acc


def _bank_account(payment):
    if payment.bank_account and payment.bank_account.gl_account:
        return payment.bank_account.gl_account
    acc = get_gl_account("CASH_ACCOUNT", "Asset", "Bank")
    if not acc:
        raise GatewayDisbursementError("No Bank/Cash GL account found for settlement.")
    return acc


def _settlement_figures(payment):
    """``(gross, [(gl_account, amount)], net)``.

    Deductions come from the linked PV; a standalone payment has
    ``gross == net == total_amount`` and no deductions — mirroring the
    normal deduction-aware post.
    """
    pv = getattr(payment, "payment_voucher", None)
    net = payment.total_amount
    if pv is None:
        return net, [], net
    gross = pv.gross_amount or net
    lines = [
        (d.gl_account, d.amount)
        for d in pv.deductions.select_related("gl_account").all()
        if d.amount and d.amount > 0 and d.gl_account_id
    ]
    return gross, lines, net


def _beneficiary(payment):
    v = payment.vendor
    if not v or not v.bank_account_number:
        raise GatewayDisbursementError(
            "The payee has no bank account on file; a gateway payout needs one."
        )
    return v


@transaction.atomic
def dispatch_payment_via_gateway(payment, setting, *, actor=None):
    """Post the clearing journal and dispatch ``payment`` through ``setting``.

    Returns ``(GatewayResult, JournalHeader)``. Raises
    :class:`GatewayRefused` if the gateway is unusable, or
    :class:`GatewayDisbursementError` for a domain problem.
    """
    if payment.status == "Posted":
        raise GatewayDisbursementError("Payment is already posted.")
    if payment.journal_entry_id:
        raise GatewayDisbursementError("Payment already has a GL journal.")
    if not setting.is_usable:
        raise GatewayRefused("The selected gateway is not enabled for this tenant.")

    # The same gates the normal post enforces.
    enforce_fiscal_period(payment.payment_date, user=actor)
    enforce_payment_warrant(payment)

    vendor = _beneficiary(payment)
    ap_account, _ = get_vendor_ap_account(vendor)
    clearing = _clearing_account()
    gross, deduction_lines, net = _settlement_figures(payment)
    if net is None or net <= 0:
        raise GatewayDisbursementError(f"Net payable must be positive (got {net}).")

    BasePostingService._check_duplicate_posting(payment.payment_number)

    journal = JournalHeader.objects.create(
        posting_date=payment.payment_date,
        description=f"Gateway disbursement {payment.payment_number}",
        reference_number=payment.payment_number,
        status="Posted",
        source_module="gateway_disbursement",
        source_document_id=payment.pk,
    )
    JournalLine.objects.create(
        header=journal, account=ap_account,
        debit=gross, credit=Decimal("0.00"),
        memo=f"Payment {payment.payment_number}",
    )
    for gl_account, amount in deduction_lines:
        JournalLine.objects.create(
            header=journal, account=gl_account,
            debit=Decimal("0.00"), credit=amount,
            memo=f"Deduction {payment.payment_number}",
        )
    JournalLine.objects.create(
        header=journal, account=clearing,
        debit=Decimal("0.00"), credit=net,
        memo=f"Gateway clearing {payment.payment_number}",
    )
    BasePostingService._validate_journal_balanced(journal)
    BasePostingService._update_gl_balances(journal)

    payment.status = "Posted"
    payment.journal_entry = journal
    payment.save(_allow_status_change=True)

    request = DisburseRequest(
        reference=payment.payment_number,
        amount=net,
        beneficiary_account=vendor.bank_account_number,
        beneficiary_bank_code=getattr(vendor, "bank_sort_code", "") or "",
        beneficiary_name=vendor.name,
        narration=(payment.reference_number or f"Payment {payment.payment_number}")[:100],
    )
    result = disburse(
        tenant=connection.tenant, setting=setting, request=request,
        subject={"model": "Payment", "id": payment.pk},
    )
    return result, journal


@transaction.atomic
def settle_gateway_disbursement(txn: GatewayTransaction, *, success: bool):
    """Post the settlement journal for a completed gateway exchange.

    Idempotent on the transaction's terminal state. ``txn`` is the shared
    :class:`GatewayTransaction`; the payment is resolved from its subject.
    """
    if txn.status in (
        GatewayTransaction.Status.SUCCESS,
        GatewayTransaction.Status.REVERSED,
    ):
        return None  # already settled

    from accounting.models import Payment

    payment_id = (txn.subject or {}).get("id")
    payment = Payment.objects.filter(pk=payment_id).first() if payment_id else None
    if payment is None or not payment.journal_entry_id:
        raise GatewayDisbursementError(
            "Cannot settle: the originating payment/clearing journal is missing."
        )

    clearing = _clearing_account()
    net = txn.amount

    if success:
        # Cash actually leaves: move the clearing balance to Bank.
        bank = _bank_account(payment)
        journal = JournalHeader.objects.create(
            posting_date=timezone.now().date(),
            description=f"Gateway settlement {payment.payment_number}",
            reference_number=f"{payment.payment_number}-STL",
            status="Posted",
            source_module="gateway_settlement",
            source_document_id=payment.pk,
        )
        JournalLine.objects.create(
            header=journal, account=clearing, debit=net, credit=Decimal("0.00"),
            memo=f"Gateway settled {payment.payment_number}",
        )
        JournalLine.objects.create(
            header=journal, account=bank, debit=Decimal("0.00"), credit=net,
            memo=f"Cash out {payment.payment_number}",
        )
        BasePostingService._validate_journal_balanced(journal)
        BasePostingService._update_gl_balances(journal)
        txn.status = GatewayTransaction.Status.SUCCESS
        txn.settled_at = timezone.now()
        txn.save(update_fields=["status", "settled_at", "updated_at"])
        return journal

    # Failure: auto-reverse the clearing journal, reinstating the payable.
    # Reversing each original line (swap debit/credit) restores AP to the
    # gross owed, removes the deduction accruals, and clears the clearing
    # balance — back to the pre-dispatch state, ready to re-attempt.
    original = payment.journal_entry
    reversal = JournalHeader.objects.create(
        posting_date=timezone.now().date(),
        description=f"Gateway failure reversal {payment.payment_number}",
        reference_number=f"{payment.payment_number}-REV",
        status="Posted",
        source_module="gateway_settlement",
        source_document_id=payment.pk,
    )
    for line in original.lines.all():
        JournalLine.objects.create(
            header=reversal, account=line.account,
            debit=line.credit, credit=line.debit,
            memo=f"Reversal {payment.payment_number}",
        )
    BasePostingService._validate_journal_balanced(reversal)
    BasePostingService._update_gl_balances(reversal)
    txn.status = GatewayTransaction.Status.REVERSED
    txn.settled_at = timezone.now()
    txn.save(update_fields=["status", "settled_at", "updated_at"])
    return reversal
