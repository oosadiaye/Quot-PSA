# E2E Test Findings — Tenant Module Sweep

**Tenant:** delta_state (Delta State Government)
**User:** tenantadmin (role: admin)
**Date:** 2026-04-24
**Scope:** Accounting, Budget, Procurement, Contracts, Supplier Payments, Bank Reconciliation (manual + auto-upload), Reports
**Rules:** Test-only pass — no code modifications during the sweep.

---

## Severity Legend
- **CRITICAL**: Page 500, crash, data loss risk, or broken core flow
- **HIGH**: Broken feature, missing data, 404 on linked route
- **MEDIUM**: UX issue, slow load, missing validation
- **LOW**: Cosmetic, nit, enhancement idea

---

`★ Insight ─────────────────────────────────────`
Three distinct failure patterns emerged across the sweep: (1) JSX shell/tag-nesting mismatches from a shared `<ListPageShell>` refactor that wasn't fully applied, (2) a value-vs-type import regression from a lucide-react upgrade, and (3) otherwise healthy list/form surfaces that render but were not exercisable end-to-end due to missing seed data for bank statements and supplier invoices. The JSX errors are especially dangerous because Vite's dynamic `import()` for code-split routes fails silently until a user navigates — CI type-check alone would not catch them unless the router eagerly imports or a build-time JSX validator runs on every page module.
`─────────────────────────────────────────────────`

---

## Findings

### CRITICAL — 1. `/accounting/data-quality` route crashes (Vite 500 on dynamic import)
- **File:** `frontend/src/pages/gov/DataQualityPage.tsx:302`
- **Symptom:** Parse error — `</main>` encountered where `</ListPageShell>` was expected. Vite returns 500 on the dynamic chunk; the React error boundary traps rendering for the whole SPA until a full page reload.
- **Root cause:** Shell refactor wrapped the page in `<ListPageShell>` at line 209 but left an inner `<main>` / `<div>` stack whose closing tag order no longer matches the shell. Closing `</ListPageShell>` is at line 332 with a stray `</main>` at 302.
- **Fix (no behavior change):** Audit tags between lines 209 and 332. Either remove the inner `<main>` wrapper (shell already renders `<main>`) or align open/close order. Do NOT introduce new wrappers.
- **Impact:** Data Quality dashboard is unreachable from the sidebar.

### CRITICAL — 2. Budget report routes crash (same JSX pattern)
- **File:** `frontend/src/pages/gov/reports/ExecutionReport.tsx:342`
- **Symptom:** Identical `</main>` vs `</ListPageShell>` mismatch. Blocks `/budget/execution-report`, and because the error boundary does not reset on SPA navigation, it cascades into `/budget/commitment-report` and `/budget/warrant-utilization` until a hard reload.
- **Likely siblings to audit (same refactor batch, same failure signature):**
  - `frontend/src/pages/gov/reports/CommitmentReport.tsx`
  - `frontend/src/pages/gov/reports/BudgetVsActualReport.tsx`
  - `frontend/src/pages/gov/reports/CashFlowStatementReport.tsx`
  - `frontend/src/pages/gov/reports/ChangesInNetAssetsReport.tsx`
  - `frontend/src/pages/gov/reports/NotesToFinancialStatementsReport.tsx`
  - `frontend/src/pages/gov/reports/FinancialPerformanceReport.tsx`
  - `frontend/src/pages/gov/reports/FinancialPositionReport.tsx`
  - `frontend/src/pages/gov/reports/FunctionalClassificationReport.tsx`
  - `frontend/src/pages/gov/reports/GeographicDistributionReport.tsx`
  - `frontend/src/pages/gov/reports/ProgrammePerformanceReport.tsx`
  - `frontend/src/pages/gov/reports/RevenuePerformanceReport.tsx`
  - `frontend/src/pages/gov/reports/ReportError.tsx`
- **Fix:** Grep for `<ListPageShell>` across `pages/gov/reports/` and verify the closing tag immediately matches the last opened JSX element. Remove the redundant inner `<main>` introduced before the shell refactor.

### CRITICAL — 3. `/contracts/dashboard` crashes on import
- **File:** `frontend/src/features/contracts/ContractsDashboard.tsx:1`
- **Symptom:** `import { FileText, AlertTriangle, Scale, TrendingUp, ArrowRight, LucideIcon } from 'lucide-react';` — `LucideIcon` is a TYPE-only export in the current lucide-react version. Runtime resolves to `undefined`, crashing the component tree.
- **Fix:** Split the import:
  ```ts
  import { FileText, AlertTriangle, Scale, TrendingUp, ArrowRight } from 'lucide-react';
  import type { LucideIcon } from 'lucide-react';
  ```
- **Impact:** Contracts dashboard landing unreachable; list/new/ipcs/variations routes still work.

---

### HIGH — 4. SPA error boundary does not reset on route change
- **Symptom:** Once any of the CRITICAL pages above throws, every subsequent in-app navigation shows the error boundary. Users must hard-reload.
- **Fix suggestion:** Key the `<ErrorBoundary>` on `location.pathname` so a navigation forces a remount, or add a "Try again" action that calls `resetErrorBoundary()` and triggers `navigate(0)`.
- **Impact:** One broken route contaminates the whole session UX until reload.

### HIGH — 5. Bank Reconciliation end-to-end not exercisable without seed data
- **Route:** `/accounting/bank-reconciliation`
- **UI confirmed rendering:** "Upload & Parse" button, file input (`.csv,.tsv,.txt`), TSA Account ID numeric input, Refresh button, manual match table.
- **Gap:** No seeded bank statement fixtures or TSA accounts for `delta_state`; unable to verify auto-match against the ledger. Manual entry UI present but no existing unreconciled transactions to pair.
- **Fix suggestion (non-breaking):** Add a management command `seed_demo_bank_reconciliation` mirroring `seed_demo_gl` / `seed_demo_registers` that creates a TSA account, a handful of GL payment entries, and a CSV fixture with a mix of matching/non-matching rows. Required to complete QA of this module.

### HIGH — 6. Supplier Payment flow not end-to-end testable without seeded invoices
- **Route:** `/accounting/payment-vouchers/new`
- **Form confirmed rendering (all fields present):** PAYMENT TYPE, invoice picker (MDA-filtered), SUPPLIER NAME, BANK, ACCOUNT NUMBER (NUBAN), SORT CODE, GROSS AMOUNT, TOTAL DEDUCTIONS, NET PAID, NARRATION, PO/CONTRACT REF, INVOICE NUMBER, INVOICE DATE, NOTES, "Add Deduction", "Raise Payment Request".
- **Gap:** Invoice picker returned an empty list for `delta_state`; cannot submit a real service-procurement or contract payment without a seeded supplier invoice + approved PO/contract. Deduction schedule submits but without a parent invoice the request is void.
- **Fix suggestion:** Extend `seed_demo_registers` (or add `seed_demo_supplier_payments`) to create 2 suppliers, 1 PO-backed invoice, 1 contract-backed IPC invoice, and their approvals so the voucher flow can be exercised end-to-end.

---

### MEDIUM — 7. Dynamic import failures produce no user-visible diagnostic
- **Observation:** When Vite serves a 500 on a chunk, the SPA flashes the error boundary but the default message does not surface the route name or a reload CTA. Browser console is the only hint.
- **Fix suggestion:** In the route-level `<Suspense fallback>` + `<ErrorBoundary fallbackRender>` wrapper, display the failed route and a "Reload" button.

### MEDIUM — 8. Login flow depends on bare `localhost` + tenant selector
- **Observation:** Subdomain routing (`delta.localhost:5173`) does not resolve in the preview browser environment. Login at `/login` requires the post-auth tenant-picker call to `/core/auth/select-tenant/`. Production DNS should be verified; if wildcard subdomains are expected, add a dev-env note to the README.
- **Fix suggestion:** Documentation-only — add `127.0.0.1 delta.localhost` guidance to `CONTRIBUTING.md` or `frontend/README.md`.

### MEDIUM — 9. Sidebar links to broken routes are not visually flagged
- **Observation:** Data Quality, Execution Report, Commitment Report entries in the sidebar route to the failing pages above. Users click → error boundary → confusion.
- **Fix suggestion:** Until CRITICAL #1–#3 are fixed, hide the affected menu items behind a feature flag, or short-circuit the route with a "Coming soon" placeholder page.

---

### LOW — 10. Payment voucher form lacks inline validation before submit
- Missing client-side check that GROSS - DEDUCTIONS == NET PAID before the "Raise Payment Request" POST; server likely rejects but a prompt would save round-trips.

### LOW — 11. Bank Reconciliation upload accepts `.txt` without format hint
- Accepting `.txt` alongside CSV/TSV is fine, but a tooltip describing the column schema (date, description, debit, credit, balance) would reduce malformed uploads.

### LOW — 12. Reports routes do not persist filter state in URL
- Refreshing a report page resets MDA / period / fund filters. Persisting in query params (already a pattern in other list pages) improves shareability.

---

## Confirmed Working Surfaces (no findings)

**Accounting**
- `/accounting/chart-of-accounts`
- `/accounting/trial-balance`
- `/accounting/balance-sheet`
- `/accounting/income-statement`
- `/accounting/cash-flow`
- `/accounting/bank-cash`
- `/accounting/payment-vouchers` (list)
- `/accounting/revenue-collections`
- `/accounting/tsa-accounts`
- `/accounting/bank-reconciliation` (UI only; see HIGH #5)
- All 4 IPSAS routes

**Budget**
- `/budget/appropriations`
- `/budget/warrants`
- `/budget/revenue-budget`

**Procurement**
- `/procurement/dashboard`, `/vendors`, `/requisitions`, `/orders`, `/grn`, `/matching`, `/vendor-performance`, `/returns`

**Contracts**
- `/contracts` (list), `/contracts/new`, `/contracts/ipcs`, `/contracts/variations`

**Auth / Shell**
- `/login` → tenant selection → tenant shell with sidebar + header renders cleanly for `tenantadmin`.

---

## Recommended Fix Order (lowest blast radius first)
1. **#3 Contracts dashboard** — one-line import type fix. Restores `/contracts/dashboard`.
2. **#1 Data Quality** and **#2 Budget reports (+ siblings)** — JSX tag audit in `pages/gov/reports/` and `DataQualityPage.tsx`. Mechanical.
3. **#4 ErrorBoundary reset on route change** — small resilience win that masks any future regression.
4. **#5 / #6 Seed data** — add management commands so QA and demos have end-to-end exercisable flows.
5. **#7–#9** polish.
6. **LOW** items as time permits.

---

## Test Artifacts
- Frontend dev server: `http://localhost:5173`
- Backend: `http://localhost:8000/api/v1`
- Tenant domain header: `X-Tenant-Domain: delta.localhost`
- Auth token: DRF token for `tenantadmin` on `delta_state` schema
- Browser automation: Claude_Preview MCP (Playwright-equivalent)
