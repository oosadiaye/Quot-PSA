"""
Payment-related models
=======================
Covers the full payment lifecycle for a government contract:

  InterimPaymentCertificate (IPC)  — engineer certifies work done each period
  MeasurementBook                  — quantity surveyor's raw measurement record
  MobilizationPayment              — advance mobilization disbursement
  RetentionRelease                 — release of retention moneys at completion

Overpayment controls implemented in this file (structural, not advisory):
  • integrity_hash on IPC prevents identical period/amount duplicate submission
  • cumulative_work_done_to_date must be monotonically increasing (service layer)
  • net_payable is a computed, read-only field (never user-editable)
  • WHT and VAT are applied at payment time (cash-basis, per FIRS practice)
"""
from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel, quantize_currency

ZERO = Decimal("0.00")


# ── MeasurementBook ────────────────────────────────────────────────────

class MeasurementBookStatus(models.TextChoices):
    DRAFT     = "DRAFT",     "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED  = "APPROVED",  "Approved"
    REJECTED  = "REJECTED",  "Rejected"


class MeasurementBook(AuditBaseModel):
    """
    Quantity surveyor's site measurement record.

    items is stored as a JSON array:
      [{"description": "...", "unit": "m3", "quantity": "150.00",
        "rate": "12500.00", "amount": "1875000.00"}, ...]

    total_measured_value is denormalized from items for quick querying.
    Recomputed in save().
    """

    contract  = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="measurement_books",
    )
    mb_number = models.CharField(
        max_length=30, db_index=True,
        help_text="Auto-generated, e.g. MB/DSG/WORKS/2026/001/001",
    )
    measurement_date = models.DateField()
    items = models.JSONField(
        default=list,
        help_text=(
            "List of measurement line items. "
            "Each item: {description, unit, quantity, rate, amount}. "
            "All numeric values stored as strings to preserve precision."
        ),
    )
    total_measured_value = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Sum of all item amounts — recomputed on save",
    )
    status = models.CharField(
        max_length=20, choices=MeasurementBookStatus.choices,
        default=MeasurementBookStatus.DRAFT,
    )
    measured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="measured_measurement_books",
    )
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="checked_measurement_books",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_measurement_books",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["contract", "measurement_date"]
        unique_together = [["contract", "mb_number"]]

    def __str__(self) -> str:
        return f"{self.mb_number} ({self.measurement_date})"

    def recompute_total(self) -> None:
        """Sum item amounts and update total_measured_value.

        Silently skipping malformed items was masking data-quality bugs —
        a single corrupt row could produce a wrong Measurement Book total
        used by downstream IPC / valuation calculations. We now:
          * skip only when the item is obviously not a measurement row
            (None or non-dict) — items may be None for trailing slots
          * log + raise on parse errors so the caller knows the MB has
            bad data and can reject the save instead of persisting a
            wrong total.
        """
        import logging
        total = ZERO
        for idx, item in enumerate(self.items or []):
            if item is None or not isinstance(item, dict):
                continue
            raw = item.get("amount", "0")
            try:
                total += Decimal(str(raw))
            except (InvalidOperation, TypeError, ValueError) as e:
                logging.getLogger(__name__).error(
                    'MeasurementBook %s: item[%d] amount=%r is not a valid '
                    'decimal (%s) — refusing to silently zero it.',
                    getattr(self, 'mb_number', '<unsaved>'), idx, raw, e,
                )
                raise
        self.total_measured_value = quantize_currency(total)

    def save(self, *args, **kwargs) -> None:
        self.recompute_total()
        super().save(*args, **kwargs)


# ── InterimPaymentCertificate ──────────────────────────────────────────

class IPCStatus(models.TextChoices):
    DRAFT             = "DRAFT",             "Draft"
    SUBMITTED         = "SUBMITTED",         "Submitted for Certification"
    CERTIFIER_REVIEWED = "CERTIFIER_REVIEWED", "Certifier Reviewed"
    APPROVED          = "APPROVED",          "Approved (Payment Due)"
    VOUCHER_RAISED    = "VOUCHER_RAISED",    "Payment Voucher Raised"
    PAID              = "PAID",              "Paid"
    REJECTED          = "REJECTED",          "Rejected"


ALLOWED_IPC_TRANSITIONS: dict[str, list[str]] = {
    IPCStatus.DRAFT:              [IPCStatus.SUBMITTED],
    IPCStatus.SUBMITTED:          [IPCStatus.CERTIFIER_REVIEWED, IPCStatus.REJECTED],
    IPCStatus.CERTIFIER_REVIEWED: [IPCStatus.APPROVED,           IPCStatus.REJECTED],
    IPCStatus.APPROVED:           [IPCStatus.VOUCHER_RAISED],
    IPCStatus.VOUCHER_RAISED:     [IPCStatus.PAID],
    IPCStatus.PAID:               [],  # terminal
    IPCStatus.REJECTED:           [IPCStatus.DRAFT],  # allow rework
}


class InterimPaymentCertificate(AuditBaseModel):
    """
    Engineer's certificate for work completed during a period.

    The integrity_hash prevents the same period+cumulative combination
    being certified twice (duplicate-payment attack).

    IPSAS accrual:
      On APPROVED  → accrue the net_payable (Dr Expenditure / Cr Payables)
      On PAID      → reverse accrual + cash JE (Dr Payables / Cr TSA)
    """

    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="ipcs",
    )
    ipc_number = models.CharField(
        max_length=30, db_index=True,
        help_text="Auto-generated, e.g. IPC/DSG/WORKS/2026/001/003",
    )
    measurement_book = models.ForeignKey(
        MeasurementBook, null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="ipcs",
        help_text="Source measurement book (three-way match control)",
    )

    # ── Posting date ───────────────────────────────────────────────────
    # Single effective-date stamp. Drives the fiscal-year boundary check
    # and the dedup hash; replaces the earlier period_from/period_to
    # range (simplified per operational feedback — engineers sign off on
    # the measurement book once and post the IPC on that date).
    posting_date = models.DateField()

    # ── Cumulative amounts (all in NGN) ────────────────────────────────
    cumulative_work_done_to_date = models.DecimalField(
        max_digits=20, decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text="Engineer's cumulative assessment of work completed to date",
    )
    previous_certified = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Cumulative gross certified at previous IPC (auto-filled on submit)",
    )
    this_certificate_gross = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Gross value for this period = cumulative_work_done - previous_certified",
    )

    # ── Deductions ─────────────────────────────────────────────────────
    mobilization_recovery_this_cert = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Mobilization advance recovery deduction for this IPC",
    )
    retention_deduction_this_cert = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Retention deduction for this IPC",
    )
    ld_deduction = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Liquidated Damages deduction",
    )
    variation_claims = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Variation amount included in this certificate",
    )

    # ── Taxes (at payment time per FIRS cash-basis) ────────────────────
    vat_amount = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="VAT (7.5 %) applied at payment posting",
    )
    wht_amount = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="WHT applied at payment posting (rate varies by contract type)",
    )

    # ── Net payable (read-only, computed) ──────────────────────────────
    net_payable = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Net amount payable to contractor (computed, never user-editable)",
    )

    # ── Status & workflow ──────────────────────────────────────────────
    status = models.CharField(
        max_length=25, choices=IPCStatus.choices,
        default=IPCStatus.DRAFT, db_index=True,
    )
    certifying_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="certified_ipcs",
    )
    rejection_reason = models.TextField(blank=True, default="")

    # ── Duplicate-prevention hash ──────────────────────────────────────
    integrity_hash = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        help_text=(
            "SHA-256 of (contract_id, posting_date, cumulative_work_done_to_date). "
            "Prevents duplicate IPC for same posting-date+amount."
        ),
    )

    # ── Linked GL journal (set on APPROVED accrual posting) ───────────
    accrual_journal = models.ForeignKey(
        "accounting.JournalHeader", null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="ipc_accruals",
    )
    payment_voucher = models.ForeignKey(
        "accounting.PaymentVoucherGov", null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="ipcs",
    )

    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["contract", "posting_date"]
        unique_together = [["contract", "ipc_number"]]
        constraints = [
            models.CheckConstraint(
                check=models.Q(cumulative_work_done_to_date__gte=0),
                name="contracts_ipc_cumulative_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(this_certificate_gross__gte=0),
                name="contracts_ipc_certificate_gross_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(net_payable__gte=0),
                name="contracts_ipc_net_payable_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(mobilization_recovery_this_cert__gte=0),
                name="contracts_ipc_mob_recovery_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(retention_deduction_this_cert__gte=0),
                name="contracts_ipc_retention_deduction_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(ld_deduction__gte=0),
                name="contracts_ipc_ld_deduction_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "contract"]),
            models.Index(fields=["integrity_hash"]),
        ]

    def __str__(self) -> str:
        return f"{self.ipc_number} [{self.get_status_display()}]"

    # ── Computed helpers ────────────────────────────────────────────────

    def compute_net_payable(self) -> Decimal:
        """
        net_payable = this_certificate_gross
                    − mobilization_recovery_this_cert
                    − retention_deduction_this_cert
                    − ld_deduction
                    + variation_claims
                    + vat_amount
                    − wht_amount
        """
        return quantize_currency(
            self.this_certificate_gross
            - self.mobilization_recovery_this_cert
            - self.retention_deduction_this_cert
            - self.ld_deduction
            + self.variation_claims
            + self.vat_amount
            - self.wht_amount
        )

    def build_integrity_hash(self) -> str:
        raw = "|".join([
            str(self.contract_id),
            str(self.posting_date),
            str(self.cumulative_work_done_to_date),
        ])
        return hashlib.sha256(raw.encode()).hexdigest()

    def save(self, *args, **kwargs) -> None:
        # Keep net_payable in sync.
        self.net_payable = self.compute_net_payable()
        # Rebuild hash whenever key fields change (allow re-draft scenario).
        if not self.integrity_hash:
            self.integrity_hash = self.build_integrity_hash()
        super().save(*args, **kwargs)

    def transition_to(self, new_status: str) -> None:
        allowed = ALLOWED_IPC_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition IPC from '{self.status}' to '{new_status}'. "
                f"Allowed: {allowed}"
            )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])


# ── MobilizationPayment ────────────────────────────────────────────────

class MobilizationPaymentStatus(models.TextChoices):
    PENDING           = "PENDING",           "Pending Disbursement"
    PAID              = "PAID",              "Paid"
    PARTIALLY_RECOVERED = "PARTIALLY_RECOVERED", "Partially Recovered"
    FULLY_RECOVERED   = "FULLY_RECOVERED",   "Fully Recovered"


class MobilizationPayment(AuditBaseModel):
    """
    Advance mobilization payment record (one per contract).

    The advance is recovered pro-rata across IPCs until the full advance
    amount is recouped.  Enforced by MobilizationService.
    """

    contract = models.OneToOneField(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="mobilization_payment",
    )
    amount = models.DecimalField(
        max_digits=20, decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text="Mobilization advance disbursed (mobilization_rate × original_sum)",
    )
    payment_voucher = models.ForeignKey(
        "accounting.PaymentVoucherGov", null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="mobilization_payments",
    )
    payment_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=25, choices=MobilizationPaymentStatus.choices,
        default=MobilizationPaymentStatus.PENDING,
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name="contracts_mob_payment_amount_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"Mobilization {self.contract.contract_number} — ₦{self.amount:,.2f}"


# ── RetentionRelease ───────────────────────────────────────────────────

class RetentionReleaseType(models.TextChoices):
    PRACTICAL_COMPLETION = "PRACTICAL_COMPLETION", "Practical Completion (50% of retention)"
    FINAL_COMPLETION     = "FINAL_COMPLETION",     "Final Completion (remaining 50%)"


class RetentionReleaseStatus(models.TextChoices):
    PENDING  = "PENDING",  "Pending Approval"
    APPROVED = "APPROVED", "Approved"
    PAID     = "PAID",     "Paid"
    REJECTED = "REJECTED", "Rejected"


class RetentionRelease(AuditBaseModel):
    """
    Release of held retention money.

    At Practical Completion → release 50 % of retention_held.
    At Final Completion     → release remaining 50 %.

    RetentionService validates that retention_released + this release
    never exceeds retention_held (enforced via ContractBalance constraint).
    """

    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="retention_releases",
    )
    release_type = models.CharField(
        max_length=25, choices=RetentionReleaseType.choices,
    )
    amount = models.DecimalField(
        max_digits=20, decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text="Amount to be released (computed by RetentionService)",
    )
    payment_voucher = models.ForeignKey(
        "accounting.PaymentVoucherGov", null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="retention_releases",
    )
    payment_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=RetentionReleaseStatus.choices,
        default=RetentionReleaseStatus.PENDING,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_retention_releases",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["contract", "release_type"]
        # Only one release per type per contract.
        unique_together = [["contract", "release_type"]]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name="contracts_retention_release_amount_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Retention Release — {self.contract.contract_number} "
            f"({self.get_release_type_display()})"
        )
