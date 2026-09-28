"""Compute the proposed journal entries for a Payment (draft preview).

Central-payment model: the DR/CR journal is only built at post time
inside ``PaymentViewSet.post_payment``. Operators, however, need to SEE
what will post while the Payment is still a DRAFT. This module derives
the same balanced entries from the linked PV (gross / deductions / net)
WITHOUT writing anything, so the draft's "Proposed Journal Entries"
preview always matches what posting will produce.

The three shapes mirror ``post_payment`` exactly:

  * Invoice PV / allocation → DR Accounts Payable = gross
    (the expense was already recognised when the invoice posted — paying
    it is balance-sheet only, NO expense at payment)
  * Advance / mobilisation  → DR Vendor-Advance recon (SGL 'A') = gross
    (a balance-sheet advance — NO expense at payment)
  * Direct non-invoice PV   → DR Expenditure line = gross
    (the ONLY branch that recognises an expense at payment, because
    nothing recognised it earlier)

In every shape: CR each deduction G/L = its amount, then the net credit —
CR Bank = net normally, or CR Gateway Settlement Clearing = net when the
payment would post through an active e-payment gateway (the cash is parked,
not gone, until the PSP settles). ``Σdebit == Σcredit`` by construction
(net = gross − Σdeductions).
"""
from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0.00")


def _line(account, *, debit=ZERO, credit=ZERO, memo=""):
    return {
        "account": getattr(account, "name", "") if account is not None else "",
        "account_code": getattr(account, "code", "") if account is not None else "",
        "debit": debit,
        "credit": credit,
        "memo": memo,
    }


def _resolve_ap_account():
    from django.conf import settings as dj
    from accounting.models import Account
    default_gl = getattr(dj, "DEFAULT_GL_ACCOUNTS", {})
    acct = Account.objects.filter(
        reconciliation_type="accounts_payable", is_active=True,
    ).first()
    if acct is None:
        acct = Account.objects.filter(
            code=default_gl.get("ACCOUNTS_PAYABLE", "20100000"),
        ).first()
    if acct is None:
        acct = Account.objects.filter(
            account_type="Liability", name__icontains="Payable",
        ).first()
    return acct


def _resolve_bank_account(payment):
    from django.conf import settings as dj
    from accounting.models import Account
    default_gl = getattr(dj, "DEFAULT_GL_ACCOUNTS", {})
    if payment.bank_account_id and getattr(payment.bank_account, "gl_account", None):
        return payment.bank_account.gl_account
    acct = Account.objects.filter(
        reconciliation_type="bank_accounting", is_active=True,
    ).first()
    if acct is None:
        acct = Account.objects.filter(
            code=default_gl.get("CASH_ACCOUNT", "10100000"),
        ).first()
    if acct is None:
        acct = Account.objects.filter(
            account_type="Asset", name__icontains="Bank",
        ).first()
    return acct


def compute_payment_entries(payment) -> list[dict]:
    """Return the balanced proposed journal lines for ``payment``.

    Amounts are exact; account resolution is best-effort and mirrors
    ``post_payment``. Returns ``[]`` when there is nothing to disburse.
    """
    pv = getattr(payment, "payment_voucher", None)
    deductions = (
        list(pv.deductions.select_related("gl_account").all())
        if pv is not None else []
    )
    gross = pv.gross_amount if pv is not None else payment.total_amount
    net = pv.net_amount if pv is not None else payment.total_amount
    if gross is None:
        return []
    gross = Decimal(str(gross))
    net = Decimal(str(net if net is not None else gross))

    has_allocations = payment.allocations.exists()
    lines: list[dict] = []

    # ── Debit leg — which account depends on the PV type ─────────────
    if payment.is_advance:
        from accounting.services.vendor_advance import VendorAdvanceService
        recon = VendorAdvanceService.resolve_advance_account()
        lines.append(_line(
            recon, debit=gross,
            memo="Vendor advance (Special-GL 'A') — no expense recognised",
        ))
    elif pv is not None and not has_allocations:
        # Direct non-invoice PV (salary / statutory / direct expense) —
        # recognises the expense now via its NCoA economic line.
        econ = getattr(getattr(pv, "ncoa_code", None), "economic", None)
        lines.append(_line(
            econ, debit=gross,
            memo="Expenditure (direct PV) — expense recognised at payment",
        ))
    else:
        ap = _resolve_ap_account()
        lines.append(_line(
            ap, debit=gross,
            memo="Accounts Payable — invoice already posted DR expense / CR supplier",
        ))

    # ── Credit legs: each deduction, then Bank at net ────────────────
    for d in deductions:
        amt = d.amount
        if amt and Decimal(str(amt)) > 0 and getattr(d, "gl_account_id", None):
            label = (
                d.get_deduction_type_display()
                if hasattr(d, "get_deduction_type_display") else "Deduction"
            )
            desc = getattr(d, "description", "") or ""
            lines.append(_line(
                d.gl_account, credit=Decimal(str(amt)),
                memo=f"{label} withheld" + (f" — {desc}" if desc else ""),
            ))

    # ── Net credit leg: Bank, OR Gateway Settlement Clearing when this
    #    payment would post through an active e-payment gateway ──────────
    # Mirrors post_payment's routing (same active_disbursement_setting +
    # can_disburse_via_gateway gate), so the preview shows the clearing leg
    # exactly when the real post will use it — the cash is parked, not gone,
    # until the PSP settlement webhook moves it to Bank.
    clearing = _gateway_clearing_if_routed(payment)
    if clearing is not None:
        lines.append(_line(
            clearing, credit=net,
            memo="Gateway Settlement Clearing — net parked; cash leaves on gateway settlement",
        ))
    else:
        bank = _resolve_bank_account(payment)
        lines.append(_line(bank, credit=net, memo="Bank / Cash — net cash out"))

    return lines


def _gateway_clearing_if_routed(payment):
    """The Gateway Settlement Clearing account IFF ``payment`` would post
    through the gateway (eligible AND an active usable tenant gateway), else
    None. Uses the SAME gates as ``post_payment`` so the preview cannot claim a
    clearing leg the post would not book, or hide one it would."""
    from accounting.services.gateway_disbursement import (
        can_disburse_via_gateway, active_disbursement_setting,
    )
    if not can_disburse_via_gateway(payment):
        return None
    if active_disbursement_setting() is None:
        return None
    from accounting.services.base_posting import get_gl_account
    return get_gl_account("GATEWAY_SETTLEMENT_CLEARING", "Liability", "Gateway Clearing")
