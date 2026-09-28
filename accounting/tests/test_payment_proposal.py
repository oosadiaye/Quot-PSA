from decimal import Decimal
import pytest


@pytest.fixture
def pp_bank(db):
    from accounting.models import Account, BankAccount
    gl, _ = Account.objects.get_or_create(
        code="31010101", defaults={"name": "TSA Cash", "account_type": "Asset",
                                    "is_active": True, "is_postable": True,
                                    "reconciliation_type": "bank_accounting"})
    bank, _ = BankAccount.objects.get_or_create(
        account_number="0000000009",
        defaults={"name": "PP TSA", "bank_name": "CBN", "gl_account": gl,
                  "current_balance": Decimal("1000000.00"), "currency": None})
    return bank


@pytest.fixture
def pp_api(db):
    """Superuser APIClient pinned to the pytest tenant, re-asserting the public
    Client+Domain first. A preceding ``transaction=True`` test flushes those
    rows (see project memory ci_tenant_flush_wipes_domain), which otherwise 400s
    'Unknown tenant domain' on the next request. Mirrors ``pd_api``."""
    from django.db import connection
    from rest_framework.test import APIClient
    from django.contrib.auth import get_user_model
    from tenants.models import Client, Domain
    connection.set_schema_to_public()
    try:
        tenant, _ = Client.objects.get_or_create(schema_name="pytest_schema", defaults={"name": "PyTest Tenant"})
        Domain.objects.get_or_create(domain="pytest.localhost", tenant=tenant, defaults={"is_primary": True})
        User = get_user_model()
        user, _ = User.objects.get_or_create(username="pp_admin", defaults={"is_staff": True, "is_superuser": True})
    finally:
        connection.set_schema("pytest_schema")
    client = APIClient(HTTP_X_TENANT_DOMAIN="pytest.localhost")
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_payment_cannot_have_both_pv_and_document(pp_bank):
    """A Payment is PV-sourced OR PD-sourced, never both."""
    from django.db import IntegrityError, transaction
    from accounting.models import Payment, PaymentVoucherGov, PaymentDocument
    # PaymentVoucherGov requires ncoa_code/tsa_account (real FKs, no default);
    # reuse the proven fixture helpers from test_central_payment_processing
    # instead of re-deriving the NCoA segment tree here.
    from accounting.tests.test_central_payment_processing import _ncoa, _tsa
    pv = PaymentVoucherGov.objects.create(
        voucher_number="PV-PP-1", payment_type="VENDOR", ncoa_code=_ncoa(),
        payee_name="Test Payee", narration="payment proposal test",
        tsa_account=_tsa(), gross_amount=Decimal("100.00"), net_amount=Decimal("100.00"))
    pd = PaymentDocument.objects.create(document_number="PD-PP-1", bank_account=pp_bank)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Payment.objects.create(bank_account=pp_bank, total_amount=Decimal("100.00"),
                                   payment_voucher=pv, payment_document=pd)


# ── Task 2: Payment Document proposal lifecycle ──────────────────────────────

@pytest.mark.django_db
def test_payment_document_has_proposal_statuses(pp_bank):
    from accounting.models import PaymentDocument
    values = {c[0] for c in PaymentDocument._meta.get_field("status").choices}
    assert {"Draft", "Pending Approval", "Approved", "Paid", "Void"} <= values


@pytest.mark.django_db
def test_paid_payment_document_is_immutable(pp_bank):
    """A Paid Payment Document cannot be edited without the _allow_status_change
    escape hatch — the immutability guard extends to the new terminal state."""
    from django.core.exceptions import ValidationError
    from accounting.models import PaymentDocument
    pd = PaymentDocument.objects.create(document_number="PD-IMM-1", bank_account=pp_bank, status="Draft")
    pd.status = "Paid"
    pd.save(_allow_status_change=True)     # a legitimate transition still works
    pd.description = "tampered"
    with pytest.raises(ValidationError):
        pd.save()                          # editing a Paid doc without the hatch is blocked


# ── Task 4: provisioning a Draft Payment for an approved document ─────────────

@pytest.mark.django_db
def test_ensure_draft_payment_for_document_is_idempotent(pp_bank):
    from django.db import transaction
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account, Payment
    from accounting.services.document_payment_provisioning import ensure_draft_payment_for_document
    liab, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    pd = PaymentDocument.objects.create(document_number="PD-PROV-1", bank_account=pp_bank,
                                        reference_number="R1", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=liab, debit=Decimal("500.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("500.00"))
    with transaction.atomic():
        p1 = ensure_draft_payment_for_document(pd)
    with transaction.atomic():
        p2 = ensure_draft_payment_for_document(pd)   # idempotent — never a 2nd
    assert p1.pk == p2.pk
    assert p1.payment_document_id == pd.pk
    assert p1.payment_voucher_id is None
    assert p1.status == "Draft"
    assert p1.total_amount == Decimal("500.00")       # cash-out = credit to bank GL
    assert Payment.objects.filter(payment_document=pd).exclude(status="Void").count() == 1


# ── Task 5: posting a document-sourced Outgoing Payment ──────────────────────

@pytest.fixture
def open_period_pp(db):
    from accounting.models import FiscalPeriod
    from datetime import date
    today = date.today()
    fp, _ = FiscalPeriod.objects.get_or_create(
        fiscal_year=today.year, period_number=today.month, period_type="Monthly",
        defaults={"start_date": today.replace(day=1), "end_date": today,
                  "status": "Open", "is_closed": False})
    return fp


@pytest.mark.django_db(transaction=True)
def test_post_document_sourced_payment_posts_journal(pp_bank, open_period_pp):
    from django.db import transaction
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account
    from accounting.services.document_payment_provisioning import (
        ensure_draft_payment_for_document, post_document_sourced_payment)
    liab, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    pd = PaymentDocument.objects.create(document_number="PD-POSTPP-1", bank_account=pp_bank,
                                        reference_number="R2", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=liab, debit=Decimal("700.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("700.00"))
    with transaction.atomic():
        pay = ensure_draft_payment_for_document(pd)
    post_document_sourced_payment(pay, actor=None)
    pay.refresh_from_db(); pd.refresh_from_db()
    assert pay.status == "Posted"
    assert pd.status == "Paid"
    assert pd.journal_id is not None
    assert pay.journal_entry_id == pd.journal_id
    j = pd.journal
    assert sum(l.debit for l in j.lines.all()) == sum(l.credit for l in j.lines.all()) == Decimal("700.00")


# ── Task 9: unified payment-proposals register endpoint ──────────────────────

@pytest.mark.django_db
def test_payment_proposals_unions_pv_and_pd(pp_bank, pp_api):
    from accounting.models import PaymentDocument
    from accounting.models.treasury import PaymentVoucherGov
    from accounting.tests.test_central_payment_processing import _ncoa, _tsa
    client, _ = pp_api
    PaymentVoucherGov.objects.create(
        voucher_number="PV-UNI-1", payment_type="VENDOR", ncoa_code=_ncoa(),
        payee_name="Union Payee", narration="union test", tsa_account=_tsa(),
        gross_amount=Decimal("10.00"), net_amount=Decimal("10.00"), status="DRAFT")
    PaymentDocument.objects.create(document_number="PD-UNI-1", bank_account=pp_bank,
                                   reference_number="R5", status="Draft")
    resp = client.get("/api/v1/accounting/payment-proposals/?status=Proposed",
                      HTTP_HOST="localhost")
    assert resp.status_code == 200, resp.content
    rows = resp.json()["results"]
    assert {"pv", "pd"} <= {r["source"] for r in rows}
    assert {"PV-UNI-1", "PD-UNI-1"} <= {r["number"] for r in rows}


# ── Tasks 6-8: workflow registration, submit, approval dispatch ───────────────

def _pp_liability():
    from accounting.models import Account
    acct, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    return acct


@pytest.mark.django_db
def test_paymentdocument_registered_in_workflow():
    from workflow.views import _MODEL_TO_MODULE_KEY, APPROVABLE_MODELS
    assert _MODEL_TO_MODULE_KEY.get("paymentdocument") == "PaymentDocument"
    assert "paymentdocument" in APPROVABLE_MODELS


@pytest.mark.django_db(transaction=True)
def test_submit_required_mode_goes_pending(pp_bank, pp_api):
    """Submit under Required approval → the document goes Pending Approval and NO
    Payment is provisioned yet (that happens on approval completion)."""
    from workflow.models import GlobalApprovalSettings
    from accounting.models import PaymentDocument, PaymentDocumentLine, Payment
    client, _ = pp_api
    GlobalApprovalSettings.objects.update_or_create(
        module="PaymentDocument", defaults={"approval_mode": "Required"})
    pd = PaymentDocument.objects.create(document_number="PD-SUB-REQ", bank_account=pp_bank,
                                        reference_number="R7", status="Draft")
    PaymentDocumentLine.objects.create(payment_document=pd, account=_pp_liability(), debit=Decimal("100.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("100.00"))
    resp = client.post(f"/api/v1/accounting/payment-documents/{pd.pk}/submit/", {},
                       format="json", HTTP_HOST="localhost")
    assert resp.status_code == 200, resp.content
    pd.refresh_from_db()
    assert pd.status == "Pending Approval"
    assert Payment.objects.filter(payment_document=pd).exclude(status="Void").count() == 0


@pytest.mark.django_db
def test_submit_rejects_non_draft(pp_bank, pp_api):
    from accounting.models import PaymentDocument
    client, _ = pp_api
    pd = PaymentDocument.objects.create(document_number="PD-SG-1", bank_account=pp_bank, status="Paid")
    resp = client.post(f"/api/v1/accounting/payment-documents/{pd.pk}/submit/", {},
                       format="json", HTTP_HOST="localhost")
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_dispatch_receiver_provisions_on_approval(pp_bank):
    """The approval-completion dispatch receiver provisions the draft Payment."""
    from unittest.mock import MagicMock
    from accounting.models import PaymentDocument, PaymentDocumentLine, Payment
    from accounting.signals.workflow_dispatch import auto_post_paymentdocument_on_approval
    pd = PaymentDocument.objects.create(document_number="PD-DISP-1", bank_account=pp_bank,
                                        reference_number="R8", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=_pp_liability(), debit=Decimal("300.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("300.00"))
    auto_post_paymentdocument_on_approval(
        sender=MagicMock(), approval=MagicMock(pk=1),
        model_name="paymentdocument", document=pd, action="approve")
    assert Payment.objects.filter(payment_document=pd).exclude(status="Void").count() == 1


# ── Review fixes: delete guard, double-post guard, rejected mapping ───────────

@pytest.mark.django_db
def test_cannot_delete_in_flight_document(pp_bank, pp_api):
    """A submitted (Pending Approval / Approved) document cannot be hard-deleted —
    it would orphan its workflow Approval. Only Draft/Rejected are deletable."""
    from accounting.models import PaymentDocument
    client, _ = pp_api
    pd = PaymentDocument.objects.create(document_number="PD-DEL-1", bank_account=pp_bank,
                                        status="Pending Approval")
    resp = client.delete(f"/api/v1/accounting/payment-documents/{pd.pk}/", HTTP_HOST="localhost")
    assert resp.status_code == 400, resp.content
    assert PaymentDocument.objects.filter(pk=pd.pk).exists()  # not deleted


@pytest.mark.django_db(transaction=True)
def test_double_post_document_payment_rejected(pp_bank, open_period_pp):
    """Posting a document-sourced Payment twice is rejected — the second call
    (after the first commits + locks) finds it already Posted."""
    from django.db import transaction
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.document_payment_provisioning import (
        ensure_draft_payment_for_document, post_document_sourced_payment)
    from accounting.services.payment_document_posting import PaymentDocumentError
    pd = PaymentDocument.objects.create(document_number="PD-DP-1", bank_account=pp_bank,
                                        reference_number="DP", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=_pp_liability(), debit=Decimal("100.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("100.00"))
    with transaction.atomic():
        pay = ensure_draft_payment_for_document(pd)
    post_document_sourced_payment(pay, actor=None)
    pay.refresh_from_db()
    with pytest.raises(PaymentDocumentError):
        post_document_sourced_payment(pay, actor=None)


@pytest.mark.django_db
def test_rejected_document_shows_under_void(pp_bank, pp_api):
    from accounting.models import PaymentDocument
    client, _ = pp_api
    PaymentDocument.objects.create(document_number="PD-REJ-1", bank_account=pp_bank, status="Rejected")
    resp = client.get("/api/v1/accounting/payment-proposals/?status=Void", HTTP_HOST="localhost")
    assert resp.status_code == 200, resp.content
    assert "PD-REJ-1" in {r["number"] for r in resp.json()["results"]}


def test_proposals_endpoint_declares_model_for_rbac():
    """The unified endpoint sets ``model`` so RBACPermission enforces
    ``view_paymentdocument`` instead of its no-queryset SAFE_METHODS
    blanket-allow (which would let ANY authenticated role read the register)."""
    from accounting.views.payment_proposals import PaymentProposalsView
    from accounting.models import PaymentDocument
    assert PaymentProposalsView.model is PaymentDocument
