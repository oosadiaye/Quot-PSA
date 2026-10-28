# Playwright E2E suite — Quot PSE

## Prerequisites

1. Backend running:  `python manage.py runserver 8000`
2. Frontend running: `npm run dev`  (5173)
3. Test credentials in environment or `.env.test`:
   - `E2E_USER` (default: `admin@example.com`)
   - `E2E_PASSWORD` (default: `Admin@1234`)
   - Optional: `E2E_BASE_URL` (default: `http://localhost:5173`)
4. Seed data assumed present:
   - One open fiscal year
   - One organisation / department
   - One Vote/Programme with an approved Appropriation > NGN 10,000,000
   - One active Vendor
   - One Bank Account with TSA mapping
   - The login user must have the role bundle: PROCUREMENT_OFFICER + BUDGET_OFFICER + ACCOUNTANT + APPROVER (or equivalent).

## Run

```bash
cd frontend

# all tests
npx playwright test

# single spec
npx playwright test e2e/cross-module/p2p-to-asset.spec.ts

# headed (watch the browser)
npx playwright test --headed

# show last HTML report
npx playwright show-report
```

## Mocked-API specs (no backend needed)

`e2e/mocked/` drives the real SPA in Chromium but answers every `/api/v1/**`
call from the test (`e2e/mocked/mockApi.ts`), with a seeded superuser session.
No backend, tenant, seed data or login — fast and deterministic, so they run
anywhere. They cover UI behaviour; backend rules are covered by pytest.

```bash
cd frontend
npm run test:e2e:mock                       # whole mocked suite
npx playwright test --config playwright.mock.config.ts e2e/mocked/gl-adopt.spec.ts

# use a system Chromium instead of Playwright's own download:
E2E_CHROMIUM_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome npm run test:e2e:mock
```

| Spec | Covers |
|---|---|
| `master-data-lookup.spec.ts` | NCoA MDA / Fund / Functional / Programme / Geographic create forms: inline "already exists" hint, save-time prompt, Use this one / Create anyway, exact-code collision, lookup failure |
| `master-data-lookup-more.spec.ts` | Chart of Accounts, inventory product, bank (TSA) account, vendor category, asset category |
| `vendor-lookup.spec.ts` | Vendor create form + CSV import skipping duplicates |
| `gl-adopt.spec.ts` | Journal and recurring-journal GL-coding check: warn → Use this account / Post anyway / Go back |

## Layout

```
e2e/
  fixtures/
    auth.ts          login helper, persisted storageState
    api.ts           direct REST helpers (seed/cleanup)
  modules/           per-module smoke tests
    accounting.spec.ts
    procurement.spec.ts
    contracts.spec.ts
    inventory.spec.ts
    budget-warrant.spec.ts
    payment-voucher.spec.ts
    assets.spec.ts
    rbac.spec.ts
  cross-module/
    p2p-to-asset.spec.ts   PR → PO → GRN → Invoice → PV → Payment → R2R → Asset
  invariants/
    appropriation-balance.spec.ts   asserts cached vs live total_committed match
```

## Live-data invariants

After every state change in the chain, `invariants/` specs hit
`/api/v1/budget/appropriations/<id>/` and assert
`cached_total_committed === total_committed_live` (the latter is exposed by the
serializer recompute path). This catches the **#1 risk** documented in
`LIVE_DATA_REVIEW.md`.
