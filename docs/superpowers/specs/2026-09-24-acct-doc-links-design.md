# "Acct Doc" links on contract milestones + payment sub-lines

**Date:** 2026-09-24
**Branch:** `feat/milestone-as-invoice`
**Status:** Approved — implementing

## Context

On the contract detail page each milestone (once invoiced) posts an accrual
journal (DR expense / CR vendor-AP) and each posted payment sub-line posts a
disbursement journal (DR AP / CR deductions / CR bank). Add a **"Acct Doc"**
link on each milestone row and each payment sub-line to open the GL journal
posted for it.

Recon: a self-fetching `JournalDetailModal` (`{id, onClose}` → `GET
/accounting/journals/:id/` → header + DR/CR lines) already backs the Mobilization
tab and Outgoing Payments. `VendorInvoice.journal_entry_id` and
`Payment.journal_entry_id` are confirmed FKs. So the contract page needs only the
journal **id** — the modal fetches the body.

## Scope

### Backend — `MilestoneScheduleSerializer` (`contracts/serializers.py`)
- `get_invoice` → add `journal_entry_id: inv.journal_entry_id` (milestone invoice
  accrual journal).
- `get_payments` → add `journal_entry_id: pay.journal_entry_id` per payment row
  (disbursement journal).
Both are free (FK id column on the already-prefetched row; no join, no N+1).

### Frontend — `ContractDetail.tsx`
- Extend `MilestonePaymentRow` and the `invoice` shape with
  `journal_entry_id?: number | null`.
- Import `JournalDetailModal`; add `viewJournalId` state + render the modal;
  thread `onViewJournal(id)` into `MilestonesTab`.
- Milestone row action cell: **"Acct Doc"** link when `m.invoice?.journal_entry_id`
  → opens the invoice accrual journal.
- Payment sub-line: **"Acct Doc"** link per payment (`p.journal_entry_id`) →
  opens that payment's journal.

### Testing
- Extend the serializer test to assert `journal_entry_id` on `invoice` and each
  `payment`.
- tsc + Playwright: open the journal modal from a milestone and from a payment.

## Out of scope
- A read-only `/accounting/journals/:id` route (none exists; modal is the
  established pattern).
