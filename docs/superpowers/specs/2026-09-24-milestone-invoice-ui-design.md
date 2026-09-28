# Milestone-as-Invoice UI (coding lines + Post Invoice) — retires Convert-to-IPC

**Date:** 2026-09-24
**Branch:** `feat/milestone-as-invoice`
**Status:** Approved — implementing

## Context

The milestone-as-invoice backend exists (`post-invoice` action →
`approve_and_invoice`; `MilestoneInvoiceLine` CRUD) but nothing in the UI wires
it — a completed milestone can only "Convert to IPC". This builds the UI so a
user adds appropriation/coding lines to a milestone and posts it as an invoice,
replacing the IPC conversion (unblocking IPC retirement).

Confirmed backend (recon):
- `POST /contracts/milestones/{id}/post-invoice/` (hyphen, milestone viewset,
  perm `CanApproveMilestone`), no body → `approve_and_invoice`. Requires **≥1**
  `MilestoneInvoiceLine` (else `400 "Add at least one appropriation line…"`);
  rejects already-INVOICED. Success `201 {invoice_number, total_amount, …}` →
  milestone `INVOICED`.
- `MilestoneInvoiceLine` CRUD: `/contracts/milestone-lines/?milestone={id}`,
  `IsAuthenticated`. Fields: `milestone`, `account` (Account FK), `account_code`
  /`account_name` (display), `appropriation` (Appropriation FK, optional),
  `description`, `amount`. Edit-locked once INVOICED (403).
- Status flow: PENDING →(start) IN_PROGRESS →(approve) COMPLETED →(post-invoice)
  INVOICED. Show the invoice flow at COMPLETED.
- Reusable Account picker: `makeAccountSearch` + `SearchableSelect`. No
  Appropriation picker (must build). Contract has an `appropriation` FK to
  default lines from.

**Decision (user):** per-line Appropriation picker, defaulting to the contract's
appropriation.

## Scope

### Backend
- Add `appropriation_code` / `appropriation_name` display fields to
  `MilestoneInvoiceLineSerializer` (read-only) so the editor shows the selection.
  No new endpoints.

### Frontend hooks (`useContracts.ts`)
- `usePostMilestoneInvoice(milestoneId)` → `POST /contracts/milestones/{id}/post-invoice/`
  (no body); invalidate `['contract', cid]`, `['contracts']`, `['contract-balance', cid]`.
- `useMilestoneLines(milestoneId)` → `GET /contracts/milestone-lines/?milestone=`.
- `useCreateMilestoneLine` → `POST /contracts/milestone-lines/`.
- `useDeleteMilestoneLine` → `DELETE /contracts/milestone-lines/{id}/`.

### Frontend components
- **`AppropriationSelect`** (new, small) — `SearchableSelect` fed by
  `GET /budget/appropriations/?status=ACTIVE&search=`, mapping to
  `{value:id, label:"<code/name>", sublabel:amount}`. Optional; defaults to the
  contract's appropriation.
- **`MilestoneInvoiceModal`** (new) — a coding-lines editor (mirrors
  `VendorInvoiceForm`'s grid): rows of Account (`SearchableSelect`, required) ·
  Appropriation (`AppropriationSelect`, default contract's) · Description ·
  Amount, with add/remove + running total. Lines persist via the milestone-lines
  CRUD (seed from `m.lines`). A **Post Invoice** primary action (disabled until
  ≥1 saved line) → `usePostMilestoneInvoice`; on success closes and the milestone
  flips to INVOICED. Errors surface via `formatServiceError`.

### `ContractDetail.tsx` MilestonesTab
- Replace the `COMPLETED && !ipc` **Convert to IPC** button with a **Post Invoice**
  button opening the modal. Remove `handleConvertToIPC` + `useConvertMilestoneToIPC`
  wiring (IPC *backend* stays — Phase 3).
- Add `lines?: MilestoneInvoiceLine[]` to the `MilestoneRow` type.

## Testing
- Backend: `MilestoneInvoiceLineSerializer` exposes `appropriation_code`/
  `appropriation_name` (null when no appropriation). The ≥1-line rule is already
  covered by `test_requires_appropriation_lines`.
- Frontend: tsc + Playwright — on a COMPLETED milestone, open the modal, add an
  account+amount line, Post Invoice → milestone INVOICED, accrual journal posted.

## Out of scope
- Removing the IPC backend / `convert-to-ipc` action (Phase 3).
- A full milestone detail page (the modal suffices).
