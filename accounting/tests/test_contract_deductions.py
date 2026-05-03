"""
Tests for ``accounting.services.contract_deductions`` — the codified
implementation of Delta State Circular AG/CIR/54/C/Vol.10/1/134 (April
2026).

These tests lock the circular's numerical rules. Failing them means
either a bug in the calculator, or a policy change that needs to be
cross-checked against a new circular and this test file updated
deliberately.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


# ── Constants freeze ──────────────────────────────────────────────────

class TestCircularMetadata:
    """Metadata is auditable — keep the circular reference stable so
    reports and audit logs can trace a deduction back to policy."""

    def test_circular_ref(self):
        from accounting.services.contract_deductions import CIRCULAR_REF
        assert CIRCULAR_REF == "AG/CIR/54/C/Vol.10/1/134"

    def test_circular_date(self):
        from accounting.services.contract_deductions import CIRCULAR_DATE
        assert CIRCULAR_DATE == "April 2026"


class TestRateConstants:

    def test_stamp_duty_abolished(self):
        from accounting.services.contract_deductions import STAMP_DUTY_RATE
        assert STAMP_DUTY_RATE == Decimal("0.00")

    def test_handling_factor_matches_circular(self):
        """Circular gives 0.5/107.5 = 0.004651. Factor is computed
        exactly; quantise for display comparison."""
        from accounting.services.contract_deductions import HANDLING_CHARGE_FACTOR
        expected = Decimal("0.5") / Decimal("107.5")
        assert HANDLING_CHARGE_FACTOR == expected
        # 6-dp circular-quoted value
        assert HANDLING_CHARGE_FACTOR.quantize(Decimal("0.000001")) == Decimal("0.004651")

    def test_status_verification_fee(self):
        from accounting.services.contract_deductions import STATUS_VERIFICATION_ANNUAL_FEE
        assert STATUS_VERIFICATION_ANNUAL_FEE == Decimal("40000.00")


# ── Stamp duty ────────────────────────────────────────────────────────

class TestStampDuty:
    """Circular: Stamp Duty is nil for every payment regardless of
    amount, date of award, or contract type."""

    def test_zero_for_any_payment(self):
        from accounting.services.contract_deductions import stamp_duty
        for amt in [Decimal("10000"), Decimal("450000000"), Decimal("0")]:
            d = stamp_duty(amt)
            assert d.amount == Decimal("0.00"), amt
            assert d.rate == Decimal("0.00"), amt
            assert d.kind == "STAMP_DUTY"

    def test_description_cites_circular(self):
        from accounting.services.contract_deductions import stamp_duty
        d = stamp_duty(Decimal("1000000"))
        assert "AG/CIR/54/C/Vol.10/1/134" in d.description
        assert "Nil" in d.description


# ── Handling charge ──────────────────────────────────────────────────

class TestHandlingCharge:

    def test_450m_contract_first_payment(self):
        """₦450,000,000 × 0.004651... = ₦2,093,023.26 (to 2dp).

        Hand-computed: 450,000,000 × (0.5/107.5)
                     = 225,000,000 / 107.5
                     = 2,093,023.2558139... → ₦2,093,023.26
        """
        from accounting.services.contract_deductions import handling_charge
        d = handling_charge(
            gross_contract_value=Decimal("450000000"),
            is_first_payment=True,
        )
        assert d.kind == "HANDLING"
        assert d.rate == Decimal("0.50")
        assert d.amount == Decimal("2093023.26")

    def test_45m_contract_first_payment(self):
        """₦45,000,000 × factor → ₦209,302.33 to 2dp."""
        from accounting.services.contract_deductions import handling_charge
        d = handling_charge(
            gross_contract_value=Decimal("45000000"),
            is_first_payment=True,
        )
        assert d.amount == Decimal("209302.33")

    def test_120m_contract_first_payment(self):
        """₦120,000,000 × factor → ₦558,139.53 to 2dp."""
        from accounting.services.contract_deductions import handling_charge
        d = handling_charge(
            gross_contract_value=Decimal("120000000"),
            is_first_payment=True,
        )
        assert d.amount == Decimal("558139.53")

    def test_zero_on_subsequent_payment(self):
        """Circular: handling charge deducted *at source from first
        payment as usual* — i.e. once only."""
        from accounting.services.contract_deductions import handling_charge
        d = handling_charge(
            gross_contract_value=Decimal("450000000"),
            is_first_payment=False,
        )
        assert d.amount == Decimal("0.00")
        assert d.rate == Decimal("0.00")

    def test_negative_value_rejected(self):
        from accounting.services.contract_deductions import handling_charge
        with pytest.raises(ValueError):
            handling_charge(
                gross_contract_value=Decimal("-1"),
                is_first_payment=True,
            )

    def test_description_cites_circular(self):
        from accounting.services.contract_deductions import handling_charge
        d = handling_charge(
            gross_contract_value=Decimal("1000000"),
            is_first_payment=True,
        )
        assert "AG/CIR/54/C/Vol.10/1/134" in d.description
        assert "0.5" in d.description


# ── Status verification ──────────────────────────────────────────────

class TestStatusVerificationFee:

    def test_40k_when_not_paid_this_year(self):
        from accounting.services.contract_deductions import status_verification_fee
        d = status_verification_fee(already_paid_this_year=False)
        assert d.kind == "STATUS_VERIFICATION"
        assert d.amount == Decimal("40000.00")

    def test_zero_when_already_paid(self):
        from accounting.services.contract_deductions import status_verification_fee
        d = status_verification_fee(already_paid_this_year=True)
        assert d.amount == Decimal("0.00")


# ── Bundle ───────────────────────────────────────────────────────────

class TestComputeAll:

    def test_first_payment_bundle(self):
        from accounting.services.contract_deductions import compute_all
        bundle = compute_all(
            gross_contract_value=Decimal("450000000"),
            payment_amount=Decimal("45000000"),
            is_first_payment=True,
            status_verification_paid_this_year=False,
        )
        assert [d.kind for d in bundle] == [
            "STAMP_DUTY", "HANDLING", "STATUS_VERIFICATION",
        ]
        assert bundle[0].amount == Decimal("0.00")
        assert bundle[1].amount == Decimal("2093023.26")
        assert bundle[2].amount == Decimal("40000.00")

    def test_subsequent_payment_bundle(self):
        from accounting.services.contract_deductions import compute_all
        bundle = compute_all(
            gross_contract_value=Decimal("450000000"),
            payment_amount=Decimal("45000000"),
            is_first_payment=False,
            status_verification_paid_this_year=True,
        )
        # Every line reduces to zero for a subsequent same-year payment
        assert all(d.amount == Decimal("0.00") for d in bundle)
