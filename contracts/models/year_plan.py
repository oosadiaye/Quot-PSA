"""
ContractYearPlan — multi-year contract payment-plan rows.
=========================================================
Public-sector contracts (typically capital projects: roads, hospitals,
buildings) routinely run 18–36 months. The Appropriation Act, however,
is annual — each fiscal year requires its own legislative authority to
spend. To reconcile these two realities, every active contract is
backed by one ``ContractYearPlan`` row per fiscal year it touches.

Invariants
----------
* ``sum(year_plans.planned_amount) == contract.original_sum`` —
  enforced at activation time by ``ContractActivationService``.
* ``unique_together(contract, fiscal_year)`` — one plan per year,
  no double-counting of a single year's spend.
* ``planned_amount > 0`` — DB-level CheckConstraint.
* Each plan's ``fiscal_year`` is what gates IPC posting (Control 8 in
  ``IPCService.submit_ipc``): a posting_date must fall inside SOME
  year_plan's fiscal_year, not just ``Contract.fiscal_year``.

Single-year contracts get exactly one ``ContractYearPlan`` row created
automatically — either by the activation flow when the operator
declines to define a multi-year breakdown, or by the data migration
backfill for legacy contracts that pre-date this feature.

IPSAS 24 alignment
-------------------
Each year plan independently consumes its fiscal year's appropriation
and contributes to that year's Budget Performance variance disclosure.
Carried-forward unspent commitments from a prior year (when the tenant
operates carry-over policy rather than lapse) are recorded on
``carried_forward_from_prior_year`` so the IPSAS 24 narrative can
distinguish "prior-year spillover" from "current-year spend".
"""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from core.models import AuditBaseModel


ZERO = Decimal("0.00")


class ContractYearPlan(AuditBaseModel):
    """One fiscal-year slice of a contract's payment plan.

    Rows are sequenced 1..N chronologically. Year 1's appropriation is
    typically known at contract activation; Years 2..N may have their
    appropriation FK populated later (at the time that year's
    Appropriation Act is enacted), which is why ``appropriation`` is
    nullable.
    """

    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="year_plans",
    )
    fiscal_year = models.ForeignKey(
        "accounting.FiscalYear",
        on_delete=models.PROTECT,
        related_name="contract_year_plans",
        help_text="Fiscal year this slice covers; gates IPC posting in that year",
    )
    appropriation = models.ForeignKey(
        "budget.Appropriation",
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="contract_year_plans",
        help_text=(
            "Budget appropriation that authorises this year's planned "
            "spend. Required at contract activation for the primary "
            "year; subsequent years may have it assigned later (typically "
            "when that year's Appropriation Act is enacted)."
        ),
    )
    planned_amount = models.DecimalField(
        max_digits=20, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Planned IPC spend for this fiscal year (NGN, > 0)",
    )
    carried_forward_from_prior_year = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text=(
            "Unspent commitment carried over from the prior year's plan "
            "(when tenant policy is carry-over, not lapse). Disclosed "
            "in the IPSAS 24 variance narrative as 'prior-year "
            "spillover' so it doesn't distort current-year variance."
        ),
    )
    sequence = models.PositiveSmallIntegerField(
        help_text="1, 2, 3 … chronological order of fiscal years for this contract",
    )

    class Meta:
        ordering = ["contract", "sequence"]
        unique_together = [("contract", "fiscal_year")]
        constraints = [
            models.CheckConstraint(
                check=models.Q(planned_amount__gt=ZERO),
                name="contract_year_plan_planned_positive",
            ),
            models.CheckConstraint(
                check=models.Q(sequence__gte=1),
                name="contract_year_plan_sequence_positive",
            ),
            models.CheckConstraint(
                check=models.Q(carried_forward_from_prior_year__gte=ZERO),
                name="contract_year_plan_carryforward_non_negative",
            ),
        ]
        verbose_name = "Contract Year Plan"
        verbose_name_plural = "Contract Year Plans"

    def __str__(self) -> str:
        return (
            f"{getattr(self.contract, 'contract_number', self.contract_id)} "
            f"· Year {self.sequence} · FY {self.fiscal_year}"
        )

    @property
    def total_authorised_for_year(self) -> Decimal:
        """Year's spend ceiling = planned + carried-forward.

        This is the figure the year's appropriation must cover. The
        Budget Execution Report sums this across all year plans hitting
        a given appropriation when computing committed-vs-available.
        """
        return (self.planned_amount or ZERO) + (
            self.carried_forward_from_prior_year or ZERO
        )
