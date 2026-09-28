# Milestone → Invoice → Payment Sub-Lines on the Contract Page

**Date:** 2026-09-24
**Branch:** `feat/milestone-as-invoice`
**Status:** Approved — implementing

## Context

For contract tracking/history: on the contract detail page, once a milestone
(which becomes a `VendorInvoice` when approved) is **paid**, show its settling
payment(s) as sub-lines nested under the milestone row.

The milestone→invoice link is a **string convention** (`invoice_number =
{contract_number}/M{n}`, `reference = contract_number`) — no FK. Payments link
to the invoice via `PaymentAllocation` (`invoice.payment_allocations → .payment`);
`allocation.amount` is what was applied to that invoice.

**Decision (user):** show **posted** payments only.

## Scope

### Backend — `contracts/serializers.py` `MilestoneScheduleSerializer`
Two read-only `SerializerMethodField`s (mirroring the existing string-convention
resolvers `get_retention_withheld_open` / `sync_contract_paid`):

- **`invoice`** → the milestone's `VendorInvoice` (by `invoice_number`), or `null`:
  `{ id, invoice_number, status, total_amount, paid_amount, payable_now }`.
- **`payments`** → from that invoice, walk `payment_allocations.select_related('payment')`,
  keep only `payment.status == 'Posted'` (skip Void/soft-deleted), return per line:
  `{ payment_id, payment_number, payment_date, amount (= allocation.amount),
  status, is_advance }`, ordered by `payment_date`.

Add both to `Meta.fields` + `read_only_fields`.

**N+1 guard** — the link is a string, not an FK, so a naive method field is 1–2
queries per milestone. In `ContractViewSet.retrieve`, build a context map once:
`VendorInvoice.objects.filter(reference=contract_number)
.prefetch_related('payment_allocations__payment')` → `{invoice_number: invoice}`,
passed via serializer `context['milestone_invoice_map']`. The method fields read
the map and fall back to a single query when the context is absent (list views).

### Frontend — `frontend/src/features/contracts/ContractDetail.tsx` `MilestonesTab`
- Extend `MilestoneRow` with `invoice?: {...} | null` and `payments?: PaymentSubRow[]`.
- Wrap each milestone in a `<Fragment>`; after its `<tr>`, when `status ===
  'INVOICED'`, emit a nested `<tr><td colSpan={8}>` sub-row:
  - posted payments → indented lines `PAY-… · DD/MM/YYYY · ₦amount · Posted`,
    with an "Invoice …/M{n} · ₦paid of ₦total" header;
  - invoiced but none yet → subtle "Invoice posted — awaiting payment" hint.
- Rides the existing `useContract` payload (no new fetch); milestone/payment
  mutations already invalidate `['contract', id]`.

## Testing
- Backend test in `test_milestone_invoice.py` (CI DB tier): a milestone with a
  **posted** allocated payment → `payments` returns it; a **draft** allocation is
  excluded; `invoice` returns the link; no-payment milestone → empty `payments`.
- Frontend nesting is presentational → tsc + Playwright live check.

## Out of scope
- Draft/pending payment sub-lines (user chose posted-only).
- A dedicated milestone-payments endpoint (the serializer field suffices).
