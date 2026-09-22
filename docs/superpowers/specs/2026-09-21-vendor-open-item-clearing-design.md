# Vendor Open-Item Clearing (Supplier History)

**Date:** 2026-09-21
**Status:** Approved (brainstorming)

## Goal

In the Supplier/Vendor Transaction History modal, let an operator work the
vendor's **open items** and settle them — SAP F-44 style open-item clearing:

1. **Three tabs** over the existing subledger rows: **Open Items**,
   **Cleared Items**, **All**.
2. A **Clear** action that matches available vendor credit against open
   invoices, either by **manual selection** or **auto-clear (one click, FIFO
   oldest-first)**.

## What "clear" means (accounting)

Clearing applies available vendor **credit** to **open invoices**
(`balance_due > 0`). Two credit sources, each routed to its correct engine:

| Credit source | Mechanism | GL effect |
|---|---|---|
| **Outstanding vendor advance** (`VendorAdvance`, OUTSTANDING/PARTIAL) | `VendorAdvanceService.clear(...)` | Posts **DR AP-recon / CR Vendor-Advance** (the advance obligation moves into AP), then the invoice's `paid_amount` is bumped so its `balance_due` drops. Net AP == what is still owed. This is the SAP down-payment clearing. |
| **Unapplied posted payment** (non-advance `Payment`, `total_amount − Σ allocations > 0`) | new `PaymentAllocation(payment, invoice, amount)` | **GL-neutral** — the payment already debited AP at post time; the allocation just records the link and bumps `paid_amount`. |

Both paths are idempotent-safe (never over-apply): an advance is capped at its
`amount_outstanding`, a payment at its unapplied remainder, and an invoice at
its `balance_due`.

## Backend

**Service** `accounting/services/vendor_open_items.py`:
- `open_items_for_vendor(vendor) -> {open_invoices, available_credits}` — read
  model (open invoices oldest-first; advances via
  `VendorAdvanceService.list_outstanding`; unapplied non-advance posted payments).
- `clear_open_items(vendor, *, invoice_ids=None, actor, posting_date=today) -> summary`
  — FIFO within a single `transaction.atomic`:
  - target invoices = open invoices (all, or restricted to `invoice_ids` for
    manual mode), oldest-first;
  - for each, draw from available credit (advances first, then payments),
    oldest-first, capped at `balance_due`;
  - advance draw → `VendorAdvanceService.clear(cleared_against_type='vendor_invoice',
    cleared_against_id=inv.id, cleared_against_reference=inv.invoice_number)` +
    `inv.paid_amount += amount`;
  - payment draw → `PaymentAllocation.objects.create(...)` + `inv.paid_amount += amount`;
  - flip invoice status → `Partially Paid` / `Paid`;
  - returns `{cleared: [...], total_cleared, remaining_open}`.

**Endpoint** on `PaymentViewSet` or a small dedicated view:
`POST /accounting/vendor-open-items/clear/` body `{vendor, invoice_ids?}` →
runs `clear_open_items`; `GET .../?vendor=` → `open_items_for_vendor`.

## Frontend (`VendorHistoryModal.tsx`)

- Add a tab strip: **Open Items** (invoices `balance_due>0` + unapplied
  credits) · **Cleared Items** (paid invoices, applied payments/returns) ·
  **All** (today's view). Filter the existing `transactions` list by `clearKey`.
- On the **Open Items** tab: row checkboxes (open invoices only) + two buttons:
  - **Clear selected** → `POST /clear/ {vendor, invoice_ids}`.
  - **Auto-clear all** → `POST /clear/ {vendor}` (no ids = all, FIFO).
- After success, invalidate `['vendor-history', vendorId]` so balances refresh.
- Show a short result toast ("Cleared ₦X across N invoices").

## Non-goals (v2)

- Purchase-return credits as a clearing source (no invoice-allocation model yet).
- Un-clear / reverse a clearing (advances already reverse via their own flow).
- Cross-vendor or partial-amount manual entry (v1 is FIFO full-draw per invoice).

## Tests (TDD)

- `test_vendor_open_item_clearing.py` (transaction=True for the advance GL path):
  - advance fully clears one open invoice → advance CLEARED, invoice Paid,
    contra JV posted (DR AP / CR Vendor-Advance), balanced;
  - advance partially clears (advance < invoice) → invoice Partially Paid,
    advance PARTIAL/consumed;
  - unapplied payment clears an invoice → `PaymentAllocation` created, invoice
    Paid, **no new journal** (GL-neutral);
  - auto-clear FIFO across several invoices; manual `invoice_ids` restricts scope;
  - never over-applies (caps at balance_due / outstanding / unapplied).
