"""
Contract & ContractBalance models
==================================
The Contract is the root aggregate.  ContractBalance is a single-row
ledger per contract that enforces the payment-ceiling invariants at the
database layer via CheckConstraints and a PostgreSQL trigger (in migration
0002_contract_balance_trigger.py).

Money invariants (all enforced at DB level):
  cumulative_gross_paid  ≤ cumulative_gross_certified
  cumulative_gross_certified + pending_voucher_amount ≤ contract_ceiling
  mobilization_recovered ≤ mobilization_paid
  retention_released     ≤ retention_held
"""
from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel, quantize_currency

if TYPE_CHECKING:
    from contracts.models.variation import ContractVariation

# ── Constants ──────────────────────────────────────────────────────────
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


# ── Choices ────────────────────────────────────────────────────────────

class ContractType(models.TextChoices):
    WORKS           = "WORKS",          "Works (Civil / Construction)"
    GOODS           = "GOODS",          "Goods / Supply"
    CONSULTANCY     = "CONSULTANCY",    "Consultancy Services"
    NON_CONSULTANCY = "NON_CONSULTANCY","Non-Consultancy Services"


class ContractStatus(models.TextChoices):
    DRAFT                 = "DRAFT",                 "Draft"
    ACTIVATED             = "ACTIVATED",             "Activated"
    IN_PROGRESS           = "IN_PROGRESS",           "In Progress"
    PRACTICAL_COMPLETION  = "PRACTICAL_COMPLETION",  "Practical Completion"
    DEFECTS_LIABILITY     = "DEFECTS_LIABILITY",     "Defects Liability Period"
    FINAL_COMPLETION      = "FINAL_COMPLETION",      "Final Completion"
    CLOSED                = "CLOSED",                "Closed"


ALLOWED_CONTRACT_TRANSITIONS: dict[str, list[str]] = {
    ContractStatus.DRAFT:                [ContractStatus.ACTIVATED],
    ContractStatus.ACTIVATED:            [ContractStatus.IN_PROGRESS],
    ContractStatus.IN_PROGRESS:          [ContractStatus.PRACTICAL_COMPLETION],
    ContractStatus.PRACTICAL_COMPLETION: [ContractStatus.DEFECTS_LIABILITY],
    ContractStatus.DEFECTS_LIABILITY:    [ContractStatus.FINAL_COMPLETION],
    ContractStatus.FINAL_COMPLETION:     [ContractStatus.CLOSED],
    ContractStatus.CLOSED:               [],  # terminal
}


class ProcurementMethod(models.TextChoices):
    OPEN_TENDER      = "OPEN_TENDER",       "Open Competitive Tender"
    RESTRICTED       = "RESTRICTED",        "Restricted Tender"
    SELECTIVE        = "SELECTIVE",         "Selective Tender"
    DIRECT_LABOUR    = "DIRECT_LABOUR",     "Direct Labour"
    DIRECT_AWARD     = "DIRECT_AWARD",      "Direct Award (Emergency)"


# ── Contract ───────────────────────────────────────────────────────────

class Contract(AuditBaseModel):
    """
    Root aggregate for a government contract.

    Overpayment Prevention Controls implemented here:
      • mobilization_rate capped at 30 % (CheckConstraint + validator)
      • retention_rate    capped at 20 % (CheckConstraint + validator)
      • original_sum must be > 0       (CheckConstraint)
      • Status transitions enforced in save() — no skipping stages
      • Contract ceiling = original_sum + SUM(approved variations)
        exposed as a property; ContractBalance stores the snapshot.
    """

    # ── Identity ───────────────────────────────────────────────────────
    contract_number = models.CharField(
        max_length=30, unique=True, db_index=True,
        help_text="Auto-generated on activation, e.g. DSG/WORKS/2026/001",
    )
    title       = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    reference   = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Internal reference / file number",
    )

    # ── Classification ─────────────────────────────────────────────────
    contract_type      = models.CharField(max_length=20, choices=ContractType.choices)
    procurement_method = models.CharField(
        max_length=20, choices=ProcurementMethod.choices,
        default=ProcurementMethod.OPEN_TENDER,
    )
    status = models.CharField(
        max_length=30, choices=ContractStatus.choices,
        default=ContractStatus.DRAFT, db_index=True,
    )

    # ── Parties & Classification ────────────────────────────────────────
    vendor = models.ForeignKey(
        "procurement.Vendor",
        on_delete=models.PROTECT,
        related_name="gov_contracts",
        help_text="Contractor / supplier",
    )
    mda = models.ForeignKey(
        "accounting.AdministrativeSegment",
        on_delete=models.PROTECT,
        related_name="contracts",
        help_text="Implementing / procuring MDA",
    )
    ncoa_code = models.ForeignKey(
        "accounting.NCoACode",
        on_delete=models.PROTECT,
        related_name="contracts",
        help_text="Expenditure charge account (NCoA 52-digit code)",
    )
    appropriation = models.ForeignKey(
        "accounting.BudgetEncumbrance",
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="contracts",
        help_text="Budget appropriation line; validated on each IPC payment",
    )
    fiscal_year = models.ForeignKey(
        "accounting.FiscalYear",
        on_delete=models.PROTECT,
        related_name="contracts",
        help_text="Primary fiscal year — used for IPSAS accrual boundary",
    )

    # ── Financial Terms ─────────────────────────────────────────────────
    original_sum = models.DecimalField(
        max_digits=20, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Original contract sum in NGN",
    )
    mobilization_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("30")),
        ],
        help_text="Mobilization advance as % of original sum (0–30%)",
    )
    retention_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("5.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("20")),
        ],
        help_text="Retention deduction as % of each certified payment (0–20%)",
    )

    # ── Due-Process Compliance ──────────────────────────────────────────
    bpp_no_objection_ref = models.CharField(
        max_length=100, blank=True, default="",
        help_text="BPP Certificate of No Objection reference number",
    )
    due_process_certificate = models.CharField(
        max_length=100, blank=True, default="",
        help_text="State Due Process Bureau certificate number",
    )

    # ── Dates ───────────────────────────────────────────────────────────
    signed_date          = models.DateField(null=True, blank=True)
    commencement_date    = models.DateField(null=True, blank=True)
    contract_start_date  = models.DateField(null=True, blank=True)
    contract_end_date    = models.DateField(null=True, blank=True)
    defects_liability_period_days = models.PositiveIntegerField(
        default=365,
        help_text="Duration of defects liability period in days after practical completion",
    )

    # ── Notes ───────────────────────────────────────────────────────────
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "mda"]),
            models.Index(fields=["fiscal_year", "status"]),
            models.Index(fields=["vendor", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(original_sum__gt=0),
                name="contracts_contract_original_sum_positive",
            ),
            models.CheckConstraint(
                check=models.Q(mobilization_rate__gte=0, mobilization_rate__lte=30),
                name="contracts_contract_mobilization_rate_0_to_30",
            ),
            models.CheckConstraint(
                check=models.Q(retention_rate__gte=0, retention_rate__lte=20),
                name="contracts_contract_retention_rate_0_to_20",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.contract_number} — {self.title[:60]}"

    # ── Computed helpers ────────────────────────────────────────────────

    @property
    def mobilization_amount(self) -> Decimal:
        """Advance mobilization payment = rate × original_sum."""
        return quantize_currency(self.original_sum * self.mobilization_rate / HUNDRED)

    @property
    def approved_variations_total(self) -> Decimal:
        """Sum of all APPROVED variation amounts (additions − omissions)."""
        from django.db.models import Sum
        result = (
            self.variations.filter(status="APPROVED")
            .aggregate(total=Sum("amount"))["total"]
        )
        return quantize_currency(result or ZERO)

    @property
    def contract_ceiling(self) -> Decimal:
        """Hard payment ceiling = original_sum + approved variations."""
        return quantize_currency(self.original_sum + self.approved_variations_total)

    # ── Status transition ───────────────────────────────────────────────

    def transition_to(self, new_status: str, *, actor: object = None) -> None:
        """
        Move contract to `new_status`.  Raises ValidationError if the
        transition is not in ALLOWED_CONTRACT_TRANSITIONS.

        Use this method (rather than direct field assignment) so all
        state-change logic stays in one place.
        """
        allowed = ALLOWED_CONTRACT_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition contract from '{self.status}' to '{new_status}'. "
                f"Allowed: {allowed or ['none (terminal state)']}"
            )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])

    def clean(self) -> None:
        super().clean()
        if (
            self.contract_start_date
            and self.contract_end_date
            and self.contract_end_date < self.contract_start_date
        ):
            raise ValidationError(
                {"contract_end_date": "End date cannot be before start date."}
            )

    def save(self, *args, **kwargs):
        """Auto-allocate ``contract_number`` on first save when blank.

        Format: ``DSG/<TYPE>/<YYYY>/<NNN>`` — e.g. ``DSG/WORKS/2026/042``.
        Uses ``accounting.TransactionSequence`` under SELECT FOR UPDATE
        so two concurrent creations cannot both grab the same number.

        Idempotent: only runs on the *first* save of a Draft contract.
        ``ContractActivationService.activate()`` has the same
        ``if not contract.contract_number`` guard, so an explicit
        number set by tests / data import is preserved end-to-end.

        Wrapped in try/except: if the sequence allocation fails
        (transient DB issue, missing TransactionSequence row), the
        save still succeeds with a blank ``contract_number`` —
        activation will retry the allocation, matching the
        previous behaviour. The unique-index on the column then
        keeps the row ambiguity-safe.
        """
        if not self.pk and not self.contract_number:
            try:
                from contracts.services.numbering import next_contract_number
                fy = self.fiscal_year
                fy_year = (
                    getattr(fy, "year", None)
                    if fy is not None
                    else None
                ) or self.fiscal_year_id
                if self.contract_type and fy_year:
                    self.contract_number = next_contract_number(
                        contract_type=self.contract_type,
                        fiscal_year=fy_year,
                    )
            except Exception:  # noqa: BLE001 — must not block save
                pass
        super().save(*args, **kwargs)


# ── ContractBalance ────────────────────────────────────────────────────

class ContractBalance(models.Model):
    """
    Real-time payment ledger — one row per contract.

    This is the single source of truth for whether a payment is within
    the contract ceiling.  All updates must go through the service layer
    (IPCService, MobilizationService, RetentionService) which use
    SELECT FOR UPDATE + optimistic version bump so that concurrent
    requests cannot both pass the ceiling check.

    The CheckConstraints below are the *last line of defence* at the DB
    layer; the PostgreSQL trigger in migration 0002 fires BEFORE UPDATE
    and raises an exception if any invariant is violated.
    """

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="balance",
    )

    # ── Running totals (all NGN, cumulative) ───────────────────────────
    contract_ceiling = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Snapshot of ceiling at last update (original + approved variations)",
    )
    cumulative_gross_certified = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Total gross value certified across all approved IPCs",
    )
    # Highest ``cumulative_work_done_to_date`` value yet *submitted* on
    # any IPC (Draft / Submitted / Certifier-Reviewed / Approved /
    # Voucher-Raised / Paid). Updated atomically inside ``submit_ipc``
    # under the same SELECT FOR UPDATE that holds the row lock. Two
    # concurrent submissions on the same contract can't both pass the
    # monotonicity check because the second submission re-reads the
    # locked row and sees the first's update.
    last_cumulative_submitted = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text=(
            "Highest cumulative_work_done_to_date submitted on any IPC. "
            "Anchors the monotonicity check — IPC submit refuses values "
            "<= this. Bumped under SELECT FOR UPDATE so concurrent "
            "submissions can't double-certify the same work."
        ),
    )
    pending_voucher_amount = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="IPC approved but PV not yet raised (committed, not yet paid)",
    )
    cumulative_gross_paid = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Total net payments actually disbursed to contractor",
    )

    # ── Mobilization sub-ledger ────────────────────────────────────────
    mobilization_paid      = models.DecimalField(max_digits=20, decimal_places=2, default=ZERO)
    mobilization_recovered = models.DecimalField(max_digits=20, decimal_places=2, default=ZERO)

    # ── Retention sub-ledger ───────────────────────────────────────────
    retention_held     = models.DecimalField(max_digits=20, decimal_places=2, default=ZERO)
    retention_released = models.DecimalField(max_digits=20, decimal_places=2, default=ZERO)

    # ── Optimistic locking ─────────────────────────────────────────────
    version = models.BigIntegerField(
        default=0,
        help_text="Incremented on every write; DB trigger rejects non-increasing version",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # The trigger (in migration 0002) enforces these at a deeper level,
        # but CheckConstraints give us database-level constraint names for
        # introspection and early error messages.
        constraints = [
            models.CheckConstraint(
                check=models.Q(cumulative_gross_certified__gte=0),
                name="contracts_balance_certified_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(cumulative_gross_paid__gte=0),
                name="contracts_balance_paid_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(
                    cumulative_gross_paid__lte=models.F("cumulative_gross_certified")
                ),
                name="contracts_balance_paid_lte_certified",
            ),
            models.CheckConstraint(
                check=models.Q(mobilization_recovered__lte=models.F("mobilization_paid")),
                name="contracts_balance_mob_recovered_lte_paid",
            ),
            models.CheckConstraint(
                check=models.Q(retention_released__lte=models.F("retention_held")),
                name="contracts_balance_retention_released_lte_held",
            ),
            models.CheckConstraint(
                check=models.Q(contract_ceiling__gt=0),
                name="contracts_balance_ceiling_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"Balance for {self.contract_id}"

    # ── Computed helpers ────────────────────────────────────────────────

    @property
    def available_for_certification(self) -> Decimal:
        """
        Maximum additional gross amount that can be certified without
        breaching the contract ceiling.
        """
        return max(
            ZERO,
            self.contract_ceiling
            - self.cumulative_gross_certified
            - self.pending_voucher_amount,
        )

    @property
    def mobilization_outstanding(self) -> Decimal:
        return max(ZERO, self.mobilization_paid - self.mobilization_recovered)

    @property
    def retention_balance(self) -> Decimal:
        return max(ZERO, self.retention_held - self.retention_released)


# ── MilestoneSchedule ──────────────────────────────────────────────────

class MilestoneStatus(models.TextChoices):
    PENDING     = "PENDING",     "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED   = "COMPLETED",   "Completed"
    WAIVED      = "WAIVED",      "Waived"


class MilestoneSchedule(AuditBaseModel):
    """
    Payment milestone / deliverable schedule.

    For lump-sum contracts the percentage_weight must sum to 100 across
    all milestones on the same contract (enforced in the service layer,
    not at DB level, because partial saves are valid during DRAFT stage).
    """

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="milestones",
    )
    milestone_number = models.PositiveSmallIntegerField(
        help_text="Ordering number within the contract",
    )
    description = models.CharField(max_length=300)
    scheduled_value = models.DecimalField(
        max_digits=20, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Scheduled payment value for this milestone",
    )
    percentage_weight = models.DecimalField(
        max_digits=6, decimal_places=3,
        validators=[MinValueValidator(ZERO), MaxValueValidator(HUNDRED)],
        help_text="% of contract sum attributable to this milestone",
    )
    target_date            = models.DateField(null=True, blank=True)
    actual_completion_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=MilestoneStatus.choices,
        default=MilestoneStatus.PENDING,
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["contract", "milestone_number"]
        unique_together = [["contract", "milestone_number"]]
        constraints = [
            models.CheckConstraint(
                check=models.Q(scheduled_value__gt=0),
                name="contracts_milestone_value_positive",
            ),
            models.CheckConstraint(
                check=models.Q(percentage_weight__gte=0, percentage_weight__lte=100),
                name="contracts_milestone_weight_0_to_100",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.contract.contract_number} / Milestone {self.milestone_number}"

    def clean(self) -> None:
        """Aggregate guards across all milestones on the same contract.

        Two invariants enforced here (per-row checks like ``> 0`` and
        ``≤ 100`` already live on the field validators / DB
        CheckConstraints):

          1. **Sum(scheduled_value) ≤ contract.contract_ceiling**
          2. **Sum(percentage_weight) ≤ 100**

        Mirrors the upstream rule that the contract sum cannot exceed
        the appropriated budget.

        SCOPING: the aggregate check is **only triggered when the
        budgetary fields (`scheduled_value` / `percentage_weight`)
        actually change** — pure status transitions, completion-date
        updates, and notes edits don't re-run it. This matters because
        legacy contracts may already exceed the cap (data created
        before this validator existed); without the scope, every
        post-clean save (Approve, Convert-to-IPC, status flips) would
        be blocked even on an unchanged budgetary value.
        """
        super().clean()
        if not self.contract_id:
            return

        # Detect whether the budget-relevant fields actually changed
        # since the row was last loaded from the DB. ``self._state.adding``
        # is True for new rows — we always validate those.
        if not getattr(self._state, 'adding', True) and self.pk:
            try:
                prior = type(self).objects.only(
                    'scheduled_value', 'percentage_weight',
                ).get(pk=self.pk)
                value_unchanged = (prior.scheduled_value or ZERO) == (self.scheduled_value or ZERO)
                weight_unchanged = (prior.percentage_weight or ZERO) == (self.percentage_weight or ZERO)
                if value_unchanged and weight_unchanged:
                    return  # nothing budgetary to re-validate
            except type(self).DoesNotExist:
                pass

        # Exclude the current row when summing — editing must not
        # double-count its own contribution against the cap.
        siblings = MilestoneSchedule.objects.filter(
            contract_id=self.contract_id,
        )
        if self.pk:
            siblings = siblings.exclude(pk=self.pk)

        from django.db.models import Sum
        existing_scheduled = siblings.aggregate(
            total=Sum('scheduled_value'),
        )['total'] or ZERO
        try:
            ceiling = Decimal(str(self.contract.contract_ceiling or 0))
        except Exception:
            ceiling = ZERO
        new_total = existing_scheduled + (self.scheduled_value or ZERO)
        if ceiling > 0 and new_total > ceiling:
            overflow = new_total - ceiling
            raise ValidationError({
                'scheduled_value': (
                    f"Total milestone value would be NGN {new_total:,.2f}, "
                    f"which exceeds the contract sum of NGN {ceiling:,.2f} by "
                    f"NGN {overflow:,.2f}. Reduce this milestone's value or "
                    f"raise a contract variation first."
                ),
            })

        existing_pct = siblings.aggregate(
            total=Sum('percentage_weight'),
        )['total'] or ZERO
        new_pct_total = existing_pct + (self.percentage_weight or ZERO)
        if new_pct_total > HUNDRED:
            overflow = new_pct_total - HUNDRED
            raise ValidationError({
                'percentage_weight': (
                    f"Total milestone weight would be {new_pct_total:.2f}% — "
                    f"{overflow:.2f}% over the 100% cap. The weights describe "
                    f"how the contract sum is distributed and cannot exceed "
                    f"100% in aggregate."
                ),
            })

    def save(self, *args, **kwargs):
        # ``full_clean`` runs the custom ``clean`` above. We skip
        # ``validate_constraints`` because the per-field rules are
        # already enforced by DB CheckConstraints (defence in depth).
        self.full_clean(exclude=None, validate_constraints=False)
        super().save(*args, **kwargs)
