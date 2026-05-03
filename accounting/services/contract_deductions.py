"""
Contract-payment deductions — Delta State Ministry of Finance
Circular ``AG/CIR/54/C/Vol.10/1/134`` (April 2026).

This module is the **single source of truth** for the three statutory
deductions applied to State Government contract/contractor/vendor
payments under the current circular.

Rules encoded
-------------
1. **Stamp Duty**        — Nil (0 %). Abolished for all contractor /
   supplier / vendor payments irrespective of the date or year of
   award.

2. **Handling Charge**   — 0.5 % of Gross Contract Value, deducted at
   source at the point of the *first* payment on a contract (or first
   payment after an upward review). Computed via the circular's
   factor:

       Handling Charge Factor = 0.5 / 107.5 = 0.004651
       Handling Charge        = Contract Sum × 0.004651

3. **Status Verification** — ₦40,000.00 flat fee per contractor /
   vendor per year.

The service returns ``Deduction`` dataclasses; callers (IPC service,
Payment Voucher service) decide whether to materialise them as
``PaymentVoucherDeduction`` rows.

**Do not hard-code these rates elsewhere.** If the circular is
superseded, update this module and its tests — every caller will pick
up the new rates automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.models import quantize_currency


# ── Circular constants (April 2026) ────────────────────────────────────

#: Circular reference — keep alongside the rates so a policy edit is
#: traceable to the source document.
CIRCULAR_REF = "AG/CIR/54/C/Vol.10/1/134"
CIRCULAR_DATE = "April 2026"

STAMP_DUTY_RATE = Decimal("0.00")  # Abolished.

#: Handling Charge factor (0.5 / 107.5). Multiply by the gross contract
#: sum (or upward-revised sum) to get the charge.
HANDLING_CHARGE_FACTOR = Decimal("0.5") / Decimal("107.5")

#: Pretty rate for display purposes — "0.5 %".
HANDLING_CHARGE_RATE_DISPLAY = Decimal("0.50")

#: Annual per-contractor / per-vendor flat fee in NGN.
STATUS_VERIFICATION_ANNUAL_FEE = Decimal("40000.00")


# ── Output shape ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Deduction:
    """One computed deduction line."""
    kind: str           # "STAMP_DUTY" | "HANDLING" | "STATUS_VERIFICATION"
    rate: Decimal       # Rate for display (0.00, 0.50, etc.)
    amount: Decimal     # NGN, already quantised to 2dp.
    description: str


# ── Calculators ────────────────────────────────────────────────────────

def stamp_duty(payment_amount: Decimal) -> Deduction:
    """
    Return the stamp-duty deduction line.

    After the April 2026 circular this is always zero, but we keep the
    function so callers can carry a documented line in the audit trail
    showing the deduction was evaluated and came out to nil.
    """
    _ = payment_amount  # signature parity — rate is zero regardless
    return Deduction(
        kind="STAMP_DUTY",
        rate=STAMP_DUTY_RATE,
        amount=Decimal("0.00"),
        description=(
            f"Stamp Duty — Nil per Circular {CIRCULAR_REF} "
            f"({CIRCULAR_DATE})."
        ),
    )


def handling_charge(
    *,
    gross_contract_value: Decimal,
    is_first_payment: bool,
) -> Deduction:
    """
    Return the handling-charge deduction line.

    Per the circular, the charge is levied **only** on the first payment
    on a contract (or on the first payment after an approved upward
    revision). On all subsequent payments it is zero.

    Args:
        gross_contract_value: The contract sum, or the revised sum if
            this is the first payment after an upward review.
        is_first_payment: True if no prior handling charge has been
            deducted against this contract / upward revision.
    """
    if gross_contract_value < Decimal("0"):
        raise ValueError("gross_contract_value must be non-negative.")

    if not is_first_payment:
        return Deduction(
            kind="HANDLING",
            rate=Decimal("0.00"),
            amount=Decimal("0.00"),
            description=(
                "Handling Charge — already deducted at first payment "
                f"(Circular {CIRCULAR_REF})."
            ),
        )

    amount = quantize_currency(gross_contract_value * HANDLING_CHARGE_FACTOR)
    return Deduction(
        kind="HANDLING",
        rate=HANDLING_CHARGE_RATE_DISPLAY,
        amount=amount,
        description=(
            f"Handling Charge — 0.5 % × gross contract value "
            f"(factor {HANDLING_CHARGE_FACTOR:.6f}) per Circular "
            f"{CIRCULAR_REF}."
        ),
    )


def status_verification_fee(*, already_paid_this_year: bool) -> Deduction:
    """
    Return the annual Status Verification fee deduction line.

    ₦40,000 is payable once per calendar year per contractor/vendor. If
    the contractor has already paid this year (tracked by the caller),
    the deduction is nil.
    """
    if already_paid_this_year:
        return Deduction(
            kind="STATUS_VERIFICATION",
            rate=Decimal("0.00"),
            amount=Decimal("0.00"),
            description=(
                "Status Verification — already paid for the current "
                f"year (Circular {CIRCULAR_REF})."
            ),
        )
    return Deduction(
        kind="STATUS_VERIFICATION",
        rate=Decimal("0.00"),
        amount=quantize_currency(STATUS_VERIFICATION_ANNUAL_FEE),
        description=(
            f"Status Verification — ₦{STATUS_VERIFICATION_ANNUAL_FEE:,.2f} "
            f"annual fee per contractor/vendor (Circular {CIRCULAR_REF})."
        ),
    )


def compute_all(
    *,
    gross_contract_value: Decimal,
    payment_amount: Decimal,
    is_first_payment: bool,
    status_verification_paid_this_year: bool,
) -> list[Deduction]:
    """
    Convenience wrapper — returns the full deduction bundle for a
    contract payment under the current circular.

    Callers should persist only the non-zero lines, but the zero lines
    are useful to show in the audit trail (proves the rule was applied
    and evaluated).
    """
    return [
        stamp_duty(payment_amount),
        handling_charge(
            gross_contract_value=gross_contract_value,
            is_first_payment=is_first_payment,
        ),
        status_verification_fee(
            already_paid_this_year=status_verification_paid_this_year,
        ),
    ]
