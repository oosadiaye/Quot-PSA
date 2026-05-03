"""URL wiring for the employee self-service portal.

Mounted at ``/api/my/`` by ``quot_pse/urls.py``.
"""
from django.urls import path

from hrm import views_portal as v

urlpatterns = [
    path("dashboard", v.my_dashboard, name="portal-dashboard"),
    path("profile", v.my_profile, name="portal-profile"),
    path("payslips", v.my_payslips, name="portal-payslips"),
    path("payslips/<int:pk>", v.my_payslip_detail, name="portal-payslip-detail"),
    path("payslips/<int:pk>/pdf", v.my_payslip_pdf, name="portal-payslip-pdf"),
    path("leave/types", v.my_leave_types, name="portal-leave-types"),
    path("leave/balances", v.my_leave_balances, name="portal-leave-balances"),
    path("leave/requests", v.my_leave_requests, name="portal-leave-requests"),
    path("leave/requests/<int:pk>/cancel", v.my_leave_cancel, name="portal-leave-cancel"),
    path("documents", v.my_documents, name="portal-documents"),
    path("documents/<int:pk>", v.my_document_delete, name="portal-document-delete"),
    path("verification/cycles", v.my_verification_cycles, name="portal-verification-cycles"),
    path("verification/cycles/<int:pk>/submit", v.my_verification_submit, name="portal-verification-submit"),
]
