"""Payment Document API — CRUD, submit-for-approval, proposed-entries preview."""
from __future__ import annotations

import logging
import os
from decimal import Decimal

from django.db import transaction
from django.http import FileResponse
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from accounting.models import PaymentDocument, PaymentDocumentLine, TransactionSequence
from accounting.services.payment_document_posting import _bank_credit
from core.mixins import OrganizationFilterMixin

logger = logging.getLogger(__name__)

# Source-document attachment allowlist — the security crux. An upload is
# accepted only when BOTH its declared content type AND its lowercased file
# extension are in these sets, it is at or under the size cap, AND its actual
# leading bytes match the declared kind (see ``_attachment_bytes_match_type``).
# Anything else is rejected (fail-closed). Note: the non-standard "image/jpg"
# is deliberately NOT accepted — browsers send "image/jpeg" — while ".jpg"
# stays a valid extension.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_ATTACHMENT_CONTENT_TYPES = frozenset({
    "image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf",
})
ALLOWED_ATTACHMENT_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf",
})
PDF_MAGIC = b"%PDF-"


def _attachment_bytes_match_type(f) -> bool:
    """Verify the uploaded bytes actually match the declared content type.

    The allowlist above only checks metadata (content type + extension), which
    a client fully controls. This opens the real file and confirms it decodes:
    images must parse under Pillow; PDFs must start with the ``%PDF-`` marker.
    The file pointer is always reset to 0 so the subsequent save streams the
    whole file. Any decode failure means reject (fail-closed).
    """
    content_type = f.content_type or ""
    if content_type.startswith("image/"):
        from PIL import Image
        try:
            Image.open(f).verify()
        except Exception:  # noqa: BLE001 — any decode failure is a rejection
            return False
        finally:
            f.seek(0)
        return True
    if content_type == "application/pdf":
        header = f.read(len(PDF_MAGIC))
        f.seek(0)
        return header == PDF_MAGIC
    return False  # defensive: allowlist already excludes anything else


class PaymentDocumentLineSerializer(serializers.ModelSerializer):
    # ``default=None`` keeps these null-safe for a vendor-only line (no GL
    # account yet — resolved to the vendor's AP recon account at posting).
    account_code = serializers.CharField(source="account.code", read_only=True, default=None)
    account_name = serializers.CharField(source="account.name", read_only=True, default=None)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)

    class Meta:
        model = PaymentDocumentLine
        fields = ["id", "account", "account_code", "account_name", "vendor", "vendor_name",
                  "debit", "credit", "is_deduction"]

    def validate(self, attrs):
        # A line posts to EITHER a GL account OR a vendor (a vendor-only line is
        # a direct vendor payment; its GL is the vendor's AP recon account,
        # resolved at posting). Reject a line that names neither.
        account = attrs.get("account", getattr(self.instance, "account", None))
        vendor = attrs.get("vendor", getattr(self.instance, "vendor", None))
        if account is None and vendor is None:
            raise serializers.ValidationError("Each line needs a GL account or a vendor.")
        return attrs


class PaymentDocumentSerializer(serializers.ModelSerializer):
    lines = PaymentDocumentLineSerializer(many=True)
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True)
    # The model field is blank=True (DRF would default it to not-required), so
    # override it here to make a non-blank reference MANDATORY on create AND
    # PATCH — the requiredness is enforced at the API, not the DB.
    reference_number = serializers.CharField(
        required=True, allow_blank=False, max_length=100,
        error_messages={"required": "A reference is required.", "blank": "A reference is required."},
    )
    # ``mda`` is OPTIONAL — the model field is null=True/blank=True, so the
    # ModelSerializer defaults it to not-required. It stays in Meta.fields so a
    # caller can still set it (it flows onto the posted journal's dimensions).

    # Read-only attachment metadata. The raw file URL is deliberately NOT
    # exposed — the file is only reachable via the authenticated
    # ``attachment/download`` action, and it is uploaded only via the
    # ``attachment`` action, never through this serializer's writable fields.
    has_attachment = serializers.SerializerMethodField()
    attachment_name = serializers.SerializerMethodField()

    def get_has_attachment(self, obj) -> bool:
        return bool(obj.attachment)

    def get_attachment_name(self, obj):
        # The human display name — NEVER the randomized stored path/basename.
        return obj.attachment_original_name or None

    class Meta:
        model = PaymentDocument
        fields = ["id", "document_number", "document_date", "bank_account", "bank_account_name",
                  "reference_number", "description", "status", "source",
                  "mda", "fund", "function", "program", "geo",
                  "net_amount", "journal", "lines", "has_attachment", "attachment_name",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "document_number", "status", "source", "net_amount",
                            "journal", "created_at", "updated_at"]

    def validate(self, attrs):
        # Reject any mutation of a non-Draft document BEFORE any DB write — once
        # submitted, a document is under approval / provisioned / paid and its
        # lines must never be edited. The ImmutableModelMixin only guards the
        # header ``save()``, which runs AFTER the line delete/recreate in
        # ``update()``, so the check lives here too.
        if self.instance and self.instance.status not in ("Draft", "Rejected"):
            raise serializers.ValidationError("Only a Draft or Rejected payment document can be modified.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        validated_data["document_number"] = TransactionSequence.get_next("payment_document", "PD-")
        doc = PaymentDocument.objects.create(**validated_data)
        for ln in lines:
            PaymentDocumentLine.objects.create(payment_document=doc, **ln)
        bank_gl_id = doc.bank_account.gl_account_id if doc.bank_account_id else None
        doc.net_amount = _bank_credit(list(doc.lines.all()), bank_gl_id)
        doc.save(update_fields=["net_amount"])
        return doc

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if lines is not None:
            instance.lines.all().delete()
            for ln in lines:
                PaymentDocumentLine.objects.create(payment_document=instance, **ln)
        bank_gl_id = instance.bank_account.gl_account_id if instance.bank_account_id else None
        instance.net_amount = _bank_credit(list(instance.lines.all()), bank_gl_id)
        instance.save()
        return instance


class PaymentDocumentViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    serializer_class = PaymentDocumentSerializer
    queryset = PaymentDocument.objects.prefetch_related("lines").all()
    # Tenant MDA-isolation: PaymentDocument carries an ``mda`` FK directly,
    # so in SEPARATED mode an operator sees only their own MDA's documents.
    # UNIFIED mode (the default) applies no filter.
    org_filter_field = "mda"

    # CRUD + submit inherit the project-global RBACPermission (see settings
    # DEFAULT_PERMISSION_CLASSES). There is no cash-moving action on this
    # viewset anymore: a document is submitted for approval here, and the actual
    # disbursement (IsApprover('post') + MFA) happens when the provisioned
    # Outgoing Payment is posted (accounting/views/payables.py post_payment).

    def get_throttles(self):
        # Dedicated cheap-DoS cap on the file upload: the parser reads the whole
        # body before the size check runs, so a scoped rate limit bounds how
        # often a client can force that read. Mirrors snapshots/views.py.
        if self.action == "upload_attachment":
            self.throttle_scope = "payment_doc_attachment"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def perform_destroy(self, instance):
        # Only a Draft/Rejected document may be deleted. A submitted document
        # (Pending Approval / Approved) has a live workflow Approval referencing
        # it by GenericForeignKey (no DB FK), so a hard delete would orphan the
        # approval audit trail; Paid/Void are terminal. Matches PaymentViewSet /
        # VendorInvoiceViewSet.
        if instance.status not in ("Draft", "Rejected"):
            raise serializers.ValidationError(
                "Only a Draft or Rejected payment document can be deleted."
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"], url_path="submit")
    def submit_for_approval(self, request, pk=None):
        """Submit a Draft/Rejected payment document for multi-level approval.

        Routes through the shared workflow engine (``auto_route_approval``). If
        approvals for the ``PaymentDocument`` module are Disabled/below-threshold
        the engine auto-approves and we provision the draft Outgoing Payment HERE
        (the completion signal does not fire in that path); otherwise the document
        goes ``Pending Approval`` and the draft Payment is provisioned by the
        approval-completion dispatch receiver. The document does NOT post any GL —
        that happens only when the provisioned Payment is posted in Outgoing
        Payments.
        """
        from workflow.views import auto_route_approval
        from accounting.services.document_payment_provisioning import ensure_draft_payment_for_document
        from accounting.services.payment_document_posting import (
            _lines, _validate_lines_and_bank, PaymentDocumentError,
        )
        doc = self.get_object()
        if doc.status not in ("Draft", "Rejected"):
            return Response({"error": "Only a Draft or Rejected payment document can be submitted."},
                            status=status.HTTP_400_BAD_REQUEST)
        # It must be a postable, balanced document before it enters approval.
        try:
            _validate_lines_and_bank(doc, _lines(doc))
        except PaymentDocumentError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            result = auto_route_approval(
                doc, "paymentdocument", request,
                title=f"PD-{doc.document_number}: {(doc.description or '')[:50]}",
                amount=doc.net_amount,
            )
            if result.get("auto_approved"):
                doc.status = "Approved"
                doc.save(update_fields=["status", "updated_at"], _allow_status_change=True)
                ensure_draft_payment_for_document(doc, actor=request.user)
            else:
                doc.status = "Pending Approval"
                doc.save(update_fields=["status", "updated_at"], _allow_status_change=True)

        doc.refresh_from_db()
        data = self.get_serializer(doc).data
        data["approval_id"] = result.get("approval_id")
        return Response(data)

    @action(detail=True, methods=["get"], url_path="proposed-entries")
    def proposed_entries(self, request, pk=None):
        """DR/CR preview of the document's lines AS ENTERED (bank is a real line).

        The bank credit is now an explicit document line, so this returns the
        lines exactly and does NOT append a synthetic bank leg. ``net_amount``
        is the cash out — the credit(s) against the bank's GL account.
        """
        doc = self.get_object()
        lines = list(doc.lines.select_related("account", "vendor").all())
        bank_gl_id = doc.bank_account.gl_account_id if doc.bank_account_id else None
        entries = []
        for ln in lines:
            acct = ln.account
            if acct is None and ln.vendor_id:
                # Vendor-only draft line — preview the vendor's AP recon GL it
                # will post to. Best-effort: never let a config gap 500 the
                # preview (the real check happens at post).
                try:
                    from accounting.services.procurement_posting import get_vendor_ap_account
                    acct, _src = get_vendor_ap_account(ln.vendor)
                except Exception:  # noqa: BLE001
                    acct = None
            entries.append({
                "account": acct.code if acct else "—",
                "account_name": acct.name if acct else (f"Vendor: {ln.vendor.name}" if ln.vendor_id else "—"),
                "debit": str(ln.debit or Decimal("0.00")),
                "credit": str(ln.credit or Decimal("0.00")),
            })
        return Response({"entries": entries, "net_amount": str(_bank_credit(lines, bank_gl_id))})

    @action(detail=True, methods=["post"], url_path="attachment",
            parser_classes=[MultiPartParser, FormParser])
    def upload_attachment(self, request, pk=None):
        """Attach a source-document scan (image/PDF) to the payment document.

        Fail-closed validation, in order: size cap, then BOTH allowlists
        (declared content type + lowercased extension), then a magic-byte check
        that the actual bytes match the declared kind. Allowed on Posted
        documents too — a source scan is supporting reference material, not an
        edit to the posted journal, so the metadata-only save bypasses
        ImmutableModelMixin via ``_allow_status_change=True``. Provenance
        (``updated_by``/``updated_at``) is recorded on every attach/replace,
        which matters most when the host document is already Posted.
        """
        doc = self.get_object()
        f = request.FILES.get("file")
        if not f:
            return Response({"error": "Upload a file in the 'file' field."},
                            status=status.HTTP_400_BAD_REQUEST)
        if f.size > MAX_ATTACHMENT_BYTES:
            return Response({"error": "File too large (max 10MB)."},
                            status=status.HTTP_400_BAD_REQUEST)
        ext = os.path.splitext(f.name)[1].lower()
        if (f.content_type not in ALLOWED_ATTACHMENT_CONTENT_TYPES
                or ext not in ALLOWED_ATTACHMENT_EXTENSIONS):
            return Response({"error": "Only images (PNG/JPG/WEBP/GIF) or PDF are allowed."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not _attachment_bytes_match_type(f):
            return Response({"error": "File content does not match its declared type."},
                            status=status.HTTP_400_BAD_REQUEST)
        # Stored under a random UUID name; keep the human name for display.
        doc.attachment.save(f.name, f, save=False)
        doc.attachment_original_name = f.name
        doc.updated_by = request.user
        doc.save(
            update_fields=["attachment", "attachment_original_name", "updated_by", "updated_at"],
            _allow_status_change=True,
        )
        return Response(self.get_serializer(doc).data)

    @action(detail=True, methods=["get"], url_path="attachment/download")
    def download_attachment(self, request, pk=None):
        """Stream the attachment inline over an authenticated request.

        Inherits ``get_permissions`` → the project-global RBACPermission (view
        perm), so the file is NEVER served as an open /media URL.
        """
        doc = self.get_object()
        if not doc.attachment:
            return Response({"error": "No attachment on this document."},
                            status=status.HTTP_404_NOT_FOUND)
        resp = FileResponse(doc.attachment.open("rb"))
        resp["Content-Disposition"] = f'inline; filename="{os.path.basename(doc.attachment.name)}"'
        return resp

    @action(detail=False, methods=["get"], url_path="download-template")
    def download_template(self, request):
        from django.http import HttpResponse
        from accounting.services.payment_document_import import build_template_csv
        resp = HttpResponse(build_template_csv(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="payment-document-template.csv"'
        return resp

    @action(detail=False, methods=["post"], url_path="import")
    def bulk_import(self, request):
        from accounting.services.payment_document_import import parse_rows, import_payment_documents_from_rows
        f = request.FILES.get("file")
        if not f:
            return Response({"error": "Upload a CSV file in the 'file' field."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rows = parse_rows(f.read())
            created = import_payment_documents_from_rows(rows, source="import")
        except Exception:  # noqa: BLE001
            logger.exception("Payment document import failed")
            return Response({"error": "Import failed. Check the file format and values."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"created": len(created),
                         "documents": self.get_serializer(created, many=True).data},
                        status=status.HTTP_201_CREATED)
