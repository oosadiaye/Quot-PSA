"""HR-side endpoints for the leave approval queue.

Routes (mounted under ``/api/hrm/leave-approvals/``):
    GET  pending/                       → steps awaiting the current user
    POST <step_pk>/decide/              → record an Approved/Rejected decision
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from hrm.models import LeaveApprovalStep
from hrm.services.leave_approval import (
    ApprovalError,
    decide_step,
    pending_steps_for,
)


def _serialize_step(step: LeaveApprovalStep) -> dict:
    req = step.leave_request
    emp = req.employee
    return {
        "id": step.pk,
        "step_order": step.step_order,
        "role": step.role,
        "decision": step.decision,
        "decided_at": step.decided_at.isoformat() if step.decided_at else None,
        "comments": step.comments,
        "request": {
            "id": req.pk,
            "status": req.status,
            "start_date": req.start_date.isoformat(),
            "end_date": req.end_date.isoformat(),
            "total_days": str(req.total_days),
            "reason": req.reason,
            "leave_type": req.leave_type.name,
            "employee": {
                "id": emp.pk,
                "name": f"{emp.first_name} {emp.last_name}",
                "employee_id": emp.employee_id,
            },
        },
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_approvals(request: Request) -> Response:
    """Return approval steps assigned to the calling user."""
    qs = pending_steps_for(request.user).order_by("leave_request_id", "step_order")
    return Response({"results": [_serialize_step(s) for s in qs]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decide_approval(request: Request, pk: int) -> Response:
    """Record a decision on a specific approval step."""
    try:
        step = LeaveApprovalStep.objects.select_related(
            "leave_request", "leave_request__employee", "leave_request__leave_type",
        ).get(pk=pk)
    except LeaveApprovalStep.DoesNotExist:
        return Response({"detail": "Step not found."}, status=status.HTTP_404_NOT_FOUND)

    data = request.data if isinstance(request.data, dict) else {}
    decision = data.get("decision")
    comments = data.get("comments", "")

    # Enforce assignment if step has a specific assignee.
    if step.assigned_to and step.assigned_to_id != request.user.pk:
        return Response(
            {"detail": "This step is assigned to another user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        leave_request = decide_step(
            step, user=request.user, decision=decision, comments=comments,
        )
    except ApprovalError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    step.refresh_from_db()
    return Response({
        "step": _serialize_step(step),
        "request_status": leave_request.status,
    })
