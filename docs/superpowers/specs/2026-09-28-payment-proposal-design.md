# Payment Proposal — unified approval-staged payment register (Sub-project A)

**Date:** 2026-09-28
**Status:** Design approved (brainstorming), ready for implementation plan
**Branch:** `feat/payment-proposal` (off `main`)

## 1. Goal

Make every outgoing payment flow through a single **Payment Proposal** stage that is
**approved before any cash moves**. Concretely:

1. Rename the user-facing "Payment Vouchers" surface to **"Payment Proposal"**.
2. Present a **unified register** of Payment Vouchers (PV) **and** Payment Documents (PD)
   with **status tabs**.
3. Stop Payment Documents from **posting directly**. A PD is submitted, routed through
   **multi-level workflow approval**, and — on approval — provisions a **Draft Outgoing
   Payment**. The **GL journal and cash-out happen only when that Payment is posted** in
   Outgoing Payments.

This is **Sub-project A**. Sub-project **B** (e-payment / gateway settlement — post to a
clearing GL and fire a real-time disbursement at Payment-post time) is designed and built
separately, on top of the seam this creates. See §11.

## 2. Decisions (from brainstorming)

- **Sequence:** A first, then B.
- **"Payment Proposal" =** a **unified read-side queue** of PVs + PDs (not a model merge).
- **List depth:** union list with **native** PV/PD detail + forms (no new shared detail view).
- **Approval:** **multi-level maker/checker** via the existing generic `workflow` engine
  (a deliberate shift from the current access-based SoD, which had no transaction-level
  maker/checker). PVs are already wired to the engine; **PDs get newly registered**.
- **PD → Outgoing Payment mechanism:** `Payment` gains a nullable `payment_document` FK
  (mirroring `payment_voucher`); `post_payment` **dispatches by source**.

## 3. Current architecture (what we build on)

- **PV** (`accounting/models/treasury.py:130` `PaymentVoucherGov`) already: approves via the
  `workflow` engine / the `approve` action, and on approval provisions a Draft `Payment` via
  `ensure_draft_payment_for_pv` (`accounting/services/pv_payment_provisioning.py:72`). The
  dispatch bridge is `accounting/signals/workflow_dispatch.py:225`
  (`auto_post_paymentvoucher_on_approval`).
- **Payment** (`accounting/models/receivables.py:134`): `status` Draft/Posted/Void,
  `payment_voucher` FK (PROTECT), `bank_account`, `total_amount` (NET cash-out),
  `document_number`; partial unique `uniq_live_payment_per_pv`. Posting action
  `post_payment` (`accounting/views/payables.py:1772`) posts DR-AP / CR-deductions / CR-bank
  and runs fiscal/warrant/budget/immutability controls; decrements bank + vendor.
- **PD** (`accounting/models/payment_document.py:42` `PaymentDocument`): an arbitrary
  balanced multi-line journal, `status` Draft/Posted/Void, posts its **own** journal directly
  via `post_payment_document` (`accounting/services/payment_document_posting.py`), independent
  of `Payment` / Outgoing Payments.
- **Workflow engine** (`workflow` app): `GlobalApprovalSettings`
  (`workflow/models.py:9`, modes Disabled/Optional/Required/Strict, per module key),
  ContentType-based approvals, `workflow/views.py` model registration +
  `_MODEL_TO_MODULE_KEY`, `_trigger_document_action` (sets `doc.status='Approved'` on
  completion), and the dispatch signal `document_approval_completed`.
- **Frontend:** `GenericListPage` (`frontend/src/components/GenericListPage.tsx`) already
  supports an optional `tabs` prop; the PV list (`frontend/src/pages/gov/index.tsx:1382`) and
  PD list (`frontend/src/features/accounting/ap/PaymentDocumentsList.tsx`) render separately
  today. Outgoing Payments list: `frontend/src/features/accounting/ap/OutgoingPaymentsPage.tsx`.

## 4. Unified status model + tabs

Both sources map onto a small **unified proposal status** used only for the register + tabs
(each source keeps its own native status field):

| Unified status | PV (`PaymentVoucherGov`) | PD (`PaymentDocument`) |
|---|---|---|
| **Proposed** | DRAFT, CHECKED, AUDITED | Draft, Pending Approval |
| **Approved** | APPROVED, SCHEDULED | Approved |
| **Paid** | PAID | Paid (see §6 — replaces the old direct "Posted") |
| **Void** | CANCELLED, REVERSED | Void |

Register tabs: **Proposed · Approved · Paid · Void** (default view = Proposed). "Pending
Approval" (an open workflow instance on a still-Proposed document) is shown as a badge within
the Proposed tab in v1; a dedicated tab is a later refinement.

## 5. Unified register (read-side union)

- **Backend:** a new read-only endpoint `GET /api/v1/accounting/payment-proposals/` that
  unions PVs + PDs into a common row shape and filters by unified `status` + optional
  `source` (`pv` | `pd`). Row shape: `{ source, id, number, date, payee_or_description,
  amount, native_status, unified_status, detail_path }`.
  - v1 merges the two querysets in Python, maps each to the common shape, sorts by date desc,
    and paginates in-memory. Volumes are modest (hundreds), so this is acceptable; a DB-level
    `UNION`/keyset pagination is a documented scaling follow-up.
  - `OrganizationFilterMixin`-equivalent MDA scoping is applied to each source before merge.
  - Reuses each model's existing serializer for the fields it needs; **no** new write paths.
- **Frontend:** rename the Sidebar entry "Payment Vouchers" → **"Payment Proposal"**
  (`Sidebar.tsx:147`) pointing at a new **unified register page** (route
  `/accounting/payment-proposals`). The page uses `GenericListPage` with the four status
  `tabs`, driving the union endpoint's `status` param. Each row's action opens its **native**
  detail (`/accounting/payment-vouchers/:id` or `/accounting/payment-documents/:id`). A **New**
  control offers "New Payment Voucher" and "New Payment Document". The standalone "Payment
  Documents" Sidebar entry is **removed** (folded into the register); its create/detail routes
  remain. The old PV list route can redirect to the register.
- **Display-only rename** also updates: `GovernmentDashboard.tsx:160` tile label,
  `pages/gov/index.tsx:1386/1406` (list title + "New" button), `PaymentVoucherForm.tsx:267-268`,
  `PaymentVoucherDetail.tsx` header/subtitle, `treasury.py:226-227` `verbose_name(_plural)`,
  and `workflow/models.py:20` module label. Routes, endpoints, model class names, and
  `voucher_number` are unchanged.

## 6. Payment Document lifecycle change

**PD stops posting its own journal directly.** New status set:
`Draft → Pending Approval → Approved → Paid`, plus `Void`.

- The PD form's **"Post & Pay"** action is replaced by **"Submit for approval"**, which sets
  `status = "Pending Approval"` and opens a workflow approval instance (§7). A Draft PD stays
  fully editable; a Pending/Approved/Paid PD is read-only (existing immutability guard extends
  to the new terminal states).
- **`post_payment_document` is retained but no longer called from the PD viewset.** Its
  journal-building core (`_validate_lines_and_bank`, `_resolve_vendor_only_accounts`,
  `_enforce_expense_budget_gates`, `_build_and_post_journal`, `_settle_vendor_and_bank`) is
  reused verbatim when the **Payment** is posted (§8). It requires the PD be in the
  **Approved** state (guard added) and flips it to **Paid** (renamed terminal; the current
  code path that set `"Posted"` now sets `"Paid"`).
- **Existing directly-posted PDs** (PD-000001..PD-000004 on `main`) are historical and
  immutable. A data migration maps their `status = "Posted"` → `"Paid"`; they already carry a
  journal and moved cash, so they appear under the **Paid** tab with no re-posting.
- The PD viewset's `post` action is removed; a `submit` action is added. `proposed_entries`
  (preview) is unchanged.

## 7. Multi-level approval (workflow engine) for PDs

- **Register `PaymentDocument`** with the `workflow` engine: add a module key (e.g.
  `PaymentDocument` → "Payment Documents") in `workflow/models.py`, register the model in
  `workflow/views.py` (model registration + `_MODEL_TO_MODULE_KEY`), so
  `GlobalApprovalSettings` can gate it (Disabled/Optional/Required/Strict), exactly as PVs are.
- **Submit** creates the approval instance; multi-level sign-off proceeds through the engine's
  existing UI. On **approval completion**, `_trigger_document_action` sets the PD
  `status = "Approved"`, and a **new dispatch receiver** in
  `accounting/signals/workflow_dispatch.py` (mirroring `auto_post_paymentvoucher_on_approval`)
  fires for `model_name == "paymentdocument"` + `action == "approve"` and calls
  `ensure_draft_payment_for_document(pd)`. Failure policy: log-only (approval not rolled back),
  matching the PV receiver.
- Rejection sets the PD back to `Draft` (editable) or `Void` per the engine's reject path
  (match PV behavior).
- PVs keep their existing engine wiring unchanged.

## 8. Provisioning + posting

**`ensure_draft_payment_for_document(pd, *, actor=None)`** (new, in
`accounting/services/pv_payment_provisioning.py` or a sibling module):

- Idempotent (one non-Void `Payment` per PD): `select_for_update` on the PD, reuse any
  existing non-Void `cash_payments`-equivalent, never a second, never mutate a Posted/Void one.
  Backed by a new partial unique constraint `uniq_live_payment_per_document`.
- Creates a **Draft** `Payment`: `total_amount = _bank_credit(pd.lines, pd.bank_account.gl_account_id)`
  (the PD's cash-out / net), `payment_document = pd`, `payment_voucher = None`,
  `bank_account = pd.bank_account`, `reference_number = pd.reference_number`,
  `document_number` from `TransactionSequence`, `payment_method = "Wire"`. No
  `PaymentAllocation` (PDs aren't invoice-based). No `transaction.atomic` inside (caller owns it).

**`Payment` model changes:**
- Add nullable `payment_document` FK → `accounting.PaymentDocument` (PROTECT,
  `related_name="cash_payments"`).
- `payment_voucher` becomes nullable-in-practice for PD-sourced payments (the serializer's
  `require_pv_before_payment` gate applies only to non-PD payments).
- Add a `CheckConstraint`: at most/least the intended one of `payment_voucher` /
  `payment_document` is set for a source-backed payment (exact rule fixed in the plan:
  a payment is either PV-sourced, PD-sourced, or a standalone direct payment — the constraint
  encodes "not both PV and PD").
- Add `uniq_live_payment_per_document` partial unique constraint (non-Void, non-deleted).

**`post_payment` dispatch** (`accounting/views/payables.py`):
- If `payment.payment_document_id` is set → **PD path**: require the PD is `Approved`; post the
  PD's **own balanced lines as-entered** (the bank is an explicit credit line in the PD, so the
  PD's `bank_account` is authoritative and the PD-sourced Payment's bank is **fixed from the PD,
  not operator-changeable** — unlike a PV-sourced Payment, where the operator picks the bank).
  Link the resulting `JournalHeader` to the Payment; set the PD `status = "Paid"`; set
  `payment.status = "Posted"`, `payment.total_amount = cash_out`. All
  existing PD controls run (fiscal period, expense-only appropriation + warrant gates,
  `_budget_checked` suppression, immutability, duplicate-posting, vendor sub-ledger, bank
  decrement).
- Else → existing PV/AP/advance paths unchanged.
- This is the **single cash-out event** and the exact seam sub-project B hooks to swap the
  bank-credit leg to a clearing GL and fire the gateway.

## 9. Data flow (end to end, PD)

```
Create PD (Draft, editable)
  → Submit for approval  → status Pending Approval + workflow instance opened
  → Multi-level approval completes
        → _trigger_document_action sets PD Approved
        → dispatch receiver → ensure_draft_payment_for_document(pd)
              → Draft Payment appears in Outgoing Payments (no GL yet)
  → Operator posts the Payment (Outgoing Payments)
        → post_payment (PD path): posts PD's balanced journal (DR settlement / CR bank),
          runs controls, decrements bank + vendor sub-ledger, links journal,
          PD → Paid, Payment → Posted   ← the single cash-out event
```

PV flow is unchanged except that it now surfaces in the unified register.

## 10. Controls, error handling, testing

- **Controls preserved (non-negotiable):** fiscal-period gate, expense-only appropriation +
  warrant gates with `_budget_checked` suppression on settlement debits, journal balance,
  immutability (posted PD/Payment), duplicate-posting, vendor sub-ledger symmetry
  (debit−credit), bank decrement by net. Nothing about the journal a PD posts changes — only
  **when** and **through which door** it posts.
- **Idempotency:** provisioning + the two live-uniqueness constraints prevent double Payments;
  `post_payment`'s existing already-Posted / terminal-status guards prevent double posting.
- **Error handling:** approval-completion side effects are log-only (never roll back an
  approval); posting errors return the domain message and leave the Payment Draft + PD Approved
  (nothing partially posted — the post is `@transaction.atomic`).
- **Testing (TDD, `--reuse-db`, posted-journal tests `transaction=True`):**
  1. PD submit → Pending Approval + workflow instance; approval completion → PD Approved + one
     Draft Payment (`payment_document` set, `total_amount` == cash-out), idempotent on re-fire.
  2. Post a PD-sourced Payment → posts the PD's exact balanced journal, PD → Paid,
     Payment → Posted, bank − net, vendor sub-ledger moved; controls fire (unbalanced /
     expense-without-appropriation / period-locked all blocked); non-vacuous checks.
  3. Payment source constraint: cannot set both `payment_voucher` and `payment_document`; live
     uniqueness prevents a second Payment per PD.
  4. Unified register endpoint: returns PVs + PDs under the right unified status/tab; MDA
     scoping respected; `source` filter works.
  5. Data migration: existing "Posted" PDs read as "Paid" and are not re-postable.
  - Frontend: rename strings present; register tabs filter; "New" offers both; Submit replaces
    Post & Pay; a PD-sourced Draft Payment posts from Outgoing Payments. tsc + build clean;
    live Playwright end-to-end.

## 11. Out of scope (Sub-project B — e-payment, designed separately)

Not in this spec, but this design deliberately creates the seam for it: at `post_payment`,
when a tenant's gateway (`TenantGatewaySetting`) is active and superadmin keys are configured,
the **bank-credit leg** posts to a **Gateway Settlement Clearing** GL instead of Bank and a
**real-time Remita disbursement** is fired; a webhook later posts DR Clearing / CR Bank (or
auto-reverses). Most of that machinery already exists on `feat/payment-gateways`
(`accounting/services/gateway_disbursement.py`, `superadmin/gateway_*`,
`/settings/payment-gateways`). Sub-project B will: merge/adapt that branch, **auto-fire on
post** (today it's a manual `disburse-via-gateway` action), seed `GATEWAY_SETTLEMENT_CLEARING`
in `DEFAULT_GL_ACCOUNTS`, build the superadmin key-entry tab, and add the "which settlement
account is used where" config view.

## 12. Risks / open items

- **Maker/checker shift:** introduces transaction-level multi-level approval where the project
  previously used access-based SoD only. Deliberate per the user; PVs already had the wiring.
- **Two-model union pagination:** in-memory merge is fine for current volumes; revisit for
  scale.
- **PD status-value migration:** existing "Posted" → "Paid" is a one-way data migration; must
  run per-tenant (django-tenants) and be idempotent.
- **`payment_voucher` nullability:** relaxing the PV-required rule for PD-sourced payments must
  not weaken it for normal PV/AP payments (constraint + serializer gate scoped by source).
