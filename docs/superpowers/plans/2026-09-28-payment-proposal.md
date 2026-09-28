# Payment Proposal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every outgoing payment through an approval-staged **Payment Proposal** register; Payment Documents stop posting directly and instead, on multi-level approval, provision a Draft Outgoing Payment whose posting is the single cash-out event.

**Architecture:** A read-side **union** register of Payment Vouchers (PV) + Payment Documents (PD) with status tabs. `Payment` gains a nullable `payment_document` FK; `post_payment` dispatches by source (PD → post the PD's own balanced journal, reusing `post_payment_document`'s core). PDs are registered with the existing `workflow` engine for maker/checker approval; approval completion provisions a Draft Payment via `ensure_draft_payment_for_document`. No GL is posted until the Payment is posted in Outgoing Payments — the seam sub-project B (e-payment) will hook.

**Tech Stack:** Django 5.2 + django-tenants (schema-per-tenant), DRF, pytest-django (`--reuse-db`; posted-journal tests use `@pytest.mark.django_db(transaction=True)`), React + TypeScript + Vite. Backend dev port **8032**; SPA at `127.0.0.1:5173`. Dates are DD/MM/YYYY (en-GB) in the UI. Spec: `docs/superpowers/specs/2026-09-28-payment-proposal-design.md`.

**Conventions for every backend test task:** run with `.venv/Scripts/python.exe -m pytest <path> --reuse-db -v`. After any migration, apply to dev tenants with `for S in office_of_accountant_general_delta_state public delta_state; do .venv/Scripts/python.exe manage.py migrate_schemas --schema=$S <app> ; done`. Commits: no attribution lines, stage explicit paths (never `git add -A`), `git commit` standalone. After adding a guard/check, break it on purpose once to prove the test is non-vacuous, then revert.

---

## File structure

**Backend (create):**
- `accounting/services/document_payment_provisioning.py` — `ensure_draft_payment_for_document(pd, *, actor=None)`.
- `accounting/views/payment_proposals.py` — the union register read endpoint.
- New migrations under `accounting/migrations/` and `workflow/migrations/` (generated).

**Backend (modify):**
- `accounting/models/receivables.py` — `Payment.payment_document` FK + constraints.
- `accounting/models/payment_document.py` — status choices + immutability terminal states.
- `accounting/services/payment_document_posting.py` — split out a `post_document_journal(doc, *, actor)` core callable from the Payment post; keep back-compat.
- `accounting/views/payables.py` — `post_payment` source dispatch (PD path).
- `accounting/views/payment_documents.py` — replace `post` action with `submit`; keep `proposed_entries`.
- `accounting/signals/workflow_dispatch.py` — new receiver for `paymentdocument` approval completion.
- `workflow/models.py` + `workflow/views.py` — register `PaymentDocument` module + model.
- `accounting/models/treasury.py` — `verbose_name(_plural)` rename.
- `accounting/urls.py` (or the router module) — register the proposals endpoint.

**Frontend (modify):**
- `frontend/src/components/Sidebar.tsx` — rename entry + point at register; remove standalone PD entry.
- `frontend/src/App.tsx` — add `/accounting/payment-proposals` route.
- `frontend/src/pages/GovernmentDashboard.tsx`, `frontend/src/pages/gov/index.tsx`, `frontend/src/pages/gov/PaymentVoucherForm.tsx`, `frontend/src/pages/gov/PaymentVoucherDetail.tsx` — display-string rename.
- `frontend/src/features/accounting/ap/PaymentDocumentForm.tsx` — "Post & Pay" → "Submit for approval".
- `frontend/src/features/accounting/ap/OutgoingPaymentsPage.tsx` — show payment source (PV/PD).

**Frontend (create):**
- `frontend/src/features/accounting/ap/PaymentProposalsPage.tsx` — the unified register.
- `frontend/src/features/accounting/hooks/usePaymentProposals.ts` — hook for the union endpoint.

---

## Phase 1 — Payment can be sourced from a Payment Document

### Task 1: `Payment.payment_document` FK + constraints

**Files:**
- Modify: `accounting/models/receivables.py` (the `Payment` model, ~`:134-224`)
- Test: `accounting/tests/test_payment_proposal.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# accounting/tests/test_payment_proposal.py
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


@pytest.mark.django_db
def test_payment_cannot_have_both_pv_and_document(pp_bank):
    """A Payment is PV-sourced OR PD-sourced, never both."""
    from django.db import IntegrityError, transaction
    from accounting.models import Payment, PaymentVoucherGov, PaymentDocument
    pv = PaymentVoucherGov.objects.create(voucher_number="PV-PP-1", payment_type="VENDOR",
                                          gross_amount=Decimal("100.00"), net_amount=Decimal("100.00"))
    pd = PaymentDocument.objects.create(document_number="PD-PP-1", bank_account=pp_bank)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Payment.objects.create(bank_account=pp_bank, total_amount=Decimal("100.00"),
                                   payment_voucher=pv, payment_document=pd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_proposal.py::test_payment_cannot_have_both_pv_and_document --reuse-db -v`
Expected: FAIL — `payment_document` field does not exist / no constraint.

- [ ] **Step 3: Add the field + constraints to `Payment`**

In `accounting/models/receivables.py`, add to the `Payment` model (near `payment_voucher`):

```python
    payment_document = models.ForeignKey(
        "accounting.PaymentDocument", on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_payments",
        help_text="Source Payment Document when this payment settles a PD (mutually exclusive with payment_voucher).",
    )
```

In the `Payment` `Meta.constraints` list add:

```python
        models.CheckConstraint(
            check=~(models.Q(payment_voucher__isnull=False) & models.Q(payment_document__isnull=False)),
            name="payment_not_both_pv_and_document",
        ),
        models.UniqueConstraint(
            fields=["payment_document"],
            condition=models.Q(status__in=["Draft", "Posted"]) & models.Q(is_deleted=False),
            name="uniq_live_payment_per_document",
        ),
```

(Match the existing `uniq_live_payment_per_pv` condition style already in this `Meta`; use the same soft-delete field name this model uses — confirm it is `is_deleted`.)

- [ ] **Step 4: Generate + apply migration**

Run: `.venv/Scripts/python.exe manage.py makemigrations accounting`
Then apply: `for S in office_of_accountant_general_delta_state public delta_state; do .venv/Scripts/python.exe manage.py migrate_schemas --schema=$S accounting; done`

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_proposal.py::test_payment_cannot_have_both_pv_and_document --reuse-db -v`
Expected: PASS.

- [ ] **Step 6: Prove non-vacuous** — temporarily remove the `payment_not_both_pv_and_document` constraint from the model, `makemigrations`+migrate, rerun the test → it must FAIL (create succeeds). Revert the model + delete the throwaway migration, re-migrate.

- [ ] **Step 7: Commit**

```bash
git add accounting/models/receivables.py accounting/migrations/ accounting/tests/test_payment_proposal.py
git commit -m "feat(payments): Payment.payment_document source FK + not-both/live-unique constraints"
```

---

### Task 2: Payment Document lifecycle statuses + grandfather migration

**Files:**
- Modify: `accounting/models/payment_document.py` (`PaymentDocument.STATUS_CHOICES` ~`:43`, immutability)
- Create: a data migration mapping existing `Posted` → `Paid`
- Test: `accounting/tests/test_payment_proposal.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.django_db
def test_payment_document_has_proposal_statuses(pp_bank):
    from accounting.models import PaymentDocument
    values = {c[0] for c in PaymentDocument._meta.get_field("status").choices}
    assert {"Draft", "Pending Approval", "Approved", "Paid", "Void"} <= values
```

- [ ] **Step 2: Run test — expected FAIL** (only Draft/Posted/Void today).

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_proposal.py::test_payment_document_has_proposal_statuses --reuse-db -v`

- [ ] **Step 3: Update `STATUS_CHOICES`**

In `accounting/models/payment_document.py`:

```python
    STATUS_CHOICES = [
        ("Draft", "Draft"),
        ("Pending Approval", "Pending Approval"),
        ("Approved", "Approved"),
        ("Paid", "Paid"),
        ("Void", "Void"),
    ]
```

Confirm the `ImmutableModelMixin` terminal-state check treats `Paid` (and `Approved`/`Pending Approval`) as non-editable for the header except via `_allow_status_change=True`. If the mixin keys off a literal `"Posted"`, add a class attribute the mixin honours, or override so any of `{"Pending Approval","Approved","Paid","Void"}` block ordinary saves. Keep `Draft` editable.

- [ ] **Step 4: Schema migration + data migration**

Run: `.venv/Scripts/python.exe manage.py makemigrations accounting` (captures the choices change).
Then create a **data migration** `accounting/migrations/XXXX_pd_posted_to_paid.py`:

```python
from django.db import migrations


def posted_to_paid(apps, schema_editor):
    PaymentDocument = apps.get_model("accounting", "PaymentDocument")
    PaymentDocument.objects.filter(status="Posted").update(status="Paid")


def paid_to_posted(apps, schema_editor):
    PaymentDocument = apps.get_model("accounting", "PaymentDocument")
    PaymentDocument.objects.filter(status="Paid").update(status="Posted")


class Migration(migrations.Migration):
    dependencies = [("accounting", "<the choices migration just created>")]
    operations = [migrations.RunPython(posted_to_paid, paid_to_posted)]
```

Apply to dev tenants (the `migrate_schemas` loop). It is idempotent.

- [ ] **Step 5: Run test — expected PASS.** Also confirm existing posted PDs now read `Paid`:

`.venv/Scripts/python.exe manage.py shell -c "from django_tenants.utils import schema_context;\nwith schema_context('office_of_accountant_general_delta_state'):\n from accounting.models import PaymentDocument;\n print(list(PaymentDocument.objects.values_list('document_number','status')))"`
Expected: PD-000001..PD-000004 show `Paid`.

- [ ] **Step 6: Commit**

```bash
git add accounting/models/payment_document.py accounting/migrations/
git commit -m "feat(payments): payment-document proposal statuses; grandfather posted->paid"
```

---

### Task 3: Extract `post_document_journal` core (reusable by Payment post)

**Files:**
- Modify: `accounting/services/payment_document_posting.py`
- Test: `accounting/tests/test_payment_document.py` (existing 29 tests must still pass)

- [ ] **Step 1: Refactor without behaviour change.** Introduce a core function that posts an **Approved** PD's journal and returns the `JournalHeader`, factoring the body of today's `post_payment_document` so the public function is a thin wrapper:

```python
@transaction.atomic
def post_document_journal(doc, *, actor=None):
    """Post an Approved PaymentDocument's balanced journal and settle sub-ledgers.
    Returns the JournalHeader. Does NOT itself decide status names — caller sets
    doc.status. Used by the Payment-post dispatch (Payment sourced from a PD)."""
    lines = _lines(doc)
    bank, cash_out = _validate_lines_and_bank(doc, lines)
    _resolve_vendor_only_accounts(lines)
    _enforce_expense_budget_gates(doc, lines, actor=actor)
    journal = _build_and_post_journal(doc, lines, bank, cash_out)
    _settle_vendor_and_bank(lines, bank, cash_out)
    return journal, cash_out


@transaction.atomic
def post_payment_document(doc, *, actor=None):
    """Back-compat direct post (used by tests / any legacy caller). Flips to Paid."""
    journal, cash_out = post_document_journal(doc, actor=actor)
    doc.journal = journal
    doc.net_amount = cash_out
    doc.status = "Paid"
    doc.save(update_fields=["journal", "net_amount", "status", "updated_at"], _allow_status_change=True)
    return journal
```

Note: `_validate_lines_and_bank` currently rejects `status == "Posted"`; update it to reject any of `{"Paid","Void"}` and a present `journal_id` (a document already disbursed), while allowing `Draft`/`Pending Approval`/`Approved`.

- [ ] **Step 2: Update the existing suite for the renamed terminal.** In `accounting/tests/test_payment_document.py`, the posting tests assert `doc.status == "Posted"`; change those asserts to `"Paid"`. (These are the tests that call `post_payment_document`.)

- [ ] **Step 3: Run the full PD suite** — `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_document.py --reuse-db -q`
Expected: all pass (29), now terminal = `Paid`.

- [ ] **Step 4: Commit**

```bash
git add accounting/services/payment_document_posting.py accounting/tests/test_payment_document.py
git commit -m "refactor(payments): extract post_document_journal core; terminal status Paid"
```

---

### Task 4: `ensure_draft_payment_for_document` provisioning

**Files:**
- Create: `accounting/services/document_payment_provisioning.py`
- Test: `accounting/tests/test_payment_proposal.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.django_db
def test_ensure_draft_payment_for_document_is_idempotent(pp_bank):
    from decimal import Decimal
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account, Payment
    from accounting.services.document_payment_provisioning import ensure_draft_payment_for_document
    liab, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    pd = PaymentDocument.objects.create(document_number="PD-PROV-1", bank_account=pp_bank,
                                        reference_number="R1", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=liab, debit=Decimal("500.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("500.00"))
    p1 = ensure_draft_payment_for_document(pd)
    p2 = ensure_draft_payment_for_document(pd)
    assert p1.pk == p2.pk                       # idempotent — never a 2nd
    assert p1.payment_document_id == pd.pk
    assert p1.payment_voucher_id is None
    assert p1.status == "Draft"
    assert p1.total_amount == Decimal("500.00")  # cash-out = credit to bank GL
    assert Payment.objects.filter(payment_document=pd).exclude(status="Void").count() == 1
```

- [ ] **Step 2: Run — expected FAIL** (module missing).

- [ ] **Step 3: Implement (mirror `ensure_draft_payment_for_pv`)**

```python
# accounting/services/document_payment_provisioning.py
"""Provision the single Draft Outgoing Payment for an approved Payment Document.

Mirrors accounting/services/pv_payment_provisioning.ensure_draft_payment_for_pv:
idempotent (one non-Void Payment per PD, DB-backed by uniq_live_payment_per_document),
callers own the transaction. The Payment's cash-out is the PD's bank-credit total;
the PD's bank account is authoritative (fixed), never operator-changed.
"""
from django.db import transaction
from accounting.models import Payment, PaymentDocument, TransactionSequence
from accounting.services.payment_document_posting import _bank_credit, _lines


def ensure_draft_payment_for_document(pd, *, actor=None):
    locked = PaymentDocument.objects.select_for_update().get(pk=pd.pk)
    existing = (Payment.objects.select_for_update()
                .filter(payment_document=locked).exclude(status="Void")
                .order_by("id").first())
    if existing is not None:
        return existing
    bank_gl_id = locked.bank_account.gl_account_id if locked.bank_account_id else None
    cash_out = _bank_credit(_lines(locked), bank_gl_id)
    return Payment.objects.create(
        payment_document=locked,
        payment_voucher=None,
        bank_account=locked.bank_account,
        total_amount=cash_out,
        reference_number=locked.reference_number or locked.document_number,
        document_number=TransactionSequence.get_next("payment", "PAY-"),
        payment_method="Wire",
        status="Draft",
    )
```

Wrap the test body in `transaction.atomic()` if `select_for_update` requires it under the test's connection; provisioning itself has no atomic (caller owns it), so the test calls it inside `with transaction.atomic():`.

- [ ] **Step 4: Run — expected PASS.**

- [ ] **Step 5: Commit**

```bash
git add accounting/services/document_payment_provisioning.py accounting/tests/test_payment_proposal.py
git commit -m "feat(payments): ensure_draft_payment_for_document provisioning helper"
```

---

### Task 5: `post_payment` dispatch — PD path posts the PD journal

**Files:**
- Modify: `accounting/views/payables.py` (`post_payment` action, ~`:1772`)
- Test: `accounting/tests/test_payment_proposal.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.django_db(transaction=True)
def test_post_pd_sourced_payment_posts_document_journal(pp_bank, open_period_pp):
    from decimal import Decimal
    from accounting.models import (PaymentDocument, PaymentDocumentLine, Account, Payment)
    from accounting.services.document_payment_provisioning import ensure_draft_payment_for_document
    from accounting.views.payables import post_payment_impl  # thin callable extracted in step 3
    liab, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    pd = PaymentDocument.objects.create(document_number="PD-POSTPP-1", bank_account=pp_bank,
                                        reference_number="R2", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=liab, debit=Decimal("700.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("700.00"))
    from django.db import transaction
    with transaction.atomic():
        pay = ensure_draft_payment_for_document(pd)
    post_payment_impl(pay, actor=None)         # the dispatch entry
    pay.refresh_from_db(); pd.refresh_from_db()
    assert pay.status == "Posted"
    assert pd.status == "Paid"
    assert pd.journal_id is not None
    j = pd.journal
    assert sum(l.debit for l in j.lines.all()) == sum(l.credit for l in j.lines.all()) == Decimal("700.00")
    pp_bank.refresh_from_db()
    # bank dropped by cash-out
```

Add an `open_period_pp` fixture (copy `open_period` from `test_payment_document.py`).

- [ ] **Step 2: Run — expected FAIL** (`post_payment_impl` missing).

- [ ] **Step 3: Add the dispatch.** Extract the posting body of the `post_payment` DRF action into a module-level `post_payment_impl(payment, *, actor)` so it is unit-testable, and have the action call it. Add the PD branch **first**:

```python
def post_payment_impl(payment, *, actor=None):
    if payment.status == "Posted":
        raise PaymentError("Payment already posted.")   # reuse existing error type
    if payment.payment_document_id:
        from accounting.services.payment_document_posting import post_document_journal
        pd = payment.payment_document
        if pd.status != "Approved":
            raise PaymentError("Payment Document is not approved.")
        journal, cash_out = post_document_journal(pd, actor=actor)
        pd.journal = journal
        pd.status = "Paid"
        pd.save(update_fields=["journal", "status", "updated_at"], _allow_status_change=True)
        payment.journal_entry = journal
        payment.total_amount = cash_out
        payment.status = "Posted"
        payment.save(update_fields=["journal_entry", "total_amount", "status", "updated_at"],
                     _allow_status_change=True)
        return payment
    # ... existing PV/AP/advance body unchanged ...
```

(Use the real error class + the real Payment→journal FK name — the map calls it `journal_entry`. Keep the existing action wrapper returning the serialized payment.)

- [ ] **Step 4: Run — expected PASS.** Then run the whole file: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_proposal.py --reuse-db -v`.

- [ ] **Step 5: Prove non-vacuous** — temporarily change the PD branch to skip `post_document_journal` (leave PD Draft) → the test's `pd.status == "Paid"` / `journal_id is not None` must FAIL. Revert.

- [ ] **Step 6: Commit**

```bash
git add accounting/views/payables.py accounting/tests/test_payment_proposal.py
git commit -m "feat(payments): post_payment dispatches PD-sourced payments to the document journal"
```

---

## Phase 2 — Multi-level approval for Payment Documents

### Task 6: Register `PaymentDocument` with the workflow engine

**Files:**
- Modify: `workflow/models.py` (module choices ~`:20`), `workflow/views.py` (registration + `_MODEL_TO_MODULE_KEY`)
- Test: `accounting/tests/test_payment_proposal.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.django_db
def test_paymentdocument_registered_in_workflow():
    from workflow.views import _MODEL_TO_MODULE_KEY
    assert "paymentdocument" in _MODEL_TO_MODULE_KEY
```

- [ ] **Step 2: Run — expected FAIL.**

- [ ] **Step 3: Register.** Follow exactly the pattern the PV uses (the map: `paymentvouchergov` registered at `workflow/views.py:59`, module key mapping `:124/:131`, label `:93`; module choice `('PaymentVoucher','Payment Vouchers')` at `workflow/models.py:20`). Add a `('PaymentDocument','Payment Documents')` module choice, register the `paymentdocument` model in `workflow/views.py`, map it in `_MODEL_TO_MODULE_KEY`, and add its human label. Generate the `workflow` migration for the new module choice and apply it.

- [ ] **Step 4: Run — expected PASS.**

- [ ] **Step 5: Commit**

```bash
git add workflow/models.py workflow/views.py workflow/migrations/
git commit -m "feat(workflow): register Payment Document as an approvable module"
```

---

### Task 7: PD `submit` action (replaces `post`)

**Files:**
- Modify: `accounting/views/payment_documents.py` (remove `post`, add `submit`)
- Test: `accounting/tests/test_payment_proposal.py`

- [ ] **Step 1: Write the failing test** (uses the `pd_api` client pattern from `test_payment_document.py`)

```python
@pytest.mark.django_db
def test_submit_moves_document_to_pending_approval(pd_api, pp_bank):
    from decimal import Decimal
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account
    client, _ = pd_api
    liab, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    pd = PaymentDocument.objects.create(document_number="PD-SUB-1", bank_account=pp_bank,
                                        reference_number="R3", status="Draft")
    PaymentDocumentLine.objects.create(payment_document=pd, account=liab, debit=Decimal("100.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("100.00"))
    resp = client.post(f"/api/v1/accounting/payment-documents/{pd.pk}/submit/", {}, format="json",
                       HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 200, resp.content
    pd.refresh_from_db()
    assert pd.status == "Pending Approval"
    # a POST to the removed post/ action is gone:
    resp2 = client.post(f"/api/v1/accounting/payment-documents/{pd.pk}/post/", {}, format="json",
                        HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp2.status_code in (404, 405)
```

Copy the `pd_api` fixture (and `open_period_pp`) into `test_payment_proposal.py` or import the shared fixtures.

- [ ] **Step 2: Run — expected FAIL.**

- [ ] **Step 3: Implement.** In `accounting/views/payment_documents.py`: delete the `post` action. Add:

```python
    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        doc = self.get_object()
        if doc.status != "Draft":
            return Response({"error": "Only a Draft document can be submitted."},
                            status=status.HTTP_400_BAD_REQUEST)
        # validate it is a postable balanced doc up-front (reuse the posting validator)
        from accounting.services.payment_document_posting import _lines, _validate_lines_and_bank, PaymentDocumentError
        try:
            _validate_lines_and_bank(doc, _lines(doc))
        except PaymentDocumentError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        doc.status = "Pending Approval"
        doc.save(update_fields=["status", "updated_at"], _allow_status_change=True)
        # open a workflow approval instance if the engine gates this module (mirror the PV submit path)
        # <call the same helper the PV form uses to create the approval instance for this ContentType>
        return Response(self.get_serializer(doc).data)
```

Wire the workflow-instance creation to the same helper PVs use (find it near the PV `approve`/submit path). If the tenant's `GlobalApprovalSettings` mode for `PaymentDocument` is Disabled, `submit` may auto-approve (engine decides) — do not special-case here.

- [ ] **Step 4: Run — expected PASS.**

- [ ] **Step 5: Commit**

```bash
git add accounting/views/payment_documents.py accounting/tests/test_payment_proposal.py
git commit -m "feat(payments): payment-document submit-for-approval action; drop direct post"
```

---

### Task 8: Dispatch receiver — approval completion provisions the Payment

**Files:**
- Modify: `accounting/signals/workflow_dispatch.py`
- Test: `accounting/tests/test_payment_proposal.py`

- [ ] **Step 1: Write the failing test** — assert that invoking the receiver for an approved PD provisions exactly one Draft Payment.

```python
@pytest.mark.django_db
def test_approval_dispatch_provisions_document_payment(pp_bank):
    from decimal import Decimal
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account, Payment
    from accounting.signals.workflow_dispatch import auto_provision_paymentdocument_on_approval
    liab, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    pd = PaymentDocument.objects.create(document_number="PD-DISP-1", bank_account=pp_bank,
                                        reference_number="R4", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=liab, debit=Decimal("300.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("300.00"))
    auto_provision_paymentdocument_on_approval(sender=None, document=pd, model_name="paymentdocument", action="approve")
    assert Payment.objects.filter(payment_document=pd).exclude(status="Void").count() == 1
```

- [ ] **Step 2: Run — expected FAIL.**

- [ ] **Step 3: Implement** a receiver mirroring `auto_post_paymentvoucher_on_approval` (`accounting/signals/workflow_dispatch.py:225`), but for `model_name == "paymentdocument"` + `action == "approve"`; wrap in `transaction.atomic()` and call `ensure_draft_payment_for_document(document, actor=...)`. Log-only on failure (do not roll back the approval). Register the receiver on the same `document_approval_completed` signal.

- [ ] **Step 4: Run — expected PASS.** Then the whole file.

- [ ] **Step 5: Commit**

```bash
git add accounting/signals/workflow_dispatch.py accounting/tests/test_payment_proposal.py
git commit -m "feat(payments): provision draft outgoing payment on payment-document approval"
```

---

## Phase 3 — Unified register endpoint

### Task 9: `GET /accounting/payment-proposals/` union endpoint

**Files:**
- Create: `accounting/views/payment_proposals.py`
- Modify: the accounting router registration (`accounting/urls.py` or wherever PV/PD routes register)
- Test: `accounting/tests/test_payment_proposal.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.django_db
def test_payment_proposals_unions_pv_and_pd(pd_api, pp_bank):
    from decimal import Decimal
    from accounting.models import PaymentVoucherGov, PaymentDocument
    client, _ = pd_api
    PaymentVoucherGov.objects.create(voucher_number="PV-UNI-1", payment_type="VENDOR",
                                     gross_amount=Decimal("10.00"), net_amount=Decimal("10.00"), status="DRAFT")
    PaymentDocument.objects.create(document_number="PD-UNI-1", bank_account=pp_bank,
                                   reference_number="R5", status="Draft")
    resp = client.get("/api/v1/accounting/payment-proposals/?status=Proposed",
                      HTTP_HOST="localhost", HTTP_X_TENANT_DOMAIN="pytest.localhost")
    assert resp.status_code == 200, resp.content
    rows = resp.json()["results"] if isinstance(resp.json(), dict) else resp.json()
    sources = {r["source"] for r in rows}
    assert {"pv", "pd"} <= sources
    numbers = {r["number"] for r in rows}
    assert {"PV-UNI-1", "PD-UNI-1"} <= numbers
```

- [ ] **Step 2: Run — expected FAIL.**

- [ ] **Step 3: Implement** the read endpoint:

```python
# accounting/views/payment_proposals.py
"""Unified read-only register of Payment Vouchers + Payment Documents."""
from rest_framework.views import APIView
from rest_framework.response import Response
from accounting.models import PaymentVoucherGov, PaymentDocument

PV_UNIFIED = {"DRAFT": "Proposed", "CHECKED": "Proposed", "AUDITED": "Proposed",
              "APPROVED": "Approved", "SCHEDULED": "Approved", "PAID": "Paid",
              "CANCELLED": "Void", "REVERSED": "Void"}
PD_UNIFIED = {"Draft": "Proposed", "Pending Approval": "Proposed", "Approved": "Approved",
              "Paid": "Paid", "Void": "Void"}


def _pv_row(pv):
    return {"source": "pv", "id": pv.pk, "number": pv.voucher_number,
            "date": pv.created_at.date().isoformat() if pv.created_at else None,
            "payee_or_description": getattr(pv, "payee_name", "") or "",
            "amount": str(pv.net_amount), "native_status": pv.status,
            "unified_status": PV_UNIFIED.get(pv.status, "Proposed"),
            "detail_path": f"/accounting/payment-vouchers/{pv.pk}"}


def _pd_row(pd):
    return {"source": "pd", "id": pd.pk, "number": pd.document_number,
            "date": pd.document_date.isoformat() if pd.document_date else None,
            "payee_or_description": pd.description or "",
            "amount": str(pd.net_amount), "native_status": pd.status,
            "unified_status": PD_UNIFIED.get(pd.status, "Proposed"),
            "detail_path": f"/accounting/payment-documents/{pd.pk}"}


class PaymentProposalsView(APIView):
    def get(self, request):
        want_status = request.query_params.get("status")   # unified value or None
        want_source = request.query_params.get("source")   # 'pv' | 'pd' | None
        rows = []
        if want_source in (None, "pv"):
            rows += [_pv_row(pv) for pv in PaymentVoucherGov.objects.all()]
        if want_source in (None, "pd"):
            rows += [_pd_row(pd) for pd in PaymentDocument.objects.all()]
        if want_status:
            rows = [r for r in rows if r["unified_status"] == want_status]
        rows.sort(key=lambda r: (r["date"] or ""), reverse=True)
        return Response({"results": rows, "count": len(rows)})
```

Register the path in the accounting URLconf: `path("payment-proposals/", PaymentProposalsView.as_view(), name="payment-proposals")` under the `api/v1/accounting/` prefix. Apply the same MDA scoping the PV/PD viewsets use (call the shared `OrganizationFilterMixin` queryset helper or replicate its filter on each queryset) so an MDA-scoped operator sees only their own rows. Inherit the project-global `RBACPermission` (no custom `permission_classes`).

- [ ] **Step 4: Run — expected PASS.**

- [ ] **Step 5: Commit**

```bash
git add accounting/views/payment_proposals.py accounting/urls.py accounting/tests/test_payment_proposal.py
git commit -m "feat(payments): unified payment-proposals union register endpoint"
```

---

## Phase 4 — Frontend

### Task 10: Display rename PV → "Payment Proposal"

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx:147`, `frontend/src/pages/GovernmentDashboard.tsx:160`, `frontend/src/pages/gov/index.tsx:1386` + `:1406`, `frontend/src/pages/gov/PaymentVoucherForm.tsx:267-268`, `frontend/src/pages/gov/PaymentVoucherDetail.tsx` header, `accounting/models/treasury.py:226-227`

- [ ] **Step 1** Replace the user-facing strings "Payment Vouchers"→"Payment Proposal", "Payment Voucher"→"Payment Proposal", "New Payment Voucher"→"New Payment Proposal" at the listed sites; set `treasury.py` `verbose_name="Payment Proposal"`, `verbose_name_plural="Payment Proposals"`. Leave routes, `voucher_number`, endpoints, and internal identifiers unchanged.
- [ ] **Step 2** Run `cd frontend && npx tsc -p tsconfig.app.json --noEmit` — expected exit 0.
- [ ] **Step 3: Commit** — `git add` the six files; `git commit -m "feat(payments): rename Payment Vouchers surface to Payment Proposal (display)"`.

---

### Task 11: Unified register page + nav

**Files:**
- Create: `frontend/src/features/accounting/ap/PaymentProposalsPage.tsx`, `frontend/src/features/accounting/hooks/usePaymentProposals.ts`
- Modify: `frontend/src/App.tsx` (add route `/accounting/payment-proposals`), `frontend/src/components/Sidebar.tsx` (point "Payment Proposal" at the register; remove the standalone "Payment Documents" entry)

- [ ] **Step 1** `usePaymentProposals(status?, source?)` — a `useQuery` hitting `GET /accounting/payment-proposals/` with the params; typed `PaymentProposalRow` matching the endpoint shape (`source,id,number,date,payee_or_description,amount,native_status,unified_status,detail_path`).
- [ ] **Step 2** `PaymentProposalsPage.tsx` — render `GenericListPage` (mirror `PaymentDocumentsList.tsx`) with columns Number / Date (DD/MM/YYYY) / Payee-or-Description / Amount (₦) / Source / Status; pass a `tabs` node with **Proposed · Approved · Paid · Void** driving the `status` param; each row's action navigates to `row.detail_path`. Add a **New** control linking to `/accounting/payment-vouchers/new` and `/accounting/payment-documents/new`.
- [ ] **Step 3** Route + nav: add the route in `App.tsx`; in `Sidebar.tsx` point the (already renamed) "Payment Proposal" entry at `/accounting/payment-proposals` and remove the standalone "Payment Documents" nav item. Redirect the old `/accounting/payment-vouchers` list route to the register (keep `/new` and `/:id`).
- [ ] **Step 4** `cd frontend && npx tsc -p tsconfig.app.json --noEmit && npx vite build` — expected exit 0 both.
- [ ] **Step 5: Commit** — `git commit -m "feat(payments): unified Payment Proposal register page + nav"`.

---

### Task 12: PD form "Submit for approval"; Outgoing Payments shows source

**Files:**
- Modify: `frontend/src/features/accounting/ap/PaymentDocumentForm.tsx`, `frontend/src/features/accounting/hooks/usePaymentDocuments.ts` (swap the post hook for a submit hook), `frontend/src/features/accounting/ap/OutgoingPaymentsPage.tsx`

- [ ] **Step 1** Replace the PD form's **Post & Pay** button + confirm with **Submit for approval** (calls `POST /accounting/payment-documents/{id}/submit/`, no cash-moving confirm copy). On success, navigate to `/accounting/payment-proposals`. Keep Save Draft.
- [ ] **Step 2** In `OutgoingPaymentsPage.tsx`, add a **Source** column/badge distinguishing PV-sourced vs PD-sourced (`payment.payment_document ? 'Document' : 'Voucher'`). No behavioural change to Post — the backend dispatch handles PD-sourced posting.
- [ ] **Step 3** `cd frontend && npx tsc -p tsconfig.app.json --noEmit && npx vite build` — exit 0.
- [ ] **Step 4: Commit** — `git commit -m "feat(payments): payment-document submit-for-approval; source badge in outgoing payments"`.

---

## Phase 5 — End-to-end verification

### Task 13: Live Playwright end-to-end

- [ ] **Step 1** Ensure backend on 8032 + Vite on 5173 (restart backend after all migrations). Apply every new migration to the OAG/public/delta_state tenants.
- [ ] **Step 2** Drive the full flow on the OAG tenant: create a Payment Document (bank + balanced DR/CR lines) → **Submit for approval** → it appears under **Proposed** in the Payment Proposal register. Approve it through the workflow UI → it moves to **Approved** and a Draft Payment appears in **Outgoing Payments**. Post that payment → the PD shows **Paid**, the journal is balanced (DB check: DR settlement / CR bank, source_module=payment_document), bank decremented. Screenshot each state; verify no direct-post path remains on the PD.
- [ ] **Step 3** Regression: a normal PV still approves → Draft Payment → posts (DR AP / CR bank) unchanged, and shows in the unified register.
- [ ] **Step 4** Clean up test rows where practical (posted rows are immutable — reverse the journal to undo). Do not commit `.playwright-mcp/` artifacts.

---

## Notes for the executor

- **Controls are non-negotiable:** the PD journal a Payment posts is byte-for-byte what `post_document_journal` builds today — fiscal gate, expense-only appropriation/warrant with `_budget_checked` suppression, balance, immutability, duplicate-posting, vendor sub-ledger `(debit−credit)`, bank decrement. You are changing *when/through-which-door* it posts, not the journal.
- **Idempotency:** rely on `uniq_live_payment_per_document` + the provisioning reuse + `post_payment`'s existing already-posted guard. Never create a second live Payment per PD.
- **Break-a-check discipline:** every new guard (constraints, `Approved`-required, dispatch) gets one deliberate break to prove its test is real, then revert.
- **This is Sub-project A only.** Do not implement e-payment/gateway here; Task 5's `post_payment_impl` PD branch is the exact seam Sub-project B will extend (swap the bank-credit leg to the clearing GL + fire the gateway).
