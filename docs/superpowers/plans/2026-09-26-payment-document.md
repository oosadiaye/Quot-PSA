# Payment Document (Post Outgoing Payment) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SAP F-53–style Payment Document — a multi-line outgoing payment with a header bank account as the single credit, a DR/CR line grid (GL account + optional vendor), optional header-level appropriation, and bulk import — that posts one balanced journal through the existing engine and settles obligations without re-consuming budget.

**Architecture:** New `PaymentDocument` + `PaymentDocumentLine` models (not a stretch of the single-line, ncoa-required `PaymentVoucherGov`). A `post_payment_document` service assembles one `JournalHeader` (`DR lines / CR deductions / CR bank net`) and posts it via `BasePostingService`; the existing `budget_enforcement` pre-save signal auto-gates only expense-debit lines, so liability/vendor settlements post with no budget check. A DRF `PaymentDocumentViewSet` exposes CRUD + an approver+MFA-gated `post`, `proposed-entries`, and template import. A React `PaymentDocumentForm` reuses the `JournalForm` DR/CR grid.

**Tech Stack:** Django 4 + DRF + django-tenants (schema-per-tenant), PostgreSQL, pytest / pytest-django (`--reuse-db`), React + Vite + antd, TanStack Query.

**Spec:** [docs/superpowers/specs/2026-09-26-payment-document-design.md](../specs/2026-09-26-payment-document-design.md)

---

## File Structure

**Backend (create):**
- `accounting/models/payment_document.py` — `PaymentDocument`, `PaymentDocumentLine` models.
- `accounting/services/payment_document_posting.py` — `post_payment_document`, `compute_net`, `PaymentDocumentError`.
- `accounting/services/payment_document_import.py` — CSV template + bulk-import parser.
- `accounting/views/payment_documents.py` — serializers + `PaymentDocumentViewSet`.
- `accounting/tests/test_payment_document.py` — models + posting + API + import tests.

**Backend (modify):**
- `accounting/models/__init__.py` — re-export the two new models.
- `accounting/urls.py` — register the viewset route.

**Frontend (create):**
- `frontend/src/features/accounting/hooks/usePaymentDocuments.ts` — query/mutation hooks.
- `frontend/src/features/accounting/ap/PaymentDocumentForm.tsx` — the entry form (mirrors `JournalForm`).
- `frontend/src/features/accounting/ap/PaymentDocumentsList.tsx` — the register list.

**Frontend (modify):**
- `frontend/src/App.tsx` — routes for form + list.
- `frontend/src/components/Sidebar.tsx` — nav entry under Accounting/AP.

---

## Task 1: Models + migration

**Files:**
- Create: `accounting/models/payment_document.py`
- Modify: `accounting/models/__init__.py`
- Test: `accounting/tests/test_payment_document.py`

- [ ] **Step 1: Write the failing model test**

```python
# accounting/tests/test_payment_document.py
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
    bank, _ = BankAccount.objects.get_or_create(
        account_number="0000000001",
        defaults={"account_name": "Main TSA", "bank_name": "CBN",
                  "gl_account": pd_accounts["bank_gl"], "current_balance": Decimal("1000000.00")},
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py::test_payment_document_computes_net_from_lines --reuse-db -q`
Expected: FAIL — `ImportError`/`cannot import name 'PaymentDocument'`.

- [ ] **Step 3: Create the models**

```python
# accounting/models/payment_document.py
"""Payment Document — SAP F-53 style multi-line outgoing payment.

Header bank account is the single credit (cash out); lines are the debit/
credit legs (expenditure, liability settlement, vendor recon, or deduction).
Posts ONE balanced journal via ``payment_document_posting.post_payment_document``.
Budget appropriation is enforced only on expense-debit lines by the existing
``budget_enforcement`` signal, so liability/vendor settlements post with none.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import models

from core.models import AuditBaseModel, ImmutableModelMixin


class PaymentDocument(AuditBaseModel, ImmutableModelMixin):
    STATUS_CHOICES = [("Draft", "Draft"), ("Posted", "Posted"), ("Void", "Void")]
    SOURCE_CHOICES = [("manual", "Manual"), ("import", "Import")]

    document_number = models.CharField(max_length=30, unique=True, db_index=True)
    document_date = models.DateField(default=date.today)
    bank_account = models.ForeignKey(
        "accounting.BankAccount", on_delete=models.PROTECT, related_name="payment_documents",
    )
    reference_number = models.CharField(max_length=100, blank=True, default="")
    description = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Draft", db_index=True)

    # Header-level appropriation dimensions (all optional). Used by the
    # budget_enforcement pre-save signal to match appropriations for any
    # EXPENSE-type debit line; liability/vendor settlements ignore them.
    mda = models.ForeignKey("accounting.MDA", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")
    fund = models.ForeignKey("accounting.Fund", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")
    function = models.ForeignKey("accounting.Function", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")
    program = models.ForeignKey("accounting.Program", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")
    geo = models.ForeignKey("accounting.Geo", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_documents")

    net_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    journal = models.ForeignKey(
        "accounting.JournalHeader", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_documents",
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="manual")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Document"
        verbose_name_plural = "Payment Documents"

    def __str__(self) -> str:
        return f"{self.document_number} — {self.status} — NGN {self.net_amount:,.2f}"


class PaymentDocumentLine(models.Model):
    payment_document = models.ForeignKey(
        PaymentDocument, on_delete=models.CASCADE, related_name="lines",
    )
    account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="payment_document_lines",
    )
    vendor = models.ForeignKey(
        "procurement.Vendor", on_delete=models.PROTECT, null=True, blank=True,
        related_name="payment_document_lines",
    )
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    memo = models.CharField(max_length=255, blank=True, default="")
    is_deduction = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
```

- [ ] **Step 4: Re-export the models**

In `accounting/models/__init__.py`, add alongside the other model re-exports (follow the existing `from accounting.models.<mod> import ...` style):

```python
from accounting.models.payment_document import PaymentDocument, PaymentDocumentLine  # noqa: F401
```

(If `__init__.py` uses an `__all__` list, append `"PaymentDocument"` and `"PaymentDocumentLine"` to it.)

- [ ] **Step 5: Add `compute_net` so the import resolves**

```python
# accounting/services/payment_document_posting.py
"""Post a Payment Document as one balanced journal (see the design spec)."""
from __future__ import annotations

from decimal import Decimal


class PaymentDocumentError(Exception):
    """A payment document could not be posted for a domain reason."""


def compute_net(lines) -> Decimal:
    """Net cash out = Σ debits − Σ credits across the document's lines."""
    total_debit = sum((ln.debit or Decimal("0.00")) for ln in lines)
    total_credit = sum((ln.credit or Decimal("0.00")) for ln in lines)
    return Decimal(total_debit) - Decimal(total_credit)
```

- [ ] **Step 6: Make the migration**

Run: `.venv/Scripts/python.exe manage.py makemigrations accounting`
Expected: creates `accounting/migrations/XXXX_paymentdocument_paymentdocumentline.py` with `CreateModel` for both.

- [ ] **Step 7: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py::test_payment_document_computes_net_from_lines --reuse-db -q`
Expected: PASS. (First run may rebuild the `pytest_schema` tenant — slow; subsequent `--reuse-db` runs are fast.)

- [ ] **Step 8: Commit**

```bash
git add accounting/models/payment_document.py accounting/models/__init__.py accounting/migrations/ accounting/services/payment_document_posting.py accounting/tests/test_payment_document.py
git commit -m "feat(payments): PaymentDocument + PaymentDocumentLine models"
```

---

## Task 2: Posting service `post_payment_document`

**Files:**
- Modify: `accounting/services/payment_document_posting.py`
- Test: `accounting/tests/test_payment_document.py`

- [ ] **Step 1: Write the failing posting tests** (append to the test file)

```python
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
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.payment_document_posting import post_payment_document
    # A payable liability account tagged to a vendor settles the vendor's subledger.
    from accounting.models import Account
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


@pytest.mark.django_db(transaction=True)
def test_post_refuses_when_net_not_positive(pd_accounts, pd_bank, open_period):
    from accounting.models import PaymentDocument, PaymentDocumentLine
    from accounting.services.payment_document_posting import post_payment_document, PaymentDocumentError
    doc = PaymentDocument.objects.create(document_number="PD-POST-Z", bank_account=pd_bank)
    # Only a credit line → net = -x ≤ 0.
    PaymentDocumentLine.objects.create(payment_document=doc, account=pd_accounts["liability"], credit=Decimal("100.00"))
    with pytest.raises(PaymentDocumentError):
        post_payment_document(doc, actor=None)
    doc.refresh_from_db()
    assert doc.status == "Draft"  # nothing posted
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py -k post --reuse-db -q`
Expected: FAIL — `post_payment_document` not defined.

- [ ] **Step 3: Implement the posting service** (append to `payment_document_posting.py`)

```python
from django.db import transaction
from django.db.models import F
from django.utils import timezone


def _lines(doc):
    return list(doc.lines.select_related("account", "vendor").all())


@transaction.atomic
def post_payment_document(doc, *, actor=None):
    """Post ``doc`` as one balanced journal: DR/CR each line + CR bank (net).

    Returns the ``JournalHeader``. Raises :class:`PaymentDocumentError` for a
    domain problem, or ``ValidationError``/``TransactionPostingError`` if the
    budget signal / balance validation rejects the journal.
    """
    from accounting.models import JournalHeader, JournalLine, BankAccount
    from accounting.services.base_posting import BasePostingService
    from accounting.budget_logic import check_warrant_availability, warrant_enforcement_enabled

    if doc.status == "Posted":
        raise PaymentDocumentError("Payment document is already posted.")
    if doc.journal_id:
        raise PaymentDocumentError("Payment document already has a journal.")

    lines = _lines(doc)
    if not lines:
        raise PaymentDocumentError("A payment document needs at least one line.")
    for ln in lines:
        d, c = (ln.debit or Decimal("0.00")), (ln.credit or Decimal("0.00"))
        if d > 0 and c > 0:
            raise PaymentDocumentError("A line cannot carry both a debit and a credit.")
        if d <= 0 and c <= 0:
            raise PaymentDocumentError("Each line must carry a debit or a credit amount.")

    bank = doc.bank_account
    if not bank or not bank.gl_account_id:
        raise PaymentDocumentError("The document's bank account has no GL account configured.")

    net = compute_net(lines)
    if net <= 0:
        raise PaymentDocumentError(f"Net cash out must be positive (got {net}).")

    # (a) Fiscal-period gate — same call post_payment uses.
    BasePostingService._validate_fiscal_period(doc.document_date, user=actor)

    # (b) Payment-stage warrant/AIE gate — only EXPENSE debits consume warrant;
    # liability/vendor settlements have none, so they pass untouched. Mirrors
    # post_payment (accounting/views/payables.py). Appropriation itself is
    # enforced automatically by the budget_enforcement pre-save signal when the
    # journal below transitions to Posted, so it is not re-checked here.
    if warrant_enforcement_enabled():
        for ln in lines:
            if not (ln.debit and ln.debit > 0 and ln.account.account_type == "Expense"):
                continue
            allowed, warrant_msg, _info = check_warrant_availability(
                dimensions={"mda": doc.mda, "fund": doc.fund},
                account=ln.account, amount=ln.debit,
            )
            if not allowed:
                raise PaymentDocumentError(
                    warrant_msg or "No warrant (AIE) available for an expense line."
                )

    # Build the balanced journal.
    BasePostingService._check_duplicate_posting(doc.document_number)
    journal = JournalHeader.objects.create(
        posting_date=doc.document_date,
        description=doc.description or f"Payment Document {doc.document_number}",
        reference_number=doc.document_number,
        status="Draft",  # _update_gl_balances flips this to Posted
        source_module="payment_document",
        source_document_id=doc.pk,
        mda=doc.mda, fund=doc.fund, function=doc.function, program=doc.program, geo=doc.geo,
    )
    for ln in lines:
        JournalLine.objects.create(
            header=journal, account=ln.account,
            debit=ln.debit or Decimal("0.00"), credit=ln.credit or Decimal("0.00"),
            memo=(ln.memo or doc.document_number)[:255],
        )
    JournalLine.objects.create(
        header=journal, account=bank.gl_account,
        debit=Decimal("0.00"), credit=net, memo=f"Bank {doc.document_number}"[:255],
    )
    BasePostingService._validate_journal_balanced(journal)
    BasePostingService._update_gl_balances(journal)  # runs budget signal, flips to Posted

    # Vendor sub-ledger: a settlement debit (Liability/Asset recon) tagged to a
    # vendor clears that much of the vendor's balance. NOT for expense debits.
    for ln in lines:
        if ln.vendor_id and ln.debit and ln.debit > 0 and ln.account.account_type in ("Liability", "Asset"):
            type(ln.vendor).objects.filter(pk=ln.vendor_id).update(balance=F("balance") - ln.debit)

    # Cash out of the bank by net.
    BankAccount.objects.filter(pk=bank.pk).update(
        current_balance=F("current_balance") - net, updated_at=timezone.now(),
    )

    doc.journal = journal
    doc.net_amount = net
    doc.status = "Posted"
    doc.save(update_fields=["journal", "net_amount", "status", "updated_at"], _allow_status_change=True)
    return journal
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py -k post --reuse-db -q`
Expected: PASS (4 tests). `transaction=True` posting tests are slow — allow a few minutes.

- [ ] **Step 5: Commit**

```bash
git add accounting/services/payment_document_posting.py accounting/tests/test_payment_document.py
git commit -m "feat(payments): post_payment_document service (one balanced journal, budget-optional)"
```

> **Budget-optionality note (no extra test needed):** the "expense debit requires appropriation" behaviour is inherited automatically from `accounting/signals/budget_enforcement.py` (it gates only expense-type debits) and is already covered by that signal's own test suite. The liability-settlement test above proves the complementary case — settlement posts with no appropriation. Re-testing the whole budget engine here would duplicate existing coverage.

---

## Task 3: Serializers + ViewSet (CRUD, gated `post`, `proposed-entries`)

**Files:**
- Create: `accounting/views/payment_documents.py`
- Test: `accounting/tests/test_payment_document.py`

- [ ] **Step 1: Write the failing API tests** (append)

```python
@pytest.fixture
def pd_api(db):
    """Superuser API client on the pytest tenant."""
    from rest_framework.test import APIClient
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="pd_admin", defaults={"is_staff": True, "is_superuser": True},
    )
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py -k api --reuse-db -q`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Implement serializers + viewset**

```python
# accounting/views/payment_documents.py
"""Payment Document API — CRUD, approver+MFA-gated post, proposed-entries preview."""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
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
    bank_account_name = serializers.CharField(source="bank_account.account_name", read_only=True)

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
        # ImmutableModelMixin blocks edits once Posted; this only runs on Drafts.
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
```

- [ ] **Step 4: Register the route** — see Task 5 (do Task 5 now so the API tests can pass), then return here.

- [ ] **Step 5: Run the API tests**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py -k api --reuse-db -q`
Expected: PASS (after Task 5's route registration).

- [ ] **Step 6: Commit**

```bash
git add accounting/views/payment_documents.py accounting/tests/test_payment_document.py
git commit -m "feat(payments): PaymentDocument API — CRUD, MFA-gated post, proposed-entries"
```

---

## Task 4: Template download + bulk import

**Files:**
- Create: `accounting/services/payment_document_import.py`
- Modify: `accounting/views/payment_documents.py`
- Test: `accounting/tests/test_payment_document.py`

- [ ] **Step 1: Write the failing import test** (append)

```python
@pytest.mark.django_db
def test_bulk_import_creates_draft_documents(pd_accounts, pd_bank):
    from accounting.services.payment_document_import import import_payment_documents_from_rows
    rows = [
        {"document_ref": "SAL-01", "bank_account_number": pd_bank.account_number,
         "account_code": pd_accounts["liability"].code, "vendor_code": "",
         "debit": "90000.00", "credit": "0.00", "memo": "March net pay"},
    ]
    created = import_payment_documents_from_rows(rows, source="import")
    assert len(created) == 1
    doc = created[0]
    assert doc.status == "Draft"          # imported docs are never auto-posted
    assert doc.lines.count() == 1
    assert doc.lines.first().debit == Decimal("90000.00")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py -k import --reuse-db -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the import service**

```python
# accounting/services/payment_document_import.py
"""CSV template + bulk import for Payment Documents. Rows sharing a
``document_ref`` group into one Draft document. Never auto-posts."""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction

TEMPLATE_COLUMNS = [
    "document_ref", "bank_account_number", "account_code", "vendor_code",
    "debit", "credit", "memo",
]


def build_template_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow(["SAL-2026-03", "0000000001", "21050000", "", "90000.00", "0.00", "March net pay"])
    return buf.getvalue()


def parse_rows(file_bytes: bytes) -> list[dict]:
    text = file_bytes.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, AttributeError):
        return Decimal("0.00")


@transaction.atomic
def import_payment_documents_from_rows(rows: list[dict], *, source: str = "import") -> list:
    """Group rows by ``document_ref`` into Draft PaymentDocuments."""
    from accounting.models import Account, BankAccount, PaymentDocument, PaymentDocumentLine, TransactionSequence
    from procurement.models import Vendor

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault((row.get("document_ref") or "").strip(), []).append(row)

    created = []
    for ref, group in groups.items():
        first = group[0]
        bank = BankAccount.objects.get(account_number=(first.get("bank_account_number") or "").strip())
        doc = PaymentDocument.objects.create(
            document_number=TransactionSequence.get_next("payment_document", "PD-"),
            bank_account=bank, reference_number=ref, description=f"Imported {ref}", source=source,
        )
        for row in group:
            account = Account.objects.get(code=(row.get("account_code") or "").strip())
            vendor = None
            vcode = (row.get("vendor_code") or "").strip()
            if vcode:
                vendor = Vendor.objects.filter(code=vcode).first()
            PaymentDocumentLine.objects.create(
                payment_document=doc, account=account, vendor=vendor,
                debit=_dec(row.get("debit")), credit=_dec(row.get("credit")),
                memo=(row.get("memo") or "")[:255],
            )
        created.append(doc)
    return created
```

- [ ] **Step 4: Add download-template + import endpoints** to `PaymentDocumentViewSet`

```python
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
        except Exception as exc:  # noqa: BLE001
            return Response({"error": f"Import failed: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"created": len(created),
                         "documents": self.get_serializer(created, many=True).data},
                        status=status.HTTP_201_CREATED)
```

Add the import at the top of `payment_documents.py`: it's already covered by the service import inside the actions (kept local to avoid import-time cost).

- [ ] **Step 5: Run the import test**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py -k import --reuse-db -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add accounting/services/payment_document_import.py accounting/views/payment_documents.py accounting/tests/test_payment_document.py
git commit -m "feat(payments): PaymentDocument CSV template + bulk import (drafts only)"
```

---

## Task 5: Register the route

**Files:**
- Modify: `accounting/urls.py`

- [ ] **Step 1: Add the import and router registration**

Near the other view imports in `accounting/urls.py`:

```python
from .views.payment_documents import PaymentDocumentViewSet
```

Alongside the other `router.register(...)` calls in the payables cluster (near `router.register(r'payments', PaymentViewSet, basename='payment')`):

```python
router.register(r'payment-documents', PaymentDocumentViewSet, basename='payment-document')
```

- [ ] **Step 2: Verify the URL resolves**

Run: `.venv/Scripts/python.exe manage.py shell -c "from django.urls import reverse; print(reverse('payment-document-list'))"`
Expected: prints a path ending in `/payment-documents/`.

- [ ] **Step 3: Run the full backend test file**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py --reuse-db -q`
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add accounting/urls.py
git commit -m "feat(payments): register PaymentDocument API route"
```

---

## Task 6: Frontend hooks

**Files:**
- Create: `frontend/src/features/accounting/hooks/usePaymentDocuments.ts`

- [ ] **Step 1: Implement the hooks** (mirror `useJournal.ts`)

```typescript
// frontend/src/features/accounting/hooks/usePaymentDocuments.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const BASE = '/accounting/payment-documents/';

export interface PaymentDocumentLineInput {
  account: number | string;
  vendor?: number | string | null;
  debit: string;
  credit: string;
  memo?: string;
  is_deduction?: boolean;
}

export interface PaymentDocumentInput {
  bank_account: number | string;
  description?: string;
  reference_number?: string;
  document_date?: string;
  mda?: number | string | null;
  fund?: number | string | null;
  lines: PaymentDocumentLineInput[];
}

export function usePaymentDocuments(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['payment-documents', params],
    queryFn: async () => {
      const { data } = await apiClient.get(BASE, { params });
      return Array.isArray(data) ? data : (data?.results ?? []);
    },
  });
}

export function useCreatePaymentDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PaymentDocumentInput) => (await apiClient.post(BASE, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-documents'] }),
  });
}

export function usePostPaymentDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number | string) => (await apiClient.post(`${BASE}${id}/post/`, {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-documents'] }),
  });
}

export function useDownloadPaymentDocumentTemplate() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.get(`${BASE}download-template/`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = 'payment-document-template.csv'; a.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useBulkImportPaymentDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append('file', file);
      const { data } = await apiClient.post(`${BASE}import/`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-documents'] }),
  });
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -p tsconfig.app.json --noEmit`
Expected: no errors from this file. (Per project memory, the real frontend check is `tsc -p tsconfig.app.json`, not root `tsc --noEmit`.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/accounting/hooks/usePaymentDocuments.ts
git commit -m "feat(payments): usePaymentDocuments hooks"
```

---

## Task 7: PaymentDocumentForm

**Files:**
- Create: `frontend/src/features/accounting/ap/PaymentDocumentForm.tsx`

- [ ] **Step 1: Build the form** — reuse `JournalForm.tsx` scaffolding exactly:
  - lines state + two blank rows → **mirror JournalForm.tsx:119-122**
  - `addLine` / `removeLine` / `updateLine` handlers → **mirror JournalForm.tsx:207-214**
  - the DR/CR table JSX (SearchableSelect for account, AmountInput for debit/credit, memo input, add-line/totals footer) → **mirror JournalForm.tsx:500-576**
  - `accountOptions` via `toCodeOptions` from `useDimensions()` → **mirror JournalForm.tsx:124-146**

  The new/different code below is the header **bank account** selector, the per-line **vendor** select, the **Post & Pay** action, and the payload shape:

```tsx
// frontend/src/features/accounting/ap/PaymentDocumentForm.tsx (new/differing core)
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import SearchableSelect from '../../../components/SearchableSelect';
import AmountInput from '../../../components/AmountInput';
import { useToast } from '../../../context/ToastContext';
import { useDimensions } from '../hooks/useJournal';
import {
  useCreatePaymentDocument, usePostPaymentDocument, type PaymentDocumentLineInput,
} from '../hooks/usePaymentDocuments';

interface PDLine { id: string; account: string; vendor: string; debit: string; credit: string; memo: string; }

function useBankAccounts() {
  return useQuery({
    queryKey: ['bank-accounts-dropdown'],
    queryFn: async () => {
      const { data } = await apiClient.get('/accounting/bank-accounts/', { params: { page_size: 1000 } });
      return Array.isArray(data) ? data : (data?.results ?? []);
    },
  });
}

function useVendors() {
  return useQuery({
    queryKey: ['vendors-dropdown'],
    queryFn: async () => {
      const { data } = await apiClient.get('/procurement/vendors/', { params: { page_size: 1000, is_active: true } });
      return Array.isArray(data) ? data : (data?.results ?? []);
    },
  });
}

export default function PaymentDocumentForm() {
  const navigate = useNavigate();
  const toast = useToast();
  const { data: banks = [] } = useBankAccounts();
  const { data: vendors = [] } = useVendors();
  const { data: dims } = useDimensions();
  const createDoc = useCreatePaymentDocument();
  const postDoc = usePostPaymentDocument();

  const [bankAccount, setBankAccount] = useState('');
  const [description, setDescription] = useState('');
  // mirror JournalForm.tsx:119-122
  const [lines, setLines] = useState<PDLine[]>([
    { id: crypto.randomUUID(), account: '', vendor: '', debit: '0', credit: '0', memo: '' },
    { id: crypto.randomUUID(), account: '', vendor: '', debit: '0', credit: '0', memo: '' },
  ]);

  const totalDebit = lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0);
  const totalCredit = lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0);
  const net = totalDebit - totalCredit;               // credited to the header bank
  const canSubmit = !!bankAccount && net > 0;

  const buildPayload = () => ({
    bank_account: bankAccount,
    description,
    lines: lines
      .filter((l) => l.account && ((parseFloat(l.debit) || 0) > 0 || (parseFloat(l.credit) || 0) > 0))
      .map<PaymentDocumentLineInput>((l) => ({
        account: l.account,
        vendor: l.vendor || null,
        debit: String(parseFloat(l.debit) || 0),
        credit: String(parseFloat(l.credit) || 0),
        memo: l.memo,
      })),
  });

  const onSaveDraft = async () => {
    try { const doc = await createDoc.mutateAsync(buildPayload()); toast.success('Draft saved'); navigate(`/accounting/payment-documents`); return doc; }
    catch (e: unknown) { toast.error(e instanceof Error ? e.message : 'Save failed'); }
  };

  const onPostAndPay = async () => {
    // Save the draft, then post it — the confirm guards a real cash movement.
    if (!window.confirm('Post & Pay — this credits the bank and moves funds. Continue?')) return;
    try {
      const doc = await createDoc.mutateAsync(buildPayload());
      await postDoc.mutateAsync(doc.id);
      toast.success('Payment document posted');
      navigate('/accounting/payment-documents');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error;
      toast.error(msg || (e instanceof Error ? e.message : 'Post failed'));
    }
  };

  // ... header: bank-account SearchableSelect (options from `banks`, value=bankAccount),
  //     description input, document date shown DD/MM/YYYY via formatDate;
  // ... line grid mirroring JournalForm.tsx:500-576 but with an extra Vendor column
  //     (SearchableSelect options from `vendors`, value=l.vendor);
  // ... footer: "Net to bank" = net, balanced indicator, Save Draft + Post & Pay buttons
  //     (Post & Pay disabled unless canSubmit).
  return null; // replace with the JSX described above
}
```

- [ ] **Step 2: Fill in the JSX** by copying `JournalForm.tsx:500-576` and adding: a header bank-account `SearchableSelect` (required), a Vendor column per row (optional), a "Net to bank" total, and the two action buttons wired to `onSaveDraft` / `onPostAndPay`. Keep dates DD/MM/YYYY via `import { formatDate } from '@/utils/date';`.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc -p tsconfig.app.json --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/accounting/ap/PaymentDocumentForm.tsx
git commit -m "feat(payments): PaymentDocumentForm (header bank + DR/CR grid + Post & Pay)"
```

---

## Task 8: List page, route, and nav

**Files:**
- Create: `frontend/src/features/accounting/ap/PaymentDocumentsList.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Build the list page**

```tsx
// frontend/src/features/accounting/ap/PaymentDocumentsList.tsx
import { Link } from 'react-router-dom';
import { usePaymentDocuments } from '../hooks/usePaymentDocuments';
import { formatDate } from '@/utils/date';

export default function PaymentDocumentsList() {
  const { data: docs = [], isLoading } = usePaymentDocuments({});
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Payment Documents</h1>
        <Link to="/accounting/payment-documents/new">New Payment Document</Link>
      </div>
      {isLoading ? <p>Loading…</p> : (
        <table>
          <thead><tr><th>Document</th><th>Date</th><th>Bank</th><th>Net</th><th>Status</th></tr></thead>
          <tbody>
            {docs.map((d: any) => (
              <tr key={d.id}>
                <td>{d.document_number}</td>
                <td>{formatDate(d.document_date)}</td>
                <td>{d.bank_account_name}</td>
                <td>{d.net_amount}</td>
                <td>{d.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register routes** in `frontend/src/App.tsx` (mirror App.tsx:49 lazy-import + App.tsx:481-486 route pattern)

```tsx
const PaymentDocumentsList = lazy(() => import('./features/accounting/ap/PaymentDocumentsList'));
const PaymentDocumentForm = lazy(() => import('./features/accounting/ap/PaymentDocumentForm'));
```

```tsx
<Route path="/accounting/payment-documents" element={
  <ProtectedRoute><PaymentDocumentsList /></ProtectedRoute>
} />
<Route path="/accounting/payment-documents/new" element={
  <ProtectedRoute><PaymentDocumentForm /></ProtectedRoute>
} />
```

- [ ] **Step 3: Add the nav entry** in `frontend/src/components/Sidebar.tsx` (append to the Accounting/AP `subItems` array, Sidebar.tsx:140-159 pattern; import an icon such as `FileText` from `lucide-react`)

```tsx
{ name: 'Payment Documents', path: '/accounting/payment-documents', icon: FileText },
```

- [ ] **Step 4: Type-check + build**

Run: `cd frontend && npx tsc -p tsconfig.app.json --noEmit && npx vite build`
Expected: no type errors; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/accounting/ap/PaymentDocumentsList.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat(payments): Payment Documents list page, route, and nav entry"
```

---

## Task 9: End-to-end verification

- [ ] **Step 1: Backend suite green**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py --reuse-db -q`
Expected: all PASS.

- [ ] **Step 2: Live smoke (dev servers on :8032 / :5173)** — create a Payment Document with a `DR Payroll Liability / CR Bank` line, Post & Pay, and confirm: one journal `DR Liability / CR Bank (net)`, the bank balance dropped by net, the document shows `Posted`. Then a vendor-tagged AP line → vendor balance drops. Clean up test rows (`PD-*`).

- [ ] **Step 3: Guard against a vacuous check** (project memory: checks can be vacuous) — before trusting the suite, break one assertion on purpose (e.g. assert the bank is debited not credited) and confirm it FAILS, then revert.

---

## Self-Review (completed against the spec)

- **Spec coverage:** header bank as sole credit (Task 2 journal) ✓; DR/CR multi-line grid (Tasks 1, 7) ✓; optional vendor per line + subledger update (Tasks 1, 2, 7) ✓; optional header appropriation, budget only on expense debits (Task 2 + inherited signal) ✓; one balanced journal via the engine (Task 2) ✓; approver+MFA-gated post (Task 3) ✓; proposed-entries (Task 3) ✓; bulk import as drafts (Task 4) ✓; register/list + nav (Task 8) ✓; controls fail-closed (Task 2) ✓; DD/MM/YYYY dates (Tasks 7, 8) ✓; tests incl. `transaction=True` (Tasks 2–5) ✓.
- **Non-goals honoured:** no per-payee gateway disbursement schedule; no advance/special-GL origination via this doc; no un-post UI; header-level (not per-line) appropriation. (Register shown as a dedicated Payment Documents list adjacent to Outgoing Payments; deeper single-table union of `Payment` + `PaymentDocument` rows is a follow-up, noted here so it isn't mistaken for a gap.)
- **Type consistency:** model fields (`document_number`, `net_amount`, `is_deduction`), service names (`post_payment_document`, `compute_net`, `PaymentDocumentError`), endpoints (`/accounting/payment-documents/`, `.../post/`, `.../proposed-entries/`, `.../download-template/`, `.../import/`), and hook names (`useCreatePaymentDocument`, `usePostPaymentDocument`, …) are consistent across backend and frontend tasks.
- **Placeholder scan:** backend steps contain complete code; the one React grid step reuses `JournalForm` by explicit line-range (an existing, tested file to mirror — not a TODO). Fill-in JSX in Task 7 Step 2 is bounded to copying named line ranges plus the two documented additions (bank header, vendor column).
