# Centralize AP — IPCs as first-class vendor invoices

**Date:** 2026-09-23
**Status:** Design for sign-off (brainstorming)

## Goal

Make a contract **IPC (Interim Payment Certificate)** behave exactly like an AP
vendor invoice: Contract ≈ PO, approved Milestone ≈ GRN, certified IPC ≈ a
posted vendor invoice that ages, matches, and is **paid through the one central
AP → Outgoing Payments flow**. This dissolves the whole "payment cascade / IPC
mark-paid" failure class and centralizes all AP in one pipeline.

## Current flow (as-built) — precise map

1. Milestone approved → **Convert to IPC** → IPC `SUBMITTED`.
2. IPC `SUBMITTED → Certify → CERTIFIER_REVIEWED → Approve → APPROVED`. On
   **Approve** (`IPCService.approve` → `_post_accrual_journal` + `_ensure_vendor_invoice`):
   - Posts the accrual **DR Expense / CR Vendor-AP-Recon** — real-time to the GL.
   - `ContractBalance.cumulative_gross_certified += this_certificate_gross`.
   - Creates a **`VendorInvoice`** (status `Posted`, `invoice_number = IPC ref`,
     `total_amount = gross − mobilization recovery − retention`) pointing at the
     **same** journal. → This invoice already appears in the **AP Invoices
     Register** (`/accounting/ap-invoices`), classified as a "Direct AP" row.
3. IPC `APPROVED → Raise Voucher` → creates a draft **`PaymentVoucherGov`**
   (`gross_amount = ipc.net_payable`, **`invoice_number` NOT set**) → IPC
   `VOUCHER_RAISED`.
4. PV → central payment: `ensure_draft_payment_for_pv` → draft `Payment` →
   operator posts it in Outgoing Payments → `post_payment`:
   - Posts the cash journal **DR AP / CR Cash** (net).
   - **Post-commit best-effort cascade:** flips IPC → `PAID` via
     `IPCService.mark_paid`, which bumps `ContractBalance.cumulative_gross_paid`
     (+= paid_gross; DB-trigger-guarded ≤ certified). If it fails (ceiling
     recheck / concurrency / SoD) → a **`PaymentCascadeFailure`** row + HTTP 207.
     The cash is already committed.
5. **Contract closure** (`ContractClosureService`) is hard-blocked unless
   `cumulative_gross_paid == cumulative_gross_certified` **and** no unresolved
   `PaymentCascadeFailure` for the contract's IPCs.

### Two defects this exposes

- **Split-brain paid tracking.** Two independent trackers — `VendorInvoice.paid_amount`
  (AP subledger) and `ContractBalance.cumulative_gross_paid` (contract ledger) —
  updated by two different steps that aren't atomic with the cash leg. When
  `mark_paid` fails post-commit, they diverge → the cascade-failure queue exists
  purely to mop this up.
- **Orphaned AP invoice (confirmed).** The IPC's PV carries **no `invoice_number`**,
  so the central payment's auto-allocation never links to the IPC's `VendorInvoice`.
  Its `paid_amount` is never updated — **every paid IPC still shows fully OPEN in
  the AP register.** The AP subledger is silently wrong for IPCs.

## Target — one AP pipeline

- Certify/Approve stays as-is (accrual + `VendorInvoice`, real-time). Good.
- **Pay the IPC's `VendorInvoice` through the standard Outgoing Payments flow**
  (allocate + post), so `paid_amount` / `balance_due` are correct and the invoice
  settles like any other.
- **Drive `cumulative_gross_paid` and IPC → `PAID` from that AP payment, inside
  the same atomic `post_payment` transaction** as the cash leg — not a post-commit
  cascade. Atomic ⇒ can't half-fail ⇒ no `PaymentCascadeFailure`.
- Retire the IPC-specific PV-raise + `mark_paid` cascade, the `PaymentCascadeFailure`
  model + reconciliation queue + signal + retry command, and the closure gate's
  cascade check (closure then gates simply on the IPC invoices being fully paid).

## Phased plan

**P0 — de-risk (done in this design):** verified the orphaned-invoice defect and
the split-tracker root cause. No open unknowns block P1.

**P1 — Pay IPCs as AP invoices (atomic paid-tracking).**
- Link the IPC settlement to its `VendorInvoice` so the payment allocates to it
  (set the PV/payment's `invoice_number` to the IPC ref, or allocate by IPC link).
- In `post_payment`, when a payment settles an IPC-origin invoice, update
  `cumulative_gross_paid` and flip IPC → `PAID` **within the same transaction**;
  on any guard failure the whole post rolls back (no cash without paid-tracking).
- Result: `VendorInvoice.paid_amount` correct (no more perpetually-open IPCs),
  `cumulative_gross_paid` consistent, zero cascade failures by construction.

**P2 — Retire the cascade machinery.**
- Remove `PaymentCascadeFailure` creation, the Payment Reconciliation Queue page +
  viewset + serializer + signal + `retry_payment_cascades` command, and the
  closure gate's cascade check. (This resolves the earlier "repurpose the queue"
  question — it's deleted, not repurposed.) Keep a data migration to drop/retire
  the model after confirming no open rows.

**P3 — Unify the UI.**
- Surface IPC invoices distinctly in the **AP Invoices Register** (add a
  "Contract IPC" source classification; today they fall into "Direct AP").
- Converge **`IPCDetail`** onto the **Invoice Verification** visual template:
  extract `InvoiceMatchingView`'s presentational building blocks (`PageHeader`
  with actions, `NextStepCard`, `ComparisonCard`/breakdown, `PostedGlEntries`)
  into a shared module and rebuild IPC detail on them — or route IPC review
  through the AP/verification surfaces. IPC stays reachable from Contract →
  Milestones (Convert to IPC) as today.

## REVISED DIRECTION (2026-09-23) — delete IPC, Milestone = invoice, retention = lien

The user chose a deeper simplification. **Delete the IPC layer entirely**; the
**Milestone becomes the invoice**. Contract carries amount + retention (% or ₦).

- **Milestone** gains **appropriation lines** (`MilestoneLine`: account/appropriation
  + amount). On **Approve** it posts, atomically and real-time:
  `DR Expense (per line) / CR Mobilization Advance (recovery) / CR Vendor-AP (gross − mob)`
  and creates the `VendorInvoice` (`total_amount = gross`), bumps
  `cumulative_gross_certified`. No IPC.
- **Retention is a LIEN, not a posting.** Nothing retention-specific is journaled
  at milestone approve OR at release. The milestone invoice is booked at **gross**;
  retention is a memo hold (`VendorInvoice.retention_withheld`, rolled into
  `ContractBalance.retention_held`) that **caps disbursement** at
  `total − paid − retention_withheld`. The held slice sits as a frozen open AP
  balance until released.
  - Worked example: contract ₦100M @ 5%. Milestone ₦20M → `DR Expense 20M / CR AP 20M`,
    retention lien ₦1M, payable now ₦19M. Pay 19M. **Release Retention** lifts the
    lien → pay the ₦1M. GL only ever saw expense, AP, and two cash payments.
- **Release Retention** button: zeroes the invoice's `retention_withheld`, bumps
  `ContractBalance.retention_released`; the slice then pays through the normal AP flow.
- **Payment** of milestone invoices runs through the central AP → Outgoing Payments
  flow; `cumulative_gross_paid` updates atomically in `post_payment` (no cascade).

**Phases:** P1 milestone-as-invoice (backend) → P2 retention (contract form % / ₦,
per-milestone lien, Release button) → P3 delete IPC + cascade/reconciliation-queue →
P4 UI (milestone lines form, milestone detail as invoice-verification, AP register).

**Retire** the current IPC accrual's `CR Retention Held` liability line and the
lump-sum `retention_reserve` model — replaced by the per-milestone lien above.

## Open decisions (superseded by REVISED DIRECTION above for retention)

1. **Retention release.** Recommendation: retention is still *held* at IPC time
   (net-of-retention invoice, CR Retention Payable), and **released later via a
   small "retention release" AP invoice** so the payout is also centralized in AP.
   Don't fold retention holding into the IPC invoice beyond today's net treatment.
   (User to confirm.)
2. **Mobilization advances** already flow as advance PVs and are netted into the
   IPC invoice as recovery — keep as-is.
3. **SoD.** `mark_paid` enforces payer ≠ certifier/approver/voucher-raiser. In the
   AP-payment model, SoD moves to the Payment post (access/role-based per PR #43 +
   `IsApprover('post')`). Preserve the IPC role separation via the payment-post
   permission set.

## Risks / notes

- The `ContractBalance` DB trigger enforces `cumulative_gross_paid ≤ cumulative_gross_certified`
  — P1's atomic update must respect it (it will, since the accrual/certify already
  moved certified up first).
- Historical paid IPCs currently have an orphaned open `VendorInvoice`; a one-off
  backfill may be needed to mark them paid so the AP register is correct.
- The PV/`ensure_draft_payment_for_pv` path is shared with non-IPC PVs; changes
  must not regress direct-invoice or advance payments.
</content>
