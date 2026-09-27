"""Payment Document API — CRUD, approver+MFA-gated post, proposed-entries preview."""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounting.models import PaymentDocument, PaymentDocumentLine, TransactionSequence
from accounting.services.base_posting import TransactionPostingError
from accounting.services.payment_document_posting import (
    PaymentDocumentError, _bank_credit, post_payment_document,
)
from core.mixins import OrganizationFilterMixin
from core.permissions import IsApprover

logger = logging.getLogger(__name__)


class PaymentDocumentLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)

    class Meta:
        model = PaymentDocumentLine
        fields = ["id", "account", "account_code", "account_name", "vendor", "vendor_name",
                  "debit", "credit", "is_deduction"]


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

    class Meta:
        model = PaymentDocument
        fields = ["id", "document_number", "document_date", "bank_account", "bank_account_name",
                  "reference_number", "description", "status", "source",
                  "mda", "fund", "function", "program", "geo",
                  "net_amount", "journal", "lines", "created_at", "updated_at"]
        read_only_fields = ["id", "document_number", "status", "source", "net_amount",
                            "journal", "created_at", "updated_at"]

    def validate(self, attrs):
        # Reject any mutation of a posted document BEFORE any DB write — the
        # posted journal's lines must never be destroyed by an edit. The
        # ImmutableModelMixin only guards the header ``save()``, which runs
        # AFTER the line delete/recreate in ``update()``.
        if self.instance and self.instance.status == "Posted":
            raise serializers.ValidationError("Cannot modify a posted payment document.")
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

    def get_permissions(self):
        # CRUD inherits the project-global RBACPermission (see settings
        # DEFAULT_PERMISSION_CLASSES); only the cash-moving ``post`` action is
        # gated by approval authority + MFA (both exempt superusers/admins).
        from accounting.permissions import RequiresMFA
        if self.action == "post":
            return [IsApprover("post"), RequiresMFA()]
        return super().get_permissions()

    @action(detail=True, methods=["post"], url_path="post")
    def post(self, request, pk=None):
        doc = self.get_object()
        try:
            post_payment_document(doc, actor=request.user)
        except (PaymentDocumentError, TransactionPostingError, DjangoValidationError) as exc:
            messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
            return Response({"error": " ".join(messages)}, status=status.HTTP_400_BAD_REQUEST)
        doc.refresh_from_db()
        return Response(self.get_serializer(doc).data)

    @action(detail=True, methods=["get"], url_path="proposed-entries")
    def proposed_entries(self, request, pk=None):
        """DR/CR preview of the document's lines AS ENTERED (bank is a real line).

        The bank credit is now an explicit document line, so this returns the
        lines exactly and does NOT append a synthetic bank leg. ``net_amount``
        is the cash out — the credit(s) against the bank's GL account.
        """
        doc = self.get_object()
        lines = list(doc.lines.select_related("account").all())
        bank_gl_id = doc.bank_account.gl_account_id if doc.bank_account_id else None
        entries = [
            {"account": ln.account.code, "account_name": ln.account.name,
             "debit": str(ln.debit or Decimal("0.00")), "credit": str(ln.credit or Decimal("0.00"))}
            for ln in lines
        ]
        return Response({"entries": entries, "net_amount": str(_bank_credit(lines, bank_gl_id))})

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
