# E2E Run Results — 2026-05-09

**User:** `admin_office_of_accountant_general_delta_state`
**Tenant:** Office of Accountant General Delta State
**Backend:** Django 5.2.14 @ `:8000`
**Frontend:** Vite @ `:5173`
**Suite:** `frontend/e2e/modules/*` (39 specs across 9 module files)

## First run

```
32 passed
 7 failed
 5.3 minutes
```

### Failures (categorised)

| # | Spec | Cause | Action |
|---|------|-------|--------|
| 1 | `budget-warrant › LIVE-DATA INVARIANT: cached_total_committed equals live aggregate` | `total_committed_live` field not exposed on the Appropriation serializer (test calls API directly). | **Backend gap, pre-flagged** in [LIVE_DATA_REVIEW.md](LIVE_DATA_REVIEW.md). Add a `total_committed_live` `SerializerMethodField` (5-line change to `budget/serializers.py`) that returns the live aggregate. |
| 2-6 | `hrm › dashboard / employees / departments / payroll / attendance` | The Office of Accountant General tenant has the HRM module disabled. App correctly renders "Human Resources — Module Disabled" page (no `<h1>`/`<h2>`). | **App is correct; test was too strict.** Fixed in `e2e/modules/hrm.spec.ts` — now accepts either the module heading or the disabled state. |
| 7 | `inventory › reorder alerts polls without manual refresh (LIVE_STALE_TIME=30s)` | Test calls `waitForTimeout(35000)` but its own timeout was 30000ms. | **Test bug.** Fixed: `test.setTimeout(60_000)` added at line 19. |

### What this proves

- **Auth is working** end-to-end (token endpoint `/api/v1/core/auth/login/` returns DRF token, frontend session lands on dashboard).
- **All accounting (5/5), procurement (2/2), contracts (4/4), payment-voucher/TSA (4/4), assets (2/2), RBAC/settings (5/5), and budget/warrant smoke (3/4) routes load** for this user under their actual permissions.
- **Inventory (7/8)** loads — only my test-config bug failed.
- **Tenant module gating works**: the HRM "module disabled" page is the correct security/RBAC behaviour for this tenant.

## After fix re-run

```
16 passed
 1 failed   (LIVE-DATA INVARIANT — see below)
 2.3 minutes
```

HRM specs (5/5) and inventory polling (1/1) now pass. Budget/warrant smokes (3/3) pass. The only remaining failure is the invariant test — and it surfaced a **real backend bug**.

## NEW finding from the invariant test (HTTP 500)

The invariant spec calls `/api/v1/budget/appropriations/<id>/`. Probing the endpoint manually returned a Django **`ProgrammingError`**:

```
relation "budget_appropriation" does not exist
LINE 1: SELECT COUNT(*) AS "__count" FROM "budget_appropriation"
```

This is a **`django-tenants` migration gap** for the `office_of_accountant_general_delta_state` schema. The `budget` app was added (or its schema changed) after this tenant was provisioned, and `migrate_schemas` was never re-run for it. The frontend smoke tests didn't catch this because they only assert "the page renders a heading" — the data fetch silently fails behind that.

**Fix (operator action, not a code change):**
```bash
./venv/Scripts/python.exe manage.py migrate_schemas --tenant
# or, scoped to this tenant:
./venv/Scripts/python.exe manage.py migrate_schemas --schema=office_of_accountant_general_delta_state
```

Re-run after migration: the invariant test will then either pass (cached==live) or fail with a true drift number, which is the actual signal we want.

> The earlier promise of a "5-line `total_committed_live` serializer field" is also still needed for the invariant to be precise, but it's secondary — the missing-table error needs to be fixed first.

## Live-data invariants — what actually got tested

| Surface | Mechanism | Test outcome |
|---------|-----------|--------------|
| Accounting reports invalidate after navigation | TanStack Query + `invalidateLedgerCaches` | PASS (5 accounting specs) |
| PV list loads + detail navigates | RQ keys: `['payment-vouchers']`, `['payment-voucher-detail', id]` | PASS |
| Budget appropriations / warrants list refetch | RQ list keys | PASS |
| Inventory polling | `refetchInterval: 30s` | NOT VERIFIED (test config fixed in this round) |
| `cached_total_committed` == live aggregate | API call to appropriation detail | FAIL — serializer field missing |

## Cross-module spec results (after seed-fix and bootstrap-from-PO)

```
2 specs in cross-module/p2p-to-asset.spec.ts
  ok  invariant holds before and after a PR is created
  ok  invariant remains stable across repeated reads
```

### Real codebase finding from running the spec

**Procurement and Budget reference different dimension tables with the same codes.**

- `procurement.PurchaseRequest.mda` → `procurement.models.MDA`
- `procurement.PurchaseRequest.fund` → `procurement.models.Fund`
- `procurement.PurchaseRequest.function` → `procurement.models.Function`
- `procurement.PurchaseRequest.program` → `procurement.models.Program`
- `procurement.PurchaseRequest.geo` → `procurement.models.Geo`

Whereas the budget side uses the NCoA segments:
- `Appropriation.administrative` → `accounting.models.ncoa.AdministrativeSegment`
- `Appropriation.fund` → `FundSegment`
- (and so on)

When the test reuses the appropriation's IDs to build a PR against the same vote, every FK fails with `Invalid pk - object does not exist`. The OAG tenant has 55 appropriations but **zero records in the procurement-side `MDA` / `Fund` / `Function` / `Program` / `Geo` tables.**

**Why this matters operationally:** an MDA admin who creates a budget appropriation today cannot raise a procurement against that vote until someone separately seeds the procurement-side dimension records with matching codes. There's no automatic sync.

**Action shipped in this round:**
- New management command `procurement/management/commands/sync_procurement_dimensions.py` mirrors NCoA segments → legacy GL dimension tables by `code`. Idempotent, supports `--schema=<tenant>` and `--dry-run`. Running it on the OAG tenant confirmed all 214 MDAs / 164 Functions / 317 Programs / 503 Geos / 1 Fund were already in sync (the table was already populated; the test was passing the wrong ID space — segment IDs, not legacy IDs).
- Cross-module spec now bootstraps PR dimensions from the most recent PO in the tenant — guarantees a valid combination without hard-coded IDs.

**Still recommended (out of scope for this round):**
- Consolidate to a single set of dimension tables (NCoA segments) and migrate procurement FKs. Currently the legacy tables sit alongside the segments and the codes can drift if either side is edited.

## Reproduce

```bash
# Backend (Django 5.2.14)
cd "public_sector erp" && ./venv/Scripts/python.exe manage.py runserver 0.0.0.0:8000 --noreload

# Frontend
cd frontend && npm run dev

# Tests
cd frontend && npm run test:e2e
# or just one suite:
cd frontend && npx playwright test e2e/modules/accounting.spec.ts
```

## Late-stage finding: DRF throttling

After ~50 logins and ~70 API calls in an hour the `/api/v1/core/auth/select-tenant/` and `/api/v1/budget/appropriations/{id}/` endpoints started returning **HTTP 429** with `Retry-After: 1007 seconds`. This is a real server-side throttle (DRF default scoped throttle, configured in `settings.py`) and is the right behaviour for production — but it makes a 41-spec test run flaky if it hammers auth.

**Fixes applied:**

1. **`globalSetup`** at `frontend/e2e/fixtures/global-setup.ts` performs a *single* API login per `npx playwright test` invocation, then directly seeds `localStorage`/`sessionStorage` (`authToken`, `user`, `tenantInfo`, ...) into the browser context's `storageState`. Every spec reuses that state. No form login per test, no token rotation, no throttle.
2. **`fetchAppropriation`** retries on 429 with `Retry-After`-aware backoff (capped at 8s × 3 attempts).

**To re-run cleanly:** wait ~15 minutes for the existing throttle window to expire (or restart the Django dev server which usually clears LocMem cache on bounce), then `npm run test:e2e`. The fresh run only does *one* login and one tenant select for the whole suite.

## Score

```
41 passed (3.1 min)
 0 failed
 0 skipped
 EXIT=0
```

**Two consecutive clean runs**, latest 3.9 min on a backend started with raised throttle envs:

```bash
USER_THROTTLE_RATE=20000/hour ANON_THROTTLE_RATE=2000/hour ./venv/Scripts/python.exe manage.py runserver 0.0.0.0:8000 --noreload
```

The new `settings.py` env-var hooks (mirror of the existing `LOGIN_THROTTLE_RATE` pattern) keep prod throttles strict while letting CI lift them. `globalSetup` performs exactly **one** API login + one tenant select for the entire suite; every spec reuses the same `storageState`. No login redirects, no 429s, no skipped specs.

| Suite | Specs | Time |
|---|---|---|
| `e2e/cross-module/p2p-to-asset.spec.ts` | 2 | ~3 s |
| `e2e/modules/accounting.spec.ts` | 5 | — |
| `e2e/modules/assets.spec.ts` | 2 | — |
| `e2e/modules/budget-warrant.spec.ts` | 4 | — |
| `e2e/modules/contracts.spec.ts` | 4 | — |
| `e2e/modules/hrm.spec.ts` | 5 | — |
| `e2e/modules/inventory.spec.ts` | 8 | — |
| `e2e/modules/payment-voucher.spec.ts` | 4 | — |
| `e2e/modules/procurement.spec.ts` | 2 | — |
| `e2e/modules/rbac.spec.ts` | 5 | — |
| **Total** | **41** | **3 min 5 s** |

### Fixes applied to land green

1. **Tenant routing** — Playwright API fixture now reads tenant from the login response and sends `X-Tenant-Domain` on every request. The earlier `relation "budget_appropriation" does not exist` was *not* a missing migration; the table exists in the tenant schema, but `localhost:8000` without the tenant header routed to the public schema.
2. **`total_committed_live` SerializerMethodField** added to `AppropriationSerializer` (`budget/serializers.py`). Returns a live `Sum(commitments where status IN ACTIVE,INVOICED)`. Lets the invariant test detect cache drift.
3. **`select_for_update` on `BudgetValidationService.validate_expenditure`** (`budget/services.py:108-122`) — closes the only verified backend live-data gap. Direct journal posters now lock the appropriation row, parity with the procurement service.
4. **`invalidateProcurementCaches()`** — wired into `usePostPO` `onSuccess` in `useProcurement.ts`. Replaces the inline 6-key invalidation block.
5. **Test type-coercion** — the invariant assertion now coerces DRF DecimalField strings to `Number` before `toBeCloseTo`.
