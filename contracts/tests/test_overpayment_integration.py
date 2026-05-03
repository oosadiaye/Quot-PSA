"""
D7 — Integration & overpayment-attack test suite.

Every attack below is executed against a REAL Contract + ContractBalance
inside the tenant schema, with the full service-layer pipeline
(SELECT FOR UPDATE, version bump, DB trigger) in scope. These tests
are the structural proof that overpayment is IMPOSSIBLE, not merely
discouraged.

Attack matrix (must be 100 % pass):

    #1  Single IPC gross > ceiling
    #2  Two serial IPCs summing > ceiling
    #3  Pending voucher + new IPC > ceiling
    #4  Cumulative work-done goes backwards (monotonicity)
    #5  IPC period_to outside contract fiscal year
    #6  Duplicate IPC (same period + cumulative)          → DB unique index
    #7  Retention release > held                          → DB CheckConstraint
    #8  Mobilization recovery > paid                      → DB CheckConstraint
    #9  paid > certified                                   → DB CheckConstraint
    #10 Direct ORM tamper of ContractBalance (trigger guard)
    #11 Segregation of duties — self-approval rejected
    #12 IPC on non-ACTIVE contract
    #13 Mark-paid twice (state machine blocks)
    #14 Voucher gross ≠ IPC net_payable (3-way match)
    #15 Happy path: full DRAFT → PAID lifecycle
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from contracts.models import (
    ContractBalance,
    ContractStatus,
    InterimPaymentCertificate,
    IPCStatus,
)
from contracts.services.exceptions import (
    CeilingBreachError,
    FiscalYearBoundaryError,
    InvalidTransitionError,
    MobilizationRecoveryError,
    MonotonicityError,
    RetentionCapError,
    SegregationOfDutiesError,
    ThreeWayMatchError,
)
from contracts.services.ipc_service import IPCService
from contracts.services.retention_service import RetentionService


# ── Helpers ────────────────────────────────────────────────────────────

def _submit(contract, drafter, *, cumulative, posting_date=None, **_legacy):
    """Submit an IPC with sensible defaults.

    The ``**_legacy`` sink absorbs the deprecated ``period_from`` /
    ``period_to`` kwargs that older tests still pass; only ``posting_date``
    flows through to the service. If not supplied, we derive it from the
    legacy ``period_from`` (kept for test-data backwards compatibility).
    """
    if posting_date is None:
        posting_date = _legacy.get("period_from") or date(2026, 2, 1)
    return IPCService.submit_ipc(
        contract=contract,
        posting_date=posting_date,
        cumulative_work_done_to_date=Decimal(cumulative),
        measurement_book=None,
        actor=drafter,
    )


# ── #1 Ceiling: single IPC over ceiling ────────────────────────────────

class TestCeilingControl:

    def test_single_ipc_over_ceiling_rejected(self, activated_contract, drafter):
        """Ceiling = 100 M; attempt to certify 100,000,001 — must raise."""
        with pytest.raises(CeilingBreachError) as exc:
            _submit(activated_contract, drafter, cumulative="100000001.00")
        assert "ceiling" in str(exc.value).lower()
        # No balance pollution: pending_voucher must still be 0.
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert bal.pending_voucher_amount == Decimal("0.00")
        assert bal.cumulative_gross_certified == Decimal("0.00")

    # ── #2 Ceiling: two serial IPCs exceed ceiling ─────────────────────

    def test_two_serial_ipcs_exceed_ceiling_blocks_second(
        self, activated_contract, drafter,
    ):
        first = _submit(activated_contract, drafter, cumulative="60000000.00")
        assert first.status == IPCStatus.SUBMITTED
        # A second IPC claiming an extra 45 M would push committed to 105 M.
        with pytest.raises(CeilingBreachError):
            _submit(
                activated_contract, drafter,
                cumulative="105000000.00",
                period_from=date(2026, 3, 1),
                period_to=date(2026, 3, 31),
            )

    # ── #3 Pending voucher reserves room ───────────────────────────────

    def test_pending_voucher_reserves_ceiling_room(
        self, activated_contract, drafter,
    ):
        """
        Once submitted, the IPC's gross is held in pending_voucher_amount.
        A concurrent IPC trying to use the same headroom must fail even
        before the first one is approved.
        """
        _submit(activated_contract, drafter, cumulative="90000000.00")
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert bal.pending_voucher_amount == Decimal("90000000.00")

        # Another 20 M would overflow the 100 M ceiling.
        with pytest.raises(CeilingBreachError):
            _submit(
                activated_contract, drafter,
                cumulative="110000000.00",
                period_from=date(2026, 3, 1),
                period_to=date(2026, 3, 31),
            )


# ── #4 Monotonicity ────────────────────────────────────────────────────

class TestMonotonicity:

    def test_cumulative_work_cannot_decrease(
        self, activated_contract, drafter, certifier, approver,
    ):
        """
        After approving an IPC at 30 M cumulative, a second IPC claiming
        25 M cumulative (i.e. work went backwards) must be rejected.
        """
        ipc1 = _submit(activated_contract, drafter, cumulative="30000000.00")
        IPCService.certify(ipc=ipc1, actor=certifier)
        IPCService.approve(ipc=ipc1, actor=approver)

        with pytest.raises(MonotonicityError):
            _submit(
                activated_contract, drafter,
                cumulative="25000000.00",
                period_from=date(2026, 3, 1),
                period_to=date(2026, 3, 31),
            )


# ── #5 Fiscal year boundary ────────────────────────────────────────────

class TestFiscalYearBoundary:

    def test_ipc_period_outside_contract_fy_rejected(
        self, activated_contract, drafter,
    ):
        with pytest.raises(FiscalYearBoundaryError):
            _submit(
                activated_contract, drafter,
                cumulative="5000000.00",
                period_from=date(2027, 1, 1),
                period_to=date(2027, 1, 31),
            )


# ── #6 Duplicate IPC ───────────────────────────────────────────────────

class TestDuplicateIPC:

    def test_same_period_and_cumulative_rejected_by_db(
        self, activated_contract, drafter,
    ):
        """
        The partial unique index on integrity_hash fires at save() time.
        Two IPCs with identical contract/period_from/period_to/cumulative
        must collide.
        """
        from contracts.services.exceptions import DuplicateIPCError

        _submit(activated_contract, drafter, cumulative="10000000.00")
        with pytest.raises(DuplicateIPCError):
            # Exact same period + cumulative.
            _submit(activated_contract, drafter, cumulative="10000000.00")


# ── #7 Retention cap ───────────────────────────────────────────────────

class TestRetentionCap:

    def test_apply_deduction_negative_rejected(self, activated_contract):
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        with pytest.raises(RetentionCapError):
            RetentionService.apply_deduction(
                balance=bal,
                deduction_amount=Decimal("-1.00"),
            )

    def test_release_over_held_rejected_by_constraint(
        self, activated_contract,
    ):
        """
        Direct ORM attempt to raise retention_released above retention_held
        must be rejected by the CheckConstraint
        ``contracts_balance_retention_released_lte_held``.
        """
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        bal.retention_held = Decimal("100000.00")
        bal.retention_released = Decimal("0.00")
        bal.version += 1
        bal.save(update_fields=["retention_held", "retention_released", "version"])

        bal.retention_released = Decimal("150000.00")  # attack
        bal.version += 1
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                bal.save(update_fields=["retention_released", "version"])


# ── #8 Mobilization over-recovery ──────────────────────────────────────

class TestMobilizationRecovery:

    def test_over_recovery_via_service_rejected(self, activated_contract):
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        bal.mobilization_paid = Decimal("1000000.00")
        bal.mobilization_recovered = Decimal("999000.00")
        bal.version += 1
        bal.save(update_fields=["mobilization_paid", "mobilization_recovered", "version"])

        from contracts.services.mobilization_service import MobilizationService
        with pytest.raises(MobilizationRecoveryError):
            MobilizationService.apply_recovery(
                balance=bal,
                recovery_amount=Decimal("5000.00"),  # total 1,004,000 > paid
            )

    def test_over_recovery_via_direct_orm_rejected_by_constraint(
        self, activated_contract,
    ):
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        bal.mobilization_paid = Decimal("500000.00")
        bal.mobilization_recovered = Decimal("0.00")
        bal.version += 1
        bal.save(update_fields=["mobilization_paid", "mobilization_recovered", "version"])

        bal.mobilization_recovered = Decimal("500001.00")  # 1 kobo over
        bal.version += 1
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                bal.save(update_fields=["mobilization_recovered", "version"])


# ── #9 paid > certified ────────────────────────────────────────────────

class TestPaidLteCertified:

    def test_paid_cannot_exceed_certified(self, activated_contract):
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        bal.cumulative_gross_certified = Decimal("1000000.00")
        bal.cumulative_gross_paid = Decimal("0.00")
        bal.version += 1
        bal.save(update_fields=[
            "cumulative_gross_certified", "cumulative_gross_paid", "version",
        ])

        bal.cumulative_gross_paid = Decimal("1000000.01")  # 1 kobo over certified
        bal.version += 1
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                bal.save(update_fields=["cumulative_gross_paid", "version"])


# ── #10 Direct ORM tamper ──────────────────────────────────────────────

class TestDbTriggerLastLine:

    def test_negative_certified_rejected(self, activated_contract):
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        bal.cumulative_gross_certified = Decimal("-1.00")  # attack
        bal.version += 1
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                bal.save(update_fields=["cumulative_gross_certified", "version"])

    def test_negative_paid_rejected(self, activated_contract):
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        bal.cumulative_gross_paid = Decimal("-0.01")
        bal.version += 1
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                bal.save(update_fields=["cumulative_gross_paid", "version"])


# ── #11 Segregation of Duties ──────────────────────────────────────────

class TestSegregationOfDuties:

    def test_drafter_cannot_certify_own_ipc(
        self, activated_contract, drafter,
    ):
        ipc = _submit(activated_contract, drafter, cumulative="5000000.00")
        with pytest.raises(SegregationOfDutiesError):
            IPCService.certify(ipc=ipc, actor=drafter)

    def test_certifier_cannot_approve_own_certification(
        self, activated_contract, drafter, certifier,
    ):
        ipc = _submit(activated_contract, drafter, cumulative="5000000.00")
        IPCService.certify(ipc=ipc, actor=certifier)
        with pytest.raises(SegregationOfDutiesError):
            IPCService.approve(ipc=ipc, actor=certifier)

    def test_approver_cannot_raise_voucher(
        self, activated_contract, drafter, certifier, approver,
    ):
        ipc = _submit(activated_contract, drafter, cumulative="5000000.00")
        IPCService.certify(ipc=ipc, actor=certifier)
        IPCService.approve(ipc=ipc, actor=approver)
        with pytest.raises(SegregationOfDutiesError):
            IPCService.raise_voucher(
                ipc=ipc, payment_voucher_id=1,
                voucher_gross=ipc.net_payable, actor=approver,
            )


# ── #12 Contract not active ────────────────────────────────────────────

class TestContractStatusGate:

    def test_ipc_on_draft_contract_rejected(self, draft_contract, drafter):
        with pytest.raises(InvalidTransitionError):
            _submit(draft_contract, drafter, cumulative="5000000.00")


# ── #13 State machine: forward-only ────────────────────────────────────

class TestStateMachine:

    def test_cannot_skip_certification(
        self, activated_contract, drafter, approver,
    ):
        ipc = _submit(activated_contract, drafter, cumulative="5000000.00")
        with pytest.raises(InvalidTransitionError):
            IPCService.approve(ipc=ipc, actor=approver)

    def test_cannot_double_pay(
        self, activated_contract, drafter, certifier, approver,
        voucher_raiser, payer, payment_voucher,
    ):
        ipc = _submit(activated_contract, drafter, cumulative="5000000.00")
        IPCService.certify(ipc=ipc, actor=certifier)
        IPCService.approve(ipc=ipc, actor=approver)
        IPCService.raise_voucher(
            ipc=ipc, payment_voucher_id=payment_voucher.id,
            voucher_gross=ipc.net_payable, actor=voucher_raiser,
        )
        IPCService.mark_paid(
            ipc=ipc, payment_date=date(2026, 3, 10),
            vat_amount=Decimal("0"), wht_amount=Decimal("0"),
            actor=payer,
        )
        # Second mark_paid must fail — IPC is terminal at PAID.
        with pytest.raises(InvalidTransitionError):
            IPCService.mark_paid(
                ipc=ipc, payment_date=date(2026, 3, 11),
                vat_amount=Decimal("0"), wht_amount=Decimal("0"),
                actor=payer,
            )


# ── #14 Three-way match ────────────────────────────────────────────────

class TestThreeWayMatch:

    def test_voucher_gross_must_match_ipc_net_payable(
        self, activated_contract, drafter, certifier, approver, voucher_raiser,
    ):
        ipc = _submit(activated_contract, drafter, cumulative="5000000.00")
        IPCService.certify(ipc=ipc, actor=certifier)
        IPCService.approve(ipc=ipc, actor=approver)

        forged = ipc.net_payable + Decimal("500000.00")  # attack: inflate
        with pytest.raises(ThreeWayMatchError):
            IPCService.raise_voucher(
                ipc=ipc, payment_voucher_id=1,
                voucher_gross=forged, actor=voucher_raiser,
            )


# ── #15 Happy path ─────────────────────────────────────────────────────

class TestHappyPath:

    def test_full_ipc_lifecycle_updates_balance_correctly(
        self, activated_contract, drafter, certifier, approver,
        voucher_raiser, payer, payment_voucher,
    ):
        """
        DRAFT contract → activated (done by fixture) → full IPC cycle:
        submit (30 M) → certify → approve → voucher → paid.

        Asserts ContractBalance progression at each stage.
        """
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert bal.contract_ceiling == Decimal("100000000.00")
        assert bal.cumulative_gross_certified == Decimal("0.00")
        assert bal.pending_voucher_amount == Decimal("0.00")

        # Submit
        ipc = _submit(activated_contract, drafter, cumulative="30000000.00")
        assert ipc.status == IPCStatus.SUBMITTED
        bal.refresh_from_db()
        assert bal.pending_voucher_amount == Decimal("30000000.00")
        assert bal.cumulative_gross_certified == Decimal("0.00")

        # Certify
        IPCService.certify(ipc=ipc, actor=certifier)
        assert ipc.status == IPCStatus.CERTIFIER_REVIEWED

        # Approve → moves gross from pending → certified
        IPCService.approve(ipc=ipc, actor=approver)
        bal.refresh_from_db()
        assert bal.cumulative_gross_certified == Decimal("30000000.00")
        assert bal.pending_voucher_amount == Decimal("0.00")
        assert ipc.status == IPCStatus.APPROVED

        # Voucher
        IPCService.raise_voucher(
            ipc=ipc, payment_voucher_id=payment_voucher.id,
            voucher_gross=ipc.net_payable, actor=voucher_raiser,
        )
        assert ipc.status == IPCStatus.VOUCHER_RAISED

        # Paid
        IPCService.mark_paid(
            ipc=ipc, payment_date=date(2026, 3, 10),
            vat_amount=Decimal("0"), wht_amount=Decimal("0"),
            actor=payer,
        )
        bal.refresh_from_db()
        assert ipc.status == IPCStatus.PAID
        assert bal.cumulative_gross_paid == Decimal("30000000.00")
        assert bal.cumulative_gross_certified == Decimal("30000000.00")
        # paid ≤ certified invariant holds.
        assert bal.cumulative_gross_paid <= bal.cumulative_gross_certified

    def test_reject_releases_pending_reservation(
        self, activated_contract, drafter, certifier,
    ):
        ipc = _submit(activated_contract, drafter, cumulative="20000000.00")
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert bal.pending_voucher_amount == Decimal("20000000.00")

        IPCService.reject(ipc=ipc, actor=certifier, reason="QS rejected measurements")

        bal.refresh_from_db()
        assert bal.pending_voucher_amount == Decimal("0.00")
        assert ipc.status == IPCStatus.REJECTED
