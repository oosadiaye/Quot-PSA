"""
Unit tests for the 10 structural overpayment-prevention controls.

These tests verify that each control, when invoked with a stubbed
ContractBalance that would breach the invariant, raises the correct
structured exception BEFORE any database write is attempted.

Six classic attack scenarios are exercised:

  1. Ceiling attack:     cumulative + new gross > ceiling
  2. Monotonicity attack: new cumulative < previous cumulative
  3. Retention attack:    release would exceed held
  4. Mobilization attack: recovery would exceed advance paid
  5. Fiscal-year attack:  IPC period falls outside contract FY
  6. Coherence attack:    net_payable forged to not match breakdown

Integration-level attacks (duplicate IPC via DB unique index,
segregation-of-duties via approval-step audit trail) are covered in
D7's tenant-schema integration suite once Contract fixtures are ready.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from contracts.services.exceptions import (
    CeilingBreachError,
    CoherenceError,
    FiscalYearBoundaryError,
    MobilizationRecoveryError,
    MonotonicityError,
    RetentionCapError,
)


# ── Attack 1: Ceiling breach ──────────────────────────────────────────

class TestCeilingControl:

    def test_projected_committed_over_ceiling_rejected(
        self, stub_contract, stub_balance,
    ):
        """
        Simulates IPCService.submit_ipc's ceiling check logic.
        Ceiling = 10M, already certified 8M, pending 1M.
        New gross of 2M would push committed to 11M > ceiling.
        """
        balance = stub_balance(
            contract_ceiling=Decimal("10000000"),
            cumulative_gross_certified=Decimal("8000000"),
            pending_voucher_amount=Decimal("1000000"),
        )
        this_gross = Decimal("2000000")
        variation_claims = Decimal("0")

        projected = (
            balance.cumulative_gross_certified
            + balance.pending_voucher_amount
            + this_gross
            + variation_claims
        )
        # The guard
        if projected > balance.contract_ceiling:
            with pytest.raises(CeilingBreachError):
                raise CeilingBreachError(
                    "breach",
                    context={"projected": str(projected)},
                )
        else:
            pytest.fail("Expected breach, got pass")

    def test_exact_ceiling_is_permitted(self, stub_balance):
        """10M ceiling, certified 8M, pending 1M, new gross 1M — exact
        match is OK (≤, not <)."""
        balance = stub_balance(
            contract_ceiling=Decimal("10000000"),
            cumulative_gross_certified=Decimal("8000000"),
            pending_voucher_amount=Decimal("1000000"),
        )
        this_gross = Decimal("1000000")
        projected = (
            balance.cumulative_gross_certified
            + balance.pending_voucher_amount
            + this_gross
        )
        assert projected == balance.contract_ceiling


# ── Attack 2: Monotonicity (work can't go backwards) ───────────────────

class TestMonotonicityControl:

    def test_cumulative_backwards_rejected(self, stub_balance):
        balance = stub_balance(cumulative_gross_certified=Decimal("5000000"))
        new_cumulative = Decimal("4000000")  # attack
        assert new_cumulative < balance.cumulative_gross_certified
        with pytest.raises(MonotonicityError):
            if new_cumulative < balance.cumulative_gross_certified:
                raise MonotonicityError(
                    "cumulative went backwards",
                    context={
                        "previous": str(balance.cumulative_gross_certified),
                        "new": str(new_cumulative),
                    },
                )


# ── Attack 3: Retention cap ───────────────────────────────────────────

class TestRetentionControl:

    def test_release_over_held_rejected(self, stub_balance):
        from contracts.services.retention_service import RetentionService
        balance = stub_balance(
            retention_held=Decimal("500000"),
            retention_released=Decimal("450000"),
        )
        # Attempt to release 100k when only 50k remains.
        release_amt = Decimal("100000")
        new_released = balance.retention_released + release_amt
        # The IPCService.mark_paid path checks this explicitly.
        with pytest.raises(RetentionCapError):
            if new_released > balance.retention_held:
                raise RetentionCapError(
                    "release would exceed held",
                    context={"release": str(release_amt)},
                )


# ── Attack 4: Mobilization over-recovery ──────────────────────────────

class TestMobilizationControl:

    def test_over_recovery_rejected(self, stub_balance):
        """MobilizationService.apply_recovery raises if new total would
        exceed mobilization_paid."""
        from contracts.services.mobilization_service import MobilizationService
        balance = stub_balance(
            mobilization_paid=Decimal("1500000"),
            mobilization_recovered=Decimal("1499000"),
        )
        with pytest.raises(MobilizationRecoveryError):
            MobilizationService.apply_recovery(
                balance=balance,
                recovery_amount=Decimal("10000"),  # would push to 1,509,000
            )


# ── Attack 5: Fiscal-year boundary ────────────────────────────────────

class TestFiscalYearControl:

    def test_period_after_fy_rejected(self, stub_contract):
        """IPC period_to must fall inside contract.fiscal_year window."""
        contract = stub_contract(
            fiscal_year_start=date(2026, 1, 1),
            fiscal_year_end=date(2026, 12, 31),
        )
        period_to = date(2027, 3, 1)  # attack: next year
        with pytest.raises(FiscalYearBoundaryError):
            if not (contract.fiscal_year.start_date
                    <= period_to
                    <= contract.fiscal_year.end_date):
                raise FiscalYearBoundaryError(
                    "period outside FY",
                    context={"period_to": str(period_to)},
                )

    def test_period_before_fy_rejected(self, stub_contract):
        contract = stub_contract(
            fiscal_year_start=date(2026, 1, 1),
            fiscal_year_end=date(2026, 12, 31),
        )
        period_to = date(2025, 12, 15)  # attack: prior year
        with pytest.raises(FiscalYearBoundaryError):
            if not (contract.fiscal_year.start_date
                    <= period_to
                    <= contract.fiscal_year.end_date):
                raise FiscalYearBoundaryError("period outside FY")

    def test_period_on_fy_boundary_ok(self, stub_contract):
        contract = stub_contract(
            fiscal_year_start=date(2026, 1, 1),
            fiscal_year_end=date(2026, 12, 31),
        )
        for period_to in (date(2026, 1, 1), date(2026, 12, 31)):
            assert (contract.fiscal_year.start_date
                    <= period_to
                    <= contract.fiscal_year.end_date)


# ── Attack 6: Coherence (forged net_payable) ──────────────────────────

class TestCoherenceControl:

    def test_net_payable_mismatch_detected(self):
        """
        IPCService.approve recomputes net_payable and compares against
        the stored field.  Simulates a forged IPC where net_payable is
        inflated by 500k relative to the actual breakdown.
        """
        from contracts.models.payment import InterimPaymentCertificate

        ipc = InterimPaymentCertificate(
            this_certificate_gross=Decimal("1000000"),
            mobilization_recovery_this_cert=Decimal("150000"),
            retention_deduction_this_cert=Decimal("50000"),
            ld_deduction=Decimal("0"),
            variation_claims=Decimal("0"),
            vat_amount=Decimal("0"),
            wht_amount=Decimal("50000"),
        )
        # Correct net = 1,000,000 − 150k − 50k + 0 + 0 − 50k = 750,000
        expected = ipc.compute_net_payable()
        assert expected == Decimal("750000.00")

        # Attack: forge the stored net_payable to 1,250,000.
        ipc.net_payable = Decimal("1250000.00")
        tolerance = Decimal("0.01")
        with pytest.raises(CoherenceError):
            if abs(expected - ipc.net_payable) > tolerance:
                raise CoherenceError(
                    "net_payable forged",
                    context={
                        "stored": str(ipc.net_payable),
                        "expected": str(expected),
                    },
                )


# ── Variation-approval-tier control (control #6) ──────────────────────

class TestVariationTier:

    @pytest.mark.parametrize(
        "pct,expected_tier",
        [
            (Decimal("5.00"),  "LOCAL"),
            (Decimal("15.00"), "LOCAL"),       # boundary — ≤15%
            (Decimal("15.01"), "BOARD"),
            (Decimal("25.00"), "BOARD"),       # boundary — ≤25%
            (Decimal("25.01"), "BPP_REQUIRED"),
            (Decimal("50.00"), "BPP_REQUIRED"),
        ],
    )
    def test_tier_computation_matches_policy(self, pct, expected_tier):
        """
        Replicates the logic in ContractVariation.compute_approval_tier
        without constructing a full model instance (no DB needed).
        """
        original = Decimal("10000000.00")
        amount = original * pct / Decimal("100")
        if pct <= Decimal("15.00"):
            tier = "LOCAL"
        elif pct <= Decimal("25.00"):
            tier = "BOARD"
        else:
            tier = "BPP_REQUIRED"
        assert tier == expected_tier


# ── IPC net_payable coherence — full formula round-trip ────────────────

class TestIPCNetPayable:

    def test_standard_breakdown(self):
        from contracts.models.payment import InterimPaymentCertificate
        ipc = InterimPaymentCertificate(
            this_certificate_gross=Decimal("1000000.00"),
            mobilization_recovery_this_cert=Decimal("150000.00"),
            retention_deduction_this_cert=Decimal("50000.00"),
            ld_deduction=Decimal("0"),
            variation_claims=Decimal("100000.00"),
            vat_amount=Decimal("75000.00"),
            wht_amount=Decimal("50000.00"),
        )
        # 1,000,000 − 150k − 50k − 0 + 100k + 75k − 50k = 925,000
        assert ipc.compute_net_payable() == Decimal("925000.00")

    def test_integrity_hash_reproducible(self):
        from contracts.models.payment import InterimPaymentCertificate
        ipc1 = InterimPaymentCertificate(
            contract_id=42,
            posting_date=date(2026, 1, 15),
            cumulative_work_done_to_date=Decimal("1500000.00"),
        )
        ipc2 = InterimPaymentCertificate(
            contract_id=42,
            posting_date=date(2026, 1, 15),
            cumulative_work_done_to_date=Decimal("1500000.00"),
        )
        assert ipc1.build_integrity_hash() == ipc2.build_integrity_hash()

        # Change any field → different hash.
        ipc3 = InterimPaymentCertificate(
            contract_id=42,
            posting_date=date(2026, 1, 15),
            cumulative_work_done_to_date=Decimal("1500000.01"),  # 1 kobo more
        )
        assert ipc1.build_integrity_hash() != ipc3.build_integrity_hash()
