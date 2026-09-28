"""A contract write-up (ADDITION variation) may not exceed the budget available
on the contract's appropriation. The cap is enforced at create AND at approve,
against the appropriation's ``available_balance`` (amount_approved − committed −
expended), resolved from the contract's MDA × NCoA economic/fund × fiscal year.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.django_db(transaction=True)
class TestVariationBudgetCap:

    def test_headroom_resolves_to_appropriation_available(
        self, activated_contract, appropriation,
    ):
        from contracts.services import VariationService
        headroom = VariationService.appropriation_headroom(activated_contract)
        assert headroom is not None
        assert headroom == appropriation.available_balance

    def test_create_within_budget_is_allowed(
        self, activated_contract, appropriation, drafter,
    ):
        from contracts.models import VariationStatus
        from contracts.services import VariationService
        v = VariationService.create_draft(
            contract=activated_contract,
            variation_type="ADDITION",
            amount=Decimal("1000000.00"),  # well under the ₦500M appropriation
            description="Extra drainage",
            justification="Site instruction 12",
            actor=drafter,
        )
        assert v.status == VariationStatus.DRAFT
        assert v.variation_number == 1
        assert v.amount == Decimal("1000000.00")

    def test_create_over_budget_is_rejected(
        self, activated_contract, appropriation, drafter,
    ):
        from contracts.services import VariationService
        from contracts.services.exceptions import InvalidTransitionError
        headroom = VariationService.appropriation_headroom(activated_contract)
        with pytest.raises(InvalidTransitionError, match="exceeds the budget available"):
            VariationService.create_draft(
                contract=activated_contract,
                variation_type="ADDITION",
                amount=headroom + Decimal("1.00"),
                description="Too big",
                justification="Over the appropriation",
                actor=drafter,
            )

    def test_assert_helper_is_noop_for_omission(
        self, activated_contract, appropriation,
    ):
        """A negative/zero delta (omission, EOT) is never capped."""
        from contracts.services import VariationService
        # Should not raise even though the number is enormous — delta <= 0.
        VariationService.assert_increase_within_budget(
            activated_contract, Decimal("-999999999.00"),
        )
