# Payment Batching — Bank Payment/Confirmation Letter

**Date:** 2026-08-11
**Status:** Approved for planning
**Module:** `accounting`

## Problem

Outgoing payments are posted individually. There is no way to group them into
the signed instruction letter the Office of the Accountant General sends to a
bank — the **BANK PAYMENT(S)/CONFIRMATION(S)** form, which lists every vendor to
be credited from one government account, totals them, and carries three
signatures.

Today that document is produced outside the system. Nothing in the ERP records
which payments were sent to the bank together, so a batch cannot be reprinted,
audited, or reconciled as a unit.

## Goal

Add a durable, numbered, reprintable payment batch that produces the letter
exactly as formatted, **without changing any existing payment logic**.

## Non-goals

- Batching payroll, pension, social-benefit, or contract-IPC disbursements.
  Only AP `Payment` records are in scope. (Revisit when asked.)
- Server-side PDF generation. `weasyprint` is disabled at
  `requirements.txt:62`; every document in this codebase is browser-printed.
- Electronic transmission to the bank. The output is a printed, signed letter.
- Any change to how payments are posted, allocated, or reconciled.

## Findings from the existing codebase

| Fact | Location |
|---|---|
| `Payment` is the disbursement record; immutable + soft-deleted | `accounting/models/receivables.py:110` |
| `Payment.bank_account` → paying account; `Payment.vendor` → payee | `accounting/models/receivables.py:137-138` |
| `Payment.payment_voucher` → PV, **nullable** (required only when `AccountingSettings.require_pv_before_payment`) | `accounting/models/receivables.py:145-150` |
| `PaymentVoucherGov` already carries `payee_name`, `payee_bank`, `payee_account`, `narration`, `net_amount` | `accounting/models/treasury.py:173-183` |
| `BankAccount` carries `bank_name` + `account_number` | `accounting/models/balances.py:302` |
| `Vendor` already has `bank_name`, `bank_account_number`, `bank_sort_code` | `procurement/models.py:140-143` |
| …already exposed by the serializer | `procurement/serializers.py:62` |
| …already editable in the master-data form ("Registration & Banking") | `frontend/src/features/procurement/VendorList.tsx:555-566` |
| Cash disbursement is MFA-gated (S7-01) | `accounting/views/payables.py:1658-1663` |
| Document print pattern: settings singleton + preview route + `@media print` | `frontend/src/pages/gov/BatchWarrantPrintPreview.tsx` |
| `social_benefit_batch_pay.py` is **transient** — returns a dataclass, persists no batch | `accounting/services/social_benefit_batch_pay.py` |
| `OutgoingPaymentsPage.tsx` is already 1,746 lines | `frontend/src/features/accounting/ap/OutgoingPaymentsPage.tsx` |

### Data audit (2026-08-11, live)

Every vendor in every tenant has blank bank details:

| Tenant | Vendors | Blank account no. | Distinct bank names |
|---|---|---|---|
| `delta_state` | 4 | 4 | 0 |
| `dplux_tect` | 2 | 2 | 0 |
| `test_state` | 1 | 1 | 0 |
| `office_of_accountant_general_delta_state` | 1 | 1 | 0 |

Consequence: without a completeness guard, 100% of payments would produce a
letter with empty `BANK` and `ACCOUNT` columns.

## Decisions

1. **Scope** — AP `Payment` only, via a plain FK.
2. **Lifecycle** — the batch is a *document layer over already-`Posted`
   payments*. It never posts, voids, or edits a `Payment`.
3. **Line data** — snapshotted at add-time from the PV, falling back to the
   `Vendor` record. Reprints stay byte-identical to what was signed.
4. **Print config** — a new, fully independent `BankLetterSettings` singleton.
   `WarrantPrintoutSettings` is not modified. Accepted cost: the logo and
   office address are maintained in two places.
5. **Integration shape** — the batch is its own module, plus a minimal
   entry point on `OutgoingPaymentsPage` (row selection → "Add to Batch").
6. **Bank data** — NUBAN format validation when a value is present; vendor
   fields stay optional; completeness is enforced at the batch boundary.

## Data model

New file `accounting/models/payment_batch.py` (keeps `receivables.py` from
growing).

```python
class PaymentBatch(AuditBaseModel):
    STATUS_CHOICES = [('Draft','Draft'), ('Dispatched','Dispatched'),
                      ('Confirmed','Confirmed'), ('Cancelled','Cancelled')]

    batch_number         = CharField(max_length=30, unique=True, db_index=True)
    batch_date           = DateField(default=date.today)
    source_bank_account  = FK('accounting.BankAccount', PROTECT,
                              related_name='payment_batches')
    addressee_bank_name  = CharField(max_length=100)   # snapshot at creation
    addressee_account_no = CharField(max_length=50)    # snapshot at creation
    status               = CharField(choices=STATUS_CHOICES, default='Draft')
    dispatched_at, dispatched_by, confirmed_at, confirmed_by
    cancelled_reason     = TextField(blank=True, default='')
    notes                = TextField(blank=True, default='')

    @property
    def total_amount(self) -> Decimal:   # sum of active lines
```

```python
class PaymentBatchLine(models.Model):
    batch    = FK(PaymentBatch, CASCADE, related_name='lines')
    payment  = FK('accounting.Payment', PROTECT, related_name='batch_lines')
    sequence = PositiveIntegerField()          # the S/N column

    # frozen snapshots — never re-read after creation
    payee_name    = CharField(max_length=200)
    payee_bank    = CharField(max_length=100)
    payee_account = CharField(max_length=20)
    purpose       = CharField(max_length=255)
    amount        = DecimalField(max_digits=20, decimal_places=2)

    is_active_membership = BooleanField(default=True)

    class Meta:
        ordering = ['sequence']
        constraints = [
            models.UniqueConstraint(
                fields=['payment'],
                condition=models.Q(is_active_membership=True),
                name='uniq_active_payment_batch_membership',
            ),
        ]
```

**Why `is_active_membership` exists.** The critical failure mode is a payment
appearing in two live batches — the bank is instructed twice and the vendor is
paid twice. `unique_together('batch','payment')` does not prevent this; it only
stops duplicates *within* one batch. A cross-batch constraint cannot reference
`batch__status` because Django `UniqueConstraint` conditions cannot join. So
membership is denormalised onto the line: the partial unique index guarantees
at most one active membership per payment at the database level. Cancelling a
batch sets the flag `False`, releasing its payments back into the pool.

```python
class BankLetterSettings(AuditBaseModel):
    """Singleton per tenant. Mirrors WarrantPrintoutSettings' shape but is
    deliberately independent of it."""
    ministry_name    = CharField(default='Ministry of Finance')
    office_name      = CharField(default='Office of the Accountant General')
    office_address   = CharField(default='Asaba')
    letterhead_logo  = ImageField(upload_to='bank_letters/logos/', null=True, blank=True)

    accountant_general_name/_title/_signature
    director_treasury_name/_title/_signature
    director_mgmt_acct_name/_title/_signature

    @classmethod
    def get_singleton(cls): ...   # same accessor pattern as WarrantPrintoutSettings
```

### Snapshot resolution

At add-time, per payment, in this order:

| Line field | Primary (PV) | Fallback (Vendor / Payment) |
|---|---|---|
| `payee_name` | `pv.payee_name` | `payment.vendor.name` |
| `payee_bank` | `pv.payee_bank` | `payment.vendor.bank_name` |
| `payee_account` | `pv.payee_account` | `payment.vendor.bank_account_number` |
| `purpose` | `pv.narration` | `payment.reference_number` |
| `amount` | `pv.net_amount` | `payment.total_amount` |

`amount` uses the PV **net** amount because the bank credits the vendor after
withholding tax. Where no PV exists, `payment.total_amount` is already the
disbursed figure.

### Batch numbering

`PB/{YYYY}/{seq:04d}` where `YYYY` is the calendar year of `batch_date`
(Nigeria's fiscal year aligns with the calendar year). Sequence is
`max+1` for that year, computed inside the creating transaction under
`select_for_update` to avoid a race.

## Service layer

New `accounting/services/payment_batch.py`. All rules live here, never in the
viewset — matching `social_benefit_batch_pay.py`.

```
PaymentBatchService
  .eligible_payments(bank_account)              -> QuerySet[Payment]
  .create_batch(bank_account, batch_date, payment_ids, user) -> PaymentBatch
  .add_payments(batch, payment_ids, user)
  .remove_line(batch, line_id, user)
  .dispatch(batch, user)
  .confirm(batch, user)
  .cancel(batch, user, reason)
```

**Validation rules.** Every one raises `ValidationError` naming the offending
payment; none silently skips a row.

| Rule | Rationale |
|---|---|
| batch must be `Draft` to mutate | a dispatched letter is a signed record |
| `payment.status == 'Posted'` | decision 2 |
| `payment.bank_account == batch.source_bank_account` | one letter = one paying account |
| resolved `payee_bank` and `payee_account` both non-blank | blocks the blank-column letter |
| payment not in another active batch | `select_for_update` + partial unique index |

**Status transitions.** `Draft → Dispatched → Confirmed`; `Draft → Cancelled`
and `Dispatched → Cancelled`. `Confirmed` is terminal. Lines are immutable once
the batch leaves `Draft`.

## API

New viewset `accounting/views/payment_batch.py`, registered in
`accounting/urls.py`. No existing route changes.

```
GET|POST   /api/v1/accounting/payment-batches/
GET        /api/v1/accounting/payment-batches/{id}/
POST       /api/v1/accounting/payment-batches/{id}/add_lines/
POST       /api/v1/accounting/payment-batches/{id}/remove_line/   {line_id}
POST       /api/v1/accounting/payment-batches/{id}/dispatch/
POST       /api/v1/accounting/payment-batches/{id}/confirm/
POST       /api/v1/accounting/payment-batches/{id}/cancel/
GET        /api/v1/accounting/payment-batches/{id}/letter/
GET        /api/v1/accounting/payment-batches/eligible_payments/?bank_account=<id>
GET|PATCH  /api/v1/accounting/bank-letter-settings/current/
```

- `OrganizationFilterMixin` with `org_filter_field =
  'lines__payment__allocations__invoice__mda'`, mirroring `PaymentViewSet`'s
  MDA-isolation approach, with `.distinct()`.
- `dispatch` is gated by `IsApprover('post')` + `RequiresMFA()` — the same gate
  as `post_payment`. Dispatching produces a signed instruction to move real
  money, so the batch must not become a route around S7-01.
- `letter/` returns batch + ordered lines + resolved `BankLetterSettings` in one
  payload, so the print view makes a single request.

## Frontend

Print rendering follows `BatchWarrantPrintPreview.tsx` exactly: a dedicated
route, `@media print`, `window.print()`, A4. No new print mechanism.

**New files**

- `features/accounting/payments/batches/PaymentBatchListPage.tsx`
- `features/accounting/payments/batches/PaymentBatchDetailPage.tsx` — eligible-payment picker, running total, add/remove while `Draft`
- `features/accounting/payments/batches/BankLetterPrintPreview.tsx`
- `components/bank-letter/BankLetterLayout.tsx` — the letter markup
- `features/settings/BankLetterSettings.tsx`
- `features/accounting/hooks/usePaymentBatches.ts`

**Modified**

- `App.tsx` — 4 routes
- `Sidebar.tsx` — 1 nav entry
- `OutgoingPaymentsPage.tsx` — ~40 lines: row selection + "Add to Batch". No
  refactor of this file is in scope; it is already 1,746 lines and that debt is
  pre-existing.

### Letter layout

Matches the supplied format:

```
                    [logo]
              MINISTRY OF FINANCE
       OFFICE OF THE ACCOUNTANT GENERAL
                    ASABA
                                    DATE: DD/MM/YYYY
THE MANAGER
<addressee_bank_name>:
ACCOUNT NO:<addressee_account_no>

         BANK PAYMENT(S)/CONFIRMATION(S)
 S/N | VENDOR NAME | BANK | ACCOUNT | PURPOSE | AMOUNT
 ... 14 ruled rows minimum ...
 TOTAL |                                     | <total>

              ----------------------
              <accountant_general_name>
              <accountant_general_title>

 -------------------        -------------------
 <director_treasury_*>      <director_mgmt_acct_*>
```

Two deliberate rendering rules:

- **Dates render `DD/MM/YYYY` via `en-GB`.** ISO is confined to `input.value`,
  the API, and storage. A US-locale slip would misdate a signed bank
  instruction by up to three months.
- **The table pads to a minimum of 14 ruled rows.** Blank ruled rows on a
  signed instruction are what prevents a line being appended after signature.
  Batches larger than 14 paginate at 14 rows per page with a carried-forward
  subtotal, rather than growing the table.

## Vendor bank-data hardening

The only change to an existing model.

- Add a NUBAN validator to `Vendor.bank_account_number`: exactly 10 digits,
  applied **only when a value is present**. Today's 8 all-blank vendors remain
  saveable and no existing flow breaks.
- Add a "Bank details missing" badge to the vendor list so the gap is visible
  before payment time.
- Fields stay optional on `Vendor`. Completeness is enforced at the batch
  boundary, which is the point where a missing value would otherwise freeze
  into an immutable line.

## Testing

pytest, under `accounting/tests/`:

- eligibility: only `Posted`; `Draft`/`Void` rejected
- cross-bank payment rejected from a batch
- payment with blank payee bank/account rejected, error names the vendor
- concurrent `add_payments` for the same payment — exactly one succeeds
- snapshot immutability: edit the vendor after add, reprint is unchanged
- cancel releases payments back to eligibility
- status transitions, including that `Confirmed` is terminal
- `dispatch` returns 403 without MFA / without the approver role
- org filtering: an MDA operator sees only their own batches

Frontend (vitest): letter total equals the sum of lines; row padding to 14;
`en-GB` date formatting.

## Rollout

Purely additive. New tables, new endpoints, new routes. No data migration
beyond `CREATE TABLE`. The feature is invisible until someone opens the new
page, so it can ship dark and be verified per tenant.

## Blast radius

| | |
|---|---|
| **New** | 3 models + 1 migration, 1 service, 1 viewset, ~6 frontend files |
| **Modified** | `App.tsx`, `Sidebar.tsx`, `OutgoingPaymentsPage.tsx` (~40 lines), `accounting/urls.py`, NUBAN validator on `Vendor` |
| **Untouched** | `Payment`, `PaymentAllocation`, `PaymentVoucherGov`, `post_payment`, journal posting, bank reconciliation, `WarrantPrintoutSettings` |

## Open risks

- **Logo/address duplication.** Decision 4 accepts that `BankLetterSettings`
  and `WarrantPrintoutSettings` each hold a logo and address; they will drift.
  Accepted in exchange for zero coupling to warrant printing.
- **`OutgoingPaymentsPage.tsx` grows to ~1,790 lines.** Pre-existing debt; this
  work adds to it rather than fixing it. Flagged for a separate extraction.
- **Vendor bank details remain optional.** Operators will hit the batch-time
  rejection until master data is backfilled. The badge mitigates but does not
  prevent this.
