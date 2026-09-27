"""Payment Document — models, posting, API, import.

NEW posting model: the document is a FULL balanced journal. The bank credit
(cash out) is an EXPLICIT line crediting the bank's GL account — the service no
longer derives / appends it. Posting therefore requires ``Σ debit == Σ credit``
and at least one bank-GL credit line. An MDA is mandatory on the document.
"""
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
def pd_mda(db):
    """The header MDA every posting document now requires (mandatory field).

    get_or_create because MDA rows, like accounts, survive between transactional
    tests. Only ``code`` + ``name`` are supplied — MDA's other fields are
    nullable / default-bearing (``mda_type`` is a choices CharField that accepts
    the empty string, ``short_name`` defaults to '', ``is_active`` defaults to
    True), so this satisfies every required column.
    """
    from accounting.models import MDA
    mda, _ = MDA.objects.get_or_create(
        code="011700100100",
        defaults={"name": "Office of the Accountant General"},
    )
    return mda


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


def _balanced_liability_doc(pd_accounts, pd_bank, pd_mda, *,
                            document_number="PD-POST-1", amount=Decimal("90000.00")):
    """A minimal BALANCED settlement document: DR liability / CR bank.

    The bank credit is an EXPLICIT line (the new model), so the document is a
    complete balanced journal on its own.
    """
    from accounting.models import PaymentDocument, PaymentDocumentLine
    doc = PaymentDocument.objects.create(
        document_number=document_number, bank_account=pd_bank, mda=pd_mda,
        description="Salary settlement",
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"], debit=amount,
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["bank_gl"], credit=amount,
    )
    return doc


@pytest.mark.django_db(transaction=True)
def test_post_settles_liability_credits_bank_no_budget(pd_accounts, pd_bank, pd_mda, open_period):
    """DR Liability / CR Bank (explicit) — no expense debit, so no appropriation
    needed. Posts the two lines AS ENTERED into a balanced journal."""
    from accounting.services.payment_document_posting import post_payment_document
    doc = _balanced_liability_doc(pd_accounts, pd_bank, pd_mda, document_number="PD-POST-1")
    journal = post_payment_document(doc, actor=None)

    lines = list(journal.lines.all())
    assert len(lines) == 2  # exactly the doc lines — no appended bank leg
    assert sum(l.debit for l in lines) == Decimal("90000.00")
    assert sum(l.credit for l in lines) == Decimal("90000.00")
    debit_line = next(l for l in lines if l.debit > 0)
    credit_line = next(l for l in lines if l.credit > 0)
    assert debit_line.account_id == pd_accounts["liability"].pk   # DR Payroll Liability
    assert credit_line.account_id == pd_accounts["bank_gl"].pk    # CR Bank (explicit line)
    doc.refresh_from_db()
    assert doc.status == "Posted"
    assert doc.journal_id == journal.pk
    assert doc.net_amount == Decimal("90000.00")  # net_amount = bank credit (cash out)


@pytest.mark.django_db(transaction=True)
def test_post_decrements_bank_balance_by_net(pd_accounts, pd_bank, pd_mda, open_period):
    from accounting.services.payment_document_posting import post_payment_document
    before = pd_bank.current_balance
    doc = _balanced_liability_doc(pd_accounts, pd_bank, pd_mda, document_number="PD-POST-2")
    post_payment_document(doc, actor=None)
    pd_bank.refresh_from_db()
    assert pd_bank.current_balance == before - Decimal("90000.00")  # dropped by the cash out


@pytest.mark.django_db(transaction=True)
def test_post_vendor_settlement_decrements_vendor_balance(pd_accounts, pd_bank, pd_mda, open_period):
    from procurement.models import Vendor
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account
    from accounting.services.payment_document_posting import post_payment_document
    ap, _ = Account.objects.get_or_create(
        code="21010000",
        defaults={"name": "Accounts Payable", "account_type": "Liability", "is_active": True, "is_postable": True},
    )
    vendor = Vendor.objects.create(name="ACME Ltd", code="V-PD", is_active=True, balance=Decimal("50000.00"))
    doc = PaymentDocument.objects.create(
        document_number="PD-POST-V1", bank_account=pd_bank, mda=pd_mda, description="Vendor payout",
    )
    PaymentDocumentLine.objects.create(payment_document=doc, account=ap, vendor=vendor, debit=Decimal("50000.00"))
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["bank_gl"], credit=Decimal("50000.00"))
    post_payment_document(doc, actor=None)
    vendor.refresh_from_db()
    assert vendor.balance == Decimal("0.00")


@pytest.mark.django_db
def test_post_refuses_when_unbalanced(pd_accounts, pd_bank, pd_mda, open_period):
    """Σ debit ≠ Σ credit → the balance guard blocks the post; doc stays Draft."""
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-POST-Z", bank_account=pd_bank, mda=pd_mda)
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["liability"], debit=Decimal("100.00"))
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["bank_gl"], credit=Decimal("50.00"))
    with pytest.raises(PaymentDocumentError, match="not balanced"):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_requires_mda(pd_accounts, pd_bank, open_period):
    """A balanced document with no MDA is refused — MDA is mandatory."""
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-NO-MDA", bank_account=pd_bank)  # mda=None
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["liability"], debit=Decimal("90000.00"))
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["bank_gl"], credit=Decimal("90000.00"))
    with pytest.raises(PaymentDocumentError, match="MDA"):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_expense_debit_requires_appropriation(pd_accounts, pd_bank, pd_mda, open_period):
    """A DEBIT to an Expense GL consumes budget, so the service's own
    expense-appropriation gate must block it when no Appropriation exists.

    Proves the expense path is genuinely gated (not vacuously): account
    22020101 falls under the tenant's STRICT BudgetCheckRule. The document is
    balanced (DR expense / CR bank) and has an MDA, so it clears the structural
    guards — but with no Appropriation seeded (and no header fund to resolve
    one), ``find_matching_appropriation`` returns None and ``check_policy``
    returns blocked, so the service raises PaymentDocumentError before any
    journal is created. This is the complement of the settlement tests: only a
    settlement-only document posts budget-free.
    """
    from accounting.models import PaymentDocument, PaymentDocumentLine, JournalHeader
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(
        document_number="PD-POST-EXP", bank_account=pd_bank, mda=pd_mda, description="Direct expense payout",
    )
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["expense"], debit=Decimal("5000.00"))
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["bank_gl"], credit=Decimal("5000.00"))
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
# keeps them fast. Each sets ``mda`` so it fails on the INTENDED guard, not on
# the mandatory-MDA guard. ───────────────────────────────────────────────────
@pytest.mark.django_db
def test_post_refuses_no_lines(pd_accounts, pd_bank, pd_mda):
    from accounting.models import PaymentDocument
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-GUARD-NL", bank_account=pd_bank, mda=pd_mda)
    with pytest.raises(PaymentDocumentError):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_refuses_line_with_both_debit_and_credit(pd_accounts, pd_bank, pd_mda):
    """A both-sided line is caught by the per-line guard. A second (bank) line
    is present so the two-line minimum is satisfied and the both-sides guard —
    not the line-count guard — is what fires."""
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-GUARD-BOTH", bank_account=pd_bank, mda=pd_mda)
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"],
        debit=Decimal("10"), credit=Decimal("10"),
    )
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["bank_gl"], credit=Decimal("10"))
    with pytest.raises(PaymentDocumentError, match="both"):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_refuses_when_bank_has_no_gl_account(pd_accounts, pd_mda):
    from accounting.models import PaymentDocument, PaymentDocumentLine, BankAccount
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    bank_no_gl, _ = BankAccount.objects.get_or_create(
        account_number="0000000009",
        defaults={"name": "No-GL Bank", "bank_name": "CBN",
                  "gl_account": None, "current_balance": Decimal("1000000.00"),
                  "currency": None},
    )
    doc = PaymentDocument.objects.create(document_number="PD-GUARD-NOGL", bank_account=bank_no_gl, mda=pd_mda)
    # Two single-sided lines clear the per-line + count guards; the bank-GL
    # guard is what fires because the bank account has no GL configured.
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"], debit=Decimal("50000.00"),
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"], credit=Decimal("50000.00"),
    )
    with pytest.raises(PaymentDocumentError, match="GL account"):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted


@pytest.mark.django_db
def test_post_refuses_negative_amount(pd_accounts, pd_bank, pd_mda, open_period):
    """A negative line amount must be rejected, and ONLY the ``d < 0 or c < 0``
    guard can catch it.

    Line B (debit=-50, credit=30) slips past the both-sides guard (debit not
    > 0) and the neither guard (credit > 0). The per-line loop runs before the
    balance / cash-out checks, so the negative guard fires first regardless of
    whether the document happens to balance. PaymentDocumentLine has no DB /
    validator against negatives, so the service's guard is the only thing
    standing between this corrupted line and the GL.
    """
    from accounting.models import PaymentDocument, PaymentDocumentLine, JournalHeader
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-GUARD-NEG", bank_account=pd_bank, mda=pd_mda)
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"], debit=Decimal("200.00"),
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["liability"],
        debit=Decimal("-50.00"), credit=Decimal("30.00"),
    )
    PaymentDocumentLine.objects.create(
        payment_document=doc, account=pd_accounts["bank_gl"], credit=Decimal("150.00"),
    )
    with pytest.raises(PaymentDocumentError, match="negative"):
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
def test_api_create_draft_then_post(pd_api, pd_accounts, pd_bank, pd_mda, open_period):
    client, _ = pd_api
    payload = {
        "bank_account": pd_bank.pk,
        "reference_number": "REF-001",
        "mda": pd_mda.pk,
        "description": "API salary run",
        "lines": [
            {"account": pd_accounts["liability"].pk, "debit": "90000.00", "credit": "0.00"},
            {"account": pd_accounts["bank_gl"].pk, "debit": "0.00", "credit": "90000.00"},
        ],
    }
    resp = client.post("/api/v1/accounting/payment-documents/", payload, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 201, resp.content
    doc_id = resp.json()["id"]

    resp = client.post(f"/api/v1/accounting/payment-documents/{doc_id}/post/", {}, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "Posted"
    assert Decimal(body["net_amount"]) == Decimal("90000.00")
    # The post produced a real GL journal linked back to this document.
    from accounting.models import JournalHeader
    assert JournalHeader.objects.filter(
        source_module="payment_document", source_document_id=doc_id,
    ).exists()


@pytest.mark.django_db
def test_api_create_requires_reference(pd_api, pd_accounts, pd_bank, pd_mda):
    """A create with NO reference_number is rejected at serializer validation
    (400) — reference is MANDATORY at the API. MDA is supplied so the 400 is
    specifically about the missing reference. Fails before any posting, so
    plain django_db (no transaction=True) is fine."""
    client, _ = pd_api
    payload = {
        "bank_account": pd_bank.pk,
        "mda": pd_mda.pk,
        "description": "Missing reference",
        "lines": [
            {"account": pd_accounts["liability"].pk, "debit": "90000.00", "credit": "0.00"},
        ],
    }
    resp = client.post("/api/v1/accounting/payment-documents/", payload, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 400, resp.content
    assert "reference" in resp.content.decode().lower()


@pytest.mark.django_db
def test_api_create_requires_mda(pd_api, pd_accounts, pd_bank):
    """A create with NO mda is rejected at serializer validation (400) — MDA is
    MANDATORY at the API."""
    client, _ = pd_api
    payload = {
        "bank_account": pd_bank.pk,
        "reference_number": "REF-002",
        "description": "Missing MDA",
        "lines": [
            {"account": pd_accounts["liability"].pk, "debit": "90000.00", "credit": "0.00"},
        ],
    }
    resp = client.post("/api/v1/accounting/payment-documents/", payload, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 400, resp.content
    assert "mda" in resp.content.decode().lower()


@pytest.mark.django_db
def test_api_proposed_entries_previews_balanced_lines(pd_api, pd_accounts, pd_bank, pd_mda):
    client, _ = pd_api
    from accounting.models import PaymentDocument, PaymentDocumentLine
    doc = PaymentDocument.objects.create(document_number="PD-PREV-1", bank_account=pd_bank, mda=pd_mda)
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["liability"], debit=Decimal("500.00"))
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["bank_gl"], credit=Decimal("500.00"))
    resp = client.get(f"/api/v1/accounting/payment-documents/{doc.pk}/proposed-entries/",
                      HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 200
    body = resp.json()
    entries = body["entries"]
    assert len(entries) == 2  # exactly the doc lines — no synthetic bank leg appended
    assert sum(Decimal(e["debit"]) for e in entries) == sum(Decimal(e["credit"]) for e in entries)
    # The bank credit is a real document line now (not a computed extra entry).
    bank_entry = next(e for e in entries if e["account"] == pd_bank.gl_account.code)
    assert bank_entry["credit"] == "500.00"
    assert body["net_amount"] == "500.00"  # net_amount = bank credit (cash out)


@pytest.mark.django_db
def test_api_patch_draft_replaces_lines(pd_api, pd_accounts, pd_bank, pd_mda):
    client, _ = pd_api
    payload = {
        "bank_account": pd_bank.pk,
        "reference_number": "REF-001",
        "mda": pd_mda.pk,
        "description": "Draft to edit",
        "lines": [
            {"account": pd_accounts["liability"].pk, "debit": "100.00", "credit": "0.00"},
            {"account": pd_accounts["bank_gl"].pk, "debit": "0.00", "credit": "100.00"},
        ],
    }
    resp = client.post("/api/v1/accounting/payment-documents/", payload, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 201, resp.content
    doc_id = resp.json()["id"]

    patch = {"lines": [
        {"account": pd_accounts["liability"].pk, "debit": "250.00", "credit": "0.00"},
        {"account": pd_accounts["expense"].pk, "debit": "0.00", "credit": "50.00"},
        {"account": pd_accounts["bank_gl"].pk, "debit": "0.00", "credit": "200.00"},
    ]}
    resp = client.patch(f"/api/v1/accounting/payment-documents/{doc_id}/", patch, format="json",
                        HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert len(body["lines"]) == 3                            # old lines were replaced
    assert Decimal(body["net_amount"]) == Decimal("200.00")   # bank credit = cash out


@pytest.mark.django_db(transaction=True)
def test_api_cannot_patch_posted_document(pd_api, pd_accounts, pd_bank, pd_mda, open_period):
    client, _ = pd_api
    from accounting.models import PaymentDocument
    payload = {
        "bank_account": pd_bank.pk,
        "reference_number": "REF-001",
        "mda": pd_mda.pk,
        "description": "To be posted then edited",
        "lines": [
            {"account": pd_accounts["liability"].pk, "debit": "90000.00", "credit": "0.00"},
            {"account": pd_accounts["bank_gl"].pk, "debit": "0.00", "credit": "90000.00"},
        ],
    }
    resp = client.post("/api/v1/accounting/payment-documents/", payload, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 201, resp.content
    doc_id = resp.json()["id"]
    resp = client.post(f"/api/v1/accounting/payment-documents/{doc_id}/post/", {}, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 200, resp.content

    lines_before = list(
        PaymentDocument.objects.get(pk=doc_id).lines.values_list("account_id", "debit", "credit")
    )
    resp = client.patch(f"/api/v1/accounting/payment-documents/{doc_id}/",
                        {"lines": []}, format="json",
                        HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    # A clean 400 — NOT a 500 from destroying the posted journal's lines.
    assert resp.status_code == 400, resp.content
    lines_after = list(
        PaymentDocument.objects.get(pk=doc_id).lines.values_list("account_id", "debit", "credit")
    )
    assert lines_after == lines_before  # posted document's lines are untouched


# ── Bulk import — CSV rows grouped by ``document_ref`` create DRAFT documents
# for operator review. Imported docs are NEVER auto-posted, so they carry no
# MDA / explicit bank line here — those become required only at POST time. ────
@pytest.mark.django_db
def test_bulk_import_creates_draft_documents(pd_accounts, pd_bank):
    from accounting.services.payment_document_import import import_payment_documents_from_rows
    rows = [
        {"document_ref": "SAL-01", "bank_account_number": pd_bank.account_number,
         "account_code": pd_accounts["liability"].code, "vendor_code": "",
         "debit": "90000.00", "credit": "0.00"},
    ]
    created = import_payment_documents_from_rows(rows, source="import")
    assert len(created) == 1
    doc = created[0]
    assert doc.status == "Draft"          # imported docs are never auto-posted
    assert doc.lines.count() == 1
    assert doc.lines.first().debit == Decimal("90000.00")
