"""Payment Document — SAP F-53 style multi-line outgoing payment.

Header bank account is the single credit (cash out); lines are the debit/
credit legs (expenditure, liability settlement, vendor recon, or deduction).
Posts ONE balanced journal via ``payment_document_posting.post_payment_document``.
Budget appropriation is enforced only on expense-debit lines by the existing
``budget_enforcement`` signal, so liability/vendor settlements post with none.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import models

from core.models import AuditBaseModel, ImmutableModelMixin


class PaymentDocument(AuditBaseModel, ImmutableModelMixin):
    STATUS_CHOICES = [("Draft", "Draft"), ("Posted", "Posted"), ("Void", "Void")]
    SOURCE_CHOICES = [("manual", "Manual"), ("import", "Import")]

    document_number = models.CharField(max_length=30, unique=True, db_index=True)
    document_date = models.DateField(default=date.today)
    bank_account = models.ForeignKey(
        "accounting.BankAccount", on_delete=models.PROTECT, related_name="payment_documents",
    )
    reference_number = models.CharField(max_length=100, blank=True, default="")
    description = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Draft", db_index=True)

    mda = models.ForeignKey("accounting.MDA", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")
    fund = models.ForeignKey("accounting.Fund", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")
    function = models.ForeignKey("accounting.Function", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")
    program = models.ForeignKey("accounting.Program", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")
    geo = models.ForeignKey("accounting.Geo", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")

    net_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    journal = models.ForeignKey(
        "accounting.JournalHeader", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_documents",
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="manual")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Document"
        verbose_name_plural = "Payment Documents"

    def __str__(self) -> str:
        return f"{self.document_number} — {self.status} — NGN {self.net_amount:,.2f}"


class PaymentDocumentLine(models.Model):
    payment_document = models.ForeignKey(
        PaymentDocument, on_delete=models.CASCADE, related_name="lines",
    )
    account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="payment_document_lines",
    )
    vendor = models.ForeignKey(
        "procurement.Vendor", on_delete=models.PROTECT, null=True, blank=True,
        related_name="payment_document_lines",
    )
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    memo = models.CharField(max_length=255, blank=True, default="")
    is_deduction = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
