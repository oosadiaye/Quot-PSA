# B6 Workflow Receivers — Implementation Plan (Remaining 10 types)

**Status:** Accounting receivers: 8 of 8 DONE; remaining: contract chain (6), HRM (2 deferred).

Receivers landed:
- `journalheader` — reference receiver (prior sprint)
- `warrant` — reference receiver (prior sprint)
- `appropriationvirement` — **DONE** (this sprint, `budget/signals.py`)
- `revenuebudget` — **DONE** (this sprint, `budget/signals.py`)
- `appropriation` — **DONE** (this sprint, `budget/signals.py`)
- `revenuecollection` — **DONE** (B6 partial, `accounting/signals/workflow_dispatch.py`; service at `accounting/services/revenue_collection_posting.py`)
- `paymentvoucher` / `paymentvouchergov` — **DONE** (B6 partial, `accounting/signals/workflow_dispatch.py`; service at `accounting/services/payment_voucher_posting.py`)
- `baddebtwriteoff` — **DONE** (B6 partial, `accounting/signals/workflow_dispatch.py`; service extracted to `accounting/services/bad_debt_writeoff_posting.py`; view refactored to call service)
- `vendoradvance` — **DONE** (B6 partial, `accounting/signals/workflow_dispatch.py`; calls `VendorAdvanceService.disburse()` with fields mapped from document; see parameter mapping note in receiver docstring)
- `tsareconciliation` — **DONE** (B6 partial, `accounting/signals/workflow_dispatch.py`; service extracted to `accounting/services/tsa_reconciliation_service.py`; view refactored to call service; MFA bypass documented in service docstring)
- `assetdisposal` — **DONE** (B6 final, `accounting/signals/workflow_dispatch.py`; calls `AssetPostingService.post_asset_disposal(disposal)`; receiver normalises `'Approved'` → `'APPROVED'` before service call — see status normalisation note in receiver docstring)
- `fixedasset` — **BLOCKED** (investigation finding: `apply_asset_capitalization(journal)` takes a JournalHeader not a FixedAsset; `FixedAssetViewSet.acquire` is ViewSet-bound and requires `request.data` for payment method; `FixedAsset` has no `capitalisation_journal_id` field. A dedicated `FixedAssetPostingService.capitalise(asset)` method must be added before this receiver can be wired. Deferred to a future sprint.)

This document covers the remaining types in priority order.

**Reference template:** `procurement/signals.py:auto_post_invoicematching_on_approval`
**Signal contract:** `workflow.signals.document_approval_completed(sender, approval, model_name, document, action)`
**Dispatch location:** `workflow/views.py:ApprovalViewSet._trigger_document_action` — runs inside `transaction.atomic()`

---

## Failure policy decision matrix

| Failure policy | When to use | Effect |
|---|---|---|
| **Log-only (don't re-raise)** | Side-effect is retryable via a UI button. Approval should commit so the workflow trail is preserved. | Approval stays "Approved". Error stamped/logged. Operator retries. |
| **Re-raise (rolls back approval)** | Side-effect is *load-bearing* — a half-applied state causes silent data corruption (e.g. budget balance inflation). | Approval reverts to Pending. Operator investigates and re-approves. |

---

## 1. `paymentvoucher` / `paymentvouchergov` — Post payment to GL

**Trigger:** `model_name in ('paymentvoucher', 'paymentvouchergov')` + `action='approve'`

**Service to call:**
- File: `accounting/views/treasury_revenue.py`
- Method: `PaymentVoucherViewSet._post_payment_journal(pv, user)` (or extract into a standalone service)
- What it does: builds IPSAS DR Expenditure / CR TSA Cash / CR deductions journal then calls `IPSASJournalService.post_journal()`
- Note: the existing view guard requires `pv.status == 'SCHEDULED'` before posting and sets `pv.status = 'PAID'` after. The workflow will have set `pv.status = 'Approved'` (workflow generic). The receiver must map `'Approved'` → post, NOT call the view guard directly. Extract `_post_payment_journal` into `accounting/services/payment_voucher_posting.py` so it can be called without a `self` (ViewSet) context.

**Idempotency check:** skip if `document.status in ('PAID', 'REVERSED')`

**Failure policy:** Log-only (mirror InvoiceMatching pattern). Approval commits; operator retries via "Post to GL" button. Add a `gl_post_error` migration to `PaymentVoucherGov` if you want UI-surfaced errors (currently no such field).

**Domain to place receiver:** `accounting/signals/workflow_dispatch.py` (already exists — add a second `if` block for this model_name, or a single receiver with a dispatch dict)

**Effort estimate:** 2 hours (service extraction + receiver + 4 tests)

---

## 2. `appropriation` — Flip to ACTIVE status

**Trigger:** `model_name='appropriation'` + `action='approve'`

**Service to call:**
- File: `budget/views.py`
- Method: `AppropriationViewSet.enact` action logic — sets `status='ACTIVE'`, stamps `enactment_date=today`, snapshots `original_amount`
- Extract into `budget/services.py:activate_appropriation(appropriation)` so it can be called without a ViewSet
- Note: B7's `Appropriation.clean()` validates NCoA bridges — call `.full_clean()` before `.save()` to surface missing bridges. The receiver should call `clean()` explicitly (or rely on the extracted service doing so) rather than raw `.save()`.

**Idempotency check:** skip if `document.status == 'ACTIVE'`

**Failure policy:** Re-raise. A half-enacted appropriation with no budget lines visible would silently block all expenditure for that MDA line. Better to hold the approval in Pending and let the MDA admin fix the bridge configuration.

**Domain to place receiver:** `budget/signals.py` (already exists from this sprint)

**Effort estimate:** 1.5 hours (service extraction + receiver + 3 tests)

---

## 3. `appropriationvirement` — Apply virement (move budget between lines)

**Trigger:** `model_name='appropriationvirement'` + `action='approve'`

**Service to call:**
- File: `budget/services_virement.py`
- Function: `approve_and_apply_virement(virement, user)` — `@transaction.atomic`, transitions `SUBMITTED → APPROVED → APPLIED`, moves `amount_approved` between source and target `Appropriation` rows using `select_for_update()`
- Call with `user=None` (or pass the `approval.initiated_by` user if available via `approval.created_by`)

**Idempotency check:** skip if `document.status == 'APPLIED'`

**Failure policy:** Re-raise. A partial virement (source deducted, target not credited) would corrupt available balances. The function itself is atomic but the receiver must propagate the failure.

**Domain to place receiver:** `budget/signals.py`

**Effort estimate:** 1 hour (service already exists, receiver is thin + 3 tests)

---

## 4. `revenuecollection` — Post revenue to GL

**Trigger:** `model_name='revenuecollection'` + `action='approve'`

**Service to call:**
- File: `accounting/views/treasury_revenue.py`
- Method: `RevenueCollectionViewSet._post_revenue_journal(collection, user)` — IPSAS DR Cash in TSA / CR Revenue, calls `IPSASJournalService.post_journal()`
- Extract into `accounting/services/revenue_posting.py:post_revenue_collection(collection, user=None)` to remove ViewSet dependency

**Idempotency check:** skip if `document.status in ('POSTED', 'RECONCILED')`

**Failure policy:** Log-only. Revenue collection already confirmed by cash receipt; GL post failure shouldn't reverse the confirmed collection. Operator retries via the "Post to GL" endpoint.

**Domain to place receiver:** `accounting/signals/workflow_dispatch.py`

**Effort estimate:** 2 hours (service extraction + receiver + 4 tests)

---

## 5. `revenuebudget` — Flip to ACTIVE status

**Trigger:** `model_name='revenuebudget'` + `action='approve'`

**Service to call:**
- File: `budget/views.py` — `RevenueBudgetViewSet` (no dedicated activate action exists)
- Action: simple `status='ACTIVE'` + `save(update_fields=['status', 'updated_at'])`
- No service extraction needed — the receiver directly flips the field (same pattern as the warrant receiver)

**Idempotency check:** skip if `document.status == 'ACTIVE'`

**Failure policy:** Re-raise. An ACTIVE revenue budget is a precondition for revenue collection against that line. Half-activation is not meaningful but a DB error should block the approval.

**Domain to place receiver:** `budget/signals.py`

**Effort estimate:** 1 hour (thin receiver + 3 tests)

---

## 6. `baddebtwriteoff` — Post write-off journal

**Trigger:** `model_name='baddebtwriteoff'` + `action='approve'`

**Service to call:**
- File: `accounting/views/workflows.py`
- Class: `BadDebtWriteOffViewSet`
- Action: `post_writeoff` (detail POST) — DR Allowance for Doubtful Accounts / CR Accounts Receivable
- Extract posting logic into `accounting/services/bad_debt_posting.py:post_bad_debt_writeoff(writeoff, user=None)`
- Idempotency guard in the view: rejects if `wo.status == 'POSTED'`; sets `wo.journal_id` on success

**Idempotency check:** skip if `document.status == 'POSTED'` or `document.journal_id` is set

**Failure policy:** Re-raise. A write-off approved but not posted leaves the receivable on the books while the approval says it was written off — silent AR overstatement.

**Domain to place receiver:** `accounting/signals/workflow_dispatch.py`

**Effort estimate:** 2 hours (service extraction + receiver + 4 tests)

---

## 7. `assetdisposal` — Derecognize asset + post disposal journal

**Trigger:** `model_name='assetdisposal'` + `action='approve'`

**Service to call:**
- File: `accounting/services/asset_posting.py`
- Class: `AssetPostingService`
- Method: `post_asset_disposal(disposal)` — preferred canonical path (already a service, no ViewSet dependency)
- Guard: raises `TransactionPostingError` if `disposal.status != 'APPROVED'` or `disposal.journal_id` already set
- Note: the workflow sets `disposal.status = 'Approved'` (title-case); the service guard checks `'APPROVED'` (upper-case). Receiver must normalise or the guard will reject it. Either (a) update the workflow approved_status dict in `workflow/views.py` to map `'assetdisposal' → 'APPROVED'` (out of scope for B6), or (b) set `disposal.status = 'APPROVED'` inside the receiver before calling the service

**Idempotency check:** skip if `document.journal_id` is already set

**Failure policy:** Re-raise. A disposal posted to GL but asset not derecognized (or vice versa) causes overstated fixed assets on the balance sheet.

**Domain to place receiver:** `accounting/signals/workflow_dispatch.py`

**Effort estimate:** 1.5 hours (thin wrapper needed for status normalisation + receiver + 4 tests)

**Known concern:** The status normalisation issue means this receiver requires coordination with workflow team to align status strings, or an adapter layer in the receiver itself.

---

## 8. `fixedasset` — Flip to capitalised status + post capitalisation journal

**Trigger:** `model_name='fixedasset'` + `action='approve'`

**Service to call:**
- File: `accounting/services/asset_capitalization.py`
- Function: `apply_asset_capitalization(journal)` — creates `FixedAsset` with `status='Active'` from a capex journal line
- However: for workflow-driven capitalisation the entry point is more likely `accounting/views/assets.py:FixedAssetViewSet.acquire` which posts a DR Asset / CR Capital Expenditure journal
- **Recommendation:** Investigate whether `fixedasset` workflow approval is for a *draft asset record* (pending capitalisation) or for a *capex payment request*. The service path differs between the two. This receiver may need a dedicated `FixedAssetPostingService.capitalise(asset)` method that wraps `apply_asset_capitalization`.

**Idempotency check:** skip if `document.status == 'Active'` or `document.created_from_journal_line_id` is set

**Failure policy:** Re-raise. An asset appearing as capitalised but without a GL entry causes fixed-asset register / balance sheet divergence.

**Domain to place receiver:** `accounting/signals/workflow_dispatch.py`

**Effort estimate:** 2–3 hours (service path investigation required first + receiver + 4 tests)

---

## 9. `vendoradvance` — Post advance (F-48 special-GL)

**Trigger:** `model_name='vendoradvance'` + `action='approve'`

**Service to call:**
- File: `accounting/services/vendor_advance.py`
- Class: `VendorAdvanceService`
- Method: `disburse(source_type, source_id, vendor, amount, posting_date, actor)` — DR Vendor-Advance Recon (Special GL) / CR Cash/TSA
- Note: `disburse` takes explicit parameters not a document instance. The receiver must extract these from `document` fields. Inspect `VendorAdvance` model fields to map correctly.

**Idempotency check:** `VendorAdvanceService.disburse` already guards via `(source_type, source_id)` uniqueness — raises `TransactionPostingError` if a `VendorAdvance` already exists for this source. Additionally skip if `document.status == 'CLEARED'`.

**Failure policy:** Re-raise. An advance approved but not disbursed (or double-disbursed) corrupts the vendor's special-GL advance balance and subsequent clearing entries.

**Domain to place receiver:** `accounting/signals/workflow_dispatch.py`

**Effort estimate:** 2 hours (parameter mapping work + receiver + 4 tests)

---

## 10. `tsareconciliation` — Finalise reconciliation

**Trigger:** `model_name='tsareconciliation'` + `action='approve'`

**Service to call:**
- File: `accounting/views/tsa_reconciliation_views.py`
- Class: `TSAReconciliationViewSet`
- Method: `complete` action logic — sets `recon.status='COMPLETED'`, flags matched `PaymentInstruction.is_reconciled=True`, `RevenueCollection.is_reconciled=True`, locks bank statement to `'COMPLETED'`
- Extract into `accounting/services/tsa_reconciliation_service.py:complete_reconciliation(recon)` to remove ViewSet + request dependency
- Note: the existing action requires `CanReconcileTSA` + `RequiresMFA` — the receiver bypasses these permission gates. Document this clearly in the receiver so future auditors know the workflow approval is the authorisation gate instead.

**Idempotency check:** skip if `document.status == 'COMPLETED'`

**Failure policy:** Re-raise. A half-completed reconciliation (some payments marked reconciled, bank statement not locked) causes duplicate reconciliation risk on the next cycle.

**Domain to place receiver:** `accounting/signals/workflow_dispatch.py`

**Effort estimate:** 2 hours (service extraction + receiver + 4 tests)

---

## 11. Contract chain (6 sub-types)

All services exist in `contracts/services/`. The workflow approval for contract documents may fire at different lifecycle points, so each needs investigation before implementing.

| Type | File | Service / Function | Idempotency | Failure policy |
|---|---|---|---|---|
| `contract` | `contracts/services/contract_activation.py` | `activate_contract(contract)` or equivalent — sets `contract.status='ACTIVE'` | `status == 'ACTIVE'` | Re-raise — inactive contract blocks all IPC / payment chains |
| `interimpaymentcertificate` | `contracts/services/ipc_service.py` | `IPCService.approve(ipc)` — posts accrual journal + creates `VendorInvoice`; then `IPCService.raise_voucher(ipc)` when PV is ready | `ipc.payment_voucher_id` already set (for voucher leg); `ipc.journal_id` set (for accrual leg) | Re-raise on accrual/voucher failure |
| `contractvariation` | `contracts/services/variation_service.py` | `VariationService.approve(variation)` — updates `ContractBalance.contract_ceiling` | `variation.status == 'APPROVED'` | Re-raise — budget ceiling update must be atomic |
| `milestoneschedule` | `contracts/services/ipc_service.py` | `IPCService.create_from_milestone(milestone)` — may be triggered when milestone is approved | Milestone already linked to an IPC | Log-only — milestone approval is advisory; IPC can be raised manually |
| `mobilizationpayment` | `contracts/services/mobilization_service.py` | `MobilizationService.issue_advance(contract)` — posts mobilization advance journal | `contract.mobilization_payment` already exists | Re-raise — double mobilization would create duplicate advance journal |
| `retentionrelease` | `contracts/services/retention_service.py` | Retention release service (practical or final completion leg) | `retention.status == 'RELEASED'` | Re-raise — double release inflates contractor payment |

**Cross-cutting concern:** Several IPC-chain services already call `IPSASJournalService.post_journal()` internally and are `@transaction.atomic`. The receiver wrapper is thin — just call the service and let its own atomic propagate.

**Effort estimate:** 1–2 hours per sub-type (services already exist; receivers are thin wrappers). The IPC type may need 3 hours due to the two-phase accrual + voucher split.

---

## 12. HRM (2 sub-types) — DEFER

**Recommendation: Do not implement until HRM PII hardening lands.**

The HRM module has open PII work (employee data masking, audit trail for sensitive HR actions). Adding a workflow-dispatch receiver that automatically transitions HR documents without user context would:
1. Bypass any PII-access logging that the HRM hardening work adds
2. Make `leaverequest` approvals trigger without the approving manager's identity being stamped on the leave record (the workflow `approval.created_by` is the submitter, not the approver)

| Type | File | Service | Idempotency | Deferred reason |
|---|---|---|---|---|
| `leaverequest` | `hrm/views.py:LeaveRequestViewSet.approve` | Status flip to `'Approved'` + notification | `status == 'Approved'` | PII hardening pending |
| `payrollrun` | `hrm/views.py:PayrollRunViewSet` + `hrm/services/payroll_runner.py` | `process → approve → post_to_gl` chain | `status == 'Paid'` or `journal_id` set | PII hardening pending; payroll GL post requires additional audit controls |

**Action:** Re-evaluate after HRM PII hardening milestone closes. At that point both receivers should be straightforward — the service paths exist and the idempotency guards are clear.

---

## Summary table

| # | Type | Domain file | Service exists? | Failure policy | Effort |
|---|---|---|---|---|---|
| 1 | paymentvoucher / paymentvouchergov | `accounting/signals/workflow_dispatch.py` | Yes (`accounting/services/payment_voucher_posting.py`) | Log-only | 2h | **DONE** |
| 2 | appropriation | `budget/signals.py` | Partial (extract from ViewSet) | Re-raise | 1.5h | **DONE** |
| 3 | appropriationvirement | `budget/signals.py` | Yes (`budget/services_virement.py`) | Re-raise | 1h | **DONE** |
| 4 | revenuecollection | `accounting/signals/workflow_dispatch.py` | Yes (`accounting/services/revenue_collection_posting.py`) | Log-only | 2h | **DONE** |
| 5 | revenuebudget | `budget/signals.py` | N/A (simple status flip) | Re-raise | 1h | **DONE** |
| 6 | baddebtwriteoff | `accounting/signals/workflow_dispatch.py` | Yes (`accounting/services/bad_debt_writeoff_posting.py`) | Re-raise | 2h | **DONE** |
| 7 | assetdisposal | `accounting/signals/workflow_dispatch.py` | Yes (`accounting/services/asset_posting.py`) | Re-raise | 1.5h | **DONE** |
| 8 | fixedasset | `accounting/signals/workflow_dispatch.py` | Partial — needs `FixedAssetPostingService.capitalise(asset)` (see BLOCKED note above) | Re-raise | 2–3h | **BLOCKED** |
| 9 | vendoradvance | `accounting/signals/workflow_dispatch.py` | Yes (`accounting/services/vendor_advance.py`) | Re-raise | 2h | **DONE** |
| 10 | tsareconciliation | `accounting/signals/workflow_dispatch.py` | Yes (`accounting/services/tsa_reconciliation_service.py`) | Re-raise | 2h | **DONE** |
| 11a | contract | `contracts/signals.py` (new) | Yes (contracts/services/) | Re-raise | 1.5h |
| 11b | interimpaymentcertificate | `contracts/signals.py` | Yes (ipc_service.py) | Re-raise | 3h |
| 11c | contractvariation | `contracts/signals.py` | Yes (variation_service.py) | Re-raise | 1h |
| 11d | milestoneschedule | `contracts/signals.py` | Yes (ipc_service.py) | Log-only | 1h |
| 11e | mobilizationpayment | `contracts/signals.py` | Yes (mobilization_service.py) | Re-raise | 1.5h |
| 11f | retentionrelease | `contracts/signals.py` | Yes (retention_service.py) | Re-raise | 1.5h |
| 12a | leaverequest | DEFERRED | — | — | — |
| 12b | payrollrun | DEFERRED | — | — | — |

**Total estimated effort (non-deferred):** ~26 hours across 4 sprints.

**Recommended sprint packaging:**
- Sprint 1: Types 3, 5 (thin budget receivers — services exist)
- Sprint 2: Types 7, 9 (accounting service-level, clean interfaces)
- Sprint 3: Types 1, 4, 10 (ViewSet service extractions — accounting)
- Sprint 4: Types 2, 6, 8 (ViewSet extractions with edge cases)
- Sprint 5: Types 11a–11f (contracts chain — separate module)
- Post-HRM-PII: Types 12a, 12b
