# AP Register → Create PV → Deduction-Aware Payment (delta pass)

**Date:** 2026-09-23
**Branch:** `feat/milestone-as-invoice`
**Status:** Approved — implementing

## Context

The user wants: the moment a milestone is invoiced it appears in the AP
Invoices Register; every **open** invoice in that register (from AP entry,
PO/GRN invoice verification, or milestone approval) carries a **Create PV**
button that raises an **editable draft PV** with deduction lines; approving the
PV creates a **draft payment line in Outgoing Payments carrying the
deductions**; posting that payment disburses net cash.

Reconnaissance (backend + frontend) established that **the spine already exists
and is wired** — this is the delta pass, not a rebuild:

| Requirement | Already in code |
|---|---|
| Milestone → AP register | `MilestoneInvoiceService.approve_and_invoice` posts `VendorInvoice(Posted)`; `APInvoicesRegister.tsx` lists all vendor invoices |
| Open invoice → Create PV | `create-draft-voucher` action → `pv_factory.create_draft_voucher_from_invoice` (idempotent by `invoice_number`) |
| Editable draft PV + deductions | `DeductionLinesEditor.tsx`, PV create form, edit-in-place while DRAFT |
| Approve → draft payment w/ deductions | `approve` action calls `ensure_draft_payment_for_pv`; `post_payment` is deduction-aware (DR AP gross / CR each deduction GL / CR bank net) |

## Decision

Create PV on a register row always raises an **invoice PV** against the booked
payable. **No advance split-button** — advances are a PV-only, pre-invoice flow
and keep their own "Vendor Down Payment" page. (User choice.)

## Scope — four deltas

### Phase 0 — Verify the flow live (before any change)

Non-destructive baseline confirmation against the real DB / journal engine:

1. Run existing suites: `accounting/tests/test_central_payment_processing.py`,
   `accounting/tests/test_workflow_dispatch.py::TestPaymentVoucherAutoPost`,
   `contracts/tests/test_milestone_invoice.py` (`--reuse-db`, posted-journal
   tests `transaction=True`).
2. Add one integration test walking the actual path: milestone →
   `VendorInvoice(Posted)` → `create-draft-voucher` → add a WHT line →
   `approve` → assert DRAFT `Payment` (net total, gross allocation) →
   `post_payment` → assert GL (DR AP gross / CR WHT / CR bank net), invoice
   `Paid`, PV `PAID`, `cumulative_gross_paid` synced. Permanent regression guard.
3. Drive the UI end-to-end with Playwright (dev tenant, SPA `127.0.0.1:5173`,
   API `localhost:8032`) to confirm the operator-visible flow.

### Delta A — Create PV on every open row

- **Frontend** (`APInvoicesRegister.tsx`): show Create PV for all open
  payables — `status ∈ {Posted, Partially Paid}` (and Approved-with-journal),
  `payable_now > 0`, no live PV — not only `Posted`. Surfaces it on milestone
  and partially-paid invoices.
- **Backend** (`pv_factory.create_draft_voucher_from_invoice`): raise the PV for
  **`payable_now`** (= `total − paid − retention_withheld`), **not**
  `balance_due`, so a milestone invoice's **retention lien is never pulled into
  the PV**. This is the correctness fix that makes "retention is a lien that
  can't be accessed until released" hold at the PV step.

### Delta B — Show deductions on the Outgoing payment

No new storage. Add read-only `gross_amount`, `net_amount`, `deductions[]` to the
Payment serializer, sourced from `payment.payment_voucher.deductions`. Render a
gross → deductions → net breakdown on the Outgoing Payments row (expandable) and
in `PaymentFormModal`/detail, reusing the proposed-entries styling.

### Delta C — Approve = one step

Hide the redundant **Schedule Payment** button (`PaymentVoucherDetail.tsx`) —
`approve` already provisions the draft payment. Keep the `schedule_payment`
*endpoint* (the E-payment surface still creates `PaymentInstruction`). Phase 0
confirms PV goes `APPROVED → PAID` cleanly without the `SCHEDULED` hop.

## Out of scope (flagged follow-ups)

- Paying **released** retention as a top-up PV on an already-PV'd invoice (needs
  a second-PV path; register hides Create PV once a PV is linked). The
  lien/release machinery exists; only the register + factory idempotency would
  need a top-up mode.
- Surfacing advances as register rows (user chose invoice-only).

## Testing & risk

- Delta A backend is the only accounting-correctness change → covered by the
  Phase 0 integration test (assert PV amount = `payable_now`, retention not
  disbursed) plus an explicit unit test on `pv_factory`.
- Delta B is read-only surfacing; Delta C is frontend-only visibility. Low risk.
- No changes to the cash-disbursement math in `post_payment` (already
  deduction-aware and CI-verified).
