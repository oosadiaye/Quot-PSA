"""
ContractApprovalStep & ContractDocument models
===============================================
ContractApprovalStep is an **immutable** audit trail for every approval
action on any contract-related document (IPC, variation, completion cert,
etc.).  Records are created, never modified.

ContractDocument stores uploaded files against a contract.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import AuditBaseModel


# ── ContractApprovalStep ───────────────────────────────────────────────

class ApprovalAction(models.TextChoices):
    APPROVE      = "APPROVE",       "Approve"
    REJECT       = "REJECT",        "Reject"
    REQUEST_INFO = "REQUEST_INFO",  "Request Additional Information"
    ESCALATE     = "ESCALATE",      "Escalate to Higher Authority"
    CERTIFY      = "CERTIFY",       "Certify (Engineer)"
    VERIFY       = "VERIFY",        "Verify (Quantity Surveyor)"


class ApprovalObjectType(models.TextChoices):
    IPC          = "IPC",       "Interim Payment Certificate"
    VARIATION    = "VARIATION", "Contract Variation"
    COMPLETION   = "COMPLETION","Completion Certificate"
    MOBILIZATION = "MOB",       "Mobilization Payment"
    RETENTION    = "RETENTION", "Retention Release"
    CONTRACT     = "CONTRACT",  "Contract"


class ContractApprovalStep(models.Model):
    """
    Immutable audit step for a single approval action.

    The step is created (INSERT) only — never updated or deleted.
    An application-level guard in save() enforces this.

    object_type + object_id form a generic reference to any contract-
    related document so the approval trail is unified across IPCs,
    variations, completion certificates, etc.
    """

    # Generic object reference (IPC / variation / completion cert)
    object_type = models.CharField(
        max_length=20, choices=ApprovalObjectType.choices,
    )
    object_id = models.BigIntegerField(
        help_text="PK of the related IPC / Variation / Completion cert / etc.",
    )
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="approval_steps",
    )

    step_number   = models.PositiveSmallIntegerField(
        help_text="Sequential step number within this object's workflow",
    )
    role_required = models.CharField(
        max_length=100,
        help_text="Permission / role required to take this action, e.g. 'contracts.approve_ipc'",
    )
    assigned_to   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_approval_steps",
    )
    action    = models.CharField(max_length=20, choices=ApprovalAction.choices)
    action_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="taken_approval_steps",
    )
    action_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notes     = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["contract", "action_at"]
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return (
            f"[{self.object_type}/{self.object_id}] Step {self.step_number} "
            f"— {self.get_action_display()} by {self.action_by_id}"
        )

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            raise ValidationError(
                "ContractApprovalStep records are immutable — they cannot be modified."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "ContractApprovalStep records are immutable — they cannot be deleted."
        )


# ── CompletionCertificate ──────────────────────────────────────────────

class CertificateType(models.TextChoices):
    PRACTICAL       = "PRACTICAL",       "Practical Completion Certificate"
    DEFECTS_LIABILITY = "DEFECTS_LIABILITY", "Defects Liability Certificate"
    FINAL           = "FINAL",           "Final Completion Certificate"


class CompletionCertificate(AuditBaseModel):
    """
    Formal completion certificate issued by the certifying engineer.

    Each type may only be issued once per contract.  Issuing a
    PRACTICAL certificate triggers the 50 % retention release workflow;
    FINAL triggers the remaining 50 %.
    """

    contract      = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="completion_certificates",
    )
    certificate_type = models.CharField(
        max_length=20, choices=CertificateType.choices,
    )
    issued_date    = models.DateField()
    effective_date = models.DateField()
    certified_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_completion_certificates",
    )
    notes          = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["contract", "certificate_type"]
        unique_together = [["contract", "certificate_type"]]

    def __str__(self) -> str:
        return (
            f"{self.contract.contract_number} — "
            f"{self.get_certificate_type_display()} ({self.issued_date})"
        )

    def clean(self) -> None:
        super().clean()
        if (
            self.effective_date
            and self.issued_date
            and self.effective_date < self.issued_date
        ):
            raise ValidationError(
                {"effective_date": "Effective date cannot be before issued date."}
            )


# ── ContractDocument ───────────────────────────────────────────────────

class DocumentType(models.TextChoices):
    CONTRACT         = "CONTRACT",          "Signed Contract"
    VARIATION_ORDER  = "VARIATION_ORDER",   "Variation Order"
    IPC_DOCUMENT     = "IPC_DOCUMENT",      "Interim Payment Certificate"
    MEASUREMENT_BOOK = "MEASUREMENT_BOOK",  "Measurement Book"
    COMPLETION_CERT  = "COMPLETION_CERT",   "Completion Certificate"
    PERFORMANCE_BOND = "PERFORMANCE_BOND",  "Performance Bond / Guarantee"
    INSURANCE        = "INSURANCE",         "Insurance Certificate"
    BPP_CERTIFICATE  = "BPP_CERTIFICATE",   "BPP No-Objection Certificate"
    OTHER            = "OTHER",             "Other"


def contract_document_path(instance: "ContractDocument", filename: str) -> str:
    """Store under contracts/<contract_number>/<doc_type>/<filename>."""
    return (
        f"contracts/{instance.contract.contract_number}/"
        f"{instance.document_type}/{filename}"
    )


class ContractDocument(AuditBaseModel):
    """Supporting documents uploaded against a contract."""

    contract      = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    title         = models.CharField(max_length=200)
    file          = models.FileField(
        upload_to=contract_document_path,
        help_text="Uploaded document (PDF, DOCX, XLSX, image)",
    )
    description   = models.TextField(blank=True, default="")
    uploaded_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_contract_documents",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.contract.contract_number} / {self.title}"
