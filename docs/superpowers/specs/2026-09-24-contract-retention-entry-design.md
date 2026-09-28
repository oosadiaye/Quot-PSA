# Contract Retention Entry (₦/%) + Lien-Release Button (P2)

**Date:** 2026-09-24
**Branch:** `feat/milestone-as-invoice`
**Status:** Approved — implementing

## Context

The milestone-as-invoice epic's contract-form slice. From the original ask:
"the amount and retention field added to the contract create/edit form in
percentage OR value, calculated and deducted from the contract, and a button to
release the retention."

Recon found most of it already exists — Amount (`original_sum`), Retention Rate
(%), the computed `retention_reserve` feeding `contract_ceiling`, and a Release
Retention button on the contract detail page. The real gaps: entering retention
as a **₦ value**, and a retention **summary** on the detail page. The user also
chose to **rewire the release button** to the centralised-AP lien path.

Settled retention model (from the AP-centralisation work): activation seeds
`ContractBalance.retention_held` lump-sum (`original_sum × retention_rate`); each
invoiced milestone withholds its slice as a `VendorInvoice.retention_withheld`
lien; releasing unfreezes the liens and bumps `retention_released`, posting
nothing.

## Decisions (user)

1. **Dual ₦/% input, store % only.** No new stored field, no migration.
2. **Rewire the Release button to path B** (`MilestoneInvoiceService.release_retention`).

## Scope

### 1. Dual ₦/% retention entry — `frontend/src/features/contracts/ContractForm.tsx`
Replace the single "Retention Rate (%)" input with a synced pair: a **%** field
and a **₦** field. Editing either recomputes the other from `original_sum`
(`rate = ₦/amount×100`, capped 0–20; `₦ = amount×rate/100`). Only
`retention_rate` is submitted. Live readout beneath: "Retention reserve ₦X ·
Contract ceiling ₦(amount − reserve)". Keep the existing DRAFT-only edit guard
(post-activation edits route to a Variation). Guard amount=0 (no ₦→% divide).

### 2. Retention summary — `frontend/src/features/contracts/ContractDetail.tsx`
Add a Retention panel: **Withheld (open liens) · Released · Reserve**.
- Withheld = live sum of open `VendorInvoice.retention_withheld` for the contract
  (the operative figure for path B) — exposed read-only from the backend as
  `retention_withheld_open`.
- Released = `ContractBalance.retention_released`.
- Reserve = `ContractBalance.retention_held` (lump-sum).

### 3. Backend — expose `retention_withheld_open`
Add a read-only field (sum of `VendorInvoice.filter(reference=contract_number,
retention_withheld__gt=0).aggregate(Sum)`) to the contract detail / balance
payload the detail page already fetches. Serializer-level; no model change.

### 4. Rewire Release Retention → path B
Point the button's hook at `POST /contracts/{id}/release-retention/`
(`ContractViewSet.release_retention` → `MilestoneInvoiceService.release_retention`).
Drop the 50%/remainder + Practical/Final-Completion gating (path A); **enable
when `retention_withheld_open > 0`**. Update Popconfirm copy: "Release the held
retention (₦X) — makes it payable, posts no journal."

## Testing
- Unit-test the ₦↔% conversion helper (20% cap, amount=0 guard, rounding).
- `retention_withheld_open` serializer test (open liens summed; 0 when none).
- Path-B release already covered by
  `test_release_retention_unfreezes_lien_with_no_posting`.
- Add all touched backend tests to the CI DB tier.

## Out of scope (Phase 3)
- Removing the now-unused RetentionService path (A) and its `RetentionRelease` UI.
- Reconciling the lump-sum `retention_held` seed with pure per-milestone accrual.
  P2 presents honest numbers (gates/summarises on open liens) without collapsing
  the two — see memory: retention_held-double-count.

## Rationale for key nuance
Rewiring to path B makes the per-invoice lien the operative retention, so
`held − released` is no longer meaningful (the seed stays at the full reserve
even when less was ever withheld). The summary therefore gates and displays on
**open liens**, not the reserve.
