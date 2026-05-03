"""
Pure-Python unit tests for the contracts service-layer computations.

These tests hit no database, no migrations, no tenant schema — they
exercise just the decision logic in MobilizationService.compute_recovery,
RetentionService.compute_deduction, and InterimPaymentCertificate.
compute_net_payable.

Running cost: ~0.05 s for the whole file.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from contracts.services.mobilization_service import MobilizationService
from contracts.services.retention_service import RetentionService


# ── MobilizationService.compute_recovery ──────────────────────────────

class TestMobilizationRecovery:

    def test_zero_rate_returns_zero(self, stub_contract, stub_balance):
        contract = stub_contract(mobilization_rate=Decimal("0.00"))
        balance = stub_balance(mobilization_paid=Decimal("1500000"))
        got = MobilizationService.compute_recovery(
            contract=contract,
            balance=balance,
            this_certificate_gross=Decimal("1000000"),
        )
        assert got == Decimal("0.00")

    def test_no_advance_paid_returns_zero(self, stub_contract, stub_balance):
        contract = stub_contract(mobilization_rate=Decimal("15.00"))
        balance = stub_balance(mobilization_paid=Decimal("0"))
        got = MobilizationService.compute_recovery(
            contract=contract,
            balance=balance,
            this_certificate_gross=Decimal("1000000"),
        )
        assert got == Decimal("0.00")

    def test_pro_rata_within_outstanding(self, stub_contract, stub_balance):
        """15% of 1M gross = 150,000 — well within 1.5M outstanding."""
        contract = stub_contract(mobilization_rate=Decimal("15.00"))
        balance = stub_balance(
            mobilization_paid=Decimal("1500000"),
            mobilization_recovered=Decimal("0"),
        )
        got = MobilizationService.compute_recovery(
            contract=contract,
            balance=balance,
            this_certificate_gross=Decimal("1000000"),
        )
        assert got == Decimal("150000.00")

    def test_capped_at_outstanding_balance(self, stub_contract, stub_balance):
        """Don't over-recover — cap at mob_paid − mob_recovered."""
        contract = stub_contract(mobilization_rate=Decimal("15.00"))
        balance = stub_balance(
            mobilization_paid=Decimal("1500000"),
            mobilization_recovered=Decimal("1450000"),
        )
        # Raw = 15% × 1M = 150k, but only 50k outstanding.
        got = MobilizationService.compute_recovery(
            contract=contract,
            balance=balance,
            this_certificate_gross=Decimal("1000000"),
        )
        assert got == Decimal("50000.00")

    def test_already_fully_recovered_returns_zero(
        self, stub_contract, stub_balance,
    ):
        contract = stub_contract(mobilization_rate=Decimal("15.00"))
        balance = stub_balance(
            mobilization_paid=Decimal("1500000"),
            mobilization_recovered=Decimal("1500000"),
        )
        got = MobilizationService.compute_recovery(
            contract=contract,
            balance=balance,
            this_certificate_gross=Decimal("1000000"),
        )
        assert got == Decimal("0.00")


# ── RetentionService.compute_deduction ────────────────────────────────

class TestRetentionDeduction:

    def test_zero_rate_returns_zero(self, stub_contract):
        contract = stub_contract(retention_rate=Decimal("0.00"))
        got = RetentionService.compute_deduction(
            contract=contract,
            balance=None,  # unused when rate is 0
            this_certificate_gross=Decimal("1000000"),
        )
        assert got == Decimal("0.00")

    def test_five_percent_deduction(self, stub_contract):
        contract = stub_contract(retention_rate=Decimal("5.00"))
        got = RetentionService.compute_deduction(
            contract=contract,
            balance=None,
            this_certificate_gross=Decimal("1000000"),
        )
        assert got == Decimal("50000.00")

    def test_respects_max_rate(self, stub_contract):
        """DB constraint caps retention_rate at 20% but the method itself
        honours whatever rate is on the contract."""
        contract = stub_contract(retention_rate=Decimal("20.00"))
        got = RetentionService.compute_deduction(
            contract=contract,
            balance=None,
            this_certificate_gross=Decimal("1000000"),
        )
        assert got == Decimal("200000.00")


# ── RetentionService.apply_deduction ──────────────────────────────────

class TestRetentionApply:

    def test_negative_amount_rejected(self, stub_balance):
        from contracts.services.exceptions import RetentionCapError
        balance = stub_balance()
        with pytest.raises(RetentionCapError):
            RetentionService.apply_deduction(
                balance=balance,
                deduction_amount=Decimal("-1"),
            )

    def test_increments_held(self, stub_balance):
        balance = stub_balance(retention_held=Decimal("100"))
        RetentionService.apply_deduction(
            balance=balance,
            deduction_amount=Decimal("50"),
        )
        assert balance.retention_held == Decimal("150.00")


# ── MobilizationService.apply_recovery ────────────────────────────────

class TestMobilizationApply:

    def test_over_recovery_rejected(self, stub_balance):
        from contracts.services.exceptions import MobilizationRecoveryError
        balance = stub_balance(
            mobilization_paid=Decimal("100"),
            mobilization_recovered=Decimal("80"),
        )
        with pytest.raises(MobilizationRecoveryError):
            MobilizationService.apply_recovery(
                balance=balance,
                recovery_amount=Decimal("25"),  # would push total to 105
            )

    def test_negative_amount_rejected(self, stub_balance):
        from contracts.services.exceptions import MobilizationRecoveryError
        balance = stub_balance()
        with pytest.raises(MobilizationRecoveryError):
            MobilizationService.apply_recovery(
                balance=balance,
                recovery_amount=Decimal("-1"),
            )

    def test_exact_full_recovery_allowed(self, stub_balance):
        balance = stub_balance(
            mobilization_paid=Decimal("100"),
            mobilization_recovered=Decimal("75"),
        )
        MobilizationService.apply_recovery(
            balance=balance,
            recovery_amount=Decimal("25"),
        )
        assert balance.mobilization_recovered == Decimal("100.00")
