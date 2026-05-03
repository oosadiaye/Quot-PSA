"""
Vendor Advance Ledger — Special GL tracking for advance payments.

Inspired by SAP's Special GL Indicator pattern (typically "A" for
down-payments). One central ledger of every advance disbursed to a
vendor — regardless of source — so the vendor sub-ledger view can
union ordinary trade payables (AP recon) with advances (special GL
recon) under a single audit trail.

Three originating flows feed this ledger:
  * Mobilisation advances on contracts  (contracts.MobilizationPayment)
  * Down-payment requests on POs        (procurement.DownPaymentRequest)
  * Direct advance payments in AP       (accounting.advance_payment)

Each disbursement of an advance is recorded here with:
  * the special-GL recon account that received the DR (Asset side),
  * the vendor it relates to,
  * a free reference + source FK so the originating document can be
    deep-linked from the vendor ledger,
  * cumulative recovery counters so the popup logic can ask "how
    much is still outstanding?" in one indexed query.

Lifecycle:
  OUTSTANDING ──┐                                  ┌── CLEARED
                ├── partial recovery ── PARTIAL ──┤
                └─────────── full recovery ──────┘

Recovery is recorded by ``VendorAdvanceClearance`` rows so the audit
trail captures every clearing event with its journal pin.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import AuditBaseModel


ZERO = Decimal("0.00")


class VendorAdvanceStatus(models.TextChoices):
    OUTSTANDING = "OUTSTANDING", "Outstanding"
    PARTIAL     = "PARTIAL",     "Partially Recovered"
    CLEARED     = "CLEARED",     "Fully Cleared"


class VendorAdvanceSource(models.TextChoices):
    """Where the advance originated. The pair (source_type, source_id)
    deep-links back to the source document (Mobilization, DPR, etc.)."""
    MOBILIZATION    = "MOBILIZATION",    "Contract Mobilisation"
    PO_DOWNPAYMENT  = "PO_DOWNPAYMENT",  "PO Down Payment"
    AP_DOWNPAYMENT  = "AP_DOWNPAYMENT",  "AP Down Payment"
    OTHER           = "OTHER",           "Other Advance"


class VendorAdvance(AuditBaseModel):
    """A single advance payment to a vendor, recorded in a Special GL
    recon account (``Account.reconciliation_type='vendor_advance'``).

    Mirrors SAP's pattern: this row tags a sub-ledger entry for the
    vendor with an "AD" indicator so the vendor's GL statement shows
    a separate advances column distinct from ordinary AP.
    """

    vendor = models.ForeignKey(
        "procurement.Vendor",
        on_delete=models.PROTECT,
        related_name="advances",
        db_index=True,
    )
    recon_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        related_name="vendor_advances",
        # Special-GL recon — distinct from ``accounts_payable``.
        limit_choices_to={"reconciliation_type": "vendor_advance"},
        help_text="Special-GL account that holds the advance "
                  "(behaves like AP recon but for advances).",
    )

    # Originating document — denormalised pair so the vendor ledger
    # can deep-link without a polymorphic FK at the DB level.
    source_type = models.CharField(
        max_length=20, choices=VendorAdvanceSource.choices, db_index=True,
    )
    source_id = models.PositiveIntegerField(
        null=True, blank=True, db_index=True,
        help_text="FK id of the originating document "
                  "(MobilizationPayment / DownPaymentRequest / etc.).",
    )
    reference = models.CharField(
        max_length=100, db_index=True,
        help_text='User-visible reference, e.g. "DSG/WORKS/2026/001-MOB".',
    )

    # Money
    amount_paid = models.DecimalField(
        max_digits=20, decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text="Gross amount disbursed at the time the advance was paid.",
    )
    amount_recovered = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
        help_text="Cumulative amount cleared (recovered) so far.",
    )

    status = models.CharField(
        max_length=15,
        choices=VendorAdvanceStatus.choices,
        default=VendorAdvanceStatus.OUTSTANDING,
        db_index=True,
    )

    # Audit pins
    posting_date = models.DateField(
        help_text="Date the disbursement journal posted.",
    )
    disbursement_journal = models.ForeignKey(
        "accounting.JournalHeader",
        on_delete=models.PROTECT,
        related_name="vendor_advances_disbursed",
        null=True, blank=True,
        help_text="The DR Vendor-Advance / CR Cash journal that "
                  "recognised this advance.",
    )

    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-posting_date", "-created_at"]
        indexes = [
            # Hot path: "any uncleared advances for this vendor?"
            # — the popup query that gates AP / PV / IPC posting.
            models.Index(
                fields=["vendor", "status"],
                name="acct_vendor_advance_open_idx",
            ),
            models.Index(
                fields=["source_type", "source_id"],
                name="acct_vendor_advance_src_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount_paid__gte=0),
                name="acct_vendor_advance_paid_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(amount_recovered__gte=0),
                name="acct_vendor_advance_recovered_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(amount_recovered__lte=models.F("amount_paid")),
                name="acct_vendor_advance_recovered_lte_paid",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.reference} — {self.vendor_id} "
            f"AD ₦{self.amount_paid:,.2f} ({self.status})"
        )

    # ── Computed helpers ───────────────────────────────────────────────

    @property
    def amount_outstanding(self) -> Decimal:
        return (self.amount_paid or ZERO) - (self.amount_recovered or ZERO)

    @property
    def is_cleared(self) -> bool:
        return self.status == VendorAdvanceStatus.CLEARED

    def recompute_status(self) -> None:
        """Set ``status`` from the recovered/paid ratio. Call after
        every clearance event. Persisting is the caller's job."""
        if self.amount_recovered <= ZERO:
            self.status = VendorAdvanceStatus.OUTSTANDING
        elif self.amount_recovered >= self.amount_paid:
            self.status = VendorAdvanceStatus.CLEARED
        else:
            self.status = VendorAdvanceStatus.PARTIAL


class VendorAdvanceClearance(AuditBaseModel):
    """One clearing event against a VendorAdvance.

    The clearing journal moves the obligation from the special-GL
    recon (Vendor Advance) to either the standard AP recon (when
    netted against an AP invoice) or to an expense account (when
    written off). The ``cleared_against_*`` columns capture the
    target so the vendor ledger can show the linkage.
    """

    advance = models.ForeignKey(
        VendorAdvance, on_delete=models.CASCADE,
        related_name="clearances",
    )
    amount = models.DecimalField(
        max_digits=20, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Amount cleared in this event.",
    )
    posting_date = models.DateField()
    clearing_journal = models.ForeignKey(
        "accounting.JournalHeader", on_delete=models.PROTECT,
        related_name="vendor_advance_clearances",
        null=True, blank=True,
        help_text="The DR-AP / CR-Vendor-Advance contra journal.",
    )
    # Optional pin to the document that triggered the clearance.
    cleared_against_type = models.CharField(
        max_length=30, blank=True, default="",
        help_text='e.g. "VendorInvoice", "IPC", "PaymentVoucher".',
    )
    cleared_against_id = models.PositiveIntegerField(
        null=True, blank=True,
    )
    cleared_against_reference = models.CharField(
        max_length=100, blank=True, default="",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-posting_date", "-created_at"]
        indexes = [
            models.Index(fields=["advance", "posting_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="acct_vadv_clearance_amount_positive",
            ),
        ]
