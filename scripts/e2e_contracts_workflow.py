"""
End-to-end smoke test for the contracts module against the delta_state
tenant schema.  Exercises:

    contract create -> activate -> milestones -> mobilization
 -> IPC #1 submit -> certify -> approve -> raise voucher -> mark paid
 -> IPC #2 submit -> certify -> approve -> raise voucher -> mark paid
 -> variation submit -> review -> approve  (ceiling increases)
 -> practical completion -> retention release (50%) -> paid
 -> defects liability -> final completion -> retention release (rest)
 -> contract close

Run from repo root via Django shell -c, loading this file's contents.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import traceback

from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context

# Silence noisy Celery/Redis connection errors from contracts.signals on_commit
# hooks — the e2e harness doesn't need real notification dispatch.
import logging
logging.getLogger("contracts.signals").setLevel(logging.CRITICAL)
logging.getLogger("celery").setLevel(logging.CRITICAL)
logging.getLogger("kombu").setLevel(logging.CRITICAL)

# Monkey-patch the Celery task .delay so enqueue failures don't pollute stderr.
try:
    from contracts import signals as _contracts_signals
    if hasattr(_contracts_signals, "notify_approval_assigned"):
        _orig_delay = _contracts_signals.notify_approval_assigned.delay
        def _safe_delay(*a, **kw):
            try:
                return _orig_delay(*a, **kw)
            except Exception:  # noqa: BLE001
                return None
        _contracts_signals.notify_approval_assigned.delay = _safe_delay
except Exception:  # noqa: BLE001
    pass

U = get_user_model()
RESET = True  # set False to resume from previous state


def step(name, fn):
    print(f"\n--- {name} " + "-" * max(0, 60 - len(name)))
    try:
        result = fn()
        print(f"  OK: {result}")
        return result
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


with schema_context("delta_state"):
    from procurement.models import Vendor
    from accounting.models.ncoa import AdministrativeSegment, NCoACode
    from accounting.models.advanced import FiscalYear
    from accounting.models.treasury import TreasuryAccount, PaymentVoucherGov
    from contracts.models import (
        Contract, ContractStatus, ContractType, IPCStatus,
        MilestoneSchedule, RetentionReleaseType, RetentionReleaseStatus,
    )
    from contracts.services.contract_activation import ContractActivationService
    from contracts.services.ipc_service import IPCService
    from contracts.services.variation_service import VariationService
    from contracts.services.retention_service import RetentionService
    from contracts.services.contract_closure_service import ContractClosureService

    admin = U.objects.get(username="admin")
    vendor = Vendor.objects.first()
    mda = AdministrativeSegment.objects.first()
    ncoa = NCoACode.objects.first()
    fy = FiscalYear.objects.get(year=2026)
    tsa = TreasuryAccount.objects.first()

    print(f"admin={admin}  vendor={vendor}  mda={mda}  ncoa={ncoa}  fy={fy}  tsa={tsa}")
    assert tsa is not None, "Need at least one TreasuryAccount seeded"

    # ── voucher helper ────────────────────────────────────────────────
    _pv_seq = {"n": 0}

    def make_voucher(*, gross, wht, payee, source):
        _pv_seq["n"] += 1
        num = f"E2E-PV-{_pv_seq['n']:04d}"
        return PaymentVoucherGov.objects.create(
            voucher_number=num,
            payment_type="VENDOR",
            ncoa_code=ncoa,
            payee_name=payee,
            payee_account="0123456789",
            payee_bank="CBN",
            gross_amount=gross,
            wht_amount=wht,
            net_amount=gross - wht,
            narration=f"E2E stub voucher for {source}",
            tsa_account=tsa,
            source_document=source,
            status="APPROVED",
            created_by=admin,
            updated_by=admin,
        )

    # 1. Create contract (DRAFT) — reuse if already seeded by earlier run
    existing = Contract.objects.filter(reference="E2E-001").first()
    if existing and RESET:
        print(f"  RESET=True — deleting prior contract id={existing.id}")
        existing.delete()  # cascades to IPCs, variations, milestones, releases
        PaymentVoucherGov.objects.filter(
            voucher_number__startswith="E2E-PV-").delete()
        existing = None
    if existing:
        print(f"  reusing existing contract id={existing.id} status={existing.status}")
        contract = existing
    else:
        def _create():
            c = Contract.objects.create(
                title="E2E Test Road Construction",
                description="Smoke-test contract for e2e harness",
                reference="E2E-001",
                contract_type=ContractType.WORKS,
                procurement_method="OPEN",
                vendor=vendor,
                mda=mda,
                ncoa_code=ncoa,
                fiscal_year=fy,
                original_sum=Decimal("10000000.00"),
                mobilization_rate=Decimal("15.00"),
                retention_rate=Decimal("10.00"),
                bpp_no_objection_ref="BPP-E2E-001",
                due_process_certificate="DPC-E2E-001",
                signed_date=date(2026, 2, 1),
                commencement_date=date(2026, 2, 10),
                contract_start_date=date(2026, 2, 10),
                contract_end_date=date(2026, 11, 30),
                defects_liability_period_days=365,
                created_by=admin,
                updated_by=admin,
            )
            return f"id={c.id} status={c.status}"
        step("Create DRAFT contract", _create)
        contract = Contract.objects.filter(reference="E2E-001").first()

    if not contract:
        print("ABORT: contract not created")
        raise SystemExit(1)

    # 2. Activate (idempotent guard)
    if contract.status == ContractStatus.DRAFT:
        step("Activate contract", lambda: ContractActivationService.activate(
            contract=contract, actor=admin, notes="e2e activation"
        ).status)
    contract.refresh_from_db()
    print(f"  contract.status now = {contract.status}")
    print(f"  contract_ceiling = {contract.contract_ceiling}")

    # 3. Milestones
    if not contract.milestones.exists():
        def _mile():
            m1 = MilestoneSchedule.objects.create(
                contract=contract, milestone_number=1,
                description="25% earthworks",
                scheduled_value=Decimal("2500000.00"),
                percentage_weight=Decimal("25.000"),
                target_date=date(2026, 4, 30),
                created_by=admin, updated_by=admin,
            )
            m2 = MilestoneSchedule.objects.create(
                contract=contract, milestone_number=2,
                description="50% base course",
                scheduled_value=Decimal("2500000.00"),
                percentage_weight=Decimal("25.000"),
                target_date=date(2026, 7, 31),
                created_by=admin, updated_by=admin,
            )
            return f"m1={m1.id} m2={m2.id}"
        step("Create milestone schedule", _mile)

    # ── IPC driver ───────────────────────────────────────────────────
    def run_ipc_cycle(*, label, posting_date, cumulative, payment_date, wht):
        print(f"\n========== {label} cumulative={cumulative} ==========")
        ipc = step(f"{label} submit", lambda: IPCService.submit_ipc(
            contract=contract,
            posting_date=posting_date,
            cumulative_work_done_to_date=cumulative,
            measurement_book=None,
            actor=admin,
        ))
        if not ipc:
            return None
        step(f"{label} certify", lambda: IPCService.certify(
            ipc=ipc, actor=admin, notes="certified").status)
        ipc.refresh_from_db()
        step(f"{label} approve", lambda: IPCService.approve(
            ipc=ipc, actor=admin, notes="approved").status)
        ipc.refresh_from_db()
        pv = make_voucher(
            gross=ipc.net_payable, wht=Decimal("0.00"),
            payee=str(vendor), source=f"Contract {contract.reference} {label}",
        )
        print(f"  stub voucher {pv.voucher_number} net={pv.net_amount}")
        step(f"{label} raise_voucher", lambda: IPCService.raise_voucher(
            ipc=ipc, payment_voucher_id=pv.id,
            voucher_gross=ipc.net_payable, actor=admin,
            notes="voucher raised").status)
        ipc.refresh_from_db()
        step(f"{label} mark_paid", lambda: IPCService.mark_paid(
            ipc=ipc, payment_date=payment_date,
            vat_amount=Decimal("0.00"), wht_amount=wht,
            actor=admin, notes="paid").status)
        ipc.refresh_from_db()
        print(f"  {label} final status = {ipc.status}")
        return ipc

    # 4. IPC #1 — 25% milestone
    if not contract.ipcs.exists():
        run_ipc_cycle(
            label="IPC#1",
            posting_date=date(2026, 5, 1),
            cumulative=Decimal("2500000.00"),
            payment_date=date(2026, 5, 15),
            wht=Decimal("125000.00"),
        )
    contract.refresh_from_db()
    bal = contract.balance
    print(f"\n  after IPC1: certified={bal.cumulative_gross_certified} "
          f"paid={bal.cumulative_gross_paid} retention={bal.retention_held}")

    # 5. IPC #2 — cumulative jumps to 5M
    if contract.ipcs.count() < 2:
        run_ipc_cycle(
            label="IPC#2",
            posting_date=date(2026, 8, 1),
            cumulative=Decimal("5000000.00"),
            payment_date=date(2026, 8, 15),
            wht=Decimal("125000.00"),
        )
    contract.refresh_from_db()
    bal = contract.balance
    print(f"\n  after IPC2: certified={bal.cumulative_gross_certified} "
          f"paid={bal.cumulative_gross_paid} retention={bal.retention_held}")

    # 6. Variation (ADDITION N1,000,000 — LOCAL tier: 10% of 10M)
    from contracts.models import ContractVariation, VariationType, VariationStatus
    var = ContractVariation.objects.filter(contract=contract).first()
    if not var:
        def _var():
            v = ContractVariation.objects.create(
                contract=contract,
                variation_number=1,
                variation_type=VariationType.ADDITION,
                description="Scope addition — drainage works",
                justification="Unforeseen drainage required after geotech survey",
                amount=Decimal("1000000.00"),
                time_extension_days=30,
                created_by=admin,
                updated_by=admin,
            )
            return f"id={v.id} status={v.status} tier={v.approval_tier}"
        step("Create variation (DRAFT)", _var)
        var = ContractVariation.objects.filter(contract=contract).first()

    if var and var.status == VariationStatus.DRAFT:
        step("Variation submit", lambda: VariationService.submit(
            variation=var, actor=admin, notes="submit").status)
        var.refresh_from_db()
    if var and var.status == VariationStatus.SUBMITTED:
        step("Variation review", lambda: VariationService.review(
            variation=var, actor=admin, notes="tech review").status)
        var.refresh_from_db()
    if var and var.status == VariationStatus.REVIEWED:
        step("Variation approve", lambda: VariationService.approve(
            variation=var, actor=admin, notes="approved").status)

    contract.refresh_from_db()
    print(f"\n  final ceiling after variation = {contract.contract_ceiling}")
    print(f"  contract status = {contract.status}")

    # 6b. Transition ACTIVATED -> IN_PROGRESS (manual "work commenced")
    if contract.status == ContractStatus.ACTIVATED:
        step("Transition to IN_PROGRESS", lambda: (
            contract.transition_to(ContractStatus.IN_PROGRESS, actor=admin),
            contract.save(),
            contract.status,
        )[-1])
        contract.refresh_from_db()

    # 7. Practical completion
    if contract.status == ContractStatus.IN_PROGRESS:
        step("Issue practical completion", lambda: ContractClosureService.issue_practical_completion(
            contract=contract,
            issued_date=date(2026, 10, 1),
            effective_date=date(2026, 10, 1),
            actor=admin,
            notes="Practical completion certificate — e2e",
        ).certificate_type)
    contract.refresh_from_db()
    print(f"  contract.status = {contract.status}")

    # 8. Practical retention release — 50% of held
    if contract.status == ContractStatus.PRACTICAL_COMPLETION:
        rel1 = step("Practical retention create", lambda: RetentionService.create_release(
            contract=contract,
            release_type=RetentionReleaseType.PRACTICAL_COMPLETION,
            actor=admin,
        ))
        if rel1:
            step("Practical retention approve", lambda: RetentionService.approve(
                release=rel1, actor=admin, notes="approved").status)
            rel1.refresh_from_db()
            pv_ret1 = make_voucher(
                gross=rel1.amount, wht=Decimal("0.00"),
                payee=str(vendor), source=f"Retention practical {contract.reference}",
            )
            step("Practical retention mark_paid", lambda: RetentionService.mark_paid(
                release=rel1, payment_voucher_id=pv_ret1.id,
                payment_date=date(2026, 10, 10), actor=admin).status)

    # 9. Defects liability
    contract.refresh_from_db()
    if contract.status == ContractStatus.PRACTICAL_COMPLETION:
        step("Enter defects liability", lambda: ContractClosureService.enter_defects_liability(
            contract=contract, actor=admin, notes="12-month DLP start"
        ).status)

    # 10. Final completion
    contract.refresh_from_db()
    if contract.status == ContractStatus.DEFECTS_LIABILITY:
        step("Issue final completion", lambda: ContractClosureService.issue_final_completion(
            contract=contract,
            issued_date=date(2027, 10, 1),
            effective_date=date(2027, 10, 1),
            actor=admin,
            notes="Final completion certificate — e2e",
        ).certificate_type)

    # 11. Final retention release
    contract.refresh_from_db()
    if contract.status == ContractStatus.FINAL_COMPLETION:
        rel2 = step("Final retention create", lambda: RetentionService.create_release(
            contract=contract,
            release_type=RetentionReleaseType.FINAL_COMPLETION,
            actor=admin,
        ))
        if rel2:
            step("Final retention approve", lambda: RetentionService.approve(
                release=rel2, actor=admin, notes="approved").status)
            rel2.refresh_from_db()
            pv_ret2 = make_voucher(
                gross=rel2.amount, wht=Decimal("0.00"),
                payee=str(vendor), source=f"Retention final {contract.reference}",
            )
            step("Final retention mark_paid", lambda: RetentionService.mark_paid(
                release=rel2, payment_voucher_id=pv_ret2.id,
                payment_date=date(2027, 10, 10), actor=admin).status)

    # 12. Close
    contract.refresh_from_db()
    bal = contract.balance
    print(f"\n  pre-close: certified={bal.cumulative_gross_certified} "
          f"paid={bal.cumulative_gross_paid} "
          f"retention held={bal.retention_held} released={bal.retention_released}")
    if contract.status == ContractStatus.FINAL_COMPLETION:
        step("Close contract", lambda: ContractClosureService.close(
            contract=contract, actor=admin, notes="closed — e2e"
        ).status)

    contract.refresh_from_db()
    print(f"\n=== FINAL: contract.status = {contract.status} ===")

print("\n=== e2e harness complete ===")
