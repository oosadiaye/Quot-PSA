"""Unified read-only Payment Proposal register.

A union of Payment Vouchers (PaymentVoucherGov) and Payment Documents
(PaymentDocument) into one common row shape, filterable by a unified proposal
status. Read-only: each source keeps its own model, serializers and write paths;
this endpoint only merges them for the register list + status tabs. The row's
``detail_path`` points at the source's native detail page.

MDA scoping: the default (UNIFIED) organisation mode applies no per-MDA filter
(admins see every row), matching the source viewsets' default. Tightening to
per-MDA scope for SEPARATED-mode tenants is a tracked follow-up.
"""
from decimal import Decimal

from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.models import PaymentDocument

# Native status → unified proposal status (used only for the register + tabs).
PV_UNIFIED = {
    "DRAFT": "Proposed", "CHECKED": "Proposed", "AUDITED": "Proposed",
    "APPROVED": "Approved", "SCHEDULED": "Approved",
    "PAID": "Paid",
    "CANCELLED": "Void", "REVERSED": "Void",
}
PD_UNIFIED = {
    "Draft": "Proposed", "Pending Approval": "Proposed",
    "Approved": "Approved",
    "Paid": "Paid",
    "Rejected": "Void", "Void": "Void",
}


def _pv_row(pv):
    return {
        "source": "pv",
        "id": pv.pk,
        "number": pv.voucher_number,
        "date": pv.created_at.date().isoformat() if pv.created_at else None,
        "payee_or_description": getattr(pv, "payee_name", "") or "",
        "amount": str(pv.net_amount if pv.net_amount is not None else Decimal("0.00")),
        "native_status": pv.status,
        "unified_status": PV_UNIFIED.get(pv.status, "Proposed"),
        "detail_path": f"/accounting/payment-vouchers/{pv.pk}",
    }


def _pd_row(pd):
    return {
        "source": "pd",
        "id": pd.pk,
        "number": pd.document_number,
        "date": pd.document_date.isoformat() if pd.document_date else None,
        "payee_or_description": pd.description or "",
        "amount": str(pd.net_amount if pd.net_amount is not None else Decimal("0.00")),
        "native_status": pd.status,
        "unified_status": PD_UNIFIED.get(pd.status, "Proposed"),
        "detail_path": f"/accounting/payment-documents/{pd.pk}",
    }


class PaymentProposalsView(APIView):
    """GET /api/v1/accounting/payment-proposals/?status=<unified>&source=<pv|pd>

    ``model`` is set so the project-global RBACPermission enforces
    ``accounting.view_paymentdocument`` for this read (otherwise its
    no-queryset fallback would allow GET for ANY authenticated role). A caller
    who can view payment documents can view the whole proposal register.
    """
    model = PaymentDocument

    def get(self, request):
        from accounting.models.treasury import PaymentVoucherGov

        want_status = request.query_params.get("status") or None   # unified value
        want_source = request.query_params.get("source") or None   # 'pv' | 'pd'

        rows = []
        if want_source in (None, "pv"):
            rows += [_pv_row(pv) for pv in PaymentVoucherGov.objects.all()]
        if want_source in (None, "pd"):
            rows += [_pd_row(pd) for pd in PaymentDocument.objects.all()]

        if want_status:
            rows = [r for r in rows if r["unified_status"] == want_status]
        rows.sort(key=lambda r: (r["date"] or ""), reverse=True)
        return Response({"results": rows, "count": len(rows)})
