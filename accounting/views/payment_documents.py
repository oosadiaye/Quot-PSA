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
    PaymentDocumentError, compute_net, post_payment_document,
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
                  "debit", "credit", "memo", "is_deduction"]


class PaymentDocumentSerializer(serializers.ModelSerializer):
    lines = PaymentDocumentLineSerializer(many=True)
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True)

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
        doc.net_amount = compute_net(list(doc.lines.all()))
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
        instance.net_amount = compute_net(list(instance.lines.all()))
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
        """Balanced DR/CR preview (computed, not persisted)."""
        doc = self.get_object()
        lines = list(doc.lines.select_related("account").all())
        net = compute_net(lines)
        entries = [
            {"account": ln.account.code, "account_name": ln.account.name,
             "debit": str(ln.debit or Decimal("0.00")), "credit": str(ln.credit or Decimal("0.00"))}
            for ln in lines
        ]
        bank = doc.bank_account
        entries.append({
            "account": getattr(bank.gl_account, "code", ""), "account_name": "Bank",
            "debit": "0.00", "credit": str(net if net > 0 else Decimal("0.00")),
        })
        return Response({"entries": entries, "net_amount": str(net)})

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
