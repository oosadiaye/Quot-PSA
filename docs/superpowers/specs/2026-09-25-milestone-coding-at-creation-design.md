# Milestone coding at creation → AP invoice on approval

**Date:** 2026-09-25
**Branch:** `feat/milestone-as-invoice`
**Status:** Approved — implementing

## Context

The milestone-as-invoice epic moved contract milestones off the IPC path onto
the centralised-AP path (`approve_and_invoice` posts DR expense / CR vendor-AP).
The coding lines were captured in a separate **Post Invoice** modal *after*
approval. The product owner wants the milestone to appear in the **AP register
the moment it is approved**, and the GL/budget coding to be captured **at
milestone creation** (adopted from the contract), with the creation form
**beautified to match the invoice-creation UI**.

Confirmed with the user:
- **Multi-line coding grid** on the milestone (not a single line).
- **Approve auto-posts to AP** (no separate Post Invoice step).
- Coding lines **must sum to Scheduled Value** (milestone value = invoice total).
- **Approve requires coding lines** (a milestone with none cannot be approved).

## Scope

### Backend

1. **Nested writable coding lines on the milestone serializer**
   `MilestoneScheduleSerializer.lines` becomes **writable**. `create()` pops
   `lines` and creates `MilestoneInvoiceLine` rows in one atomic call; `update()`
   replaces them (only while status is not INVOICED — locked after). Each line:
   `account` (required), `appropriation` (optional), `description`, `amount > 0`.
   Validation: **≥1 line** and **Σ amount == scheduled_value** (tolerance 0.01),
   else `400` with a clear message. Editing lines on an INVOICED milestone → 403.

2. **`approve` becomes approve-and-post**
   `MilestoneScheduleViewSet.approve` calls
   `MilestoneInvoiceService.approve_and_invoice` (posts DR expense per line / CR
   vendor-AP gross, withholds the retention lien, materialises the
   `VendorInvoice`, bumps the contract balance, flips milestone → **INVOICED**).
   Accepts the existing optional `actual_completion_date` / `notes`. If the
   milestone has no coding lines → `400 "Add coding lines before approving"`.
   Already-INVOICED → `400`.

3. **Retire the post-invoice endpoint**
   The `post-invoice` action is removed (superseded by `approve`).
   `approve_and_invoice` (the service) stays — it is now the single posting path.
   The `convert-to-ipc` action and IPC models stay untouched (Phase 3), no UI.

### Frontend

4. **Beautified New Milestone form** (`ContractDetail.tsx` modal, extracted into a
   focused component if it grows large). Top fields unchanged (Description,
   Scheduled Value, Weight, Target Date with the native date input, Notes) plus a
   **coding grid** modelled on `VendorInvoiceForm`: rows of **Account**
   (`SearchableSelect` + `makeAccountSearch`) · **Appropriation**
   (`makeAppropriationSearch`) · **Description** · **Amount** (`AmountInput`),
   with add/remove and a **running total reconciled to Scheduled Value** (block
   submit until they match). The **first row defaults from the contract**:
   Account = the contract's GL (NCoA economic) account, Appropriation =
   `contract.appropriation` (label from `appropriation_label`), Amount =
   Scheduled Value. The milestone POST sends `lines` nested.

5. **Remove the Post Invoice flow**
   Delete `MilestoneInvoiceModal.tsx`, the **Post Invoice** button, and the
   `usePostMilestoneInvoice` / `useMilestoneLines` / `useCreateMilestoneLine` /
   `useDeleteMilestoneLine` hooks (superseded). The milestone actions become
   **Start → Approve** (Approve now posts to AP). The INVOICED sub-rows
   (invoice + payments + Acct Doc) stay.

### Data resolution note
The first line's default Account is the contract's GL. The contract serializer
exposes `ncoa_code_economic_id` + `ncoa_economic_code`/`ncoa_economic_name`.
Implementation must confirm `ncoa_code_economic_id` resolves to a postable
`Account` (the economic segment *is* the chart of accounts); if the id is a
segment id rather than an Account id, expose the resolved Account id/label on the
contract serializer for the default. If no GL is set on the contract, the first
row's Account is left blank for the user to pick.

## Testing

- **Backend** (`contracts/tests/test_milestone_invoice.py`):
  - create milestone with nested lines (persisted, linked);
  - Σ lines ≠ scheduled_value → 400; zero lines → 400;
  - `approve` posts the accrual (DR expense per line / CR AP), sets INVOICED,
    withholds retention, and the `VendorInvoice` is queryable in the AP register;
  - `approve` with no lines → 400; editing lines on INVOICED → 403.
- **Frontend**: tsc; the form renders the grid, defaults the first row from the
  contract, and blocks submit until the total reconciles.
- **Live Playwright**: create a milestone with coding → Approve → confirm it
  appears in the AP register (AP Invoices Register) as an open invoice, with the
  accrual journal posted.

## Out of scope
- Removing the IPC backend / `convert-to-ipc` (Phase 3).
- The retention lump-sum-vs-lien reconciliation (tracked separately).
- Editing a milestone's coding through a dedicated edit page (nested PATCH on the
  existing modal covers pre-approval edits).
