"""Payment Document — SAP F-53 style multi-line outgoing payment.

Header bank account is the single credit (cash out); lines are the debit/
credit legs (expenditure, liability settlement, vendor recon, or deduction).
Posts ONE balanced journal via ``payment_document_posting.post_payment_document``.
Budget appropriation is enforced by ``post_payment_document`` itself on
expense-type debit lines: the ``budget_enforcement`` signal gates by GL code
range (not account_type), which would otherwise block liability/vendor
settlements whose codes fall in the expenditure range, so the service runs the
expense-only appropriation/warrant check and sets ``journal._budget_checked`` to
suppress the signal's broader gate. Liability/vendor/asset settlements post with
no budget check.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import models

from core.models import AuditBaseModel, ImmutableModelMixin


def payment_document_attachment_path(instance, filename):
    """Randomized, tenant-scoped upload path for the source-document scan.

    The stored name is a random UUID (NOT the user's filename), so the file
    is NOT reachable by a guessable/constructible URL even if a webserver
    ``/media/`` alias serves the directory unauthenticated. The human filename
    is preserved separately in ``attachment_original_name`` for display; the
    only sanctioned way to fetch the bytes is the authenticated
    ``attachment/download`` action.
    """
    import os
    import uuid
    from django.db import connection
    schema = getattr(connection, "schema_name", "public")
    ext = os.path.splitext(filename)[1].lower()
    return f"tenants/{schema}/documents/payment_docs/{uuid.uuid4().hex}{ext}"


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
    # Source-document scan (image or PDF). The file is stored under a random
    # UUID name (see ``payment_document_attachment_path``) so it cannot be
    # reached by a guessable /media URL; the human filename lives in
    # ``attachment_original_name``. Download is ONLY via the authenticated
    # ``attachment/download`` action on the ViewSet.
    # max_length 255 (not the FileField default of 100): the tenant-scoped
    # media path (long schema name + payment_docs/ + a 32-char uuid) can exceed
    # 100 chars, which would otherwise force the storage backend to truncate the
    # random name to fit.
    attachment = models.FileField(upload_to=payment_document_attachment_path, max_length=255, null=True, blank=True)
    attachment_original_name = models.CharField(max_length=255, blank=True, default="")

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
    # A line posts to EITHER a GL account OR a vendor. ``account`` is nullable
    # so a vendor-only line can be entered; at posting the vendor's AP
    # reconciliation account (via get_vendor_ap_account) is resolved into
    # ``account`` so the journal always debits/credits a real GL. The
    # account-or-vendor rule is enforced by the serializer and the posting
    # service (PaymentDocumentLine has no DB-level check).
    account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, null=True, blank=True,
        related_name="payment_document_lines",
    )
    vendor = models.ForeignKey(
        "procurement.Vendor", on_delete=models.PROTECT, null=True, blank=True,
        related_name="payment_document_lines",
    )
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    is_deduction = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            # Belt-and-suspenders for the account-OR-vendor rule the serializer
            # and posting service enforce: a hard DB backstop so no future
            # direct-ORM write path (bulk action, fixture, another importer) can
            # persist a line that names neither.
            models.CheckConstraint(
                check=models.Q(account__isnull=False) | models.Q(vendor__isnull=False),
                name="paymentdocumentline_account_or_vendor",
            ),
        ]
