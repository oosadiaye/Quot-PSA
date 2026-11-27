# Future Modules: Complete Integration and Full Playwright Verification

> **For agentic workers:** this is the *completion programme*. It sits under `2026-10-31-future-modules-integration.md` (the design: the "with or without" contract, seams, risks) and replaces its phase status with what is actually on `main` today. Phase T is written at task level. Every later phase gets its own task-level plan, written with `superpowers:writing-plans` when that phase starts, because each one touches different seams. Steps use checkbox (`- [ ]`) syntax.

**Goal:** every module on the All modules launcher is wired into the live application (ledger, budget, workflow, permissions, MDA scoping), can be switched on and off without harming anything else, and is proven by backend tests plus Playwright journeys that run in CI.

**Architecture:** unchanged from the 31 Oct plan: one-way dependency (new module → existing app), provenance as plain string columns, cross-module reactions through signals the existing apps *emit*, module switch (`ModuleEnabled`) with data kept when OFF. This plan adds a **test architecture** (section 3) and orders the remaining integration work by dependency (section 4).

**Tech stack:** Django + django-tenants + DRF, pytest `--reuse-db`; React 18 + TS, config-driven `ModuleCrudPage`; Playwright 1.59 (`frontend/e2e`), CI job `E2E (Playwright)` (PR #58).

---

## 1. The 15 modules, named as the launcher names them

The launcher list you pasted (Settings plus 14 single-page modules) maps to the apps like this. `integrations` is the fifteenth app; it has no tile in your list and stays deferred (decision D6 in the 31 Oct plan).

| Launcher tile | App | Entities (tabs) | Backend tests | Posts to GL | Workflow | MDA-scoped | Signals |
|---|---|---|---|---|---|---|---|
| Budget Preparation | `budget_prep` | 8 | 10 files | no | yes | **yes** | no |
| Establishment & Payroll | `personnel_budget` | 5 | 3 | no | yes | partly | no |
| Cash Planning | `cash_planning` | 6 | 3 | no | **no** | partly | 1 |
| Supplier Catalogue | `catalogue` | 4 | 3 | no | yes | no | no |
| e-Procurement | `egp` | 10 | 4 | no | yes | partly | no |
| Revenue Administration | `revenue_admin` | 9 | **0** | no | partly | no | no |
| Public Debt | `debt` | 7 | 4 | **yes** | no | no | no |
| Advances & Travel | `staff_advances` | 8 | **0** | **yes** | **no** | no | no |
| Fleet Management | `fleet` | 6 | **0** | no | no | partly | no |
| Legal & Risk | `legal` | 6 | **0** | no | no | no | no |
| Asset Declaration | `disclosure` | 5 | **0** | no | partly | no | no |
| Internal Audit | `internal_audit` | 8 | **0** | no | **no** | no | no |
| Fiscal Transparency | `transparency` | 5 | 2 | no | no | partly | no |
| Results & M&E | `results` | 8 | **0** | no | no | partly | no |
| (Settings, 12 menus) | existing | module switch lives here | n/a | n/a | n/a | n/a | n/a |

*Counts are from the tree on 2026-11-26 (tracked files, models, `ViewSet` classes; see Task A1 for the script that regenerates this table).*

### What the survey says

1. **Every app is on `main`**, in `TENANT_APPS`, with migrations, a config-driven register page and a generic Playwright walk (`e2e/modules/future-module-pages.spec.ts`, 227 lines) that checks tabs, fields, required fields and one create/edit/delete round trip.
2. **Phase 0 (module switch) is done**; **Phase 1A (supplier portal, catalogue, bids)** and **1B (e-Procurement award → draft PO)** are largely done, with dedicated Playwright specs; **Phase 2 is partial** (MTEF, CSV import, print).
3. **Most modules are islands.** Only `debt` and `staff_advances` touch the ledger; only `cash_planning` has a signal; MDA scoping is real only in `budget_prep`. The seams the 31 Oct plan describes (A–E tables) are mostly **not built**.
4. **Seven apps have no backend tests**: `revenue_admin`, `staff_advances`, `fleet`, `legal`, `disclosure`, `internal_audit`, `results`.
5. **Playwright proves pages render, not that modules integrate.** Only `p2p-to-asset` is a cross-module journey. No spec asserts module OFF/ON behaviour, role access, or MDA isolation for these modules.
6. **The E2E job in CI was not actually running the suite** until PR #58 (still open); every claim below that depends on CI depends on #58 landing.

"Integrated completely" therefore means closing the gaps in section 4 and then proving each with the tests in section 3.

---

## 2. Definition of done (per module)

A module is complete only when all ten hold. Each has a named test.

| # | Criterion | Proven by |
|---|---|---|
| 1 | CRUD for every entity works end to end, with validation errors shown, not 500s | register walk (exists) + API contract test |
| 2 | **Permissions**: each role sees/does only what it should; no module endpoint is reachable without the permission | RBAC matrix spec + pytest permission tests |
| 3 | **MDA scoping**: a user assigned to MDA A cannot read or write MDA B's records | pytest + Playwright two-user spec |
| 4 | **Workflow**: submit → approve → reject paths use the existing workflow engine and leave an audit trail | Playwright journey |
| 5 | **Ledger effect** (where the module should post): journals balance, post once, respect period lock and budget enforcement, are immutable after posting | pytest + Playwright + GL reconcile |
| 6 | **Seams** from the 31 Oct plan: the existing module is reacted to/read exactly as designed, idempotent on replay | pytest + cross-module Playwright |
| 7 | **Switch**: OFF ⇒ 403 `module_disabled`, tile and menu hidden, data kept; ON again ⇒ data back; *not installed* ⇒ app boots | three-run matrix |
| 8 | **Imports/exports/print** the module advertises work (CSV import template, print views) | Playwright download/print checks |
| 9 | **Presentation**: light + dark theme, phone width, no console errors, no 5xx, no horizontal overflow | sweep spec (Task T6) |
| 10 | **Docs**: one short user guide and the seam list kept in the module's README | review |

---

## 3. Test architecture (the Playwright side)

Today there is one generic spec and a few feature specs. The target is five layers, each run by a different CI trigger.

| Layer | What it proves | Where | Runs |
|---|---|---|---|
| **L1 Contract walk** | every tab, form, required field, linked-record search, 5xx watcher | `e2e/modules/future-module-pages.spec.ts` (extend) | every PR |
| **L2 Module journeys** | one happy path and one rejection path per module, through the real UI | `e2e/modules/<module>.spec.ts` | every PR (smoke subset) + nightly |
| **L3 Cross-module journeys** | the seams: data moving from one module into another and the ledger | `e2e/cross-module/*.spec.ts` | nightly + before merge of a phase |
| **L4 Switch and access matrix** | OFF/ON/data-kept, role matrix, MDA isolation | `e2e/matrix/*.spec.ts` | nightly |
| **L5 Presentation sweep** | all routes × light/dark × desktop/phone: no overflow, no console error, fonts, contrast (I already have a crawler that does this) | `e2e/sweep/routes.spec.ts` | nightly |

Supporting pieces, all small:

- **Fixtures** (`e2e/fixtures/`): add `modules.ts` (switch a module on/off for the test tenant through the API and restore it), `roles.ts` (create a user with a given role and MDA, return an authenticated page), `ledger.ts` (read a journal's lines and the trial balance by API for assertions).
- **Seed** (`seed_e2e_tenant`): enable all 15 modules, a second MDA, a second user per role, a fiscal year, appropriation, vendor, employee. Idempotent. (Already seeds user, FY, NCoA segments, appropriation, vendor.)
- **Rules:** assert on the **ledger/API outcome as well as the screen** for every money-moving step; no `waitForTimeout` (wait on a response or a visible state); every test cleans up what it creates; every test uses the `watch()` helper to fail on 5xx or uncaught exceptions.
- **Cost control:** CI runs L1 + the L2 smoke subset per PR; L3–L5 nightly and on phase PRs; shard with `--shard` once the suite passes 20 minutes.
- **The one-session login limit and API throttles** (hit during my sweep): tests share one stored session; the dev throttle is raised with `USER_THROTTLE_RATE` for local full runs.

---

## 4. Integration work, in dependency order

IDs (A1…E3) are the master-plan IDs. **Status** is as surveyed; Task A1 verifies each one before work starts.

### Wave 1: Budget cycle (corrected 2026-11-27: mostly built, so this wave is verification and the few real gaps)
`budget` (Appropriation, Warrant, Virement, Amendment, RevenueBudget) was already built and is **not** touched. The modules around it were checked in code:

| ID | Module | Already on `main` (code, UI and tests) | What is left |
|---|---|---|---|
| B1 | budget_prep → `Appropriation` | `services/incorporation.py` (idempotent on `source_module` + `source_reference`), `/incorporate` endpoint, `BudgetHandoff.tsx`, 3 test files | a Playwright journey; confirm the draft then activates through the unchanged enactment flow |
| B2 | adopt actuals | `services/adoption.py`, `/adoption-preview` and `/adopt-actuals`, UI, 2 test files | a Playwright journey; reproduce adopted figures from the GL to the kobo |
| B3 | personnel_budget | 4 models, `PayrollFunding.tsx`; **payroll gate is hooked** in `accounting/services/payroll_posting.py` with its own switch tests in `accounting/tests` | `personnel_budget` has **no tests of its own** (`conftest` only); forecast-vs-payroll-runs report to confirm |
| B4 | cash_planning | `WarrantRecommendation` generate / accept / reject / **convert to a real `Warrant`** (`warrants.py`), `WarrantPlanning.tsx`, `test_warrants.py` | debt service feeding the cash plan (not found); Playwright journey |
| B5 | calendar, supplementary | calendar service and `/upcoming`, `/supplementary-report`, tests | revenue forecast → `RevenueBudget` (v) and results ↔ budget lines (iv): confirm, likely not built |

So Wave 1 is: write the missing tests (personnel_budget backend, the budget-to-cash Playwright journey), and check three links (debt service to cash plan, revenue forecast to revenue budget, results to budget lines). It is much smaller than the table in section 1 implied.

### Waves 2 to 5, checked against the code on 2026-11-27

"Built" = code + screen/API + tests. "Model only" = tables exist, no behaviour. "Not built" = nothing beyond a docstring that states the intent.

#### Wave 2: Procurement completion (mostly built)
| ID | Module | Built | Left |
|---|---|---|---|
| A1 | catalogue | catalogue, items, **price history**, `valid_to` expiry, supplier price proposals through the portal (`portal_service.py`), price hint on the PO line | Playwright journey for the hint (one exists: `catalogue-hint.spec.ts`); expiry handling on the line |
| A2 | supplier portal | portal backend, login, bids, `VendorBankChangeRequest` model | confirm the bank-detail change is **approved by procurement** before it applies (fraud control) and add the negative test |
| A3 | egp | tender, sealed bids, opening, ranking, **award → draft PO** (`awarding.py`, `bidding.py`, `sealed.py`) | **threshold routing and the Certificate of No Objection gate are model only**: the code names them in a docstring but never uses them; contract creation on award |

#### Wave 3: Revenue and treasury (largely not built)
| ID | Module | Built | Left |
|---|---|---|---|
| C1 | revenue_admin | 8 models, register screens | **Not built:** no service, no signal, no collection → arrears reduction, no assessments/billing run, demand notices, enforcement or clearance logic; **0 tests** |
| C2 | debt | `gl.py` + `services.py` (drawdown, reclass, coupon posting), `DebtPosition.tsx`, 2 test files | debt service feeding the cash plan is a **docstring only**, not built |
| C3 | staff_advances | `services.py` posts to the GL | **No workflow, no retirement flow, no payroll recovery** (nothing in `hrm` or payroll posting references advances); no UI beyond the register; **0 tests** |

#### Wave 4: Assets, people, risk, assurance (models only)
| ID | Module | Built | Left |
|---|---|---|---|
| D1 | fleet | `Vehicle` has a real one-to-one to `accounting.FixedAsset` | no services: fuel/mileage logic, maintenance cost to expense or capitalise through the asset flow; **0 tests** |
| D2 | legal | case register and a flag "raise the IPSAS 19 provision" | **no link to `Provision` / `ContingentLiability` is built** (docstring only); **0 tests** |
| D3 | disclosure (Asset Declaration) | declaration records | cycles, access log and workflow behaviour; **0 tests** |
| D4 | internal_audit | universe, plan, engagement, working papers, findings, follow-up, and a `ContinuousAuditRule` model | **no rule engine**: nothing runs a rule or raises a finding; the read-only guarantee test is needed from day one; **0 tests** |

#### Wave 5: Publication and performance
| ID | Module | Built | Left |
|---|---|---|---|
| E1 | transparency | publication policy, **public serializers/views/urls** (gated backend), 1 test file | confirm the explicit publish action and redaction; a Playwright spec asserting the public payload only ever holds published fields |
| E2 | results | 7 models; the programme link to `ProgrammeSegment` **is a real foreign key** | no services (indicator actuals, performance reports); **0 tests** |

**What this changes:** Waves 1 and 2 are mostly verification and a handful of gaps. **Waves 3 to 5 are where the real building is**, because six modules (revenue admin, staff advances, fleet, legal, disclosure, internal audit) are registers with no behaviour yet and no tests. Phase T (the test harness) is still the right first step, because it makes every later change provable.

### Wave 6: Hardening and rollout
Full three-run matrix on all modules; role and MDA matrix; pricing catalogue; user guides; migration rehearsal on a copy of the Delta State tenant; rollback runbook; the orphaned `integrations` schema decision.

---

## 5. Phases and exit criteria

| Phase | Content | Exit (all proven in CI) |
|---|---|---|
| **T: Test foundation** (task level below) | audit, fixtures, seed, CI wiring, sweep, switch/role matrix harness, direction guard | suite green in CI on `main`; every module has OFF/ON and role cases; harness ready for waves |
| **W1** Budget cycle (verification + 3 link checks) | B1–B5 | a submission incorporates to draft appropriations that activate through the *unchanged* enactment flow; adopted figures reproduce from the GL to the kobo; budget boots with the three apps absent |
| **W2** Procurement completion | A1–A3 | vendor sees only own data (negative tests); an award produces a PO that passes the existing approval, GRN and invoice match untouched |
| **W3** Revenue and treasury | C1–C3 | posted revenue reduces arrears once on replay; debt GL tests carried over; advance recovery opt-in only |
| **W4** Assets, people, risk, audit | D1–D4 | audit rules cannot write to the ledger (test); a case links to a provision; a vehicle capitalises through the asset flow |
| **W5** Publication and performance | E1–E2 | unpublished or redacted fields never leave the tenant (public-portal spec asserts payloads) |
| **W6** Hardening | section 4, wave 6 | rehearsal on a tenant copy passes; runbook reviewed |

Each wave ends as one PR per module behind the switch, default OFF for existing tenants, with its L2 and L3 specs green.

---

## 6. Phase T: test foundation (task level)

**Files**

- Create: `docs/superpowers/plans/audit/2026-11-26-module-matrix.md` (generated)
- Create: `scripts/module_matrix.py`
- Create: `frontend/e2e/fixtures/modules.ts`, `frontend/e2e/fixtures/roles.ts`, `frontend/e2e/fixtures/ledger.ts`
- Create: `frontend/e2e/matrix/module-switch.spec.ts`, `frontend/e2e/matrix/rbac-modules.spec.ts`
- Create: `frontend/e2e/sweep/routes.spec.ts`
- Create: `tests/test_module_direction_guard.py`
- Modify: `core/management/commands/seed_e2e_tenant.py` (enable modules, second MDA, role users)
- Modify: `.github/workflows/ci.yml` (nightly job and shards)
- Test: the files above are tests

### Task A1: Regenerate the status matrix from the code

- [ ] **Step 1: Write `scripts/module_matrix.py`**

```python
"""Print the per-module wiring matrix used in docs/superpowers/plans (tracked files only)."""
import subprocess

APPS = ["budget_prep", "personnel_budget", "cash_planning", "catalogue", "egp", "revenue_admin", "debt",
        "staff_advances", "fleet", "legal", "disclosure", "internal_audit", "transparency", "results", "integrations"]
MARKS = {
    "gl": ("JournalHeader", "JournalLine", "post_journal"),
    "workflow": ("workflow", "approval"),
    "mda": ("mda", "administrative"),
    "signals": ("receiver", "signals"),
}


def tracked(app: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", app], capture_output=True, text=True, check=True).stdout.split()
    return [p for p in out if p.endswith(".py") and "/migrations/" not in p]


def has(path: str, words: tuple[str, ...]) -> bool:
    try:
        text = open(path, encoding="utf-8").read().lower()
    except OSError:
        return False
    return any(w.lower() in text for w in words)


def main() -> None:
    print(f"{'app':18}{'tests':>6}" + "".join(f"{k:>10}" for k in MARKS))
    for app in APPS:
        files = tracked(app)
        tests = sum(1 for f in files if "/tests/" in f or "test_" in f)
        row = "".join(f"{sum(has(f, w) for f in files if '/tests/' not in f):>10}" for w in MARKS.values())
        print(f"{app:18}{tests:>6}{row}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it** — `venv/Scripts/python.exe scripts/module_matrix.py > docs/superpowers/plans/audit/2026-11-26-module-matrix.md`. Expected: 15 rows; `debt` and `staff_advances` show GL > 0; seven apps show tests = 0.
- [ ] **Step 3: For each ID in section 4 marked "verify" (B1, A3), open the code and set the status to done / partial / not built in this plan.** Commit: `docs: module wiring matrix and verified status`.

### Task A2: One-way dependency guard (pytest)

- [ ] **Step 1: Write the failing test** `tests/test_module_direction_guard.py`

```python
"""Existing apps must never import the future-module apps (the 'with or without' contract, rule 1)."""
import pathlib
import re

FUTURE = ["budget_prep", "personnel_budget", "cash_planning", "catalogue", "egp", "revenue_admin", "debt",
          "staff_advances", "fleet", "legal", "disclosure", "internal_audit", "transparency", "results", "integrations"]
EXISTING = ["budget", "procurement", "accounting", "hrm", "contracts", "inventory"]
ROOT = pathlib.Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"^\s*(?:from|import)\s+(?:%s)\b" % "|".join(FUTURE), re.M)


def test_existing_apps_do_not_import_future_modules():
    offenders = []
    for app in EXISTING:
        for path in (ROOT / app).rglob("*.py"):
            parts = set(path.parts)
            if "migrations" in parts or "tests" in parts or "venv" in parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if PATTERN.search(text):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"existing apps import future modules: {offenders}"
```

- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests/test_module_direction_guard.py -q`. Expected: PASS if the contract already holds, otherwise the failure names every offender; **fix each offender by turning the import into a signal or a string reference, never by loosening the test.**
- [ ] **Step 3: Commit** `test: guard the one-way dependency between existing and future modules`.

### Task A3: Fixtures for switching modules, roles and reading the ledger

- [ ] **Step 1: Find the per-tenant switch endpoint**: `grep -n "module" superadmin/urls.py tenants/urls.py` (the tenant API for the current state is `tenants/enabled-modules/`; the toggle is under `superadmin/modules/`). Record the exact path and payload in the fixture's header comment.
- [ ] **Step 2: Write `frontend/e2e/fixtures/modules.ts`**

```ts
import type { APIRequestContext } from '@playwright/test';

/** Keys of modules the test tenant has on, as the app itself reports them. */
export async function enabledModules(api: APIRequestContext): Promise<string[]> {
  const res = await api.get('/api/v1/tenants/enabled-modules/');
  if (!res.ok()) throw new Error(`enabled-modules answered ${res.status()}`);
  const body = await res.json();
  return (body.modules ?? body.enabled ?? body) as string[];
}

/**
 * Turn one module off (or on) for the test tenant, run `body`, then put the original state back, even if `body` throws.
 * `setModule` is the single place that knows the switch endpoint found in Task A3 step 1.
 */
export async function withModuleState<T>(
  api: APIRequestContext,
  key: string,
  on: boolean,
  setModule: (api: APIRequestContext, key: string, on: boolean) => Promise<void>,
  body: () => Promise<T>,
): Promise<T> {
  const before = (await enabledModules(api)).includes(key);
  await setModule(api, key, on);
  try {
    return await body();
  } finally {
    await setModule(api, key, before);
  }
}
```

- [ ] **Step 3: Add `setModule` to `modules.ts`** using the endpoint and payload recorded in step 1 (one function: `setModule(api, key, on)`; it throws on any non-2xx answer).
- [ ] **Step 4: Write `frontend/e2e/fixtures/moduleList.ts`**: move the 15 `moduleConfig` imports and the `MODULES` array out of `future-module-pages.spec.ts` into this file and export `MODULES`; make the walk spec import it from here, so the contract walk and the switch matrix can never list different modules.
- [ ] **Step 5: Write `roles.ts` and `ledger.ts`**: `roles.ts` exports `pageAs(browser, { role, mda })`, which creates the user through the seed command and returns a logged-in page; `ledger.ts` exports `journalLines(api, reference)` and `trialBalanceTotals(api)`, which read the existing accounting endpoints (find the paths with `grep -n "journal" accounting/urls.py`).
- [ ] **Step 6: Typecheck** `npm run typecheck:e2e`. Commit `test(e2e): fixtures to switch modules, act as a role, and read the ledger`.

### Task A4: Module switch matrix spec (all 15, OFF → ON, data kept)

- [ ] **Step 1: Write `frontend/e2e/matrix/module-switch.spec.ts`**

```ts
import { test, expect } from '../fixtures/auth';
import { apiContext } from '../fixtures/api';
import { withModuleState, setModule } from '../fixtures/modules'; // setModule is the one switch call found in Task A3 step 1
import { MODULES } from '../fixtures/moduleList';                  // Task A3 step 3

for (const m of MODULES) {
  test(`${m.key}: off hides it and answers module_disabled, on brings the data back`, async ({ page }) => {
    const api = await apiContext();
    const first = m.entities[0];
    const list = `/api/v1/${m.apiBase}/${first.endpoint}/`;
    const before = await (await api.get(list)).json();
    await withModuleState(api, m.key, false, setModule, async () => {
      const off = await api.get(list);
      expect(off.status()).toBe(403);
      expect((await off.json()).code).toBe('module_disabled');
      await page.goto(m.basePath);
      await expect(page.getByText(/module disabled/i)).toBeVisible();
    });
    const after = await (await api.get(list)).json();
    expect(after.count ?? after.length).toBe(before.count ?? before.length); // data survived OFF → ON
  });
}
```

- [ ] **Step 2: Run** `npx playwright test e2e/matrix/module-switch.spec.ts`. Expected: 15 passing, or failures that name the modules whose gating is missing, which become bugs for the relevant wave.
- [ ] **Step 3: Commit** `test(e2e): module switch matrix for all 15 modules`.

### Task A5: Role and MDA matrix

- [ ] **Step 1:** write `rbac-modules.spec.ts`: for each module, a role without the module permission gets 403 on the list API and no tile; a user assigned to MDA B cannot read an MDA A record created by the admin (404, not 403, so existence is not leaked).
- [ ] **Step 2:** run; modules where MDA scoping is missing (see the survey: most) will fail. **That failure list is the wave backlog, not a test to relax.** Commit `test(e2e): role and MDA isolation matrix`.

### Task A6: Presentation sweep as a spec

- [ ] **Step 1:** port the crawler used in this session (`scratchpad/crawl.cjs`) into `e2e/sweep/routes.spec.ts`: for every static route, in light and dark, assert no console error / 5xx, no horizontal overflow, Geist body font, and the dark-mode light-leak and text-contrast checks it already computes. Budget: failures listed once in the report; a known-exceptions list for the IPSAS print sheet.
- [ ] **Step 2:** run nightly only (205 routes × 2 themes ≈ 15 minutes). Commit `test(e2e): presentation sweep across all routes in both themes`.

### Task A7: Seed and CI

- [ ] **Step 1:** extend `seed_e2e_tenant` to enable all 15 modules, add MDA B, and add one user per role (viewer, officer, approver, MDA-B officer). Keep it idempotent (`get_or_create`).
- [ ] **Step 2:** in `ci.yml` keep `E2E (Playwright)` as the PR job (L1 + smoke via `--grep @smoke`), add a `schedule:` nightly job for the full suite. Tag one journey per module `@smoke`.
- [ ] **Step 3:** make PR #58 green first (it is the prerequisite for every CI claim here). Commit `ci: nightly full Playwright run and PR smoke subset`.

---

## 7. Cross-module journeys (L3) to write alongside the waves

Each is one spec; each asserts the **screen and the ledger/API**.

1. **Budget to cash:** call circular → submission → incorporate → draft appropriation → enact → warrant → cash plan shows the release → recommendation becomes a warrant.
2. **Procure to pay to asset to fleet:** PR with catalogue price → PO → GRN → invoice match → payment → asset → fleet vehicle → maintenance cost posts.
3. **Award to PO:** tender → sealed bids → opening → award → draft PO → existing approval (extends the current supplier-bidding spec).
4. **Revenue:** collection posts to the ledger → arrears reduce once → replaying the signal changes nothing.
5. **Payroll:** payroll run → personnel budget variance → advance recovery deducted (opt-in) → net pay.
6. **Debt:** drawdown posts → debt service appears in the cash plan and budget.
7. **Case to provision:** legal case → linked IPSAS 19 provision → shown on the statement notes.
8. **Audit:** a continuous-audit rule raises a finding; a test proves it cannot write a journal.
9. **Publish:** enacted budget and awarded contract → transparency dataset → public portal shows only published fields (assert the JSON payload).
10. **Switch under load:** switch a module OFF mid-journey; existing modules continue untouched.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Tests that only pass because of the CI seed | each spec creates its own records and cleans up; seed holds only reference data |
| A test that cannot fail (I have hit this in this repo: checks that passed without doing their job) | for each new spec, break the behaviour on purpose once and watch it fail before trusting it |
| Posted records are immutable | build state in the real order (create → submit → approve → post); never edit a posted journal |
| Nightly run too slow or flaky | shard; no fixed sleeps; quarantine with an owner and a date, never a silent skip |
| Login and API throttles on long runs | one stored session; raise the dev throttle env vars locally |
| Scope growth | a wave is done when its exit test is green; anything extra becomes a new item here |

---

## 9. Decisions I need from you (recommended answers in bold)

1. **Order:** budget cycle first (W1), then procurement completion, then revenue and treasury. **Yes, as written.**
2. **Default state** of each module for existing tenants after rollout: **OFF.**
3. **Nightly Playwright run** in CI (uses CI minutes): **yes.**
4. **`integrations` module:** **defer** until a named customer system exists.
5. **Orphaned `integrations` schema** in the two tenants: **run the clear command** (the tables are empty).
6. **Adopt-actuals default basis** (B2): **prior-year outturn**, with last approved appropriation switchable.

When you answer (or say "go with the recommendations"), the next step is Phase T, Task A1.
