# Payment Batching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable, numbered, reprintable payment batch that groups posted AP payments drawn on one government bank account and prints the OAG **BANK PAYMENT(S)/CONFIRMATION(S)** letter.

**Architecture:** Purely additive document layer. Three new models (`PaymentBatch`, `PaymentBatchLine`, `BankLetterSettings`), one service holding all business rules, one viewset, and a browser-printed letter view. Batch lines snapshot payee data at add-time so a reprint always matches what was signed. Nothing in the existing payment, posting, or reconciliation path changes.

**Tech Stack:** Django 5.2, DRF 3.17, PostgreSQL 15 (partial unique index), `django-tenants`, pytest, React 19 + Vite + TypeScript, Ant Design v6, TanStack Query.

**Spec:** `docs/superpowers/specs/2026-08-11-payment-batching-design.md`

---

## Conventions this codebase uses (read before starting)

| Thing | Where | Note |
|---|---|---|
| `AuditBaseModel` | `core/models.py:26` | gives `created_at/updated_at/created_by/updated_by` |
| `OrganizationFilterMixin` | `core/mixins.py:10` | MDA isolation; set `org_filter_field` |
| `IsApprover` | `core/permissions.py:208` | `IsApprover('post')` |
| `RequiresMFA` | `accounting/permissions.py:103` | S7-01 cash-disbursement gate |
| Singleton accessor | `budget/models.py:1860` | `cls.objects.get_or_create(pk=1)` |
| Model re-export | `accounting/models/__init__.py` | add an explicit import + `__all__` entry |
| Router registration | `accounting/urls.py:86+` | `router.register(r'...', ViewSet, basename='...')` |
| Print precedent | `frontend/src/pages/gov/BatchWarrantPrintPreview.tsx` | `@media print` + `window.print()` |

Run backend tests with the project venv:

```bash
.venv/Scripts/python.exe -m pytest accounting/tests/<file> -v
```

Frontend tests:

```bash
cd frontend && npx vitest run src/<path>
```

---

## File structure

**Backend — create**

| File | Responsibility |
|---|---|
| `accounting/models/payment_batch.py` | the 3 new models, nothing else |
| `accounting/services/payment_batch.py` | every business rule; no DRF imports |
| `accounting/serializers_payment_batch.py` | DRF serializers for the 3 models |
| `accounting/views/payment_batch.py` | HTTP layer only; delegates to the service |
| `accounting/tests/test_payment_batch_logic.py` | fast, no-DB unit tests |
| `accounting/tests/test_payment_batch_service.py` | DB integration tests |
| `accounting/tests/test_payment_batch_api.py` | endpoint + permission tests |

**Backend — modify**

| File | Change |
|---|---|
| `accounting/models/__init__.py` | import + `__all__` for 3 models |
| `accounting/views/__init__.py` | re-export 2 viewsets |
| `accounting/urls.py` | register 2 routes |
| `procurement/models.py` | NUBAN validator on `Vendor.bank_account_number` |

**Frontend — create**

| File | Responsibility |
|---|---|
| `frontend/src/features/accounting/hooks/usePaymentBatches.ts` | queries/mutations + types |
| `frontend/src/components/bank-letter/BankLetterLayout.tsx` | the letter markup, print-only styling |
| `frontend/src/components/bank-letter/__tests__/BankLetterLayout.test.tsx` | total, padding, date-format tests |
| `frontend/src/features/accounting/payments/batches/PaymentBatchListPage.tsx` | list + create |
| `frontend/src/features/accounting/payments/batches/PaymentBatchDetailPage.tsx` | build/edit while Draft |
| `frontend/src/features/accounting/payments/batches/BankLetterPrintPreview.tsx` | print route |
| `frontend/src/features/settings/BankLetterSettings.tsx` | settings screen |

**Frontend — modify**

| File | Change |
|---|---|
| `frontend/src/App.tsx` | 4 lazy imports + 4 routes |
| `frontend/src/components/Sidebar.tsx` | 1 nav entry |
| `frontend/src/features/accounting/ap/OutgoingPaymentsPage.tsx` | ~40 lines: selection + "Add to Batch" |
| `frontend/src/features/procurement/VendorList.tsx` | "Bank details missing" badge |

---

## Task 1: BankLetterSettings model

**Files:**
- Create: `accounting/models/payment_batch.py`
- Modify: `accounting/models/__init__.py`
- Test: `accounting/tests/test_payment_batch_service.py`

- [ ] **Step 1: Write the failing test**

Create `accounting/tests/test_payment_batch_service.py`:

```python
"""Payment batching — DB integration tests."""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.integration
class TestBankLetterSettingsSingleton:

    def test_get_singleton_creates_row_with_defaults(self, db):
        from accounting.models import BankLetterSettings
        s = BankLetterSettings.get_singleton()
        assert s.pk == 1
        assert s.ministry_name == 'Ministry of Finance'
        assert s.office_name == 'Office of the Accountant General'

    def test_get_singleton_is_idempotent(self, db):
        from accounting.models import BankLetterSettings
        a = BankLetterSettings.get_singleton()
        a.office_address = 'Asaba'
        a.save()
        b = BankLetterSettings.get_singleton()
        assert b.pk == a.pk
        assert b.office_address == 'Asaba'
        assert BankLetterSettings.objects.count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'BankLetterSettings'`

- [ ] **Step 3: Create the model**

Create `accounting/models/payment_batch.py`:

```python
"""
Payment batching — the OAG BANK PAYMENT(S)/CONFIRMATION(S) letter.

A ``PaymentBatch`` groups already-Posted AP payments that are drawn on
ONE government bank account into a single numbered instruction letter
addressed to that bank's manager.

The batch is a pure document layer: it never posts, voids, or edits a
``Payment``. Existing AP logic is untouched by construction.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import AuditBaseModel

# NOTE: this project does NOT set AUTH_USER_MODEL — it resolves to the
# stock ``auth.User``. Always reference it as settings.AUTH_USER_MODEL;
# there is no ``core.User``.


class BankLetterSettings(AuditBaseModel):
    """Singleton per tenant — letterhead + the three signatories.

    Deliberately independent of ``budget.WarrantPrintoutSettings``: that
    model's three signatories are Governor / Commissioner / AG, whereas
    this letter is signed by AG / Director Treasury / Director Management
    Accounts. Keeping them separate means changing one document's
    settings can never alter the other. The cost — logo and address are
    maintained in two places — was accepted explicitly.
    """

    ministry_name = models.CharField(max_length=200, default='Ministry of Finance')
    office_name = models.CharField(max_length=200, default='Office of the Accountant General')
    office_address = models.CharField(max_length=200, blank=True, default='')
    letterhead_logo = models.ImageField(
        upload_to='bank_letters/logos/', null=True, blank=True,
        help_text='State coat of arms (PNG/JPG, ~200px tall).',
    )

    accountant_general_name = models.CharField(max_length=200, blank=True, default='')
    accountant_general_title = models.CharField(
        max_length=200, default='Permanent Secretary/Accountant General')
    accountant_general_signature = models.ImageField(
        upload_to='bank_letters/signatures/', null=True, blank=True)

    director_treasury_name = models.CharField(max_length=200, blank=True, default='')
    director_treasury_title = models.CharField(max_length=200, default='Director Treasurer')
    director_treasury_signature = models.ImageField(
        upload_to='bank_letters/signatures/', null=True, blank=True)

    director_mgmt_acct_name = models.CharField(max_length=200, blank=True, default='')
    director_mgmt_acct_title = models.CharField(
        max_length=200, default='Director Management Acct')
    director_mgmt_acct_signature = models.ImageField(
        upload_to='bank_letters/signatures/', null=True, blank=True)

    class Meta:
        verbose_name = 'Bank Letter Settings'
        verbose_name_plural = 'Bank Letter Settings'

    def __str__(self):
        return f'Bank letter settings ({self.office_name})'

    @classmethod
    def get_singleton(cls) -> 'BankLetterSettings':
        """Return (creating if needed) the single settings row.

        Same pk=1 convention as WarrantPrintoutSettings — one row per
        tenant schema thanks to django-tenants.
        """
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
```

- [ ] **Step 4: Register the model**

In `accounting/models/__init__.py`, after the `async_export` import line, add:

```python
from accounting.models.payment_batch import (  # noqa: F401
    BankLetterSettings, PaymentBatch, PaymentBatchLine,
)
```

And at the end of `__all__`, before the closing `]`, add:

```python
    # payment_batch.py — bank payment/confirmation letter (additive)
    'BankLetterSettings',
    'PaymentBatch',
    'PaymentBatchLine',
```

> Note: `PaymentBatch` and `PaymentBatchLine` don't exist yet — Task 2 adds them. Do Task 2's Step 3 before running migrations, or temporarily import only `BankLetterSettings`.

- [ ] **Step 5: Commit**

```bash
git add accounting/models/payment_batch.py accounting/models/__init__.py accounting/tests/test_payment_batch_service.py
git commit -m "feat(accounting): add BankLetterSettings singleton for bank payment letter"
```

---

## Task 2: PaymentBatch + PaymentBatchLine models

**Files:**
- Modify: `accounting/models/payment_batch.py`
- Test: `accounting/tests/test_payment_batch_service.py`

- [ ] **Step 1: Write the failing test**

Append to `accounting/tests/test_payment_batch_service.py`:

```python
@pytest.mark.integration
class TestPaymentBatchModel:

    def test_total_amount_sums_active_lines(self, db, bank_account_for_batch):
        from accounting.models import PaymentBatch, PaymentBatchLine
        batch = PaymentBatch.objects.create(
            batch_number='PB/2026/0001',
            source_bank_account=bank_account_for_batch,
            addressee_bank_name='Premium Trust Bank',
            addressee_account_no='0100070001',
        )
        for i, amt in enumerate(['100.00', '250.50'], start=1):
            PaymentBatchLine.objects.create(
                batch=batch, payment=None, sequence=i,
                payee_name=f'Vendor {i}', payee_bank='First Bank',
                payee_account='0123456789', purpose='Supplies',
                amount=Decimal(amt),
            )
        assert batch.total_amount == Decimal('350.50')

    def test_total_amount_excludes_inactive_lines(self, db, bank_account_for_batch):
        from accounting.models import PaymentBatch, PaymentBatchLine
        batch = PaymentBatch.objects.create(
            batch_number='PB/2026/0002',
            source_bank_account=bank_account_for_batch,
            addressee_bank_name='Premium Trust Bank',
            addressee_account_no='0100070001',
        )
        PaymentBatchLine.objects.create(
            batch=batch, payment=None, sequence=1, payee_name='A',
            payee_bank='B', payee_account='0123456789', purpose='X',
            amount=Decimal('100.00'), is_active_membership=False,
        )
        assert batch.total_amount == Decimal('0')
```

Add this fixture to `accounting/tests/conftest.py`:

```python
@pytest.fixture
def bank_account_for_batch(db, cash_account):
    """A government bank account that a payment batch can draw on."""
    from accounting.models import BankAccount
    return BankAccount.objects.create(
        name='Treasury Main', account_number='0100070001',
        account_type='Bank', gl_account=cash_account,
        bank_name='Premium Trust Bank', is_active=True,
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_service.py::TestPaymentBatchModel -v`
Expected: FAIL — `ImportError: cannot import name 'PaymentBatch'`

- [ ] **Step 3: Add the models**

Append to `accounting/models/payment_batch.py`:

```python
class PaymentBatch(AuditBaseModel):
    """A numbered bank instruction letter over already-Posted payments."""

    STATUS_DRAFT = 'Draft'
    STATUS_DISPATCHED = 'Dispatched'
    STATUS_CONFIRMED = 'Confirmed'
    STATUS_CANCELLED = 'Cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_DISPATCHED, 'Dispatched'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    batch_number = models.CharField(max_length=30, unique=True, db_index=True)
    batch_date = models.DateField(default=date.today)
    source_bank_account = models.ForeignKey(
        'accounting.BankAccount', on_delete=models.PROTECT,
        related_name='payment_batches',
        help_text='The government account the bank is instructed to debit.',
    )
    # Snapshotted at creation: the letter must reprint what was signed even
    # if the BankAccount record is later renamed or renumbered.
    addressee_bank_name = models.CharField(max_length=100)
    addressee_account_no = models.CharField(max_length=50)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dispatched_payment_batches')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='confirmed_payment_batches')
    cancelled_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-batch_date', '-batch_number']
        verbose_name = 'Payment Batch'
        verbose_name_plural = 'Payment Batches'
        indexes = [models.Index(fields=['status', 'batch_date'])]

    def __str__(self):
        return f'{self.batch_number} ({self.status})'

    @property
    def total_amount(self) -> Decimal:
        agg = self.lines.filter(is_active_membership=True).aggregate(
            total=models.Sum('amount'))
        return agg['total'] or Decimal('0')


class PaymentBatchLine(models.Model):
    """One vendor row on the letter. All payee data is frozen at add-time."""

    batch = models.ForeignKey(PaymentBatch, on_delete=models.CASCADE, related_name='lines')
    payment = models.ForeignKey(
        'accounting.Payment', on_delete=models.PROTECT,
        related_name='batch_lines', null=True, blank=True)
    sequence = models.PositiveIntegerField(help_text='The S/N column.')

    # ── Frozen snapshots — never re-read from source after creation ──
    payee_name = models.CharField(max_length=200)
    payee_bank = models.CharField(max_length=100)
    payee_account = models.CharField(max_length=20)
    purpose = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=20, decimal_places=2)

    # Denormalised membership flag. The critical failure mode is a payment
    # appearing in two live batches — the bank is instructed twice and the
    # vendor is paid twice. unique_together('batch','payment') would only
    # stop duplicates WITHIN one batch, and a UniqueConstraint condition
    # cannot join to batch__status. So membership is denormalised here and
    # a partial unique index enforces "at most one active membership per
    # payment" at the database level. Cancelling a batch flips this False,
    # releasing its payments back into the eligible pool.
    is_active_membership = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['sequence']
        constraints = [
            models.UniqueConstraint(
                fields=['payment'],
                condition=models.Q(is_active_membership=True),
                name='uniq_active_payment_batch_membership',
            ),
        ]

    def __str__(self):
        return f'{self.batch.batch_number} #{self.sequence} {self.payee_name}'
```

- [ ] **Step 4: Generate and apply the migration**

```bash
.venv/Scripts/python.exe manage.py makemigrations accounting
.venv/Scripts/python.exe manage.py migrate_schemas
```

Expected: a new migration creating `BankLetterSettings`, `PaymentBatch`, `PaymentBatchLine` and the `uniq_active_payment_batch_membership` constraint.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_service.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add accounting/models/payment_batch.py accounting/migrations/ accounting/tests/
git commit -m "feat(accounting): add PaymentBatch + PaymentBatchLine with double-batch guard"
```

---

## Task 3: Batch numbering (pure logic)

**Files:**
- Modify: `accounting/services/payment_batch.py` (create)
- Test: `accounting/tests/test_payment_batch_logic.py` (create)

- [ ] **Step 1: Write the failing test**

Create `accounting/tests/test_payment_batch_logic.py`:

```python
"""Payment batching — fast unit tests (no DB, no I/O)."""
from __future__ import annotations

from datetime import date

import pytest


@pytest.mark.unit
class TestBatchNumberFormat:

    def test_formats_with_year_and_zero_padded_sequence(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 1) == 'PB/2026/0001'

    def test_pads_to_four_digits(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 42) == 'PB/2026/0042'

    def test_does_not_truncate_beyond_four_digits(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 12345) == 'PB/2026/12345'

    def test_rejects_non_positive_sequence(self):
        from accounting.services.payment_batch import format_batch_number
        with pytest.raises(ValueError):
            format_batch_number(2026, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_logic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'accounting.services.payment_batch'`

- [ ] **Step 3: Write the implementation**

Create `accounting/services/payment_batch.py`:

```python
"""
Payment batching service — every business rule for the bank
payment/confirmation letter lives here, never in the viewset.

Mirrors the structure of ``social_benefit_batch_pay.py``: a service class
with classmethods, raising a domain exception the HTTP layer translates.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

BATCH_NUMBER_PREFIX = 'PB'


def format_batch_number(year: int, sequence: int) -> str:
    """``PB/2026/0001``.

    Nigeria's fiscal year aligns with the calendar year, so the year
    component is simply the calendar year of ``batch_date``.
    """
    if sequence < 1:
        raise ValueError(f'sequence must be >= 1, got {sequence}')
    return f'{BATCH_NUMBER_PREFIX}/{year}/{sequence:04d}'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_logic.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add accounting/services/payment_batch.py accounting/tests/test_payment_batch_logic.py
git commit -m "feat(accounting): add payment batch number formatting"
```

---

## Task 4: Payee snapshot resolution (pure logic)

Resolves each letter row from the PV first, falling back to the Vendor record.

**Files:**
- Modify: `accounting/services/payment_batch.py`
- Test: `accounting/tests/test_payment_batch_logic.py`

- [ ] **Step 1: Write the failing test**

Append to `accounting/tests/test_payment_batch_logic.py`:

```python
class _FakePV:
    def __init__(self, name='', bank='', acct='', narration='', net=None):
        self.payee_name = name
        self.payee_bank = bank
        self.payee_account = acct
        self.narration = narration
        self.net_amount = net


class _FakeVendor:
    def __init__(self, name='', bank_name='', acct=''):
        self.name = name
        self.bank_name = bank_name
        self.bank_account_number = acct


class _FakePayment:
    def __init__(self, pv=None, vendor=None, ref='', total=None):
        self.payment_voucher = pv
        self.vendor = vendor
        self.reference_number = ref
        self.total_amount = total


@pytest.mark.unit
class TestResolvePayeeSnapshot:

    def test_prefers_pv_fields(self):
        from decimal import Decimal
        from accounting.services.payment_batch import resolve_payee_snapshot
        pay = _FakePayment(
            pv=_FakePV('ACME Ltd', 'Zenith Bank', '0123456789',
                       'Supply of stationery', Decimal('900.00')),
            vendor=_FakeVendor('STALE NAME', 'STALE BANK', '9999999999'),
            ref='REF-1', total=Decimal('1000.00'),
        )
        snap = resolve_payee_snapshot(pay)
        assert snap['payee_name'] == 'ACME Ltd'
        assert snap['payee_bank'] == 'Zenith Bank'
        assert snap['payee_account'] == '0123456789'
        assert snap['purpose'] == 'Supply of stationery'
        # net, not gross — the bank credits the vendor after WHT
        assert snap['amount'] == Decimal('900.00')

    def test_falls_back_to_vendor_when_no_pv(self):
        from decimal import Decimal
        from accounting.services.payment_batch import resolve_payee_snapshot
        pay = _FakePayment(
            pv=None,
            vendor=_FakeVendor('Beta Works', 'First Bank', '0987654321'),
            ref='Consultancy', total=Decimal('500.00'),
        )
        snap = resolve_payee_snapshot(pay)
        assert snap['payee_name'] == 'Beta Works'
        assert snap['payee_bank'] == 'First Bank'
        assert snap['payee_account'] == '0987654321'
        assert snap['purpose'] == 'Consultancy'
        assert snap['amount'] == Decimal('500.00')

    def test_falls_back_per_field_when_pv_field_blank(self):
        from decimal import Decimal
        from accounting.services.payment_batch import resolve_payee_snapshot
        pay = _FakePayment(
            pv=_FakePV('ACME Ltd', '', '', '', Decimal('900.00')),
            vendor=_FakeVendor('ACME Ltd', 'GTB', '0123456789'),
            ref='REF-1', total=Decimal('1000.00'),
        )
        snap = resolve_payee_snapshot(pay)
        assert snap['payee_bank'] == 'GTB'
        assert snap['payee_account'] == '0123456789'

    def test_handles_payment_with_no_vendor_and_no_pv(self):
        from decimal import Decimal
        from accounting.services.payment_batch import resolve_payee_snapshot
        pay = _FakePayment(pv=None, vendor=None, ref='', total=Decimal('10.00'))
        snap = resolve_payee_snapshot(pay)
        assert snap['payee_name'] == ''
        assert snap['payee_bank'] == ''
        assert snap['payee_account'] == ''
        assert snap['amount'] == Decimal('10.00')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_logic.py::TestResolvePayeeSnapshot -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_payee_snapshot'`

- [ ] **Step 3: Write the implementation**

Append to `accounting/services/payment_batch.py`:

```python
def resolve_payee_snapshot(payment) -> dict:
    """Freeze the letter row for ``payment``.

    Reads the Payment Voucher first — it is the statutory authority to pay
    and already snapshots payee bank details as at authorisation. Falls
    back per-field to the live Vendor record, because
    ``Payment.payment_voucher`` is nullable (mandatory only when
    ``AccountingSettings.require_pv_before_payment`` is on).

    ``amount`` uses the PV **net** amount: the bank credits the vendor
    after withholding tax. Where no PV exists, ``payment.total_amount`` is
    already the disbursed figure.
    """
    pv = getattr(payment, 'payment_voucher', None)
    vendor = getattr(payment, 'vendor', None)

    def pick(pv_attr: str, vendor_attr: str) -> str:
        pv_val = (getattr(pv, pv_attr, '') or '') if pv else ''
        if pv_val:
            return pv_val
        return (getattr(vendor, vendor_attr, '') or '') if vendor else ''

    purpose = (getattr(pv, 'narration', '') or '') if pv else ''
    if not purpose:
        purpose = getattr(payment, 'reference_number', '') or ''

    amount = (getattr(pv, 'net_amount', None) if pv else None)
    if amount is None:
        amount = getattr(payment, 'total_amount', None) or Decimal('0')

    return {
        'payee_name': pick('payee_name', 'name'),
        'payee_bank': pick('payee_bank', 'bank_name'),
        'payee_account': pick('payee_account', 'bank_account_number'),
        'purpose': purpose[:255],
        'amount': amount,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_logic.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add accounting/services/payment_batch.py accounting/tests/test_payment_batch_logic.py
git commit -m "feat(accounting): resolve payee snapshot from PV with vendor fallback"
```

---

## Task 5: Eligibility + add-to-batch validation

**Files:**
- Modify: `accounting/services/payment_batch.py`
- Test: `accounting/tests/test_payment_batch_service.py`

- [ ] **Step 1: Write the failing test**

First add these fixtures to `accounting/tests/conftest.py`:

```python
@pytest.fixture
def batch_vendor(db):
    from procurement.models import Vendor
    return Vendor.objects.create(
        name='ACME Ltd', code='V-ACME', is_active=True,
        bank_name='Zenith Bank', bank_account_number='0123456789',
    )


@pytest.fixture
def vendor_without_bank(db):
    from procurement.models import Vendor
    return Vendor.objects.create(name='NoBank Ltd', code='V-NOBANK', is_active=True)


@pytest.fixture
def make_posted_payment(db, bank_account_for_batch, batch_vendor):
    """Factory for a Posted payment drawn on bank_account_for_batch."""
    from decimal import Decimal
    from accounting.models import Payment

    counter = {'n': 0}

    def _make(vendor=None, bank_account=None, status='Posted', amount='100.00'):
        counter['n'] += 1
        return Payment.objects.create(
            payment_number=f'PAY-{counter["n"]:04d}',
            payment_method='Wire',
            total_amount=Decimal(amount),
            status=status,
            bank_account=bank_account or bank_account_for_batch,
            vendor=vendor or batch_vendor,
            reference_number='Supply of stationery',
        )

    return _make
```

Append to `accounting/tests/test_payment_batch_service.py`:

```python
@pytest.mark.integration
class TestEligiblePayments:

    def test_includes_posted_payment_on_that_account(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment()
        ids = list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))
        assert p.id in ids

    def test_excludes_draft_payment(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment(status='Draft')
        ids = list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))
        assert p.id not in ids

    def test_excludes_payment_on_a_different_bank_account(
            self, db, bank_account_for_batch, make_posted_payment, cash_account):
        from accounting.models import BankAccount
        from accounting.services.payment_batch import PaymentBatchService
        other = BankAccount.objects.create(
            name='Other', account_number='0200000002', account_type='Bank',
            gl_account=cash_account, bank_name='Other Bank', is_active=True)
        p = make_posted_payment(bank_account=other)
        ids = list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))
        assert p.id not in ids


@pytest.mark.integration
class TestAddPaymentsValidation:

    def test_rejects_payment_with_blank_payee_bank(
            self, db, bank_account_for_batch, make_posted_payment, vendor_without_bank):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment(vendor=vendor_without_bank)
        with pytest.raises(ValidationError) as exc:
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[p.id], user=None)
        # the error must name the vendor so the operator knows what to fix
        assert 'NoBank Ltd' in str(exc.value)

    def test_rejects_draft_payment(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment(status='Draft')
        with pytest.raises(ValidationError):
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[p.id], user=None)

    def test_rejects_payment_already_in_an_active_batch(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment()
        PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[p.id], user=None)
        with pytest.raises(ValidationError):
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[p.id], user=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'PaymentBatchService'`

- [ ] **Step 3: Write the implementation**

Append to `accounting/services/payment_batch.py`:

```python
class PaymentBatchError(ValidationError):
    """Raised when a batch operation cannot proceed."""


class PaymentBatchService:
    """All payment-batch business rules.

    Every rule raises, naming the offending payment. Nothing is silently
    skipped — a silently-dropped row means the bank is under-instructed
    and a vendor goes unpaid without anyone noticing.
    """

    ACTIVE_STATUSES = ('Draft', 'Dispatched', 'Confirmed')

    @classmethod
    def eligible_payments(cls, bank_account):
        """Posted payments on ``bank_account`` not already actively batched."""
        from accounting.models import Payment
        return (
            Payment.objects
            .filter(status='Posted', bank_account=bank_account)
            .exclude(batch_lines__is_active_membership=True)
            .select_related('vendor', 'payment_voucher', 'currency')
            .distinct()
        )

    @classmethod
    def _validate_and_snapshot(cls, payment, bank_account) -> dict:
        label = payment.payment_number or f'payment #{payment.pk}'

        if payment.status != 'Posted':
            raise PaymentBatchError(
                f'{label}: only Posted payments can be batched '
                f'(status is {payment.status}).')

        if payment.bank_account_id != bank_account.pk:
            raise PaymentBatchError(
                f'{label}: drawn on a different bank account. A letter '
                f'instructs one bank about one account.')

        if payment.batch_lines.filter(is_active_membership=True).exists():
            raise PaymentBatchError(
                f'{label}: already belongs to an active batch.')

        snap = resolve_payee_snapshot(payment)
        who = snap['payee_name'] or label
        if not snap['payee_bank'] or not snap['payee_account']:
            raise PaymentBatchError(
                f'{who}: missing bank name or account number. The bank '
                f'cannot execute a line with blank details — add them on '
                f'the vendor record first.')
        return snap

    @classmethod
    @transaction.atomic
    def create_batch(cls, *, bank_account, batch_date, payment_ids, user):
        from accounting.models import PaymentBatch
        batch_date = batch_date or _date.today()

        # Serialise number allocation against concurrent creators.
        year = batch_date.year
        prefix = f'{BATCH_NUMBER_PREFIX}/{year}/'
        last = (PaymentBatch.objects
                .select_for_update()
                .filter(batch_number__startswith=prefix)
                .order_by('-batch_number')
                .first())
        next_seq = (int(last.batch_number.rsplit('/', 1)[1]) + 1) if last else 1

        batch = PaymentBatch.objects.create(
            batch_number=format_batch_number(year, next_seq),
            batch_date=batch_date,
            source_bank_account=bank_account,
            addressee_bank_name=bank_account.bank_name or bank_account.name,
            addressee_account_no=bank_account.account_number,
            created_by=user,
        )
        cls.add_payments(batch, payment_ids, user)
        return batch

    @classmethod
    @transaction.atomic
    def add_payments(cls, batch, payment_ids, user):
        from accounting.models import Payment, PaymentBatchLine

        if batch.status != batch.STATUS_DRAFT:
            raise PaymentBatchError(
                f'{batch.batch_number} is {batch.status}; only Draft '
                f'batches can be modified.')

        # select_for_update so two operators cannot both claim a payment.
        payments = list(
            Payment.objects.select_for_update()
            .filter(pk__in=list(payment_ids))
            .select_related('vendor', 'payment_voucher')
        )
        found = {p.pk for p in payments}
        missing = set(payment_ids) - found
        if missing:
            raise PaymentBatchError(f'Unknown payment ids: {sorted(missing)}')

        next_seq = (batch.lines.aggregate(m=models_max('sequence'))['m'] or 0) + 1
        for payment in payments:
            snap = cls._validate_and_snapshot(payment, batch.source_bank_account)
            PaymentBatchLine.objects.create(
                batch=batch, payment=payment, sequence=next_seq, **snap)
            next_seq += 1
        return batch
```

Add this import helper near the top of the file, under the existing imports:

```python
from django.db.models import Max as models_max
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_service.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add accounting/services/payment_batch.py accounting/tests/
git commit -m "feat(accounting): payment batch eligibility + add-line validation"
```

---

## Task 6: Status transitions (dispatch / confirm / cancel / remove_line)

**Files:**
- Modify: `accounting/services/payment_batch.py`
- Test: `accounting/tests/test_payment_batch_service.py`

- [ ] **Step 1: Write the failing test**

Append to `accounting/tests/test_payment_batch_service.py`:

```python
@pytest.mark.integration
class TestBatchTransitions:

    def _batch(self, bank_account, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment()
        return PaymentBatchService.create_batch(
            bank_account=bank_account, batch_date=None,
            payment_ids=[p.id], user=None), p

    def test_dispatch_moves_draft_to_dispatched(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        PaymentBatchService.dispatch(batch, user=None)
        batch.refresh_from_db()
        assert batch.status == 'Dispatched'
        assert batch.dispatched_at is not None

    def test_cannot_add_lines_once_dispatched(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        PaymentBatchService.dispatch(batch, user=None)
        other = make_posted_payment()
        with pytest.raises(ValidationError):
            PaymentBatchService.add_payments(batch, [other.id], user=None)

    def test_confirmed_is_terminal(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        PaymentBatchService.dispatch(batch, user=None)
        PaymentBatchService.confirm(batch, user=None)
        with pytest.raises(ValidationError):
            PaymentBatchService.cancel(batch, user=None, reason='nope')

    def test_cancel_releases_payments_back_to_eligible(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        batch, p = self._batch(bank_account_for_batch, make_posted_payment)
        assert p.id not in list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))
        PaymentBatchService.cancel(batch, user=None, reason='keyed in error')
        assert p.id in list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))

    def test_snapshot_survives_vendor_edit(
            self, db, bank_account_for_batch, make_posted_payment, batch_vendor):
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        batch_vendor.bank_account_number = '5555555555'
        batch_vendor.bank_name = 'Changed Bank'
        batch_vendor.save()
        line = batch.lines.first()
        line.refresh_from_db()
        assert line.payee_account == '0123456789'
        assert line.payee_bank == 'Zenith Bank'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_service.py::TestBatchTransitions -v`
Expected: FAIL — `AttributeError: type object 'PaymentBatchService' has no attribute 'dispatch'`

- [ ] **Step 3: Write the implementation**

Append to the `PaymentBatchService` class in `accounting/services/payment_batch.py`:

```python
    @classmethod
    @transaction.atomic
    def remove_line(cls, batch, line_id, user):
        if batch.status != batch.STATUS_DRAFT:
            raise PaymentBatchError(
                f'{batch.batch_number} is {batch.status}; lines are locked.')
        line = batch.lines.filter(pk=line_id).first()
        if line is None:
            raise PaymentBatchError(f'Line {line_id} is not in this batch.')
        line.delete()
        # Renumber so the printed S/N column stays 1..N with no gaps.
        for index, remaining in enumerate(batch.lines.order_by('sequence'), start=1):
            if remaining.sequence != index:
                remaining.sequence = index
                remaining.save(update_fields=['sequence'])
        return batch

    @classmethod
    @transaction.atomic
    def dispatch(cls, batch, user):
        """Mark the letter as printed and sent to the bank."""
        if batch.status != batch.STATUS_DRAFT:
            raise PaymentBatchError(
                f'Only Draft batches can be dispatched; '
                f'{batch.batch_number} is {batch.status}.')
        if not batch.lines.filter(is_active_membership=True).exists():
            raise PaymentBatchError(
                f'{batch.batch_number} has no lines — nothing to instruct.')
        batch.status = batch.STATUS_DISPATCHED
        batch.dispatched_at = timezone.now()
        batch.dispatched_by = user
        batch.save(update_fields=['status', 'dispatched_at', 'dispatched_by', 'updated_at'])
        return batch

    @classmethod
    @transaction.atomic
    def confirm(cls, batch, user):
        """Record the bank's confirmation that the payments were made."""
        if batch.status != batch.STATUS_DISPATCHED:
            raise PaymentBatchError(
                f'Only Dispatched batches can be confirmed; '
                f'{batch.batch_number} is {batch.status}.')
        batch.status = batch.STATUS_CONFIRMED
        batch.confirmed_at = timezone.now()
        batch.confirmed_by = user
        batch.save(update_fields=['status', 'confirmed_at', 'confirmed_by', 'updated_at'])
        return batch

    @classmethod
    @transaction.atomic
    def cancel(cls, batch, user, reason: str = ''):
        """Cancel and release every payment back to the eligible pool."""
        if batch.status == batch.STATUS_CONFIRMED:
            raise PaymentBatchError(
                f'{batch.batch_number} is Confirmed — the bank has already '
                f'acted on it. Cancellation is not possible.')
        if batch.status == batch.STATUS_CANCELLED:
            raise PaymentBatchError(f'{batch.batch_number} is already cancelled.')
        batch.status = batch.STATUS_CANCELLED
        batch.cancelled_reason = reason
        batch.save(update_fields=['status', 'cancelled_reason', 'updated_at'])
        # Flip membership so the partial unique index frees these payments.
        batch.lines.update(is_active_membership=False)
        return batch
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_service.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add accounting/services/payment_batch.py accounting/tests/test_payment_batch_service.py
git commit -m "feat(accounting): payment batch status transitions + release on cancel"
```

---

## Task 7: Serializers

**Files:**
- Create: `accounting/serializers_payment_batch.py`

- [ ] **Step 1: Write the serializers**

```python
"""DRF serializers for payment batching."""
from __future__ import annotations

from rest_framework import serializers

from accounting.models import BankLetterSettings, PaymentBatch, PaymentBatchLine


class PaymentBatchLineSerializer(serializers.ModelSerializer):
    payment_number = serializers.CharField(source='payment.payment_number',
                                           read_only=True, default='')

    class Meta:
        model = PaymentBatchLine
        fields = ['id', 'sequence', 'payment', 'payment_number',
                  'payee_name', 'payee_bank', 'payee_account',
                  'purpose', 'amount', 'is_active_membership']
        read_only_fields = fields


class PaymentBatchSerializer(serializers.ModelSerializer):
    lines = PaymentBatchLineSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=20, decimal_places=2,
                                            read_only=True)
    line_count = serializers.SerializerMethodField()
    source_bank_account_name = serializers.CharField(
        source='source_bank_account.name', read_only=True, default='')

    class Meta:
        model = PaymentBatch
        fields = ['id', 'batch_number', 'batch_date', 'source_bank_account',
                  'source_bank_account_name', 'addressee_bank_name',
                  'addressee_account_no', 'status', 'total_amount',
                  'line_count', 'lines', 'notes', 'cancelled_reason',
                  'dispatched_at', 'confirmed_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'batch_number', 'addressee_bank_name',
                            'addressee_account_no', 'status', 'total_amount',
                            'line_count', 'lines', 'cancelled_reason',
                            'dispatched_at', 'confirmed_at',
                            'created_at', 'updated_at']

    def get_line_count(self, obj) -> int:
        return obj.lines.filter(is_active_membership=True).count()


class PaymentBatchCreateSerializer(serializers.Serializer):
    source_bank_account = serializers.IntegerField()
    batch_date = serializers.DateField(required=False, allow_null=True)
    payment_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False)


class AddLinesSerializer(serializers.Serializer):
    payment_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False)


class RemoveLineSerializer(serializers.Serializer):
    line_id = serializers.IntegerField()


class CancelBatchSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class BankLetterSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankLetterSettings
        fields = ['id', 'ministry_name', 'office_name', 'office_address',
                  'letterhead_logo',
                  'accountant_general_name', 'accountant_general_title',
                  'accountant_general_signature',
                  'director_treasury_name', 'director_treasury_title',
                  'director_treasury_signature',
                  'director_mgmt_acct_name', 'director_mgmt_acct_title',
                  'director_mgmt_acct_signature']
        read_only_fields = ['id']
```

- [ ] **Step 2: Verify it imports**

Run: `.venv/Scripts/python.exe -c "import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','quot_pse.settings'); django.setup(); import accounting.serializers_payment_batch as m; print('ok', [n for n in dir(m) if n.endswith('Serializer')])"`
Expected: prints `ok` and the serializer names.

- [ ] **Step 3: Commit**

```bash
git add accounting/serializers_payment_batch.py
git commit -m "feat(accounting): payment batch serializers"
```

---

## Task 8: ViewSets + URL registration

**Files:**
- Create: `accounting/views/payment_batch.py`
- Modify: `accounting/views/__init__.py`, `accounting/urls.py`
- Test: `accounting/tests/test_payment_batch_api.py`

- [ ] **Step 1: Write the failing test**

Create `accounting/tests/test_payment_batch_api.py`:

```python
"""Payment batching — API surface + permission gates."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.integration
class TestPaymentBatchAPI:

    def test_list_requires_authentication(self, db):
        client = APIClient()
        resp = client.get('/api/v1/accounting/payment-batches/')
        assert resp.status_code in (401, 403)

    def test_superuser_can_list(self, db, superuser):
        client = APIClient()
        client.force_authenticate(user=superuser)
        resp = client.get('/api/v1/accounting/payment-batches/')
        assert resp.status_code == 200

    def test_eligible_payments_requires_bank_account_param(self, db, superuser):
        client = APIClient()
        client.force_authenticate(user=superuser)
        resp = client.get('/api/v1/accounting/payment-batches/eligible_payments/')
        assert resp.status_code == 400

    def test_create_returns_batch_number_and_total(
            self, db, superuser, bank_account_for_batch, make_posted_payment):
        client = APIClient()
        client.force_authenticate(user=superuser)
        p = make_posted_payment(amount='250.00')
        resp = client.post('/api/v1/accounting/payment-batches/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [p.id],
        }, format='json')
        assert resp.status_code == 201, resp.data
        assert resp.data['batch_number'].startswith('PB/')
        assert resp.data['line_count'] == 1

    def test_blank_bank_details_returns_400_naming_the_vendor(
            self, db, superuser, bank_account_for_batch,
            make_posted_payment, vendor_without_bank):
        client = APIClient()
        client.force_authenticate(user=superuser)
        p = make_posted_payment(vendor=vendor_without_bank)
        resp = client.post('/api/v1/accounting/payment-batches/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [p.id],
        }, format='json')
        assert resp.status_code == 400
        assert 'NoBank Ltd' in str(resp.data)

    def test_letter_endpoint_returns_batch_and_settings(
            self, db, superuser, bank_account_for_batch, make_posted_payment):
        client = APIClient()
        client.force_authenticate(user=superuser)
        p = make_posted_payment()
        created = client.post('/api/v1/accounting/payment-batches/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [p.id],
        }, format='json')
        batch_id = created.data['id']
        resp = client.get(f'/api/v1/accounting/payment-batches/{batch_id}/letter/')
        assert resp.status_code == 200
        assert 'batch' in resp.data and 'settings' in resp.data
        assert resp.data['settings']['office_name']


@pytest.mark.integration
class TestBankLetterSettingsAPI:

    def test_current_autocreates(self, db, superuser):
        client = APIClient()
        client.force_authenticate(user=superuser)
        resp = client.get('/api/v1/accounting/bank-letter-settings/current/')
        assert resp.status_code == 200
        assert resp.data['ministry_name'] == 'Ministry of Finance'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_api.py -v`
Expected: FAIL — 404s, routes not registered.

- [ ] **Step 3: Write the viewsets**

Create `accounting/views/payment_batch.py`:

```python
"""HTTP layer for payment batching. All rules live in the service."""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounting.models import BankAccount, BankLetterSettings, PaymentBatch
from accounting.serializers import PaymentSerializer
from accounting.serializers_payment_batch import (
    AddLinesSerializer, BankLetterSettingsSerializer, CancelBatchSerializer,
    PaymentBatchCreateSerializer, PaymentBatchSerializer, RemoveLineSerializer,
)
from accounting.services.payment_batch import PaymentBatchService
from core.mixins import OrganizationFilterMixin


def _bad_request(exc: DjangoValidationError) -> Response:
    messages = exc.messages if hasattr(exc, 'messages') else [str(exc)]
    return Response({'error': ' '.join(messages)}, status=status.HTTP_400_BAD_REQUEST)


class PaymentBatchViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """Bank payment/confirmation letters.

    MDA isolation mirrors PaymentViewSet: a batch is visible when any of
    its lines' payments allocate to an invoice in the operator's MDA.
    """

    org_filter_field = 'lines__payment__allocations__invoice__mda'
    queryset = (PaymentBatch.objects
                .select_related('source_bank_account')
                .prefetch_related('lines__payment')
                .distinct())
    serializer_class = PaymentBatchSerializer
    filterset_fields = ['status', 'batch_date', 'source_bank_account']

    def get_permissions(self):
        # Dispatching produces a signed instruction to a bank to move real
        # money — at least as sensitive as post_payment (S7-01). Without
        # this gate the batch would be a way around that control.
        if self.action == 'dispatch':
            from accounting.permissions import RequiresMFA
            from core.permissions import IsApprover
            return [IsApprover('post'), RequiresMFA()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        payload = PaymentBatchCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        bank_account = BankAccount.objects.filter(
            pk=data['source_bank_account']).first()
        if bank_account is None:
            return Response({'error': 'Unknown bank account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            batch = PaymentBatchService.create_batch(
                bank_account=bank_account,
                batch_date=data.get('batch_date'),
                payment_ids=data['payment_ids'],
                user=request.user,
            )
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def eligible_payments(self, request):
        bank_account_id = request.query_params.get('bank_account')
        if not bank_account_id:
            return Response({'error': 'bank_account query parameter is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        bank_account = BankAccount.objects.filter(pk=bank_account_id).first()
        if bank_account is None:
            return Response({'error': 'Unknown bank account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        qs = PaymentBatchService.eligible_payments(bank_account)
        return Response(PaymentSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def add_lines(self, request, pk=None):
        payload = AddLinesSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        batch = self.get_object()
        try:
            PaymentBatchService.add_payments(
                batch, payload.validated_data['payment_ids'], request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        batch.refresh_from_db()
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['post'])
    def remove_line(self, request, pk=None):
        payload = RemoveLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        batch = self.get_object()
        try:
            PaymentBatchService.remove_line(
                batch, payload.validated_data['line_id'], request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        batch.refresh_from_db()
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['post'])
    def dispatch(self, request, pk=None):
        batch = self.get_object()
        try:
            PaymentBatchService.dispatch(batch, request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        batch = self.get_object()
        try:
            PaymentBatchService.confirm(batch, request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        payload = CancelBatchSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        batch = self.get_object()
        try:
            PaymentBatchService.cancel(
                batch, request.user, payload.validated_data.get('reason', ''))
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['get'])
    def letter(self, request, pk=None):
        """Everything the print view needs, in one request."""
        batch = self.get_object()
        return Response({
            'batch': PaymentBatchSerializer(batch).data,
            'settings': BankLetterSettingsSerializer(
                BankLetterSettings.get_singleton(), context={'request': request}).data,
        })


class BankLetterSettingsViewSet(viewsets.GenericViewSet):
    """Singleton settings — mirrors the warrant-printout-settings pattern."""

    queryset = BankLetterSettings.objects.all()
    serializer_class = BankLetterSettingsSerializer

    @action(detail=False, methods=['get', 'patch'])
    def current(self, request):
        settings_obj = BankLetterSettings.get_singleton()
        if request.method == 'PATCH':
            if not (request.user.is_staff or request.user.is_superuser):
                return Response(
                    {'error': 'Only staff or superusers can update bank-letter settings.'},
                    status=status.HTTP_403_FORBIDDEN)
            serializer = self.get_serializer(
                settings_obj, data=request.data, partial=True,
                context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(
            settings_obj, context={'request': request}).data)
```

- [ ] **Step 4: Register the viewsets**

Append to `accounting/views/__init__.py`:

```python
# Payment batching — bank payment/confirmation letter (additive)
from .payment_batch import (  # noqa: F401
    PaymentBatchViewSet, BankLetterSettingsViewSet,
)
```

In `accounting/urls.py`, add to the import block from `.views`:

```python
    # Payment batching
    PaymentBatchViewSet, BankLetterSettingsViewSet,
```

and after the `payment-allocations` registration (line ~98):

```python
router.register(r'payment-batches', PaymentBatchViewSet, basename='payment-batch')
router.register(r'bank-letter-settings', BankLetterSettingsViewSet,
                basename='bank-letter-settings')
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_api.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add accounting/views/payment_batch.py accounting/views/__init__.py accounting/urls.py accounting/tests/test_payment_batch_api.py
git commit -m "feat(accounting): payment batch API with MFA-gated dispatch"
```

---

## Task 9: NUBAN validator on Vendor

**Files:**
- Modify: `procurement/models.py:141`
- Test: `accounting/tests/test_payment_batch_logic.py`

- [ ] **Step 1: Write the failing test**

Append to `accounting/tests/test_payment_batch_logic.py`:

```python
@pytest.mark.unit
class TestNUBANValidator:

    def test_accepts_ten_digits(self):
        from procurement.validators import validate_nuban
        validate_nuban('0123456789')   # must not raise

    def test_rejects_nine_digits(self):
        from django.core.exceptions import ValidationError
        from procurement.validators import validate_nuban
        with pytest.raises(ValidationError):
            validate_nuban('012345678')

    def test_rejects_non_digits(self):
        from django.core.exceptions import ValidationError
        from procurement.validators import validate_nuban
        with pytest.raises(ValidationError):
            validate_nuban('01234-6789')

    def test_allows_blank(self):
        """Bank details stay optional on Vendor; completeness is enforced
        at the batch boundary instead."""
        from procurement.validators import validate_nuban
        validate_nuban('')   # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_logic.py::TestNUBANValidator -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'procurement.validators'`

- [ ] **Step 3: Write the validator**

Create `procurement/validators.py`:

```python
"""Shared field validators for procurement master data."""
from __future__ import annotations

from django.core.exceptions import ValidationError

NUBAN_LENGTH = 10


def validate_nuban(value: str) -> None:
    """Nigerian NUBAN account numbers are exactly 10 digits.

    Blank is allowed: bank details remain optional on Vendor so existing
    records stay editable. Completeness is enforced at the payment-batch
    boundary, which is where a missing value would otherwise freeze into
    an immutable printed line.
    """
    if not value:
        return
    if not (value.isdigit() and len(value) == NUBAN_LENGTH):
        raise ValidationError(
            f'Account number must be exactly {NUBAN_LENGTH} digits (NUBAN). '
            f'Got {value!r}.'
        )
```

- [ ] **Step 4: Attach it to the model**

In `procurement/models.py`, change line 141 from:

```python
    bank_account_number = models.CharField(max_length=20, blank=True, default='')
```

to:

```python
    bank_account_number = models.CharField(
        max_length=20, blank=True, default='',
        validators=[validate_nuban],
        help_text='10-digit NUBAN. Optional here; required before the '
                  'payment can join a bank payment batch.',
    )
```

Add near the top of `procurement/models.py`, with the other imports:

```python
from procurement.validators import validate_nuban
```

- [ ] **Step 5: Generate the migration**

```bash
.venv/Scripts/python.exe manage.py makemigrations procurement
.venv/Scripts/python.exe manage.py migrate_schemas
```

Expected: an `AlterField` migration on `vendor.bank_account_number`. No data migration — validators are not enforced on existing rows.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_logic.py -v`
Expected: PASS (12 tests)

- [ ] **Step 7: Commit**

```bash
git add procurement/validators.py procurement/models.py procurement/migrations/ accounting/tests/test_payment_batch_logic.py
git commit -m "feat(procurement): validate vendor bank account as 10-digit NUBAN"
```

---

## Task 10: Frontend API hook

**Files:**
- Create: `frontend/src/features/accounting/hooks/usePaymentBatches.ts`

- [ ] **Step 1: Write the hook**

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

export type PaymentBatchStatus = 'Draft' | 'Dispatched' | 'Confirmed' | 'Cancelled';

export interface PaymentBatchLine {
  id: number;
  sequence: number;
  payment: number | null;
  payment_number: string;
  payee_name: string;
  payee_bank: string;
  payee_account: string;
  purpose: string;
  amount: string;
  is_active_membership: boolean;
}

export interface PaymentBatch {
  id: number;
  batch_number: string;
  batch_date: string;
  source_bank_account: number;
  source_bank_account_name: string;
  addressee_bank_name: string;
  addressee_account_no: string;
  status: PaymentBatchStatus;
  total_amount: string;
  line_count: number;
  lines: PaymentBatchLine[];
  notes: string;
  cancelled_reason: string;
  dispatched_at: string | null;
  confirmed_at: string | null;
}

export interface BankLetterSettings {
  id: number;
  ministry_name: string;
  office_name: string;
  office_address: string;
  letterhead_logo: string | null;
  accountant_general_name: string;
  accountant_general_title: string;
  accountant_general_signature: string | null;
  director_treasury_name: string;
  director_treasury_title: string;
  director_treasury_signature: string | null;
  director_mgmt_acct_name: string;
  director_mgmt_acct_title: string;
  director_mgmt_acct_signature: string | null;
}

const BASE = '/accounting/payment-batches';

export function usePaymentBatches(params?: { status?: PaymentBatchStatus }) {
  return useQuery({
    queryKey: ['payment-batches', params],
    queryFn: async () => {
      const { data } = await apiClient.get(`${BASE}/`, { params });
      return (data.results ?? data) as PaymentBatch[];
    },
  });
}

export function usePaymentBatch(id: number | undefined) {
  return useQuery({
    queryKey: ['payment-batch', id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await apiClient.get(`${BASE}/${id}/`);
      return data as PaymentBatch;
    },
  });
}

export function useEligiblePayments(bankAccountId: number | undefined) {
  return useQuery({
    queryKey: ['payment-batch-eligible', bankAccountId],
    enabled: !!bankAccountId,
    queryFn: async () => {
      const { data } = await apiClient.get(`${BASE}/eligible_payments/`, {
        params: { bank_account: bankAccountId },
      });
      return (data.results ?? data) as Array<Record<string, unknown>>;
    },
  });
}

export function useBatchLetter(id: number | undefined) {
  return useQuery({
    queryKey: ['payment-batch-letter', id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await apiClient.get(`${BASE}/${id}/letter/`);
      return data as { batch: PaymentBatch; settings: BankLetterSettings };
    },
  });
}

function useBatchMutation<TVars>(
  fn: (vars: TVars) => Promise<PaymentBatch>,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (batch) => {
      qc.invalidateQueries({ queryKey: ['payment-batches'] });
      qc.invalidateQueries({ queryKey: ['payment-batch', batch.id] });
      qc.invalidateQueries({ queryKey: ['payment-batch-eligible'] });
    },
  });
}

export function useCreatePaymentBatch() {
  return useBatchMutation<{ source_bank_account: number; batch_date?: string; payment_ids: number[] }>(
    async (vars) => (await apiClient.post(`${BASE}/`, vars)).data,
  );
}

export function useAddBatchLines(id: number) {
  return useBatchMutation<{ payment_ids: number[] }>(
    async (vars) => (await apiClient.post(`${BASE}/${id}/add_lines/`, vars)).data,
  );
}

export function useRemoveBatchLine(id: number) {
  return useBatchMutation<{ line_id: number }>(
    async (vars) => (await apiClient.post(`${BASE}/${id}/remove_line/`, vars)).data,
  );
}

export function useDispatchBatch(id: number) {
  return useBatchMutation<void>(
    async () => (await apiClient.post(`${BASE}/${id}/dispatch/`)).data,
  );
}

export function useConfirmBatch(id: number) {
  return useBatchMutation<void>(
    async () => (await apiClient.post(`${BASE}/${id}/confirm/`)).data,
  );
}

export function useCancelBatch(id: number) {
  return useBatchMutation<{ reason: string }>(
    async (vars) => (await apiClient.post(`${BASE}/${id}/cancel/`, vars)).data,
  );
}

export function useBankLetterSettings() {
  return useQuery({
    queryKey: ['bank-letter-settings'],
    queryFn: async () => {
      const { data } = await apiClient.get('/accounting/bank-letter-settings/current/');
      return data as BankLetterSettings;
    },
  });
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b --force`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/accounting/hooks/usePaymentBatches.ts
git commit -m "feat(frontend): payment batch API hooks"
```

---

## Task 11: BankLetterLayout component

The letter itself. Test-first, because the total, the 14-row padding, and the date format are all correctness-critical.

**Files:**
- Create: `frontend/src/components/bank-letter/BankLetterLayout.tsx`
- Test: `frontend/src/components/bank-letter/__tests__/BankLetterLayout.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import BankLetterLayout from '../BankLetterLayout';
import type { BankLetterSettings, PaymentBatch } from
  '../../../features/accounting/hooks/usePaymentBatches';

const settings: BankLetterSettings = {
  id: 1,
  ministry_name: 'MINISTRY OF FINANCE',
  office_name: 'OFFICE OF THE ACCOUNTANT GENERAL',
  office_address: 'ASABA',
  letterhead_logo: null,
  accountant_general_name: 'OKUNBOR V.I',
  accountant_general_title: 'PERMANENT SECRETARY/ACCOUNTANT GENERAL',
  accountant_general_signature: null,
  director_treasury_name: 'OGBAUDU A.B',
  director_treasury_title: 'DIRECTOR TREASURER',
  director_treasury_signature: null,
  director_mgmt_acct_name: 'AGBEDOGUN ISREAL',
  director_mgmt_acct_title: 'DIRECTOR MANAGEMENT ACCT',
  director_mgmt_acct_signature: null,
};

function makeBatch(lineCount: number, amount = '100.00'): PaymentBatch {
  return {
    id: 1,
    batch_number: 'PB/2026/0001',
    batch_date: '2026-08-11',
    source_bank_account: 1,
    source_bank_account_name: 'Treasury Main',
    addressee_bank_name: 'PREMIUM TRUST BANK',
    addressee_account_no: '0100070001',
    status: 'Draft',
    total_amount: (Number(amount) * lineCount).toFixed(2),
    line_count: lineCount,
    notes: '',
    cancelled_reason: '',
    dispatched_at: null,
    confirmed_at: null,
    lines: Array.from({ length: lineCount }, (_, i) => ({
      id: i + 1,
      sequence: i + 1,
      payment: i + 1,
      payment_number: `PAY-${i + 1}`,
      payee_name: `Vendor ${i + 1}`,
      payee_bank: 'Zenith Bank',
      payee_account: '0123456789',
      purpose: 'Supplies',
      amount,
      is_active_membership: true,
    })),
  };
}

describe('BankLetterLayout', () => {
  it('renders the date as DD/MM/YYYY', () => {
    render(<BankLetterLayout batch={makeBatch(1)} settings={settings} />);
    // 2026-08-11 is 11 August 2026 — never 08/11/2026
    expect(screen.getByText(/DATE:\s*11\/08\/2026/)).toBeInTheDocument();
  });

  it('addresses the bank holding the paying account', () => {
    render(<BankLetterLayout batch={makeBatch(1)} settings={settings} />);
    expect(screen.getByText('THE MANAGER')).toBeInTheDocument();
    expect(screen.getByText(/PREMIUM TRUST BANK/)).toBeInTheDocument();
    expect(screen.getByText(/0100070001/)).toBeInTheDocument();
  });

  it('pads to 14 rows when there are fewer lines', () => {
    const { container } = render(
      <BankLetterLayout batch={makeBatch(3)} settings={settings} />);
    const bodyRows = container.querySelectorAll('tbody tr');
    expect(bodyRows.length).toBe(14);
  });

  it('does not truncate when there are more than 14 lines', () => {
    const { container } = render(
      <BankLetterLayout batch={makeBatch(20)} settings={settings} />);
    const bodyRows = container.querySelectorAll('tbody tr');
    expect(bodyRows.length).toBe(20);
  });

  it('prints the total of all lines', () => {
    render(<BankLetterLayout batch={makeBatch(3, '100.00')} settings={settings} />);
    expect(screen.getByTestId('letter-total')).toHaveTextContent('300.00');
  });

  it('shows all three signatories', () => {
    render(<BankLetterLayout batch={makeBatch(1)} settings={settings} />);
    expect(screen.getByText('OKUNBOR V.I')).toBeInTheDocument();
    expect(screen.getByText('OGBAUDU A.B')).toBeInTheDocument();
    expect(screen.getByText('AGBEDOGUN ISREAL')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/bank-letter`
Expected: FAIL — cannot resolve `../BankLetterLayout`

- [ ] **Step 3: Write the component**

Create `frontend/src/components/bank-letter/BankLetterLayout.tsx`:

```tsx
import type { BankLetterSettings, PaymentBatch } from
  '../../features/accounting/hooks/usePaymentBatches';

/** Minimum ruled rows on the printed form.
 *
 * Blank ruled rows are not decoration: on a signed instruction they are
 * what stops a line being appended after the signatures. Reproduced from
 * the OAG's paper form.
 */
const MIN_ROWS = 14;

interface BankLetterLayoutProps {
  batch: PaymentBatch;
  settings: BankLetterSettings;
}

/** DD/MM/YYYY. Nigerian convention — never the US ordering. */
function formatLetterDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB');
}

function formatAmount(value: string): string {
  return Number(value).toLocaleString('en-NG', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function BankLetterLayout({ batch, settings }: BankLetterLayoutProps) {
  const lines = batch.lines.filter((l) => l.is_active_membership);
  const padding = Math.max(0, MIN_ROWS - lines.length);
  const total = lines.reduce((sum, l) => sum + Number(l.amount), 0);

  return (
    <div className="bank-letter">
      <style>{`
        .bank-letter { font-family: Arial, Helvetica, sans-serif; color:#000;
                       background:#fff; max-width:210mm; margin:0 auto; padding:12mm; }
        .bank-letter table { width:100%; border-collapse:collapse; margin-top:8px; }
        .bank-letter th, .bank-letter td { border:1px solid #000; padding:3px 6px;
                       font-size:11px; height:18px; }
        .bank-letter th { text-align:center; font-weight:700; }
        .bank-letter .num { text-align:right; }
        .bank-letter .ctr { text-align:center; }
        @media print {
          .bank-letter { padding:0; max-width:none; }
          @page { size:A4 portrait; margin:15mm; }
          .no-print { display:none !important; }
        }
      `}</style>

      {settings.letterhead_logo && (
        <div style={{ textAlign: 'center' }}>
          <img src={settings.letterhead_logo} alt="" style={{ height: 70 }} />
        </div>
      )}

      <div style={{ textAlign: 'center', fontWeight: 700, fontSize: 13, marginTop: 8 }}>
        <div>{settings.ministry_name}</div>
        <div style={{ marginTop: 6 }}>{settings.office_name}</div>
        {settings.office_address && <div style={{ marginTop: 6 }}>{settings.office_address}</div>}
      </div>

      <div style={{ textAlign: 'right', fontWeight: 700, fontSize: 12, marginTop: 10 }}>
        DATE: {formatLetterDate(batch.batch_date)}
      </div>

      <div style={{ fontWeight: 700, fontSize: 12, marginTop: 10, lineHeight: 1.9 }}>
        <div>THE MANAGER</div>
        <div>{batch.addressee_bank_name}:</div>
        <div>ACCOUNT NO:{batch.addressee_account_no}</div>
      </div>

      <div style={{ textAlign: 'center', fontWeight: 700, fontSize: 14, marginTop: 12 }}>
        BANK PAYMENT(S)/CONFIRMATION(S)
      </div>

      <table>
        <thead>
          <tr>
            <th style={{ width: '6%' }}>S/N</th>
            <th style={{ width: '24%' }}>VENDOR NAME</th>
            <th style={{ width: '16%' }}>BANK</th>
            <th style={{ width: '16%' }}>ACCOUNT</th>
            <th style={{ width: '20%' }}>PURPOSE</th>
            <th style={{ width: '18%' }}>AMOUNT</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.id}>
              <td className="ctr">{line.sequence}</td>
              <td>{line.payee_name}</td>
              <td>{line.payee_bank}</td>
              <td>{line.payee_account}</td>
              <td>{line.purpose}</td>
              <td className="num">{formatAmount(line.amount)}</td>
            </tr>
          ))}
          {Array.from({ length: padding }, (_, i) => (
            <tr key={`pad-${i}`}>
              <td className="ctr">{lines.length + i + 1}</td>
              <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th>TOTAL</th>
            <th /><th /><th /><th />
            <th className="num" data-testid="letter-total">
              {formatAmount(String(total))}
            </th>
          </tr>
        </tfoot>
      </table>

      <div style={{ marginTop: 48, textAlign: 'center', fontSize: 12 }}>
        {settings.accountant_general_signature && (
          <img src={settings.accountant_general_signature} alt="" style={{ height: 40 }} />
        )}
        <div>----------------------</div>
        <div style={{ fontWeight: 700, marginTop: 6 }}>{settings.accountant_general_name}</div>
        <div style={{ fontWeight: 700 }}>{settings.accountant_general_title}</div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 56, fontSize: 12 }}>
        <div style={{ textAlign: 'left' }}>
          {settings.director_treasury_signature && (
            <img src={settings.director_treasury_signature} alt="" style={{ height: 36 }} />
          )}
          <div>---------------------------</div>
          <div style={{ fontWeight: 700, marginTop: 6 }}>{settings.director_treasury_name}</div>
          <div style={{ fontWeight: 700 }}>{settings.director_treasury_title}</div>
        </div>
        <div style={{ textAlign: 'left' }}>
          {settings.director_mgmt_acct_signature && (
            <img src={settings.director_mgmt_acct_signature} alt="" style={{ height: 36 }} />
          )}
          <div>-----------------------------------</div>
          <div style={{ fontWeight: 700, marginTop: 6 }}>{settings.director_mgmt_acct_name}</div>
          <div style={{ fontWeight: 700 }}>{settings.director_mgmt_acct_title}</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/bank-letter`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/bank-letter/
git commit -m "feat(frontend): bank payment/confirmation letter layout"
```

---

## Task 12: Print preview route

**Files:**
- Create: `frontend/src/features/accounting/payments/batches/BankLetterPrintPreview.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { useParams } from 'react-router-dom';
import BankLetterLayout from '../../../../components/bank-letter/BankLetterLayout';
import { useBatchLetter } from '../../hooks/usePaymentBatches';

export default function BankLetterPrintPreview() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useBatchLetter(id ? Number(id) : undefined);

  if (isLoading) return <div style={{ padding: 24 }}>Loading letter…</div>;
  if (error || !data) {
    return (
      <div style={{ padding: 24, color: '#b91c1c' }}>
        Could not load this batch. It may have been cancelled or you may not
        have access to it.
      </div>
    );
  }

  return (
    <div style={{ background: '#f1f5f9', minHeight: '100vh', padding: '16px 0' }}>
      <div className="no-print" style={{ textAlign: 'center', marginBottom: 12 }}>
        <button
          onClick={() => window.print()}
          style={{
            padding: '8px 20px', borderRadius: 8, border: '1px solid #cbd5e1',
            background: '#fff', cursor: 'pointer', fontSize: 14, fontWeight: 600,
          }}
        >
          Print letter
        </button>
      </div>
      <div style={{ background: '#fff', boxShadow: '0 1px 4px rgba(0,0,0,.15)', maxWidth: '210mm', margin: '0 auto' }}>
        <BankLetterLayout batch={data.batch} settings={data.settings} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b --force`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/accounting/payments/batches/BankLetterPrintPreview.tsx
git commit -m "feat(frontend): bank letter print preview route"
```

---

## Task 13: Batch list page

**Files:**
- Create: `frontend/src/features/accounting/payments/batches/PaymentBatchListPage.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { Button, Space, Table, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { usePaymentBatches, type PaymentBatch, type PaymentBatchStatus }
  from '../../hooks/usePaymentBatches';

const STATUS_COLOUR: Record<PaymentBatchStatus, string> = {
  Draft: 'default',
  Dispatched: 'processing',
  Confirmed: 'success',
  Cancelled: 'error',
};

function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB');
}

export default function PaymentBatchListPage() {
  const navigate = useNavigate();
  const { data: batches = [], isLoading } = usePaymentBatches();

  const columns = [
    { title: 'Batch No.', dataIndex: 'batch_number', key: 'batch_number' },
    {
      title: 'Date', dataIndex: 'batch_date', key: 'batch_date',
      render: (v: string) => formatDate(v),
    },
    { title: 'Bank', dataIndex: 'addressee_bank_name', key: 'addressee_bank_name' },
    { title: 'Account', dataIndex: 'addressee_account_no', key: 'addressee_account_no' },
    { title: 'Lines', dataIndex: 'line_count', key: 'line_count', align: 'right' as const },
    {
      title: 'Total', dataIndex: 'total_amount', key: 'total_amount',
      align: 'right' as const,
      render: (v: string) => Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2 }),
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s: PaymentBatchStatus) => <Tag color={STATUS_COLOUR[s]}>{s}</Tag>,
    },
    {
      title: '', key: 'actions',
      render: (_: unknown, row: PaymentBatch) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/accounting/payment-batches/${row.id}`)}>
            Open
          </Button>
          <Button size="small" onClick={() => navigate(`/accounting/payment-batches/${row.id}/letter`)}>
            Letter
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3} style={{ marginBottom: 4 }}>Payment Batches</Typography.Title>
      <Typography.Paragraph type="secondary">
        Group posted payments drawn on one government account into a signed
        bank payment/confirmation letter.
      </Typography.Paragraph>
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={batches}
        columns={columns}
        size="small"
      />
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b --force`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/accounting/payments/batches/PaymentBatchListPage.tsx
git commit -m "feat(frontend): payment batch list page"
```

---

## Task 14: Batch detail page

**Files:**
- Create: `frontend/src/features/accounting/payments/batches/PaymentBatchDetailPage.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { App as AntApp, Button, Descriptions, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import {
  useCancelBatch, useConfirmBatch, useDispatchBatch, usePaymentBatch,
  useRemoveBatchLine, type PaymentBatchLine,
} from '../../hooks/usePaymentBatches';

function apiError(e: unknown): string {
  const r = (e as { response?: { data?: { error?: string } } }).response;
  return r?.data?.error || 'The operation failed. Please try again.';
}

export default function PaymentBatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const batchId = Number(id);
  const navigate = useNavigate();
  const { message } = AntApp.useApp();

  const { data: batch, isLoading } = usePaymentBatch(batchId);
  const removeLine = useRemoveBatchLine(batchId);
  const dispatchBatch = useDispatchBatch(batchId);
  const confirmBatch = useConfirmBatch(batchId);
  const cancelBatch = useCancelBatch(batchId);

  if (isLoading || !batch) return <div style={{ padding: 24 }}>Loading…</div>;

  const isDraft = batch.status === 'Draft';

  const run = (p: Promise<unknown>, ok: string) =>
    p.then(() => message.success(ok)).catch((e) => message.error(apiError(e)));

  const columns = [
    { title: 'S/N', dataIndex: 'sequence', key: 'sequence', width: 60 },
    { title: 'Vendor Name', dataIndex: 'payee_name', key: 'payee_name' },
    { title: 'Bank', dataIndex: 'payee_bank', key: 'payee_bank' },
    { title: 'Account', dataIndex: 'payee_account', key: 'payee_account' },
    { title: 'Purpose', dataIndex: 'purpose', key: 'purpose' },
    {
      title: 'Amount', dataIndex: 'amount', key: 'amount', align: 'right' as const,
      render: (v: string) => Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2 }),
    },
    ...(isDraft ? [{
      title: '', key: 'remove',
      render: (_: unknown, row: PaymentBatchLine) => (
        <Button size="small" danger
          onClick={() => run(removeLine.mutateAsync({ line_id: row.id }), 'Line removed')}>
          Remove
        </Button>
      ),
    }] : []),
  ];

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 12 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>{batch.batch_number}</Typography.Title>
        <Tag>{batch.status}</Tag>
      </Space>

      <Descriptions size="small" bordered column={2} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="Bank">{batch.addressee_bank_name}</Descriptions.Item>
        <Descriptions.Item label="Account No.">{batch.addressee_account_no}</Descriptions.Item>
        <Descriptions.Item label="Lines">{batch.line_count}</Descriptions.Item>
        <Descriptions.Item label="Total">
          {Number(batch.total_amount).toLocaleString('en-NG', { minimumFractionDigits: 2 })}
        </Descriptions.Item>
      </Descriptions>

      <Space style={{ marginBottom: 12 }}>
        <Button onClick={() => navigate(`/accounting/payment-batches/${batchId}/letter`)}>
          View letter
        </Button>
        {isDraft && (
          <Popconfirm
            title="Dispatch this batch?"
            description="This marks the letter as sent to the bank and locks the lines."
            onConfirm={() => run(dispatchBatch.mutateAsync(), 'Batch dispatched')}
          >
            <Button type="primary">Dispatch</Button>
          </Popconfirm>
        )}
        {batch.status === 'Dispatched' && (
          <Button onClick={() => run(confirmBatch.mutateAsync(), 'Batch confirmed')}>
            Mark confirmed by bank
          </Button>
        )}
        {batch.status !== 'Confirmed' && batch.status !== 'Cancelled' && (
          <Popconfirm
            title="Cancel this batch?"
            description="Its payments return to the eligible pool."
            onConfirm={() => run(
              cancelBatch.mutateAsync({ reason: 'Cancelled by operator' }), 'Batch cancelled')}
          >
            <Button danger>Cancel batch</Button>
          </Popconfirm>
        )}
      </Space>

      <Table
        rowKey="id"
        size="small"
        dataSource={batch.lines.filter((l) => l.is_active_membership)}
        columns={columns}
        pagination={false}
      />
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b --force`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/accounting/payments/batches/PaymentBatchDetailPage.tsx
git commit -m "feat(frontend): payment batch detail page with lifecycle actions"
```

---

## Task 15: Bank letter settings page

**Files:**
- Create: `frontend/src/features/settings/BankLetterSettings.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { App as AntApp, Button, Card, Form, Input, Typography } from 'antd';
import { useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import { useBankLetterSettings } from '../accounting/hooks/usePaymentBatches';

export default function BankLetterSettingsPage() {
  const [form] = Form.useForm();
  const { message } = AntApp.useApp();
  const qc = useQueryClient();
  const { data, isLoading } = useBankLetterSettings();

  useEffect(() => { if (data) form.setFieldsValue(data); }, [data, form]);

  const save = useMutation({
    mutationFn: async (values: Record<string, unknown>) =>
      (await apiClient.patch('/accounting/bank-letter-settings/current/', values)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bank-letter-settings'] });
      message.success('Bank letter settings saved');
    },
    onError: () => message.error('Could not save settings'),
  });

  if (isLoading) return <div style={{ padding: 24 }}>Loading…</div>;

  return (
    <div style={{ padding: 24, maxWidth: 760 }}>
      <Typography.Title level={3}>Bank Letter Settings</Typography.Title>
      <Typography.Paragraph type="secondary">
        Letterhead and signatories for the bank payment/confirmation letter.
        These are separate from the warrant printout settings.
      </Typography.Paragraph>

      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Card size="small" title="Letterhead" style={{ marginBottom: 16 }}>
          <Form.Item name="ministry_name" label="Ministry"><Input /></Form.Item>
          <Form.Item name="office_name" label="Office"><Input /></Form.Item>
          <Form.Item name="office_address" label="Address (e.g. Asaba)"><Input /></Form.Item>
        </Card>

        <Card size="small" title="Signatory 1 — Accountant General" style={{ marginBottom: 16 }}>
          <Form.Item name="accountant_general_name" label="Name"><Input /></Form.Item>
          <Form.Item name="accountant_general_title" label="Title"><Input /></Form.Item>
        </Card>

        <Card size="small" title="Signatory 2 — Director Treasury" style={{ marginBottom: 16 }}>
          <Form.Item name="director_treasury_name" label="Name"><Input /></Form.Item>
          <Form.Item name="director_treasury_title" label="Title"><Input /></Form.Item>
        </Card>

        <Card size="small" title="Signatory 3 — Director Management Accounts" style={{ marginBottom: 16 }}>
          <Form.Item name="director_mgmt_acct_name" label="Name"><Input /></Form.Item>
          <Form.Item name="director_mgmt_acct_title" label="Title"><Input /></Form.Item>
        </Card>

        <Button type="primary" htmlType="submit" loading={save.isPending}>Save settings</Button>
      </Form>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b --force`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/settings/BankLetterSettings.tsx
git commit -m "feat(frontend): bank letter settings page"
```

---

## Task 16: Routes + sidebar

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Add lazy imports**

In `frontend/src/App.tsx`, after the `SetupWizard` lazy import, add:

```tsx
const PaymentBatchListPage = lazy(() => import('./features/accounting/payments/batches/PaymentBatchListPage'));
const PaymentBatchDetailPage = lazy(() => import('./features/accounting/payments/batches/PaymentBatchDetailPage'));
const BankLetterPrintPreview = lazy(() => import('./features/accounting/payments/batches/BankLetterPrintPreview'));
const BankLetterSettingsPage = lazy(() => import('./features/settings/BankLetterSettings'));
```

- [ ] **Step 2: Add the routes**

Inside the `<Route element={<ModuleGuard module="accounting" />}>` block, next to the other `/accounting/...` routes, add:

```tsx
<Route path="/accounting/payment-batches" element={
  <ProtectedRoute><PaymentBatchListPage /></ProtectedRoute>
} />
<Route path="/accounting/payment-batches/:id" element={
  <ProtectedRoute><PaymentBatchDetailPage /></ProtectedRoute>
} />
<Route path="/accounting/payment-batches/:id/letter" element={
  <ProtectedRoute><BankLetterPrintPreview /></ProtectedRoute>
} />
```

Next to the other `/settings/...` routes, add:

```tsx
<Route path="/settings/bank-letter" element={
  <ProtectedRoute><BankLetterSettingsPage /></ProtectedRoute>
} />
```

- [ ] **Step 3: Add the sidebar entry**

In `frontend/src/components/Sidebar.tsx`, find the accounting section containing the `/accounting/outgoing-payments` entry and add immediately after it, matching the surrounding entry shape exactly:

```tsx
{ label: 'Payment Batches', path: '/accounting/payment-batches' },
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc -b --force && npx eslint src/App.tsx src/components/Sidebar.tsx`
Expected: both exit 0

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat(frontend): route + nav for payment batches"
```

---

## Task 17: "Add to Batch" entry point on OutgoingPaymentsPage

Keep this change minimal. The file is already 1,746 lines; do not refactor it here.

**Files:**
- Modify: `frontend/src/features/accounting/ap/OutgoingPaymentsPage.tsx`

- [ ] **Step 1: Add selection state**

Near the other `useState` declarations at the top of the component, add:

```tsx
const [selectedPaymentIds, setSelectedPaymentIds] = useState<number[]>([]);
```

- [ ] **Step 2: Add row selection to the payments table**

On the payments `<Table>`, add the `rowSelection` prop. Only Posted payments can be batched, so disable the rest rather than letting the operator select a row that will be rejected server-side:

```tsx
rowSelection={{
  selectedRowKeys: selectedPaymentIds,
  onChange: (keys) => setSelectedPaymentIds(keys as number[]),
  getCheckboxProps: (record: { status: string }) => ({
    disabled: record.status !== 'Posted',
  }),
}}
```

- [ ] **Step 3: Add the toolbar button**

Next to the existing toolbar buttons above the table, add:

```tsx
<Button
  disabled={selectedPaymentIds.length === 0}
  onClick={() => navigate('/accounting/payment-batches', {
    state: { presetPaymentIds: selectedPaymentIds },
  })}
>
  Add to Batch ({selectedPaymentIds.length})
</Button>
```

If `navigate` is not already in scope in this component, add `const navigate = useNavigate();` alongside the other hooks and ensure `useNavigate` is imported from `react-router-dom`.

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc -b --force && npx eslint src/features/accounting/ap/OutgoingPaymentsPage.tsx`
Expected: both exit 0

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/accounting/ap/OutgoingPaymentsPage.tsx
git commit -m "feat(frontend): add-to-batch entry point on outgoing payments"
```

---

## Task 18: "Bank details missing" badge on vendor list

**Files:**
- Modify: `frontend/src/features/procurement/VendorList.tsx`

- [ ] **Step 1: Add the badge**

In the vendor table's name column render function, append a warning tag when bank details are incomplete:

```tsx
{(!vendor.bank_name || !vendor.bank_account_number) && (
  <span
    title="Add bank name and 10-digit NUBAN before this vendor can be paid in a bank payment batch."
    style={{
      marginLeft: 8, padding: '1px 6px', borderRadius: 4,
      background: '#fef3c7', color: '#92400e',
      fontSize: '0.7rem', fontWeight: 600, whiteSpace: 'nowrap',
    }}
  >
    Bank details missing
  </span>
)}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc -b --force && npx eslint src/features/procurement/VendorList.tsx`
Expected: both exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/procurement/VendorList.tsx
git commit -m "feat(frontend): flag vendors missing bank details"
```

---

## Task 19: Full verification

- [ ] **Step 1: Backend suite**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests/test_payment_batch_logic.py accounting/tests/test_payment_batch_service.py accounting/tests/test_payment_batch_api.py -v`
Expected: PASS, 34 tests

- [ ] **Step 2: No regressions in the existing accounting suite**

Run: `.venv/Scripts/python.exe -m pytest accounting/tests -q`
Expected: same pass/fail counts as before this branch. Any newly failing test is a regression — fix it before continuing.

- [ ] **Step 3: Frontend**

Run: `cd frontend && npx tsc -b --force && npx vitest run && npx eslint src`
Expected: all exit 0

- [ ] **Step 4: Drive the running app**

With backend and frontend running, log in and:
1. Settings → Bank Letter Settings: fill the three signatory names, save.
2. Procurement → Vendors: confirm the "Bank details missing" badge; add a bank name and a 10-digit NUBAN to one vendor; confirm a 9-digit number is rejected.
3. Accounting → Outgoing Payments: select a Posted payment, click "Add to Batch".
4. Accounting → Payment Batches: create the batch, open it, click "View letter".
5. Confirm the letter shows the DD/MM/YYYY date, the addressee bank and account, 14 ruled rows, and a correct total.
6. Print to PDF and compare against the OAG paper form.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "test: verification fixes for payment batching"
```

---

## Self-review checklist (already applied)

- **Spec coverage:** every spec section maps to a task — models (1–2), numbering (3), snapshots (4), eligibility/validation (5), transitions (6), serializers (7), API + MFA gate (8), NUBAN validator (9), frontend hook (10), letter layout incl. 14-row padding and `en-GB` dates (11), print route (12), list/detail/settings pages (13–15), routes and nav (16), outgoing-payments entry point (17), vendor badge (18), verification (19).
- **Placeholders:** none. Every code step contains complete code.
- **Type consistency:** `format_batch_number`, `resolve_payee_snapshot`, `PaymentBatchService.{eligible_payments, create_batch, add_payments, remove_line, dispatch, confirm, cancel}` are named identically wherever referenced. Frontend hook names match their imports in Tasks 12–15. `is_active_membership` is spelled the same in the model, service, serializer, and component.
