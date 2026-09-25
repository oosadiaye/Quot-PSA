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

In every shape: CR each deduction G/L = its amount, CR Bank = net, and
``Σdebit == Σcredit`` by construction (net = gross − Σdeductions).
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


def _resolve_bank_gl(payment, override=None):
    """The cash/bank GL for the disbursement — from the operator's current
    (possibly unsaved) bank-account selection first, then the payment's saved
    bank account. NO default-GL fallback: a missing bank account must surface so
    the operator picks one, and the preview shows the SAME GL ``post_payment``
    will use (which now also requires a bank account)."""
    if override is not None and getattr(override, "gl_account", None):
        return override.gl_account
    if payment.bank_account_id and getattr(payment.bank_account, "gl_account", None):
        return payment.bank_account.gl_account
    return None


def compute_payment_entries(payment, *, bank_account=None) -> list[dict]:
    """Return the balanced proposed journal lines for ``payment``.

    ``bank_account`` (optional) is the operator's current selection used to
    resolve the cash GL before the draft is saved — mirrors what ``post_payment``
    will book. When no bank GL resolves, the cash line is a flagged placeholder
    (``_placeholder``) so the caller can tell the operator to pick a bank account.
    Amounts are exact. Returns ``[]`` when there is nothing to disburse.
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

    bank = _resolve_bank_gl(payment, bank_account)
    if bank is not None:
        lines.append(_line(bank, credit=net, memo="Bank / Cash — net cash out"))
    else:
        # No bank account chosen yet — show a placeholder instead of a made-up
        # GL, and flag it so the endpoint can tell the UI to pick a bank account.
        lines.append({
            "account": "— select a bank account —",
            "account_code": "",
            "debit": ZERO,
            "credit": net,
            "memo": "Bank / Cash — select a bank account to resolve the GL",
            "_placeholder": True,
        })

    return lines
