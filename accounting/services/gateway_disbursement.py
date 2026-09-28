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
def can_disburse_via_gateway(payment, *, has_allocations: bool | None = None) -> bool:
    """Whether ``payment`` may be disbursed through the gateway.

    Gateway disbursement books ``DR Accounts Payable``, which is only correct
    for a real vendor payable with bank details. It must NEVER take:
      * an ADVANCE (F-48 Special-GL, no invoice — DR AP would be wrong), or
      * a DIRECT / non-invoice PV (salary/pension/statutory) — those recognise
        expenditure and run the STRICT appropriation + direct-PV warrant checks,
        and have no AP to debit.
    A standalone direct vendor payment (no PV) and an invoice-backed PV payment
    (has allocations) are allowed. This predicate is the classification guard
    that fixes the "always DR AP" misclassification AND scopes the auto-fire.

    ``has_allocations`` overrides ``payment.allocations.exists()`` — needed for
    an UNSAVED payment (the New Outgoing Payment simulation), whose reverse-FK
    manager cannot be queried without a pk. Left None, it reads the DB as before.
    """
    vendor = payment.vendor
    if not (vendor and vendor.bank_account_number):
        return False
    if payment.is_advance:
        return False
    pv = payment.payment_voucher
    if has_allocations is None:
        has_allocations = payment.allocations.exists()
    if pv is not None and not has_allocations:
        return False  # direct/non-invoice PV — recognise expenditure, don't DR AP
    return True


@transaction.atomic
def active_disbursement_setting():
    """The active, usable disbursement gateway for the CURRENT tenant, or None.

    The single source of truth for "would this tenant's payment route through a
    gateway" — shared by ``post_payment`` (which fires it) and the draft preview
    (which shows the clearing leg), so the preview can never disagree with what
    posts. Fail-closed: on the public schema, an unresolved tenant (FakeTenant /
    no pk), or with no active+usable setting, returns None → the bank path.
    """
    from django.db import connection
    from superadmin.gateway_models import TenantGatewaySetting

    tenant_pk = getattr(getattr(connection, "tenant", None), "pk", None)
    if tenant_pk is None:
        return None
    setting = (
        TenantGatewaySetting.objects
        .select_related("provider")
        .filter(
            tenant_id=tenant_pk, is_active=True,
            provider__is_enabled=True, provider__supports_disbursement=True,
        )
        .order_by("-is_default", "provider__sort_order")
        .first()
    )
    return setting if (setting is not None and setting.is_usable) else None


@transaction.atomic
def dispatch_payment_via_gateway(payment, setting, *, actor=None):
    """Post the clearing journal and dispatch ``payment`` through ``setting``.

    Returns ``(GatewayResult, JournalHeader)``. Raises
    :class:`GatewayRefused` if the gateway is unusable, or
    :class:`GatewayDisbursementError` for a domain problem.

    ATOMIC — the clearing journal, the ``Posted`` status flip, the vendor
    balance decrement, and the ``disburse()`` send commit or roll back as one
    unit. If ``disburse()`` raises (credentials, network) or the gateway does
    not accept the payout, EVERYTHING rolls back: the payment stays ``Draft``,
    no clearing journal is left behind, and no half-settled ``GatewayTransaction``
    lingers. The clearing balance must never hold money for a payout that was
    never sent — the operator fixes the cause and re-posts cleanly.
    """
    if payment.status == "Posted":
        raise GatewayDisbursementError("Payment is already posted.")
    if payment.journal_entry_id:
        raise GatewayDisbursementError("Payment already has a GL journal.")
    if not setting.is_usable:
        raise GatewayRefused("The selected gateway is not enabled for this tenant.")
    if not can_disburse_via_gateway(payment):
        raise GatewayDisbursementError(
            "This payment cannot be disbursed via gateway (advance, direct/non-invoice "
            "PV, or vendor without bank details)."
        )

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

    # Reduce the vendor's outstanding balance by the gross settled — the
    # deduction is withheld from cash, not from the vendor's settlement, so
    # the payable clears at gross. Mirrors the normal post_payment path.
    if payment.vendor_id:
        from django.db.models import F
        type(payment.vendor).objects.filter(pk=payment.vendor_id).update(
            balance=F("balance") - gross,
        )

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
    if not result.accepted:
        # The PSP did not take the payout: nothing is in flight, so the
        # clearing journal must not stand. Raising inside the atomic rolls
        # back the journal + status flip; a webhook will never arrive to
        # settle or reverse it, so this is the only place to undo it.
        raise GatewayDisbursementError(
            f"The gateway did not accept the payout for {payment.payment_number}: "
            f"{getattr(result, 'error', '') or 'rejected'}."
        )
    return result, journal


@transaction.atomic
def settle_gateway_disbursement(txn: GatewayTransaction, *, success: bool):
    """Post the settlement journal for a completed gateway exchange.

    Idempotent on the transaction's terminal state. ``txn`` is the shared
    :class:`GatewayTransaction`; the payment is resolved from its subject.

    Re-fetches ``txn`` under a row lock and re-checks its status INSIDE the
    atomic, so two concurrent PSP callback deliveries (PSPs retry aggressively)
    can never both post a settlement journal — the second blocks on the lock,
    then sees the terminal status and no-ops.
    """
    txn = GatewayTransaction.objects.select_for_update().get(pk=txn.pk)
    if txn.status in (
        GatewayTransaction.Status.SUCCESS,
        GatewayTransaction.Status.REVERSED,
        GatewayTransaction.Status.FAILED,
    ):
        return None  # already settled/terminal

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
    gross = Decimal("0.00")
    for line in original.lines.all():
        JournalLine.objects.create(
            header=reversal, account=line.account,
            debit=line.credit, credit=line.debit,
            memo=f"Reversal {payment.payment_number}",
        )
        # The original DR is the AP debit at gross — the amount the payable
        # is reinstated by.
        gross += line.debit
    BasePostingService._validate_journal_balanced(reversal)
    BasePostingService._update_gl_balances(reversal)

    # Reinstate the vendor's outstanding balance (the dispatch reduced it).
    if payment.vendor_id and gross > 0:
        from django.db.models import F
        type(payment.vendor).objects.filter(pk=payment.vendor_id).update(
            balance=F("balance") + gross,
        )

    txn.status = GatewayTransaction.Status.REVERSED
    txn.settled_at = timezone.now()
    txn.save(update_fields=["status", "settled_at", "updated_at"])
    return reversal
