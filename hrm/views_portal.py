"""Employee self-service portal views.

Endpoints expose an authenticated employee's *own* data only.  All
querysets are scoped to ``request.user.employee`` so one employee can
never see another's payroll or leave data.

Routes (mounted under ``/api/my/``):

* ``GET  /profile``
* ``PATCH /profile``
* ``GET  /payslips``
* ``GET  /payslips/<id>``
* ``GET  /payslips/<id>/pdf``
* ``GET  /leave/balances``
* ``GET  /leave/requests``
* ``POST /leave/requests``
* ``POST /leave/requests/<id>/cancel``
* ``GET  /dashboard``
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from hrm.models import (
    Employee,
    EmployeeDocument,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    PayrollLine,
    Payslip,
    VerificationCycle,
    VerificationSubmission,
)
from hrm.services.payslip_pdf import render_payslip_pdf

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class IsAuthenticatedEmployee(permissions.BasePermission):
    """Grants access only to users with an attached :class:`Employee`."""

    message = "This endpoint is only available to employees."

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return Employee.objects.filter(user=user).exists()


def _get_employee(request: Request) -> Employee:
    try:
        return Employee.objects.select_related("department", "position", "user").get(
            user=request.user
        )
    except Employee.DoesNotExist as exc:  # pragma: no cover - guarded by perm
        raise PermissionDenied("No employee record linked to this user.") from exc


# ---------------------------------------------------------------------------
# Serializer helpers (lightweight — we deliberately avoid exposing sensitive
# statutory IDs or bank routing numbers through the portal).
# ---------------------------------------------------------------------------


def _serialize_employee(emp: Employee) -> dict[str, Any]:
    return {
        "id": emp.pk,
        "employee_number": emp.employee_number,
        "full_name": emp.user.get_full_name() or emp.user.username,
        "email": emp.user.email,
        "personal_info": emp.personal_info or {},
        "department": getattr(emp.department, "name", None),
        "position": getattr(emp.position, "title", None) or getattr(emp.position, "name", None),
        "employee_type": emp.employee_type,
        "hire_date": emp.hire_date,
        "confirmation_date": emp.confirmation_date,
        "status": emp.status,
        "emergency_contact_name": emp.emergency_contact_name,
        "emergency_contact_phone": emp.emergency_contact_phone,
        "emergency_contact_relation": emp.emergency_contact_relation,
        "bank_name": emp.bank_name,
        "bank_account_last4": emp.bank_account[-4:] if emp.bank_account else "",
    }


def _serialize_payroll_line(line: PayrollLine, include_detail: bool = False) -> dict[str, Any]:
    run = line.payroll_run
    period = run.period
    payload: dict[str, Any] = {
        "id": line.pk,
        "period_label": period.start_date.strftime("%B %Y"),
        "period_start": period.start_date,
        "period_end": period.end_date,
        "payment_date": period.payment_date,
        "run_number": run.run_number,
        "run_status": run.status,
        "basic_salary": line.basic_salary,
        "gross_salary": line.gross_salary,
        "total_deductions": line.total_deductions,
        "net_salary": line.net_salary,
    }
    if include_detail:
        payload["earnings"] = [
            {"name": row.component.name, "amount": row.amount}
            for row in line.earnings.select_related("component").all()
        ]
        payload["deductions"] = [
            {"name": row.component.name, "amount": row.amount}
            for row in line.deductions.select_related("component").all()
        ]
        payload["tax_deduction"] = line.tax_deduction
        payload["pension_deduction"] = line.pension_deduction
        payload["other_deductions"] = line.other_deductions
        payload["overtime_hours"] = line.overtime_hours
        payload["overtime_amount"] = line.overtime_amount
    return payload


def _serialize_leave_request(req: LeaveRequest) -> dict[str, Any]:
    return {
        "id": req.pk,
        "leave_type": req.leave_type.name,
        "leave_type_id": req.leave_type_id,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "total_days": req.total_days,
        "reason": req.reason,
        "status": req.status,
        "comments": req.comments,
        "approved_date": req.approved_date,
        "created_at": getattr(req, "created_at", None),
    }


def _serialize_leave_balance(bal: LeaveBalance) -> dict[str, Any]:
    return {
        "id": bal.pk,
        "leave_type": bal.leave_type.name,
        "leave_type_id": bal.leave_type_id,
        "year": bal.year,
        "allocated": bal.allocated,
        "taken": bal.taken,
        "balance": bal.balance,
    }


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


_PROFILE_EDITABLE_FIELDS = {
    "emergency_contact_name",
    "emergency_contact_phone",
    "emergency_contact_relation",
    "personal_info",
}


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticatedEmployee])
def my_profile(request: Request) -> Response:
    emp = _get_employee(request)

    if request.method == "PATCH":
        data = request.data if isinstance(request.data, dict) else {}
        unknown = set(data) - _PROFILE_EDITABLE_FIELDS
        if unknown:
            raise ValidationError(
                {"detail": f"Fields not editable through portal: {sorted(unknown)}"}
            )
        for key in _PROFILE_EDITABLE_FIELDS & set(data):
            setattr(emp, key, data[key])
        emp.save(update_fields=list(_PROFILE_EDITABLE_FIELDS & set(data)))
        logger.info("Portal profile update by employee %s", emp.employee_number)

    return Response(_serialize_employee(emp))


# ---------------------------------------------------------------------------
# Payslips
# ---------------------------------------------------------------------------


_PAYSLIP_VISIBLE_STATUSES = {"Approved", "Paid"}


def _payslip_qs_for(emp: Employee):
    return (
        PayrollLine.objects.filter(
            employee=emp, payroll_run__status__in=_PAYSLIP_VISIBLE_STATUSES
        )
        .select_related("payroll_run", "payroll_run__period")
        .order_by("-payroll_run__period__start_date")
    )


@api_view(["GET"])
@permission_classes([IsAuthenticatedEmployee])
def my_payslips(request: Request) -> Response:
    emp = _get_employee(request)
    lines = _payslip_qs_for(emp)
    return Response({"results": [_serialize_payroll_line(l) for l in lines]})


@api_view(["GET"])
@permission_classes([IsAuthenticatedEmployee])
def my_payslip_detail(request: Request, pk: int) -> Response:
    emp = _get_employee(request)
    try:
        line = _payslip_qs_for(emp).get(pk=pk)
    except PayrollLine.DoesNotExist:
        raise NotFound("Payslip not found.")
    return Response(_serialize_payroll_line(line, include_detail=True))


@api_view(["GET"])
@permission_classes([IsAuthenticatedEmployee])
def my_payslip_pdf(request: Request, pk: int) -> HttpResponse:
    emp = _get_employee(request)
    try:
        line = _payslip_qs_for(emp).get(pk=pk)
    except PayrollLine.DoesNotExist:
        raise NotFound("Payslip not found.")

    # Mark any existing Payslip record as Viewed for auditability.
    Payslip.objects.filter(payroll_line=line).update(status="Viewed")

    org_name = _get_organization_name()
    try:
        pdf_bytes = render_payslip_pdf(line, organization_name=org_name)
    except RuntimeError as exc:
        return Response(
            {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    filename = f"payslip-{emp.employee_number}-{line.payroll_run.period.start_date:%Y-%m}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _get_organization_name() -> str:
    """Best-effort organization name lookup.  Falls back to tenant schema."""
    try:
        from superadmin.models import SuperAdminSettings  # type: ignore
        s = SuperAdminSettings.objects.first()
        if s and getattr(s, "organization_name", ""):
            return s.organization_name
    except Exception:
        pass
    try:
        from django.db import connection  # type: ignore
        tenant = getattr(connection, "tenant", None)
        if tenant and getattr(tenant, "name", ""):
            return tenant.name
    except Exception:
        pass
    return "Payroll"


# ---------------------------------------------------------------------------
# Leave
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticatedEmployee])
def my_leave_types(request: Request) -> Response:
    """Minimal list of active leave types for the portal leave-request form."""
    types = LeaveType.objects.filter(is_active=True).order_by("name")
    return Response({
        "results": [
            {
                "id": t.pk,
                "name": t.name,
                "code": t.code,
                "max_days_per_year": t.max_days_per_year,
                "is_paid": t.is_paid,
            }
            for t in types
        ]
    })


@api_view(["GET"])
@permission_classes([IsAuthenticatedEmployee])
def my_leave_balances(request: Request) -> Response:
    emp = _get_employee(request)
    year = int(request.query_params.get("year") or timezone.now().year)
    balances = (
        LeaveBalance.objects.filter(employee=emp, year=year)
        .select_related("leave_type")
        .order_by("leave_type__name")
    )
    return Response({
        "year": year,
        "results": [_serialize_leave_balance(b) for b in balances],
    })


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticatedEmployee])
def my_leave_requests(request: Request) -> Response:
    emp = _get_employee(request)

    if request.method == "GET":
        qs = (
            LeaveRequest.objects.filter(employee=emp)
            .select_related("leave_type")
            .order_by("-start_date")
        )
        return Response({"results": [_serialize_leave_request(r) for r in qs]})

    # POST — create new leave request in 'Pending' status.
    data = request.data if isinstance(request.data, dict) else {}
    required = {"leave_type_id", "start_date", "end_date", "reason"}
    missing = required - set(data)
    if missing:
        raise ValidationError({"detail": f"Missing fields: {sorted(missing)}"})

    try:
        leave_type = LeaveType.objects.get(pk=data["leave_type_id"], is_active=True)
    except LeaveType.DoesNotExist:
        raise ValidationError({"leave_type_id": "Unknown or inactive leave type."})

    req = LeaveRequest.objects.create(
        employee=emp,
        leave_type=leave_type,
        start_date=data["start_date"],
        end_date=data["end_date"],
        reason=data["reason"],
        status="Draft",
    )
    # Kick off multi-step approval chain (Line Manager → HR).
    from hrm.services.leave_approval import submit_request
    try:
        submit_request(req, user=request.user)
    except Exception as exc:  # noqa: BLE001  surface as 400 instead of 500
        req.delete()
        raise ValidationError({"detail": str(exc)})

    logger.info("Portal leave request %s submitted by %s", req.pk, emp.employee_number)
    _notify_leave_submitted(req)

    return Response(_serialize_leave_request(req), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticatedEmployee])
def my_leave_cancel(request: Request, pk: int) -> Response:
    emp = _get_employee(request)
    try:
        req = LeaveRequest.objects.get(pk=pk, employee=emp)
    except LeaveRequest.DoesNotExist:
        raise NotFound("Leave request not found.")
    if req.status not in {"Draft", "Pending"}:
        raise ValidationError(
            {"detail": f"Cannot cancel a request in status '{req.status}'."}
        )
    req.status = "Cancelled"
    req.save(update_fields=["status"])
    return Response(_serialize_leave_request(req))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticatedEmployee])
def my_dashboard(request: Request) -> Response:
    emp = _get_employee(request)
    year = timezone.now().year

    latest_line = _payslip_qs_for(emp).first()

    balances = (
        LeaveBalance.objects.filter(employee=emp, year=year)
        .select_related("leave_type")
        .order_by("leave_type__name")
    )
    pending_leave = LeaveRequest.objects.filter(employee=emp, status="Pending").count()

    upcoming_leave = (
        LeaveRequest.objects.filter(
            employee=emp,
            status="Approved",
            end_date__gte=timezone.now().date(),
        )
        .order_by("start_date")
        .first()
    )

    return Response({
        "employee": _serialize_employee(emp),
        "latest_payslip": _serialize_payroll_line(latest_line) if latest_line else None,
        "leave_balances": [_serialize_leave_balance(b) for b in balances],
        "pending_leave_requests": pending_leave,
        "upcoming_leave": _serialize_leave_request(upcoming_leave) if upcoming_leave else None,
    })


# ---------------------------------------------------------------------------
# Notifications (best-effort; never block the mutation on email failure)
# ---------------------------------------------------------------------------


def _notify_leave_submitted(req: LeaveRequest) -> None:
    try:
        from core.localized_emails import send_localized_email  # type: ignore
    except Exception:
        return
    try:
        employee = req.employee
        if not employee.user.email:
            return
        send_localized_email(
            template_key="leave_submitted",
            recipient=employee.user.email,
            context={
                "employee_name": employee.user.get_full_name() or employee.user.username,
                "leave_type": req.leave_type.name,
                "start_date": req.start_date.isoformat(),
                "end_date": req.end_date.isoformat(),
                "total_days": str(req.total_days),
                "reason": req.reason,
            },
        )
    except Exception:
        logger.exception("leave_submitted notification failed for req=%s", req.pk)


# ---------------------------------------------------------------------------
# Employee Documents (Phase 2 — personnel file)
# ---------------------------------------------------------------------------


_ALLOWED_DOC_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB


def _serialize_document(doc: EmployeeDocument) -> dict[str, Any]:
    return {
        "id": doc.pk,
        "category": doc.category,
        "category_label": doc.get_category_display(),
        "title": doc.title,
        "original_filename": doc.original_filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "issued_on": doc.issued_on.isoformat() if doc.issued_on else None,
        "expires_on": doc.expires_on.isoformat() if doc.expires_on else None,
        "status": doc.status,
        "hr_notes": doc.hr_notes,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "verified_at": doc.verified_at.isoformat() if doc.verified_at else None,
        "download_url": doc.file.url if doc.file else None,
    }


_VALID_DOC_CATEGORIES = {c[0] for c in EmployeeDocument.CATEGORY_CHOICES}


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticatedEmployee])
def my_documents(request: Request) -> Response:
    """List or upload personnel documents for the authenticated employee."""
    emp = _get_employee(request)

    if request.method == "GET":
        qs = EmployeeDocument.objects.filter(employee=emp).order_by("-uploaded_at")
        return Response({"results": [_serialize_document(d) for d in qs]})

    # POST — multipart upload
    upload = request.FILES.get("file")
    if upload is None:
        raise ValidationError({"file": "A file is required."})
    if upload.size > _MAX_DOC_BYTES:
        raise ValidationError({"file": "File exceeds the 10 MB limit."})
    if upload.content_type and upload.content_type not in _ALLOWED_DOC_MIME:
        raise ValidationError(
            {"file": f"Unsupported file type: {upload.content_type}"}
        )

    category = (request.data.get("category") or "").strip()
    if category not in _VALID_DOC_CATEGORIES:
        raise ValidationError({"category": "Invalid document category."})

    title = (request.data.get("title") or "").strip()[:200]
    issued_on = request.data.get("issued_on") or None
    expires_on = request.data.get("expires_on") or None

    doc = EmployeeDocument.objects.create(
        employee=emp,
        category=category,
        title=title,
        file=upload,
        original_filename=getattr(upload, "name", "")[:255],
        content_type=(upload.content_type or "")[:100],
        size_bytes=upload.size,
        issued_on=issued_on or None,
        expires_on=expires_on or None,
        status="uploaded",
        created_by=request.user,
    )
    return Response(_serialize_document(doc), status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticatedEmployee])
def my_document_delete(request: Request, pk: int) -> Response:
    """Remove a document the employee uploaded — only while still unverified."""
    emp = _get_employee(request)
    try:
        doc = EmployeeDocument.objects.get(pk=pk, employee=emp)
    except EmployeeDocument.DoesNotExist as exc:
        raise NotFound("Document not found.") from exc
    if doc.status == "verified":
        raise ValidationError(
            {"status": "Verified documents can only be removed by HR."}
        )
    # Preserve the file on disk for audit; detach by deleting the DB row only.
    doc.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Verification Cycles (ghost-worker elimination)
# ---------------------------------------------------------------------------


def _serialize_cycle(cycle: VerificationCycle) -> dict[str, Any]:
    return {
        "id": cycle.pk,
        "name": cycle.name,
        "period_type": cycle.period_type,
        "period_label": cycle.get_period_type_display(),
        "start_date": cycle.start_date.isoformat(),
        "deadline": cycle.deadline.isoformat(),
        "status": cycle.status,
        "instructions": cycle.instructions,
    }


def _serialize_submission(sub: VerificationSubmission) -> dict[str, Any]:
    return {
        "id": sub.pk,
        "cycle": _serialize_cycle(sub.cycle),
        "status": sub.status,
        "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
        "verified_at": sub.verified_at.isoformat() if sub.verified_at else None,
        "employee_attestation": sub.employee_attestation or {},
        "hr_notes": sub.hr_notes,
        "rejection_reason": sub.rejection_reason,
        "document_ids": list(sub.documents.values_list("id", flat=True)),
    }


def _ensure_submission(emp: Employee, cycle: VerificationCycle) -> VerificationSubmission:
    """Lazy-create the employee's row for an active cycle on first access."""
    sub, _created = VerificationSubmission.objects.get_or_create(
        cycle=cycle, employee=emp, defaults={"status": "pending"}
    )
    return sub


@api_view(["GET"])
@permission_classes([IsAuthenticatedEmployee])
def my_verification_cycles(request: Request) -> Response:
    """Return every active cycle plus the employee's submission for each.

    Active cycles drive the dashboard banner + `/portal/documents` CTA.
    """
    emp = _get_employee(request)
    active = VerificationCycle.objects.filter(status="active").order_by("-start_date")
    results = []
    for cycle in active:
        sub = _ensure_submission(emp, cycle)
        results.append(_serialize_submission(sub))
    return Response({"results": results})


@api_view(["POST"])
@permission_classes([IsAuthenticatedEmployee])
def my_verification_submit(request: Request, pk: int) -> Response:
    """Employee attestation — freeze a snapshot and mark submitted."""
    emp = _get_employee(request)
    try:
        cycle = VerificationCycle.objects.get(pk=pk, status="active")
    except VerificationCycle.DoesNotExist as exc:
        raise NotFound("Verification cycle is not active.") from exc

    sub = _ensure_submission(emp, cycle)
    if sub.status in {"submitted", "verified"}:
        raise ValidationError({"status": "Already submitted for this cycle."})

    attestation = request.data.get("attestation") or {}
    if not isinstance(attestation, dict) or not attestation.get("confirm_accurate"):
        raise ValidationError(
            {"attestation": "You must confirm the information is accurate."}
        )

    # Snapshot authoritative employee fields so audit can replay the claim.
    snapshot = {
        "employee_number": emp.employee_number,
        "full_name": emp.user.get_full_name() or emp.user.username,
        "email": emp.user.email,
        "department": getattr(emp.department, "name", None),
        "position": getattr(emp.position, "title", None),
        "employee_type": emp.employee_type,
        "status": emp.status,
        "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
        "bank_name": getattr(emp, "bank_name", "") or "",
        "bank_account_last4": (
            (getattr(emp, "bank_account_number", "") or "")[-4:]
            if getattr(emp, "bank_account_number", None)
            else ""
        ),
        "emergency_contact_name": getattr(emp, "emergency_contact_name", "") or "",
        "emergency_contact_phone": getattr(emp, "emergency_contact_phone", "") or "",
        "attested_at": timezone.now().isoformat(),
        "attested_by_user_id": request.user.pk,
        "confirm_accurate": True,
        "notes": (attestation.get("notes") or "")[:2000],
    }

    document_ids = request.data.get("document_ids") or []
    if document_ids:
        docs = EmployeeDocument.objects.filter(
            employee=emp, pk__in=document_ids
        )
        sub.documents.set(list(docs))

    sub.employee_attestation = snapshot
    sub.status = "submitted"
    sub.submitted_at = timezone.now()
    sub.updated_by = request.user
    sub.save(update_fields=["employee_attestation", "status", "submitted_at", "updated_by", "updated_at"])

    return Response(_serialize_submission(sub))
