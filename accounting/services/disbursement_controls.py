"""
Shared pre-disbursement controls.

The fiscal-period and warrant (AIE) gates that guard cash leaving the TSA,
lifted out of ``accounting.views.payables.post_payment`` so the gateway
disbursement path enforces the *identical* controls rather than a copy
that could drift. A drifting financial control is worse than a duplicated
line of UI: one path could quietly pay past a warrant the other refuses.

View-agnostic: these raise :class:`DisbursementControlError` carrying the
same machine-readable payload the view used to return, and each caller
turns it into its own response. Behaviour for the existing payment-post
path is unchanged — the view now calls these instead of inlining them.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal


class DisbursementControlError(Exception):
    """A pre-disbursement control refused the payment.

    ``payload`` mirrors the JSON the payables view returned for that
    failure (``error`` plus flags like ``warrant_no_warrant`` /
    ``period_closed``) so the frontend keeps rendering the same CTAs.
    """

    def __init__(self, message: str, *, payload: dict | None = None, http_status: int = 400):
        super().__init__(message)
        self.message = message
        self.payload = payload if payload is not None else {"error": message}
        self.http_status = http_status


def enforce_fiscal_period(payment_date, *, user=None) -> None:
    """S1-06 — the payment date must fall in an open fiscal period."""
    from accounting.services.base_posting import BasePostingService

    try:
        BasePostingService._validate_fiscal_period(payment_date, user=user)
    except Exception as exc:  # noqa: BLE001 - re-raised as a control error
        raise DisbursementControlError(
            str(exc), payload={"error": str(exc), "period_closed": True},
        )


def enforce_payment_warrant(payment) -> None:
    """Payment-stage warrant (AIE) gate.

    Cash leaving the TSA is always the binding moment, so this consults
    only the tenant master switch (``warrant_enforcement_enabled()``,
    which fails closed). Allocations are grouped by (MDA, fund, account)
    and each bucket checked against released warrants. No-op when warrant
    enforcement is off or the payment has no invoice-backed allocations.
    """
    from accounting.budget_logic import (
        check_warrant_availability,
        warrant_enforcement_enabled,
    )

    if not warrant_enforcement_enabled():
        return

    buckets: dict = defaultdict(
        lambda: {"amount": Decimal("0"), "mda": None, "fund": None, "account": None}
    )
    for alloc in payment.allocations.select_related("invoice").all():
        inv = alloc.invoice
        if not inv or not inv.mda or not inv.fund:
            continue
        key = (inv.mda_id, inv.fund_id, getattr(inv, "account_id", None))
        b = buckets[key]
        b["amount"] += alloc.amount or Decimal("0")
        b["mda"] = inv.mda
        b["fund"] = inv.fund
        b["account"] = getattr(inv, "account", None)

    for b in buckets.values():
        if b["amount"] == 0:
            continue
        allowed, warrant_msg, info = check_warrant_availability(
            dimensions={"mda": b["mda"], "fund": b["fund"]},
            account=b["account"],
            amount=b["amount"],
        )
        if allowed:
            continue

        # Distinguish "no warrant released at all" from "warrant exceeded"
        # so the frontend can render the right CTA.
        warrants_released = info.get("warrants_released") or Decimal("0")
        appro_label = info.get("appropriation_label", "")
        if warrants_released == 0:
            msg = (
                f"No Warrant (AIE) has been released for "
                f"{appro_label or 'this expense line'}. Release a Warrant for "
                f"this appropriation before posting the payment."
            )
            raise DisbursementControlError(msg, payload={
                "error": msg,
                "warrant_no_warrant": True,
                "warrant_exceeded": False,
                "info": info,
            })
        msg = f"Warrant limit exceeded: {warrant_msg}"
        raise DisbursementControlError(msg, payload={
            "error": msg,
            "warrant_exceeded": True,
            "warrant_no_warrant": False,
            "info": info,
        })
