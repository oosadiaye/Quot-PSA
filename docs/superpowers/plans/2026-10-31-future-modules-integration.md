# Future Modules → Existing Application: Integration Master Plan

> **For agentic workers:** this is the *programme* plan: scope, seams, order, exit criteria. Each phase gets its own task-level plan (TDD steps, code, commands) written with `superpowers:writing-plans` at the moment that phase starts. Do not implement from this document directly.

**Goal:** bring the 15 modules built on `feat/future-modules` into the main application as *optional* extensions of the modules that already exist, so every tenant can run with or without any of them, and so the existing modules (procurement, budget, accounting, hrm, contracts, inventory) behave exactly as today when a future module is off or not installed.

**Architecture:** one-way dependency (`future module → existing app`, never the reverse), provenance carried as plain string columns, cross-module reactions delivered through Django signals that existing apps *emit* and future modules *receive*, and a per-tenant switch (`ModuleEnabled` + `MODULE_DEPENDENCIES`) that must land on `main` before any module does.

**Tech stack:** Django + django-tenants + DRF; React + TS + the config-driven `ModuleCrudPage`; pytest `--reuse-db`; Playwright.

---

## 0. What the review found (facts, not assumptions)

| Finding | Consequence for the plan |
|---|---|
| None of the 15 apps are in `main`'s `TENANT_APPS`. The same-named directories on `main` are untracked leftovers (0 tracked files). | "Integration" = porting onto `main`, not merging. |
| `feat/future-modules` is 13 commits ahead and **291 behind** the merge-base. It also edits ~30 existing files (module gating on legacy viewsets, `core/permissions.py` +234, `superadmin`, `tenants`, `settings`, `urls`). | Never merge the branch. Port by app, re-applying the gating changes against current `main`. |
| The module switch (`ModuleEnabled`, `MODULE_DEPENDENCIES`, module catalogue, pricing seed, `audit_module_gating`) exists **only on the branch**. | It is Phase 0; nothing else can be switched until it lands. |
| `integrations` has **orphaned schema** (3 empty tables + a recorded migration) in two tenants, incl. Delta State demo. `chore/clear-orphaned-integrations` has the command; it has not been run. | Owner decision; blocks the `integrations` app label. |
| Cross-app references the new modules already make (verified against models): `budget_prep→accounting segments`; `cash_planning→budget.Appropriation/Warrant, accounting.Fund`; `catalogue→procurement.Vendor/VendorContract, inventory.Item`; `debt→accounting Account/BankAccount/JournalHeader, budget.Warrant`; `disclosure→hrm.Employee`; `egp→procurement.Vendor/PurchaseOrder, contracts.Contract`; `fleet→accounting.FixedAsset`; `legal→accounting.Provision/ContingentLiability`; `personnel_budget→budget.Appropriation, hrm.PayrollRun, accounting segment`; `results→ProgrammeSegment`; `revenue_admin→RevenueHead`; `staff_advances→accounting Account/JournalHeader, hrm.Employee`; `transparency→ReportSnapshot`. `internal_audit` and `integrations` have none. | Every FK already points *out* of the new app. Good: the seam holds. The plan only adds what is missing. |
| `main` has **no vendor/supplier portal**. `Vendor.is_active` defaults False and is set only when the registration payment is confirmed (`VendorRenewalInvoice`). There *is* an employee self-service portal (`/portal`, `hrm.urls_portal` under `my/`). | Supplier self-service is new build, modelled on the employee portal. |
| The earlier `budget_prep → Appropriation` plan (2026-09-28) is on the branch with **0 of 24 tasks done**. Its seam design is sound. | Adopt it as the Phase 2 backbone; do not redesign. |
| Debt is already on the GL (drawdown, current-portion reclass, coupon, SoFP split), 20 tests + Playwright. | Phase 3 only re-homes it; do not rebuild. |

---

## 1. The "with or without" contract (applies to every phase)

Five rules. A phase is not done until its exit test proves all five.

1. **Direction.** Future module imports/FKs existing apps. Existing apps import nothing from future modules. Verified by a CI grep guard (`budget`, `procurement`, `accounting`, `hrm`, `contracts`, `inventory` must contain no `import budget_prep|egp|catalogue|…`).
2. **Provenance is a string.** Where an existing record is created from a future-module record, the existing model gains nullable `source_module` + `source_reference` CharFields (no FK) so history survives uninstall. (Pattern already designed for `Appropriation`.)
3. **Reactions via signals, not calls.** Existing apps *emit* narrow signals at lifecycle points (`po_approved`, `appropriation_activated`, `payroll_run_posted`, `revenue_collected`, `payment_posted`, `asset_capitalised`, `period_closed`). Future modules connect receivers in `AppConfig.ready()`. Each receiver first checks `is_module_enabled(key)`. No subscriber = no effect.
4. **Switch semantics.** *Off* ⇒ module API returns 403 `module_disabled`, its menu entry and extension widgets disappear, **data is kept**, existing modules unchanged. *Not installed* ⇒ `migrate`, boot and every existing endpoint still work. Activation of a module with unmet `MODULE_DEPENDENCIES` is rejected with a named error.
5. **Frontend extension slots.** Existing pages that surface a new module's data (e.g. "Supplier prices" tab on a PR line) render it only when `useModuleEnabled('<key>')` is true; otherwise the page is byte-for-byte today's page.

**Test matrix for every phase (three runs):** all-ON, module-OFF, app-not-installed (`INSTALLED_APPS` override). Plus "data survives OFF→ON".

---

## 2. Master list of integrations (the list you asked for)

Legend — **Hook**: existing module touched. **Needs on existing**: change required in existing app (minimal, additive). **Phase**: where it lands.

### A. Procurement chain
| # | Module | Integrates with | What it does in the live app | Needs on existing | Phase |
|---|---|---|---|---|---|
| A1 | **catalogue** | `procurement.Vendor`, `VendorContract`, `inventory.Item`, PR/PO lines | Framework/contract prices per supplier per item; price history; on a PR/PO line pick a catalogue price (price + supplier prefill), price-variance flag vs catalogue | none on models; extension slot on PR/PO line; optional signal `po_line_priced` | 1A |
| A2 | **Supplier self-service** (new, not one of the 15) | `procurement.Vendor`, catalogue, PO/GRN/payments, egp | Vendor user logs into a supplier portal: maintain profile and bank details (change request, approved by procurement), maintain own catalogue prices, view own POs/GRNs/invoice-match/payment status, acknowledge POs, submit e-bids. Activation controlled per tenant and per vendor (see §4) | `Vendor`: `portal_status` (not_invited/invited/active/suspended); new tenant-schema `VendorUser` (auth user ↔ vendor, scoped); `procurement.urls_portal`; portal permission scope = own vendor only | 1A |
| A3 | **egp** | `Vendor`, `PurchaseOrder`, `contracts.Contract`, `ProcurementThreshold`, `CertificateOfNoObjection`, workflow | Tender notice → bidder registration → bids/documents → public opening → evaluation committee/criteria/scores → award. **Award creates** a PO (goods/services) or a Contract (works) with `source_module='egp'`; threshold table decides the route; CNO required above threshold | `PurchaseOrder`/`Contract`: `source_module`, `source_reference`; signal `award_confirmed` consumed by procurement/contracts creator | 1B |

### B. Budget cycle
| # | Module | Integrates with | What it does | Needs on existing | Phase |
|---|---|---|---|---|---|
| B1 | **budget_prep** | `budget.Appropriation`, NCoA segments, fiscal year | Call circular → MDA ceilings → submissions/lines → review comments → **incorporate = DRAFT appropriations** (one-way, optional). Existing activation/enactment flow untouched | `Appropriation`: `source_module`, `source_reference` (migration); `SubmissionLine`: fund + programme | 2 |
| B2 | **Adopt actuals to plan** (feature of B1) | `budget.UnifiedBudgetVariance`, GL balances, current `Appropriation`, `RevenueBudget` | "Adopt" button on a submission/MTEF projection: seed baseline (year 0) and the line proposals from (a) last approved appropriation, (b) prior-year **outturn** from GL actuals, or (c) current-year **run-rate** annualised; apply configurable growth/inflation/policy adjustments per economic class; keep an audit of every adopted figure and the rule used; editable before submit | read-only queries over `accounting`/`budget`; no model change on existing | 2 |
| B3 | **personnel_budget** | `hrm.Position/Employee/PayrollRun`, `Appropriation`, GL posting | Establishment (approved posts vs filled), personnel cost forecast, variance vs payroll runs, **payroll budget binding** (payroll posting checked against the personnel appropriation line). `MODULE_DEPENDENCIES: hrm, budget, accounting` | signal `payroll_run_posted`; binding reads `Appropriation` | 2 |
| B4 | **cash_planning** | `Appropriation`, `Warrant`, `accounting.Fund`, bank/TSA | Cash plan and forecast lines, cash position vs plan, **warrant release recommendation** (a recommendation that a user turns into a `Warrant`; never auto-issues) | `Warrant`: `source_module`/`source_reference`; signal `warrant_issued` to update plan variance | 2 |
| B5 | **Other public-budget-planning features** (each a distinct deliverable, all optional) | see right | (i) **Budget calendar** with milestones and reminders; (ii) **supplementary budget / amendment** cycle from prep into `AppropriationAmendment`/`Virement`; (iii) **ceiling enforcement** (a submission cannot exceed its MDA ceiling; override needs a reason); (iv) **programme-based / performance link**: results indicators attach to `ProgrammeSegment` lines in the submission; (v) **revenue forecast** from revenue_admin feeding `RevenueBudget`; (vi) **citizens' budget** publication from enacted appropriations via transparency; (vii) **MTEF out-years** (+1/+2) carried into the next cycle's baseline | extra fields only where noted per phase plan | 2 / 5 |

### C. Revenue and treasury
| # | Module | Integrates with | What it does | Needs on existing | Phase |
|---|---|---|---|---|---|
| C1 | **revenue_admin** | `accounting.RevenueHead`, `RevenueCollection`, `RevenueBudget` | Taxpayer register, tax accounts, assessments/billing runs, demand notices, arrears ledger, enforcement, clearance certificates. **Collections already posted** to `RevenueCollection` reduce arrears via signal `revenue_collected` | signal on `RevenueCollection` post; none on models | 3 |
| C2 | **debt** | GL, `BankAccount`, `Warrant`, SoFP | Already integrated on the branch. Re-home: drawdown/reclass/coupon/GL mapping; debt-service line feeds cash plan and budget | none beyond ported migrations | 3 |
| C3 | **staff_advances** | `hrm.Employee`, GL, payments, payroll | Staff advances, imprest accounts/retirements, per-diem tables, travel requests/advances/retirements; posts to GL via `JournalHeader`; **unretired advance recovery deducted in payroll** (opt-in deduction code) | signal `payroll_run_posted`; deduction hook in payroll build | 3 |

### D. Assets, people, risk, assurance
| # | Module | Integrates with | What it does | Needs on existing | Phase |
|---|---|---|---|---|---|
| D1 | **fleet** | `accounting.FixedAsset`, inventory/procurement for fuel & parts | Vehicle = fixed asset + operating detail; assignments, fuel/mileage logs, maintenance cost; maintenance cost can post to expense or capitalise via existing asset flow | signal `asset_capitalised`; none on `FixedAsset` | 4 |
| D2 | **legal** | `accounting.Provision`, `ContingentLiability` | Case register, hearings, costs, risk register; `litigationProvisionLink` ties a case to an IPSAS 19 provision/contingent liability | none | 4 |
| D3 | **disclosure** | `hrm.Employee`, users | Declaration cycles, asset declarations, controlled access log | none | 4 |
| D4 | **internal_audit** | GL, procurement, workflow | Audit universe/plan/engagements/working papers/findings/follow-up; **continuous-audit rules** run read-only queries against GL/procurement for exceptions and raise findings; findings use existing workflow | none (read-only) | 4 |

### E. Publication, performance, interoperability
| # | Module | Integrates with | What it does | Needs on existing | Phase |
|---|---|---|---|---|---|
| E1 | **transparency** | `ReportSnapshot`, budget, procurement, contracts | Publication policy, redaction rules, data exports, public citizen portal (published datasets only). Sources: enacted budget, awarded contracts, quarterly reports | none; reads published snapshots | 5 |
| E2 | **results** | `ProgrammeSegment`, budget lines | Results framework → outcomes → outputs → indicators/targets/actuals → performance reports; links to B5(iv) | none | 5 |
| E3 | **integrations** | all (outbound/inbound) | Gateway per `ERP_INTEGRATION_PLAN.md` (its own 7 phases). Only phases 1–2 recommended now | clear orphaned schema first | 5 (own sub-plan) |

---

## 3. Phases

Each phase ends on `main` as a PR, behind the switch, with the three-run test matrix green and the module **default OFF** for existing tenants.

### Phase 0: Foundation (must land first)
**Scope:** (1) port the switch: `ModuleEnabled`, `MODULE_DEPENDENCIES`, module catalogue + pricing seed, superadmin/tenant toggles with the 60 s cache, `audit_module_gating` command and its CI guard; re-apply `module_key` gating to the legacy viewsets against current `main`. (2) frontend: `ModuleDisabledPage`, `useModuleEnabled`, conditional nav, the `_base` config-driven CRUD kit (with this week's fixes: file field, visible save errors). (3) the **signals registry** in `core` (one file, names documented) and the CI "no reverse imports" guard. (4) the `INSTALLED_APPS` not-installed test harness. (5) **Decision + run** of `clear_orphaned_integrations`.
**Exit:** switch works on `main` with zero new modules; guard tests green; no existing endpoint changed behaviour (diff of OpenAPI schema = module_key metadata only).

### Phase 1A: Supplier catalogue + supplier self-service
**Port:** `catalogue` (+ migrations re-based). **Build:** A2 portal (backend `urls_portal`, `VendorUser`, vendor-scoped permission class, change-request approval for bank details, invitation/activation flow, frontend `/supplier-portal` mirroring `/portal`), PR/PO-line catalogue slot.
**Exit:** vendor sees only own data (negative tests: other vendor's PO = 404); portal off ⇒ procurement unchanged; catalogue off ⇒ PR/PO form unchanged.

### Phase 1B: e-Procurement
**Port:** `egp`. **Build:** award → PO/Contract creation (`source_module`), threshold routing, CNO gate, supplier-portal bid submission.
**Exit:** an award produces a PO that passes the *existing* approval, GRN and invoice-match flow untouched; egp off ⇒ manual PO creation identical to today.

### Phase 2: Budget cycle
**Port:** `budget_prep`, `personnel_budget`, `cash_planning`. **Build:** B1 incorporate (per the 2026-09-28 plan, 24 tasks, reuse), **B2 adopt-actuals**, B3 payroll binding, B4 warrant recommendation, B5 (i)–(iv), (vii).
**Exit:** every drafted `Appropriation` activates through the unchanged enactment flow; `budget` boots with the three apps absent; adopted figures reproduce from the GL to the kobo.

### Phase 3: Revenue and treasury
**Port:** `revenue_admin`, `debt`, `staff_advances`. **Build:** C1 collections→arrears signal, B5(v) revenue forecast into `RevenueBudget`, C3 payroll recovery.
**Exit:** posted revenue collection reduces arrears exactly once (idempotent on replay); debt GL tests and Playwright carried over green; staff advance recovery opt-in only.

### Phase 4: Assets, people, risk, assurance
**Port:** `fleet`, `legal`, `disclosure`, `internal_audit`. **Build:** D1 asset link, D2 provision link, D4 continuous-audit rules (read-only).
**Exit:** read-only guarantee test for audit rules (they can never write to the ledger).

### Phase 5: Publication, performance, interoperability
**Port:** `transparency`, `results`, then `integrations` phases 1–2 under their own plan. **Build:** E1 publications from enacted budget/awards, B5(vi), E2 indicator links.
**Exit:** public portal exposes published data only; unpublished/redacted fields never leave the tenant.

### Phase 6: Hardening and rollout
Full ON/OFF/not-installed regression on all 15; navigation and role matrix; module pricing catalogue; user guide per module; migration rehearsal on a copy of the Delta State tenant; rollback runbook.

---

## 4. Supplier self-service: activation design (decision needed)

- **Tenant level:** `supplier_portal_enabled` (off by default; requires `procurement` active).
- **Vendor level:** `portal_status`: `not_invited → invited → active → suspended`. Activation is a *procurement officer* action (or auto on registration-payment confirmation, tenant setting). A vendor that is not `is_active` (registration unpaid/expired) can sign in only to a "renew registration" page.
- **Identity:** a normal auth user with a `UserTenantRole` of a new, narrow `vendor` role plus a `VendorUser(user, vendor)` row. Every portal queryset is filtered by that vendor; no portal view uses the staff permission classes.
- **Sensitive changes** (bank account, tax id) never apply directly: they create a change request that procurement approves (fraud control).
- **Audit:** every portal write is attributed and logged.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| Porting against a 291-commit drift | Port one app at a time; each migration re-generated on current `main`; branch kept read-only as reference |
| Migration order across ~15 new apps in every tenant schema | Phase 0 rehearsal on a tenant copy; apps ship OFF so data volume is zero at first |
| Hidden coupling creeps back (existing code importing a new app) | CI guard from Phase 0 |
| Signals double-firing or running when module is off | receivers check `is_module_enabled`; idempotency keys on every cross-module write |
| Supplier portal widens the attack surface | vendor-scoped permission class, negative tests, throttling, separate login route, security review before Phase 1A merge |
| Posted/immutable records | follow existing rule: build state in real order; new modules never edit posted journals |

---

## 6. Decisions needed before Phase 0

1. **Order:** as above (procurement first, then budget)? Or budget first?
2. **Supplier activation:** manual by procurement officer, automatic on registration payment, or both (tenant setting)? *Recommended: both, default manual.*
3. **Orphaned `integrations` schema:** approve running `clear_orphaned_integrations` on the two tenants (empty tables)?
4. **Default state** of each module for existing tenants after rollout: OFF (recommended).
5. **Adopt-actuals basis:** which of (a) last approved appropriation, (b) prior-year outturn, (c) run-rate should be the default? *Recommended: (b) outturn, with (a) as a switchable alternative.*
6. **`integrations` gateway:** include phases 1–2 now, or defer the whole module until a named customer system exists (its own plan recommends the latter)?
