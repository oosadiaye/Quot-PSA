"""Payment Document API — CRUD, approver+MFA-gated post, proposed-entries preview."""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import PaymentDocument, PaymentDocumentLine, TransactionSequence
from accounting.services.base_posting import TransactionPostingError
from accounting.services.payment_document_posting import (
    PaymentDocumentError, compute_net, post_payment_document,
)
from core.permissions import IsApprover


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

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        validated_data["document_number"] = TransactionSequence.get_next("payment_document", "PD-")
        doc = PaymentDocument.objects.create(**validated_data)
        for ln in lines:
            PaymentDocumentLine.objects.create(payment_document=doc, **ln)
        doc.net_amount = compute_net(list(doc.lines.all()))
        doc.save(update_fields=["net_amount"])
        return doc

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


class PaymentDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentDocumentSerializer
    permission_classes = [IsAuthenticated]
    queryset = PaymentDocument.objects.prefetch_related("lines").all()

    def get_permissions(self):
        from accounting.permissions import RequiresMFA
        if self.action == "post":
            return [IsApprover("post"), RequiresMFA()]
        return super().get_permissions()

    @action(detail=True, methods=["post"], url_path="post")
    def post(self, request, pk=None):
        doc = self.get_object()
        try:
            post_payment_document(doc, actor=request.user)
        except (PaymentDocumentError, TransactionPostingError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 - budget ValidationError etc.; clean message out
            msg = getattr(exc, "messages", None)
            return Response({"error": (msg[0] if msg else str(exc))}, status=status.HTTP_400_BAD_REQUEST)
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
