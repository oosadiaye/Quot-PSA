"""Payment Document — models, posting, API, import."""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.fixture
def pd_accounts(db):
    """Liability + Expense + Bank-GL accounts. get_or_create because
    accounting_account rows survive between transactional tests."""
    from accounting.models import Account
    liability, _ = Account.objects.get_or_create(
        code="21050000",
        defaults={"name": "Payroll Liability", "account_type": "Liability", "is_active": True, "is_postable": True},
    )
    expense, _ = Account.objects.get_or_create(
        code="22020101",
        defaults={"name": "Salaries", "account_type": "Expense", "is_active": True, "is_postable": True},
    )
    bank_gl, _ = Account.objects.get_or_create(
        code="10100001",
        defaults={"name": "TSA Cash", "account_type": "Asset", "is_active": True, "is_postable": True,
                  "reconciliation_type": "bank_accounting"},
    )
    return {"liability": liability, "expense": expense, "bank_gl": bank_gl}


@pytest.fixture
def pd_bank(db, pd_accounts):
    from accounting.models import BankAccount
    # NOTE: field is ``name`` (not ``account_name``); ``currency=None`` is
    # required because BankAccount.currency has a hardcoded FK ``default=1``
    # and a fresh pytest tenant schema has no Currency row (see conftest
    # ``bank_account_for_batch`` for the same gotcha).
    bank, _ = BankAccount.objects.get_or_create(
        account_number="0000000001",
        defaults={"name": "Main TSA", "bank_name": "CBN",
                  "gl_account": pd_accounts["bank_gl"], "current_balance": Decimal("1000000.00"),
                  "currency": None},
    )
    return bank


@pytest.mark.django_db
def test_payment_document_computes_net_from_lines(pd_accounts, pd_bank):
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.payment_document_posting import compute_net
    doc = PaymentDocument.objects.create(
        document_number="PD-000001", bank_account=pd_bank, description="Salary run",
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"], debit=Decimal("100000.00"),
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["expense"], credit=Decimal("10000.00"), is_deduction=True,
    )
    lines = list(doc.lines.all())
    assert compute_net(lines) == Decimal("90000.00")  # 100000 debit - 10000 credit


@pytest.fixture
def open_period(db):
    """Reuse the shared open fiscal period so posting isn't period-locked."""
    from accounting.models import FiscalPeriod
    from datetime import date
    today = date.today()
    fp, _ = FiscalPeriod.objects.get_or_create(
        fiscal_year=today.year, period_number=today.month, period_type="Monthly",
        defaults={"start_date": today.replace(day=1), "end_date": today, "status": "Open", "is_closed": False},
    )
    return fp


def _doc_with_liability_debit(pd_accounts, pd_bank):
    from accounting.models import PaymentDocument, PaymentDocumentLine
    doc = PaymentDocument.objects.create(
        document_number="PD-POST-1", bank_account=pd_bank, description="Salary settlement",
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"], debit=Decimal("90000.00"),
    )
    return doc


@pytest.mark.django_db(transaction=True)
def test_post_settles_liability_credits_bank_no_budget(pd_accounts, pd_bank, open_period):
    """DR Liability / CR Bank — no expense debit, so no appropriation needed."""
    from accounting.services.payment_document_posting import post_payment_document
    doc = _doc_with_liability_debit(pd_accounts, pd_bank)
    journal = post_payment_document(doc, actor=None)

    lines = list(journal.lines.all())
    assert sum(l.debit for l in lines) == Decimal("90000.00")
    assert sum(l.credit for l in lines) == Decimal("90000.00")
    debit_line = next(l for l in lines if l.debit > 0)
    credit_line = next(l for l in lines if l.credit > 0)
    assert debit_line.account_id == pd_accounts["liability"].pk   # DR Payroll Liability
    assert credit_line.account_id == pd_accounts["bank_gl"].pk    # CR Bank (net)
    doc.refresh_from_db()
    assert doc.status == "Posted"
    assert doc.journal_id == journal.pk
    assert doc.net_amount == Decimal("90000.00")


@pytest.mark.django_db(transaction=True)
def test_post_decrements_bank_balance_by_net(pd_accounts, pd_bank, open_period):
    from accounting.services.payment_document_posting import post_payment_document
    before = pd_bank.current_balance
    doc = _doc_with_liability_debit(pd_accounts, pd_bank)
    post_payment_document(doc, actor=None)
    pd_bank.refresh_from_db()
    assert pd_bank.current_balance == before - Decimal("90000.00")


@pytest.mark.django_db(transaction=True)
def test_post_vendor_settlement_decrements_vendor_balance(pd_accounts, pd_bank, open_period):
    from procurement.models import Vendor
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account
    from accounting.services.payment_document_posting import post_payment_document
    ap, _ = Account.objects.get_or_create(
        code="21010000",
        defaults={"name": "Accounts Payable", "account_type": "Liability", "is_active": True, "is_postable": True},
    )
    vendor = Vendor.objects.create(name="ACME Ltd", code="V-PD", is_active=True, balance=Decimal("50000.00"))
    doc = PaymentDocument.objects.create(document_number="PD-POST-V1", bank_account=pd_bank, description="Vendor payout")
    PaymentDocumentLine.objects.create(payment_document=doc, account=ap, vendor=vendor, debit=Decimal("50000.00"))
    post_payment_document(doc, actor=None)
    vendor.refresh_from_db()
    assert vendor.balance == Decimal("0.00")


@pytest.mark.django_db
def test_post_refuses_when_net_not_positive(pd_accounts, pd_bank, open_period):
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-POST-Z", bank_account=pd_bank)
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["liability"], credit=Decimal("100.00"))
    with pytest.raises(PaymentDocumentError):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_expense_debit_requires_appropriation(pd_accounts, pd_bank, open_period):
    """A DEBIT to an Expense GL consumes budget, so the service's own
    expense-appropriation gate must block it when no Appropriation exists.

    Proves the expense path is genuinely gated (not vacuously): account
    22020101 falls under the tenant's STRICT BudgetCheckRule, and with no
    Appropriation seeded and no header MDA/fund to resolve one, check_policy
    returns blocked and the service raises PaymentDocumentError before any
    journal is created. This is the complement of the settlement tests: only
    a settlement-only document posts budget-free.
    """
    from accounting.models import PaymentDocument, PaymentDocumentLine, JournalHeader
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(
        document_number="PD-POST-EXP", bank_account=pd_bank, description="Direct expense payout",
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["expense"], debit=Decimal("40000.00"),
    )
    with pytest.raises(PaymentDocumentError):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # gate fired before posting
    # No journal was created for this document.
    assert JournalHeader.objects.filter(
        source_module="payment_document", source_document_id=doc.pk,
    ).count() == 0


# ── Fast guard tests — these raise at the input-validation stage BEFORE any
# journal / GL posting, so plain @pytest.mark.django_db (no transaction=True)
# keeps them fast. ─────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_post_refuses_no_lines(pd_accounts, pd_bank):
    from accounting.models import PaymentDocument
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-GUARD-NL", bank_account=pd_bank)
    with pytest.raises(PaymentDocumentError):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_refuses_line_with_both_debit_and_credit(pd_accounts, pd_bank):
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-GUARD-BOTH", bank_account=pd_bank)
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"],
        debit=Decimal("10"), credit=Decimal("10"),
    )
    with pytest.raises(PaymentDocumentError):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_refuses_when_bank_has_no_gl_account(pd_accounts):
    from accounting.models import PaymentDocument, PaymentDocumentLine, BankAccount
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    bank_no_gl, _ = BankAccount.objects.get_or_create(
        account_number="0000000009",
        defaults={"name": "No-GL Bank", "bank_name": "CBN",
                  "gl_account": None, "current_balance": Decimal("1000000.00"),
                  "currency": None},
    )
    doc = PaymentDocument.objects.create(document_number="PD-GUARD-NOGL", bank_account=bank_no_gl)
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"], debit=Decimal("50000.00"),
    )
    with pytest.raises(PaymentDocumentError):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_refuses_negative_amount(pd_accounts, pd_bank, open_period):
    """A negative line amount must be rejected even when the document's net
    stays POSITIVE — so ONLY the ``d < 0 or c < 0`` guard can catch it.

    Multi-line, net-positive by design: line B (debit=-50, credit=30) slips
    past the both-sides guard (debit not > 0) and the neither guard (credit
    > 0), and the ``net <= 0`` guard does NOT fire because
    net = (200 + -50) - 30 = 120 > 0. PaymentDocumentLine has no DB/validator
    against negatives, so the service's negative-amount guard is the only
    thing standing between this corrupted line and the GL.
    """
    from accounting.models import PaymentDocument, PaymentDocumentLine, JournalHeader
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-GUARD-NEG", bank_account=pd_bank)
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"], debit=Decimal("200.00"),
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"],
        debit=Decimal("-50.00"), credit=Decimal("30.00"),
    )
    with pytest.raises(PaymentDocumentError):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted
    assert JournalHeader.objects.filter(
        source_module="payment_document", source_document_id=doc.pk,
    ).count() == 0


# ── API tests — exercise the DRF viewset over real HTTP (CRUD + gated post +
# proposed-entries preview). The superuser client bypasses IsApprover and
# RequiresMFA (both exempt superusers), so the gated post succeeds. ──────────
@pytest.fixture
def pd_api(db):
    """Superuser API client on the pytest tenant.

    Re-asserts the ``pytest.localhost`` Client + Domain on the public schema
    first. A preceding ``@pytest.mark.django_db(transaction=True)`` test
    flushes the public ``tenants_client`` / ``tenants_domain`` rows at
    teardown (the conftest patches ``sql_flush`` to CASCADE, so the flush now
    succeeds locally as it does on CI — see project memory
    ``ci_tenant_flush_wipes_domain``). Without the Domain row the tenant
    middleware 400s ``"Unknown tenant domain"`` on this test's request. The
    ``get_or_create`` calls are idempotent — a no-op when the rows survive.
    """
    from django.db import connection
    from rest_framework.test import APIClient
    from django.contrib.auth import get_user_model
    from tenants.models import Client, Domain

    # Client/Domain are public-schema rows and django-tenants refuses to
    # create a tenant while routed to a tenant schema, so re-assert them on
    # public, then restore the tenant routing the autouse fixture set up.
    connection.set_schema_to_public()
    try:
        tenant, _ = Client.objects.get_or_create(
            schema_name="pytest_schema", defaults={"name": "PyTest Tenant"},
        )
        Domain.objects.get_or_create(
            domain="pytest.localhost", tenant=tenant, defaults={"is_primary": True},
        )
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="pd_admin", defaults={"is_staff": True, "is_superuser": True},
        )
    finally:
        connection.set_schema("pytest_schema")

    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db(transaction=True)
def test_api_create_draft_then_post(pd_api, pd_accounts, pd_bank, open_period):
    client, _ = pd_api
    payload = {
        "bank_account": pd_bank.pk,
        "description": "API salary run",
        "lines": [
            {"account": pd_accounts["liability"].pk, "debit": "90000.00", "credit": "0.00"},
        ],
    }
    resp = client.post("/api/v1/accounting/payment-documents/", payload, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 201, resp.content
    doc_id = resp.json()["id"]

    resp = client.post(f"/api/v1/accounting/payment-documents/{doc_id}/post/", {}, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "Posted"


@pytest.mark.django_db
def test_api_proposed_entries_previews_balanced_lines(pd_api, pd_accounts, pd_bank):
    client, _ = pd_api
    from accounting.models import PaymentDocument, PaymentDocumentLine
    doc = PaymentDocument.objects.create(document_number="PD-PREV-1", bank_account=pd_bank)
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["liability"], debit=Decimal("500.00"))
    resp = client.get(f"/api/v1/accounting/payment-documents/{doc.pk}/proposed-entries/",
                      HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert sum(Decimal(e["debit"]) for e in entries) == sum(Decimal(e["credit"]) for e in entries)
