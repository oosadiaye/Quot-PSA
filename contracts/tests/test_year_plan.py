"""Structural unit tests for the multi-year ContractYearPlan feature.

All ``SimpleTestCase`` — no DB. Pins:
  * Model fields, Meta constraints, ordering, unique_together
  * The activation service's signature + tolerance constant
  * That ``_validate_or_create_year_plans`` is callable with a single
    contract argument

DB-backed integration tests (sum-mismatch rejection, multi-year IPC
posting acceptance, Year-2 boundary) live in
``test_overpayment_integration.py`` once the conftest fixtures grow
multi-year support — out of scope for this slice.
"""
from __future__ import annotations

from decimal import Decimal
import inspect

from django.test import SimpleTestCase


class ContractYearPlanModelShapeTests(SimpleTestCase):
    """Pin the exact fields + meta options. Catches accidental drift
    in a future migration that would silently weaken the invariant."""

    def test_model_is_importable_from_contracts_models(self):
        from contracts.models import ContractYearPlan
        self.assertIsNotNone(ContractYearPlan)

    def test_required_fields_present(self):
        from contracts.models import ContractYearPlan
        field_names = {f.name for f in ContractYearPlan._meta.get_fields()}
        for required in (
            "contract", "fiscal_year", "appropriation",
            "planned_amount", "carried_forward_from_prior_year",
            "sequence",
        ):
            self.assertIn(required, field_names, f"missing field: {required}")

    def test_planned_amount_decimal_precision(self):
        """20-digit / 2-decimal matches Contract.original_sum so the
        sum-equals-original-sum invariant doesn't get bitten by
        precision mismatch."""
        from contracts.models import ContractYearPlan
        f = ContractYearPlan._meta.get_field("planned_amount")
        self.assertEqual(f.max_digits, 20)
        self.assertEqual(f.decimal_places, 2)

    def test_unique_together_contract_fiscal_year(self):
        """Prevents two year plans for the same (contract, fiscal_year)
        — the foundation of the sum-equals-original-sum invariant."""
        from contracts.models import ContractYearPlan
        uts = ContractYearPlan._meta.unique_together
        # Django stores unique_together as a tuple-of-tuples.
        flat = {tuple(sorted(t)) for t in uts}
        self.assertIn(tuple(sorted(["contract", "fiscal_year"])), flat)

    def test_check_constraints_present(self):
        """Three CHECK constraints at DB level — these are what
        catch a non-positive planned_amount or sequence even if the
        Python validator is bypassed (e.g. raw SQL, fixtures)."""
        from contracts.models import ContractYearPlan
        names = {c.name for c in ContractYearPlan._meta.constraints}
        self.assertIn("contract_year_plan_planned_positive", names)
        self.assertIn("contract_year_plan_sequence_positive", names)
        self.assertIn("contract_year_plan_carryforward_non_negative", names)

    def test_appropriation_is_nullable(self):
        """Year 2..N appropriations may not exist at contract activation
        time (Year-2 Appropriation Act enacts later); the FK must be
        nullable so the operator can populate it later via PATCH."""
        from contracts.models import ContractYearPlan
        f = ContractYearPlan._meta.get_field("appropriation")
        self.assertTrue(f.null)
        self.assertTrue(f.blank)

    def test_total_authorised_property(self):
        """``total_authorised_for_year`` = planned + carried_forward,
        with safe defaults if either is None."""
        from contracts.models import ContractYearPlan
        plan = ContractYearPlan(
            planned_amount=Decimal("100.00"),
            carried_forward_from_prior_year=Decimal("25.00"),
        )
        self.assertEqual(plan.total_authorised_for_year, Decimal("125.00"))

        plan_zero_carry = ContractYearPlan(planned_amount=Decimal("100.00"))
        self.assertEqual(
            plan_zero_carry.total_authorised_for_year, Decimal("100.00"),
        )


class ActivationServiceShapeTests(SimpleTestCase):
    """The activation hook and tolerance must remain stable so tests
    + future maintainers can rely on the contract."""

    def test_validate_or_create_year_plans_is_classmethod(self):
        from contracts.services.contract_activation import ContractActivationService
        method = inspect.getattr_static(
            ContractActivationService, "_validate_or_create_year_plans",
        )
        self.assertIsInstance(method, classmethod)

    def test_sum_tolerance_is_kobo_level(self):
        """₦0.10 is the maximum drift the activation accepts. Tighter
        than this trips on legitimate two-decimal-place arithmetic;
        looser would accept material rounding errors."""
        from contracts.services.contract_activation import ContractActivationService
        self.assertEqual(
            ContractActivationService._SUM_TOLERANCE,
            Decimal("0.10"),
        )

    def test_validator_called_during_activate(self):
        """``activate`` must call the year-plan validator. Verified by
        reading the source — a future refactor that drops the call
        would leave the multi-year invariant unenforced."""
        import inspect as _inspect
        from contracts.services.contract_activation import ContractActivationService
        src = _inspect.getsource(ContractActivationService.activate)
        self.assertIn(
            "_validate_or_create_year_plans", src,
            "ContractActivationService.activate must invoke "
            "_validate_or_create_year_plans before flipping status",
        )


class IPCFiscalBoundaryShapeTests(SimpleTestCase):
    """Control 8 must read from year_plans, not contract.fiscal_year
    directly. Verified by source inspection."""

    def test_submit_ipc_uses_year_plans(self):
        import inspect as _inspect
        from contracts.services.ipc_service import IPCService
        src = _inspect.getsource(IPCService.submit_ipc)
        self.assertIn(
            "year_plans", src,
            "IPCService.submit_ipc Control 8 must look up posting_date "
            "against contract.year_plans (not contract.fiscal_year alone)",
        )
        self.assertIn(
            "FiscalYearBoundaryError", src,
            "Control 8 still raises FiscalYearBoundaryError on a "
            "posting_date that doesn't fall in any year plan.",
        )
