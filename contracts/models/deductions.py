"""
Per-vendor per-year tracking of the Status Verification fee.

Delta State Circular AG/CIR/54/C/Vol.10/1/134 (April 2026) sets a
₦40,000.00 Status Verification fee payable **once per contractor /
vendor per calendar year**. To decide whether a given payment voucher
should carry the fee, the IPC service needs a persistent record of
which (vendor, year) pairs have already been charged.

Invariants (DB enforced)
------------------------
- Exactly one row per (vendor, year). A partial UNIQUE INDEX on
  ``(vendor_id, year)`` would do, but a straight UniqueConstraint is
  enough since every row represents a real payment.
- ``fee_amount`` matches the circular at the time of recording. We
  store it as a snapshot rather than reading the module constant so
  historical audits remain accurate across future policy changes.
- ``year`` is the calendar year in which the fee was deducted.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models

from core.models import AuditBaseModel


class VendorStatusVerification(AuditBaseModel):
    """A single ₦40,000 Status Verification fee payment record."""

    vendor = models.ForeignKey(
        "procurement.Vendor",
        on_delete=models.PROTECT,
        related_name="status_verifications",
    )
    year = models.PositiveIntegerField(
        help_text="Calendar year in which the fee was deducted.",
    )
    fee_amount = models.DecimalField(
        max_digits=20, decimal_places=2,
        default=Decimal("40000.00"),
        help_text="Fee amount at the time of recording (historical snapshot).",
    )
    recorded_on = models.DateField(
        help_text="Date the deduction was applied on a payment voucher.",
    )
    payment_voucher_id = models.BigIntegerField(
        null=True, blank=True,
        help_text=(
            "FK-shaped reference to accounting.PaymentVoucherGov. Kept as "
            "a loose BigInteger to avoid a cross-app migration cycle; "
            "the accounting app's PV is in the same tenant schema."
        ),
    )
    circular_reference = models.CharField(
        max_length=50,
        default="AG/CIR/54/C/Vol.10/1/134",
        help_text="Source circular reference.",
    )

    class Meta:
        ordering = ["-year", "vendor_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "year"],
                name="contracts_vendorsv_unique_per_vendor_year",
            ),
            models.CheckConstraint(
                check=models.Q(fee_amount__gte=0),
                name="contracts_vendorsv_fee_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["year"]),
        ]

    def __str__(self) -> str:
        return (
            f"StatusVerification vendor={self.vendor_id} "
            f"year={self.year} amount=NGN {self.fee_amount:,.2f}"
        )
