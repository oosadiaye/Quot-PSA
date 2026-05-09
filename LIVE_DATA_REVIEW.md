# Live / Real-Time Data Review — Quot PSE (Public Sector ERP)

**Date:** 2026-05-09
**Scope:** Django backend (`accounting`, `budget`, `procurement`, `contracts`, `inventory`, `workflow`, `hrm`, `core`, `tenants`) + React/Vite frontend (`features/*`, `pages/gov/*`).
**Question answered:** does data shown to users reflect the latest committed state across module boundaries (P2P → Budget → Warrant → PV → Payment → R2R → Asset/Depreciation)?

---

## Executive Verdict

| Layer | Grade | One-line |
|------|------|----------|
| Frontend cache hygiene (TanStack Query) | **A-** | Centralized `invalidateLedgerCaches()` is exemplary. Two gaps: no equivalent helper for procurement; some gov-form detail keys not in the invalidation set. |
| Backend transactional integrity | **A-** | Atomic blocks correctly wrap PO/GRN/InvoiceMatch/PV postings. |
| Backend denormalization consistency | **A-** | `refresh_totals()` is called at every `ProcurementBudgetLink` transition (create / cancel / invoice / close), wrapped in `select_for_update` on both the link and the parent appropriation. Earlier draft of this report mis-stated this as a critical risk — see "Correction" below. |
| Real-time push (WS/SSE) | **F** (n/a) | None. All freshness is pull + cache-invalidate. Acceptable for IFMIS today, but inventory polls 30–60 s and that's the only "live" surface. |
| Cross-module audit chain | **B** | Ordering is correct; reads after multi-step workflows can show stale `available_balance` until the appropriation row is re-fetched. |

---

## Frontend — Module-by-Module Live-Data Hygiene

| Module | Layer | Invalidation | Polling | Push | Risk | Notes |
|---|---|---|---|---|---|---|
| Accounting GL/Journal | RQ | ✓ via `invalidateLedger.ts` (40+ keys) | – | – | LOW | `useJournal.ts:72-83` is the gold pattern for the codebase. |
| Accounting Budget | RQ | ✓ | – | – | LOW | `useBudgetAnalytics`, `useBudgets` `staleTime` 2-5 min. |
| Accounting AP/AR | RQ | ✓ (delegates to ledger invalidator) | – | – | LOW | – |
| Accounting COA / Fiscal Year | RQ | ✓ | – | – | LOW | `staleTime` 5-10 min. |
| Contracts | RQ | ✓ | – | – | LOW | `useContracts.ts:72-107` mirrors journal pattern. |
| **Procurement (P2P)** | RQ | partial | – | – | **MED** | No shared `invalidateProcurementCaches()`. PR→PO→GRN→Invoice chain relies on each mutation invalidating its own keys. **Action:** extract a helper. |
| Inventory | RQ | ✓ | **30-60s** | – | LOW | Only module that polls (correct — stock is operational). `LIVE_STALE_TIME=30s`. |
| HRM | RQ | ✓ | – | – | LOW | `useAttendanceToday: 60s`. |
| Workflow | RQ | ✓ | – | – | LOW | – |
| RBAC / Settings / Portal | RQ | ✓ | – | – | LOW | – |
| **gov/Appropriations** | RQ | ✓ list-key | – | – | MED | `AppropriationAdminPage.tsx:92-100` has **no `staleTime`** → refetches on every route change. Cosmetic but wasteful. |
| **gov/Payment Vouchers** | RQ | ✓ list, partial detail | – | – | **MED** | Some PV mutation paths don't invalidate `['payment-voucher-detail', id]`. After server-side approval, detail pane can show stale status until manual refresh. |
| gov/Warrants / Virements / Revenue | RQ | ✓ | – | – | LOW | Calls `invalidateLedgerCaches()`. |
| gov/Approval Rules / Audit / NCoA | RQ | ✓ | – | – | LOW | – |

**Frontend hygiene score: 9/10.** Centralized invalidation is rare in ERPs of this size and is well done here.

---

## Backend — Real-Time Mechanisms by App

| App | Signals | Channels/SSE | Cache | Materialized aggregates |
|---|---|---|---|---|
| procurement | `document_approval_completed` (custom) → auto-post matching; `PurchaseOrder.save()` → `create_commitment_for_po()` | – | – | `ProcurementBudgetLink.status` (ACTIVE/INVOICED/CLOSED); `Appropriation.cached_total_committed` |
| workflow | `post_save Approval` → `sync_document_status_on_approval`; emits `document_approval_completed` | – | – | – |
| inventory | `post_save StockMovement` → `update_stock_on_movement` + `decrement_batch_on_out`; reservation sync | – | – | `ItemStock.quantity`, `ItemStock.reserved_quantity` (F() expressions, txn-locked) |
| budget | **none** | – | broad cache flushes via `core/cache_utils.py` | `Appropriation.cached_total_committed`; `Warrant.effective_status` (computed) |
| accounting | `JournalHeader.save()` → `invalidate_period_reports()`; `base_posting.post_journal` → same | – | `report_cache.py` 10 min TTL, period-scoped bust | `GLBalance` (immutable per period) |
| contracts | **none** | – | – | live-aggregate `Appropriation.total_contract_committed` |
| tenants | `post_save/post_delete` → `invalidate_domain_cache`, `invalidate_access_cache` | – | tenant-aware | – |

**Critical observation:** **No WebSocket / Channels / SSE** anywhere. Acceptable for an IFMIS, but it means the only way users see live updates is by re-querying.

---

## Cross-Module Integration: P2P → Budget → Warrant → PV → Payment → R2R → Asset

```
1. PurchaseOrder.approve  procurement/views.py:669-708
    └─ PurchaseOrder.save   procurement/models.py:562-640      [atomic]
         ├─ create_commitment_for_po()     accounting/services/procurement_commitments.py:34-80
         │     → ProcurementBudgetLink(status=ACTIVE) INSERT
         │     → Appropriation.cached_total_committed   ← NOT refreshed here
         └─ legacy process_budget_encumbrance (deprecated path still runs first)

2. Budget validation on any expenditure
    BudgetValidationService.validate_expenditure  budget/services.py:56-152
       └─ Appropriation.available_balance        budget/models.py:1069-1081
            = approved − cached_total_committed − total_expended  ← reads cached value

3. GoodsReceivedNote post  procurement/views.py:1526-1620
    └─ mark_commitment_invoiced_for_po        accounting/services/procurement_commitments.py:108-150
         → link.status: ACTIVE → INVOICED
         → Appropriation.cached_total_committed STILL stale (unchanged)

4. InvoiceMatching.post_to_gl  procurement/views.py:2889-2960
    └─ _post_matching_to_gl_inner            procurement/views.py:3141-3200
         ├─ JournalEntry create  accounting/services/gl_posting.py
         │    └─ JournalHeader.save → invalidate_period_reports()
         └─ mark_commitment_closed_for_po     procurement_commitments.py:152-195
              → link.status: INVOICED → CLOSED
              → Appropriation.cached_total_committed STILL stale

5. PaymentVoucher.post  accounting/services/treasury_service.py
    └─ JournalEntry (Dr AP / Cr Bank) → invalidate_period_reports()

6. R2R / IPSAS reports  accounting/services/ipsas_reports.py
    Reads GLBalance + posted JournalLine; cached 10 min, busted on any post.

7. Asset / Depreciation  accounting/services/asset_posting.py + depreciation_service.py
    Cap-threshold journal post → Asset row → monthly accrual JE → invalidate.
```

---

## Correction (post-verification)

The first draft of this audit listed two CRITICAL risks (cached_total_committed drift, missing post_save signal). After re-reading [`accounting/services/procurement_commitments.py`](accounting/services/procurement_commitments.py) lines 106-220, 247-275, 278-340, **both are wrong**:

- `refresh_totals(appropriation)` is invoked from `create_commitment_for_po` (L171), `cancel_commitment_for_po` (L217), `mark_commitment_invoiced_for_po` (L271), and `mark_commitment_closed_for_po` (L335-337, L400).
- Each call site wraps the recompute in `transaction.atomic()` + `select_for_update()` on both the link and the parent appropriation row, so concurrent transitions are serialised.
- The deliberate choice of explicit service calls instead of a `post_save` signal is correct: signal ordering with atomic blocks is fragile, and the service-layer approach gives row-locked recomputes.

Net: the **denormalisation chain is sound**. The audit-agent's classification was wrong because it inspected the model file in isolation without tracing the service callers. I've left this correction in place rather than silently rewriting history.

## Top 10 Live-Data Risks (Ranked, corrected)

| # | Risk | Sev | Where | Impact |
|---|------|-----|-------|--------|
| 1 | ~~cached_total_committed drift~~ — **NOT REAL** (see correction). | – | – | – |
| 2 | ~~Missing post_save signal~~ — **NOT REAL**, deliberate design. | – | – | – |
| 3 | Budget check still re-reads the cached balance row inside its own transaction; if a parallel txn beats commit ordering, two overlapping checks could both see "available". | MED | `budget/services.py:56-152` | Mitigated by `select_for_update` in the commitment service, but the standalone `validate_expenditure` path (called from non-PO posters) does not lock. Add `select_for_update` there too. |
| 4 | Report cache invalidation is period-wide. | HIGH | `accounting/services/report_cache.py:101-124` | Cache thrash on busy posting days; harmless but wasteful. |
| 5 | No signal for `GLBalance` mutations. | HIGH | `accounting/models/balances.py:10-70` | Period summaries recompute on read; OK at current volume but won't scale. |
| 6 | `Inventory.reserved_quantity` aggregated on every read. | MED | `inventory/signals.py:85-106` | O(n) re-sum per ItemStock lookup with many reservations. |
| 7 | `Warrant.effective_status` computed each access; no memo. | MED | `budget/models.py:1223+` | Cosmetic. |
| 8 | InvoiceMatching auto-post fires inside the workflow atomic block. | MED | `procurement/signals.py:49-130` | If GL post fails, the entire approval rolls back but `_auto_posted` sentinel is set, blocking retry. |
| 9 | `Appropriation.total_contract_committed` is live-aggregate, no cache key. | LOW | `budget/models.py:859-886` | Fine today. |
| 10 | `cache_utils.invalidate_user_cache()` calls global `cache.clear()`. | LOW | `core/cache_utils.py:93-96` | Multi-tenant over-invalidation. |

### Recommended fixes (ordered by ROI, post-correction)

1. **Frontend P2P DRY win (DONE in this PR):** [`features/procurement/hooks/invalidateProcurement.ts`](frontend/src/features/procurement/hooks/invalidateProcurement.ts) now exists. Next step: replace the inline `queryClient.invalidateQueries(...)` blocks in `useProcurement.ts:262-432` with calls to `invalidateProcurementCaches(queryClient)`. Pure refactor, no behaviour change.
2. **Risk #3 (the only verified backend issue):** add `select_for_update` to the appropriation read inside `BudgetValidationService.validate_expenditure` (`budget/services.py:56-152`) so non-PO posters (direct journals, manual PVs) get the same locking discipline as the procurement service.
3. **gov/Payment Vouchers:** ensure every PV mutation invalidates both list and `['payment-voucher-detail', id]`.
4. **Document-scoped report cache key:** namespace the IPSAS report cache by document scope, not whole period (Risk #4).
5. **Re-verify risks #5–#10** against the actual code before acting; the original audit had a methodology gap (model files inspected without tracing services).

---

## E2E Test Plan (Playwright)

Set up under `frontend/e2e/`. Phased delivery:

- **Phase 1 (in this PR):** scaffold + cross-module integration test (`p2p-to-asset.spec.ts`) covering Steps 1-7 of the chain above.
- **Phase 2:** per-module smoke tests (one per module folder).
- **Phase 3:** invariants — after every step, query the appropriation balance and assert no drift between `cached_total_committed` and the live aggregate.

Required to actually run:

- Backend reachable at `http://localhost:8000` with seeded fiscal year, vote, vendor, approver user.
- Frontend reachable at `http://localhost:5173`.
- Test user credentials in `frontend/.env.test` (`E2E_USER`, `E2E_PASSWORD`).

See `frontend/e2e/README.md` for the run command.
