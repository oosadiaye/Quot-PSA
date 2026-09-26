# Payment Document (Post Outgoing Payment)

**Date:** 2026-09-26
**Status:** Approved (brainstorming)
**Branch:** `feat/payment-document` (off `main`; the unified Outgoing-Payments flow, PR #45, is already on `main`)

## Goal

A new **Payment Document** page — SAP **F-53 "Post Outgoing Payment"** — that lets an
operator pay obligations that today have no controlled on-ramp: net salaries (a
liability), pre-recognised vendor payables, direct GL/expense payments, transfers,
refunds, subventions. The document is:

- **Header-driven bank credit:** one **bank account** on the header is *always* the
  credit (cash-out) leg, for the whole document.
- **Multi-line DR/CR grid:** each line = a **GL account**, a **debit or credit**
  amount, an **optional vendor**, a memo. "Add line." Credit lines are deductions/contra.
- **Optional budget appropriation:** a header-level appropriation section (mda/fund/…),
  shown *after* the line grid, **not required** unless a line debits an expense account.
- **One balanced journal** posted through the existing engine.
- **Bulk import:** a downloadable template to create draft Payment Documents in bulk.

It appears in the existing **Outgoing Payments** register and posts through the same
controls as every other outgoing payment.

## Why (the gap this fills)

On `main` today, cash only leaves through three narrow doors: an invoice-backed
`PaymentVoucherGov` (`payment_type='VENDOR'`), an advance PV (`'ADVANCE'`), or the
hand-rolled salary journal in `hrm/views.py::mark_paid`. `pv_factory` builds **only**
VENDOR and ADVANCE vouchers. The `TRANSFER / REFUND / SUBVENTION / DEBT / PETTY_CASH /
STATUTORY` payment types exist on the model ([treasury.py:152-164](../../../accounting/models/treasury.py))
but have **no creation path**, and there is no way to settle an arbitrary
liability/GL obligation through a controlled document. Payment Document is that on-ramp.

## What it means (accounting)

Public-sector two-stage treatment: **budget/appropriation is consumed upstream at
expense recognition** (salaries imported as `DR Salary Expense / CR Payroll Liability`;
vendor invoices as `DR Expense / CR AP`). A payment merely **settles** the resulting
obligation and credits bank — it must **not** re-consume budget.

This falls straight out of the existing per-line budget gate, which is a **debit-on-
expense-GL** concept ([budget_enforcement.py:119-160](../../../accounting/signals/budget_enforcement.py)):
it skips every credit line and every debit whose account is not an Expense type (nor
under an explicit budget rule). So appropriation is enforced **per line, automatically**:

| Line (debit) | Journal effect | Budget check |
|---|---|---|
| **Liability GL** (e.g. Payroll Liability) | `DR Liability / CR Bank` — settles the obligation | **None** (not an expense debit) |
| **Vendor AP recon** (line tagged to a vendor) | `DR AP / CR Bank` + decrement `Vendor.balance` (vendor sub-ledger) | **None** |
| **Expense GL** (new spend at payment) | `DR Expense / CR Bank` | **Fires** — appropriation + payment-stage warrant required |
| **Credit line** (WHT / contra / deduction) | `CR Deduction liability` — reduces net cash | n/a (credits never gated) |

**One journal per document:** `DR each debit line / CR each credit/deduction line /
CR bank (net)`, where `net = ΣDR − ΣCR(non-bank)` is the single bank credit. Balanced
by construction; rejected if `net <= 0` or the document is unbalanced.

## Data model (new)

**`PaymentDocument`** (header):
`document_number` (unique, `PD-` sequence via `TransactionSequence`), `document_date`,
`bank_account` (FK `BankAccount`, PROTECT — requires a `gl_account`; the CR leg),
`reference_number`, `description`, `status` (`Draft`/`Posted`/`Void`),
header appropriation dims (`mda`/`fund`/`function`/`program`/`geo`, all nullable — same
shape as `JournalHeader`, used by the budget gate), `net_amount` (denormalised),
`journal` (FK `JournalHeader`, SET_NULL, set on post), `source` (`manual`/`import`),
audit fields (`AuditBaseModel`), and `ImmutableModelMixin` semantics after post.

**`PaymentDocumentLine`**:
`payment_document` (FK, CASCADE), `account` (FK `Account`, PROTECT), `vendor`
(FK `procurement.Vendor`, null/blank), `debit`, `credit` (exactly one > 0), `memo`,
`is_deduction` (bool). Ordering by id.

Rationale for a new model (not extending `PaymentVoucherGov`): a PV is rigidly
single-line and *requires* an `ncoa_code` ([treasury.py:168-171](../../../accounting/models/treasury.py)),
so it cannot represent a multi-line, no-expenditure liability settlement. Payment
Document is a first-class outgoing document **alongside** PV-backed payments in the
register; it does **not** create a PV.

## Backend

**Service `accounting/services/payment_document_posting.py::post_payment_document(doc, *, actor)`**
(one `@transaction.atomic`, `transaction=True` semantics — posts a balanced journal):
1. Guard: `status != 'Posted'`, at least one line, balanced, `net > 0`, bank has a GL account.
2. Fiscal-period gate (reuse `BasePostingService._validate_fiscal_period`).
3. Build `JournalHeader` (`source_module='payment_document'`, header appropriation dims,
   `status='Posted'`) + a `JournalLine` per document line + one CR bank line for `net`.
   The **pre-save budget signal auto-runs** appropriation + payment-stage warrant against
   the expense-debit lines only — no bespoke control code, no double-budget.
4. `_validate_journal_balanced` + `_update_gl_balances`.
5. For each **vendor-tagged settlement** line (a debit to an AP/vendor-recon liability
   account — *not* an expense debit): decrement `Vendor.balance` via `F()` (mirrors
   `procurement_posting.post_payment` / the gateway path) so the vendor sub-ledger stays true.
6. Decrement the bank's `current_balance` by `net`.
7. Link `doc.journal`, set `status='Posted'`. Fail-closed: any control/validation error
   raises and rolls back; nothing is half-posted.

**API** `accounting/views/payment_documents.py::PaymentDocumentViewSet`
(`IsAuthenticated`, module/permission gated):
- CRUD on drafts (`ImmutableModelMixin` blocks edits once Posted).
- `POST .../{id}/post/` → `post_payment_document`; `get_permissions` gates `post` with
  `[IsApprover('post'), RequiresMFA()]` (same pattern as `PaymentViewSet.post_payment`).
- `GET .../download-template/` + `POST .../import/` → template download + bulk draft create.
- `GET .../{id}/proposed-entries/` → computed balanced DR/CR preview (mirrors
  `payment_preview.compute_payment_entries`, non-persisted, preserves posted-immutability).

**Import** (`accounting/services/payment_document_import.py`): reuse the
`JournalForm` template pattern (`useDownloadJournalTemplate`/`useBulkImportJournals`).
Columns: document ref/date/bank + per-line account, vendor (optional), debit, credit,
appropriation, memo. Rows group into **Draft** Payment Documents for operator review
before Post — imported documents are never auto-posted.

## Frontend (`frontend/src/features/accounting/ap/PaymentDocumentForm.tsx`)

Reuse `JournalForm`'s building blocks: `SearchableSelect` (GL account + vendor),
`AmountInput`, add/remove-line grid, dimension pickers, `parsePostingError`,
`GlCodingWarningModal`.

- **Header:** bank-account selector (required; the auto-credit), document date
  (DD/MM/YYYY display via `formatDate`), reference, description.
- **Line grid:** GL account · Vendor (optional) · Debit · Credit · Memo · row add/delete;
  a live "Net to bank" total and a balanced/unbalanced indicator.
- **Appropriation section** *below* the grid, collapsible, **optional** (only relevant to
  expense-debit lines; a hint explains when it's needed).
- **Actions:** Save Draft · **Post & Pay** (confirms, then posts) · Import (upload template).
- **Register:** surface Payment Documents in the existing **Outgoing Payments** list
  (`OutgoingPaymentsPage.tsx`) alongside PV-backed payments, with the Type filter
  extended (e.g. "Payment Document"). Route + Sidebar entry under Accounting/AP.

## Controls & security

- Post gated by `IsApprover('post')` + `RequiresMFA()`; drafts editable, Posted immutable.
- Per-line appropriation + payment-stage warrant enforced by the existing budget signal
  (expense debits only); fiscal-period gate on post. All fail-closed.
- Input validation at the boundary (balanced, `net>0`, bank GL present, exactly one of
  debit/credit per line); server logs detail, UI shows clean messages.
- Single controlled cash door preserved — cash leaves only via a posted, balanced,
  control-checked journal.

## Testing

- **Unit:** net/derivation + balance rules; import parsing/validation.
- **Posting (`@pytest.mark.django_db(transaction=True)` — posted journals need it):**
  liability-settlement debit → posts with **no** appropriation required; expense debit
  with no appropriation → **blocked** by the budget signal; expense debit with
  appropriation → posts and consumes it; vendor-tagged line → `Vendor.balance`
  decremented; bank `current_balance` decremented by net; unbalanced / `net<=0` → refused.
- **Import:** bulk template → N Draft documents, none auto-posted.
- **Register/API:** Payment Documents appear in the Outgoing Payments query; posted docs
  are immutable; MFA/approver gate on `post`.
- Coverage ≥ 80%.

## Non-goals (v2)

- **Per-payee electronic disbursement schedule** (multi-vendor gateway/bank-file payout
  under one bank credit). v1 posts the GL payment (cash credited to bank) and records the
  payee lines; wiring each payee to the gateway rail is a follow-up — and depends on the
  paused `feat/payment-gateways` review-fixes landing first.
- **Advance / special-GL ('A') origination** via this document — advances keep their
  existing origination flow (`create_draft_voucher_from_*` → advance PV).
- **Un-post / reversal UI** (reverse via the standard journal-reversal path for now).
- **Per-line differing mda/fund appropriation** — v1 uses header-level dims (as
  `JournalForm` does); multi-appropriation documents are split into multiple documents.

## Sequencing

Independent of, and does not block, the paused `feat/payment-gateways` review-fixes.
Both touch the outgoing-payment surface; when both are ready, reconcile the
`disbursement_controls` extraction (currently gateway-branch-only) so Payment Document and
the gateway path share one control module rather than two copies.
