# Future Modules — Quot PSA

**Status:** Specification · not yet implemented
**Created:** 2026-09-02
**Branch:** `feat/future-modules`
**Source:** Gap register from the FreeBalance competitive review
(`Quot_PSA_vs_FreeBalance_Review.html`, gaps G1–G13)

---

## Purpose

The competitive review against the FreeBalance Accountability Suite identified
thirteen gaps between Quot PSA and a full Government Resource Planning suite.
This document turns each gap into a **discrete, independently licensable module**
that plugs into the existing per-tenant toggle architecture — so a client who
does not need Public Debt Management, or already runs a separate IGR platform,
simply does not buy or activate that module.

Nothing here is built yet. This is the contract each module must satisfy
before it is considered complete.

---

## Table of contents

1. [The module contract](#1-the-module-contract)
2. [Prerequisite: backend enforcement](#2-prerequisite-backend-enforcement-blocking)
3. [Disable semantics](#3-disable-semantics)
4. [Module register](#4-module-register)
5. [Module specifications](#5-module-specifications)
6. [Dependency graph](#6-dependency-graph)
7. [Delivery horizons](#7-delivery-horizons)
8. [What is deliberately not a module](#8-what-is-deliberately-not-a-module)
9. [Definition of done](#9-definition-of-done)

---

## 1. The module contract

Quot PSA already has a working module system. Every new module below plugs into
it — no new toggle mechanism is introduced.

| Layer | Where it lives | What a new module must add |
|---|---|---|
| Canonical registry | `tenants/models.py` → `AVAILABLE_MODULES` | One `(key, title, description)` tuple |
| Per-tenant toggle | `core/models.py:459` → `core.TenantModule` | A row seeded per tenant, `is_active` default per plan |
| Commercial catalogue | `tenants/models.py:552` → `ModulePricing` | Price, tagline, feature bullets, icon, sort order |
| Plan bundling | `SubscriptionPlan.allowed_modules` | Key added to the relevant plan tiers |
| Backend enforcement | **`core/permissions.py` → `ModuleEnabled`** | **Does not exist yet — see §2** |
| Frontend route guard | `frontend/src/components/ModuleGuard.tsx` | One `MODULE_META` entry + a `<Route element={<ModuleGuard module="…" />}>` group |
| Navigation | Sidebar module map | Nav group, hidden when the module is off |
| Seed | `core/management/commands/setup_state_tenant.py` | Module row created on tenant onboarding |

`SubscriptionPlan.clean()` already validates `allowed_modules` against
`AVAILABLE_MODULES` and raises on a typo, so adding the registry tuple **first**
is mandatory — everything else keys off it.

### Naming rules

- Module key: `snake_case`, stable forever (it is a billing identifier and
  appears in `ModulePricing.module_name`, plan JSON, and tenant rows).
- Never rename a key. Change the title instead.
- Never reuse a retired key for different functionality.

---

## 2. Prerequisite: backend enforcement (BLOCKING)

**This must be built before any module in §5.**

Module gating today is **frontend-only**. `ModuleGuard` renders a "Module
Disabled" page, and the sidebar hides the nav item — but no DRF permission
class checks `core.TenantModule.is_active`. A module switched off still answers
its REST API to any authenticated user holding the matching RBAC role.

For nav tidiness that is acceptable. As a **commercial entitlement boundary it
is not**: every paid module below would ship with a bypass on day one.

### Required work

Add to `core/permissions.py`:

```python
class ModuleEnabled(permissions.BasePermission):
    """Refuse the request when the owning module is toggled off for this tenant.

    Composed with RBACPermission, never instead of it:
        permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]

    The module key is declared on the ViewSet:
        module_key = 'debt'
    """
```

Design points:

- Resolve `core.TenantModule` once per request and cache on `request` — this
  runs on every API call and must not add a query per view.
- **Fail closed for new modules, fail open for existing ones.** The current
  `tenant_modules_api` pads unconfigured modules with `False`, but
  `ModuleGuard` treats an empty configuration as "allow all". Preserve that
  fallback for the twelve modules already live so no running tenant breaks,
  and require an explicit active row for every key added by this document.
- Read-only endpoints that a disabled module's data still feeds (a GL journal
  posted by a now-disabled module) stay reachable — see §3.
- Return `403` with a machine-readable body: `{"detail": …, "module": "debt",
  "code": "module_disabled"}` so the frontend can render the same disabled
  page from an API response, not only from route matching.

### Also required

- Management command `audit_module_gating` — asserts every ViewSet whose app
  belongs to a gated module declares `module_key`. Wire it into CI so a new
  endpoint cannot silently escape the gate.
- Tests: module off → `403` on write **and** on module-owned reads; module on
  → normal RBAC behaviour; unconfigured legacy module → unchanged.

**Effort:** 0.5–1 engineer-month. Everything downstream depends on it.

---

## 3. Disable semantics

A public-sector ledger cannot be treated like a SaaS feature flag. Turning a
module off must never make the accounts wrong.

### Three levels

| Level | Behaviour | Use for |
|---|---|---|
| `HIDDEN` | Nav hidden, routes 403, write APIs 403. Data retained and readable through reports. | Default for every module |
| `FROZEN` | Existing records readable and reportable, no new records, no state transitions. | A module being retired mid-year |
| `BLOCKED` | All access refused including reads. | Never used where the module has posted to the GL |

### Invariants

1. **A toggle never deletes data.** Disabling is reversible with no loss.
2. **A toggle never rewrites the general ledger.** Journals posted while a
   module was active remain posted — they are part of the statutory accounts
   and an Accountant-General has signed statements built on them.
3. **A toggle never breaks a financial statement.** IPSAS reports must render
   correctly when a module that contributed balances is off. Reports read the
   GL, not the module.
4. **Cross-module references degrade, they do not crash.** If `contracts` is on
   and `debt` is off, a contract referencing a loan-funded appropriation still
   opens; the debt panel renders as unavailable.
5. **Modules with a hard dependency cannot be activated alone.** Activating
   `personnel_budget` without `hrm` and `budget` is rejected at save time with
   a named error, not silently accepted.

### Required test per module

Each module below ships with an activation-cycle test: activate → create data →
post to GL → deactivate → assert reports still balance → reactivate → assert
data intact.

---

## 4. Module register

Fifteen new modules. Keys are final; do not change them after first release.

| # | Key | Title | Gap | Horizon | Effort |
|---|---|---|---|---|---|
| 1 | `budget_prep` | Budget Preparation (MTEF/MTSS) | G1 | H2 | 4–6 mo |
| 2 | `egp` | e-Procurement & Tendering | G2 | H3 | 5–7 mo |
| 3 | `personnel_budget` | Establishment & Personnel Cost Control | G3 | H1 | 1–2 mo |
| 4 | `debt` | Public Debt Management | G4 | H2 | 2–3 mo |
| 5 | `transparency` | Fiscal Transparency Portal | G5 | H2 | 2–3 mo |
| 6 | `results` | Results & Performance (M&E) | G6 | H3 | 3–4 mo |
| 7 | `integrations` | Integration Gateway | G7 | H2 | 3–4 mo |
| 8 | `revenue_admin` | Revenue Administration (IGR) | G8 | H3 | 6–9 mo |
| 9 | `cash_planning` | Cash Planning & Forecasting | G9 | H1 | 2 mo |
| 10 | `staff_advances` | Staff Advances, Imprest & Travel | G10 | H1 | 1–2 mo |
| 11 | `internal_audit` | Internal Audit Management | G11 | H3 | 2 mo |
| 12 | `fleet` | Fleet Management | G13 | H3 | 1 mo |
| 13 | `catalogue` | Supplier Catalogue | G13 | H3 | 1 mo |
| 14 | `disclosure` | Asset Declaration | G13 | H3 | 0.5 mo |
| 15 | `legal` | Legal, Risk & Case Tracking | G13 | H3 | 1–1.5 mo |

Total: **35–48 engineer-months**, plus 0.5–1 for §2.

---

## 5. Module specifications

Each specification states the buyer, the statutory driver, what is built, what
it depends on, and what happens when it is switched off.

---

### 1. `budget_prep` — Budget Preparation (MTEF/MTSS)

> **Gap G1 · Critical · Horizon 2 · 4–6 engineer-months**
> Closes the FreeBalance GPM pillar modules GPPB and GPBB.

**Buyer:** Ministry of Budget & Economic Planning. This is the module that turns
Quot PSA from an OAG product into a Ministry of Finance product.

**Driver:** Fiscal Responsibility Act 2007 requires a Medium Term Expenditure
Framework. Every State runs an annual budget call circular cycle that currently
happens entirely outside the system — Quot PSA's first object is the enacted
`Appropriation` (`budget/models.py:665`).

**Scope**

- `FiscalFramework` — multi-year macro envelope, revenue projection, aggregate
  expenditure ceiling, with a version chain so scenarios can be compared.
- `SectorEnvelope` → `MDACeiling` — cascade with a validation that children
  never exceed the parent.
- `BudgetCallCircular` — issue, distribution list, deadline, attachments.
- `MDABudgetSubmission` and `SubmissionLine` — MDA-side entry against the
  ceiling, classified on the existing NCoA segments so nothing is re-keyed.
- `SubmissionReview` — Budget Office scoring, query, revise, accept.
- `BudgetConsolidation` — roll-up to the draft Estimates.
- **Hand-off service** — promotes an approved consolidation into `Appropriation`
  rows. This is the seam with the existing budget module and must be
  idempotent, auditable and reversible before enactment.
- Budget Book export (the printed Estimates document, per State house style).

**Depends on:** `budget`, `dimensions`. Optional: `results` (for programme
performance narrative), `personnel_budget` (for personnel cost envelopes).

**When off:** Appropriations are captured directly as they are today. No loss of
existing capability — this module is purely additive upstream.

**Note:** the repository README currently advertises this capability. Until this
module ships, that claim must be corrected in `README.md` and in any proposal
document generated from it.

---

### 2. `egp` — Electronic Government Procurement & Tendering

> **Gap G2 · Critical · Horizon 3 · 5–7 engineer-months**
> Closes FreeBalance PEGP and PEEP.

**Buyer:** State Bureau of Public Procurement / Due Process Office.

**Driver:** Public Procurement Act 2007 and State procurement laws. The
*governance* already exists — `ProcurementThreshold` (`procurement/models.py:2274`)
resolves the approving authority, and `CertificateOfNoObjection` blocks PO
issue. The *transaction* does not: there is no tender, bid, evaluation or award.

**Scope**

- `TenderNotice` — advertisement, category, method (the `ProcurementMethod` enum
  already exists in `contracts/models/contract.py:68`), closing date, documents.
- `BidderRegistration` — supplier onboarding with certificate expiry, tax
  clearance, PenCom and ITF compliance evidence.
- `Bid` and `BidDocument` — submission with a sealed window; nothing readable
  before the recorded opening event.
- `BidOpening` — attendance register, opened-in-public record.
- `EvaluationCommittee`, `EvaluationCriterion`, `BidScore` — responsiveness
  check then technical and financial scoring.
- `TenderAward` → generates the `Contract` and the `PurchaseOrder`.
- **Public supplier portal** — a separate unauthenticated surface for notices,
  bid submission and award publication.

**Depends on:** `procurement`, `contracts`. Optional: `transparency` (award
publication), `integrations` (bidder verification).

**When off:** Procurement runs as today — requisition → PO with threshold and
No Objection governance, tender process managed on paper.

**Security note:** the sealed-bid window is the security-critical element. Bid
contents must be encrypted at rest and undecryptable before the opening event,
with the opening recorded in the audit trail. Specify this before build.

---

### 3. `personnel_budget` — Establishment & Personnel Cost Control

> **Gap G3 · Critical · Horizon 1 · 1–2 engineer-months**
> Closes FreeBalance CSPL. **Highest control value per engineer-month on this list.**

**Buyer:** Accountant-General and Head of Service jointly.

**Driver:** Personnel cost is the largest recurrent line in any State budget and
is currently the **only expenditure stream that bypasses commitment control**.
`accounting/services/payroll_posting.py` writes salary expense straight to the
GL with no appropriation lookup and no call into the budget-check rule engine.

**Scope**

- `EstablishmentPost` — approved post count per MDA per grade, with an approval
  chain. The nominal roll cannot exceed the establishment.
- `EstablishmentVariance` — filled versus approved, by MDA and grade.
- **Payroll budget gate** — bind `PayrollRun` to its personnel appropriation
  lines; commit on approval through the existing `BudgetCheckRule` engine
  (`accounting/models/budget_check_rules.py`), which already supports
  `NONE` / `WARNING` / `STRICT` by GL code range.
- `PersonnelCostForecast` — projected payroll to year end against appropriation,
  including known increments and promotions.
- Block or warn on establishment breach at appointment, promotion and transfer.

**Depends on:** `hrm`, `budget`, `accounting`. **Hard dependency — reject
activation without all three.**

**When off:** payroll posts as it does today, unbudgeted. Because this is a
control rather than a feature, the recommendation is to **default it ON for
every government tenant** and treat deactivation as an explicit, logged
decision by the Accountant-General.

---

### 4. `debt` — Public Debt Management

> **Gap G4 · High · Horizon 2 · 2–3 engineer-months**
> Closes FreeBalance GTDM and GTLN. Replaces an eight-field stub
> (`accounting/models/advanced.py:330`).

**Buyer:** State Debt Management Department / Commissioner for Finance.

**Driver:** Fiscal Responsibility Act 2007 debt limits, DMO subnational
reporting, and World Bank/donor debt sustainability conditions.

**Scope**

- `DebtInstrument` — external and domestic classification, creditor, currency,
  tenor, grace period, interest basis, contingent-liability flag.
- `Disbursement` — drawdown schedule and actuals.
- `AmortisationSchedule` — generated principal and interest by period,
  supporting the common structures (equal principal, annuity, bullet).
- `DebtServicePayment` — posts through the existing Payment Voucher pipeline so
  debt service is a normal treasury payment, not a side channel.
- `GuaranteeAndContingent` — links to `ContingentLiability`
  (`accounting/models/provision.py:171`), which already exists for IPSAS 19.
- Reports: debt stock, debt service forecast, DMO return, FRA ratio compliance.
- Feeds `cash_planning` with the debt-service line.

**Depends on:** `accounting`, `treasury`. Optional: `cash_planning`.

**When off:** existing `Loan` records remain readable. Any debt-service journals
already posted stay in the GL — invariant 2.

---

### 5. `transparency` — Fiscal Transparency Portal

> **Gap G5 · High · Horizon 2 · 2–3 engineer-months**
> Closes FreeBalance GPTP and GPER.

**Buyer:** Commissioner for Finance / State Open Government focal office.

**Driver:** Open Government Partnership State action plans and donor-funded PFM
programme conditions score fiscal transparency directly. Disproportionate
procurement weight for the engineering cost.

**Scope**

- Public, unauthenticated, read-only surface — served from
  `ReportSnapshot` (`accounting/models/report_snapshot.py`), never from live
  transactional tables.
- `PublicationPolicy` — what is published, at what aggregation, on what lag,
  approved by a named officer. Nothing reaches the public surface without an
  explicit publish action.
- Published views: enacted budget, execution against budget, contract awards,
  payments above a configurable threshold, revenue performance, citizen budget
  summary.
- Open data export — CSV and JSON per published dataset.
- Redaction rules for personal data.

**Depends on:** `accounting`, `budget`, `reporting`. Optional: `egp` (awards),
`revenue_admin`.

**When off:** no public surface is exposed at all. The portal must be a separate
URL namespace with its own throttling and its own read-only database role, so
that "off" is enforced at the routing layer and not only in a template.

**Security note:** this is the only module that serves unauthenticated traffic.
It requires its own threat model, rate limiting and cache layer before release.

---

### 6. `results` — Results & Performance Framework

> **Gap G6 · High · Horizon 3 · 3–4 engineer-months**
> Closes FreeBalance GPPM and the dashboard family.

**Buyer:** Ministry of Budget & Planning, M&E unit.

**Driver:** Programme-based budgeting is currently a *classification* in Quot
PSA — the `ProgrammeSegment` exists on every appropriation and the Programme
Performance report measures naira only. Without indicators it cannot answer
whether the programme achieved anything.

**Scope**

- `ResultsFramework` → `Outcome` → `Output` → `Indicator`, anchored to the
  existing `ProgrammeSegment` so no parallel hierarchy is created.
- `IndicatorBaseline`, `IndicatorTarget` (annual and quarterly), `IndicatorActual`
  with a named data source and a verification note.
- `PerformanceReport` — physical progress beside financial execution.
- Scorecards by MDA, by programme, by officer.
- Optional link from `Contract` and `PurchaseOrder` to the output they deliver,
  so capital spend maps to physical delivery.

**Depends on:** `dimensions`, `budget`. Optional: `budget_prep`, `contracts`,
`transparency`.

**When off:** programme reporting remains financial only, exactly as today.

---

### 7. `integrations` — Integration Gateway

> **Gap G7 · High · Horizon 2 · 3–4 engineer-months**

**Buyer:** State ICT agency and the Accountant-General jointly.

**Driver:** Remita, NIBSS, GIFMIS and IPPIS are today **reference fields and
seed data, not connectors**. `RevenueCollection.rrr` stores a Remita retrieval
reference; nothing ever calls Remita. Buyers read the field names as
integrations and will test that reading during evaluation.

**Scope**

- `IntegrationEndpoint` — per-connector configuration, credentials held in the
  existing encrypted store (`superadmin/encryption.py`), environment, enabled flag.
- `IntegrationRun` and `IntegrationMessage` — every exchange logged with
  payload hash, status, retry count and operator-visible failure reason.
- Connectors, each independently switchable:
  - **Remita** — collection reconciliation against `RevenueCollection`.
  - **NIBSS / bank** — payment file generation from `PaymentBatch`, with status
    callback into the existing `PaymentCascadeFailure` queue.
  - **GIFMIS** — chart alignment and federal return submission.
  - **IPPIS** — nominal roll reconciliation against `hrm.Employee`.
  - **BVN/TIN verification** — vendor and employee identity checks.
- Replay and idempotency: a re-delivered message must never double-post.

**Depends on:** varies by connector — declare per connector, not per module.

**When off:** all exchange is manual (file upload, manual reconciliation), which
is the current behaviour.

---

### 8. `revenue_admin` — Revenue Administration (IGR)

> **Gap G8 · High · Horizon 3 · 6–9 engineer-months**
> Closes the FreeBalance GRM pillar: GRPI, GRCT, GRPT, GRPL, GRBP, GRCM.

**Buyer:** State Internal Revenue Service.

**Driver:** Quot PSA can *record* revenue (`RevenueHead`, `RevenueCollection`)
but cannot *administer* it. There is no taxpayer account, assessment, demand
notice, arrears ledger or enforcement case anywhere in the codebase.

**Scope**

- `Taxpayer` — registry keyed on TIN, with individual and corporate profiles,
  and linkage to BVN via `integrations` where available.
- `TaxAccount` — per taxpayer per revenue type, running balance.
- `Assessment` — self-assessment and best-of-judgement, with objection and
  appeal states.
- `DemandNotice` and `BillingRun` — including property tax and licence renewal
  cycles.
- `ArrearsLedger` with ageing, and `EnforcementCase` with a distraint workflow.
- `TaxClearanceCertificate` — issue and verification, which the `egp` module
  consumes for bidder eligibility.
- Taxpayer self-service portal.

**Depends on:** `revenue`, `accounting`. Optional: `integrations`, `transparency`.

**When off:** revenue receipting works exactly as today.

**Commercial recommendation:** this is the largest single build on the list and
the strongest candidate for **partnership rather than build** — most States
already run an IRS platform. Decide build-versus-partner at the start of
Horizon 3, not at the end. If partnering, this module becomes a connector
inside `integrations` instead.

---

### 9. `cash_planning` — Cash Planning & Forecasting

> **Gap G9 · Medium · Horizon 1 · 2 engineer-months**
> Completes FreeBalance GTCM. The models exist; the engine does not.

**Buyer:** Accountant-General, Treasury cash management unit.

**Driver:** `TreasuryForecast`, `CashFlowForecast` and `CashFlowEntry` exist
(`accounting/models/advanced.py:301, 1450`) but are populated manually. The real
signal — open commitments, contract year plans, payroll obligations, debt
service — is already in the database and unused.

**Scope**

- `CashPlan` — annual plan by month, by fund, by MDA.
- **Forecast engine** driven off live data: open `ProcurementBudgetLink`
  commitments, `ContractYearPlan` schedules, payroll runs, `AmortisationSchedule`
  from `debt`, and historical revenue seasonality.
- `CashPosition` — daily projected TSA balance with a configurable warning floor.
- `WarrantRecommendation` — proposed release schedule based on projected
  availability, feeding the existing `Warrant` process rather than replacing it.
- Variance: planned versus actual inflow and outflow.

**Depends on:** `treasury`, `accounting`, `budget`. Optional: `debt`, `contracts`,
`personnel_budget`.

**When off:** the manual forecast models remain usable as today.

---

### 10. `staff_advances` — Staff Advances, Imprest & Travel

> **Gap G10 · Medium · Horizon 1 · 1–2 engineer-months**
> Completes FreeBalance PFAA; adds CSTS.

**Buyer:** MDA accounts departments — highest-volume everyday users.

**Driver:** `VendorAdvance` (`accounting/models/vendor_advance.py:60`) handles
the vendor side well, with a special-GL reconciliation account and automatic
recovery. There is no staff equivalent, so touring advances, estacode and
imprest retirement leave the system and return as spreadsheets.

**Scope**

- `StaffAdvance` — reuses the proven `VendorAdvance` special-GL pattern against
  an employee rather than a vendor.
- `ImprestAccount` — issue, expenditure, retirement, replenishment, with an
  outstanding-retirement block on further issue.
- `TravelRequest` → `TravelAdvance` → `TravelRetirement`, with an estacode and
  per-diem table by grade and destination.
- Automatic recovery from payroll for unretired advances, through
  `hrm.SalaryComponent`.
- Ageing report of outstanding retirements by officer and by MDA — the number
  an Auditor-General asks for first.

**Depends on:** `accounting`. Optional: `hrm` (payroll recovery — without it,
recovery is manual).

**When off:** vendor advances continue to work; staff advances stay off-system.

---

### 11. `internal_audit` — Internal Audit Management

> **Gap G11 · Medium · Horizon 3 · 2 engineer-months**
> Closes FreeBalance GPIA.

**Buyer:** the internal audit unit inside the OAG — **a second buyer in the same
building as the existing customer**.

**Driver:** Quot PSA has a complete audit *trail* (`TransactionAuditLog`, plus
`simple_history` on tenant models) and a viewer. It has no audit *practice*: no
universe, no plan, no working papers, no findings register.

**Scope**

- `AuditUniverse` — auditable entities with risk scoring.
- `AuditPlan` — risk-based annual plan with resource allocation.
- `AuditEngagement` — scope, team, timetable, status.
- `WorkingPaper` — evidence with immutable attachment references.
- `AuditFinding` — rating, recommendation, management response, agreed action,
  due date.
- `FollowUp` — implementation tracking and overdue escalation.
- Continuous-auditing hooks that query the existing audit trail for exceptions:
  split purchases below threshold, weekend postings, dormant-vendor payments,
  SoD override usage.

**Depends on:** `audit`. Optional: every transactional module (as audit subjects).

**When off:** the audit trail and viewer remain fully available.

---

### 12. `fleet` — Fleet Management

> **Gap G13 · Low · Horizon 3 · 1 engineer-month**
> Closes FreeBalance PFFM.

**Scope:** `Vehicle` (extending `FixedAsset` rather than duplicating it),
assignment and custody, fuel and mileage logs, maintenance schedule and history,
licence, insurance and roadworthiness expiry alerts, running-cost report per
vehicle and per MDA.

**Depends on:** `accounting` (fixed assets). Optional: `procurement`.

**When off:** vehicles remain ordinary fixed assets.

---

### 13. `catalogue` — Supplier Catalogue

> **Gap G13 · Low · Horizon 3 · 1 engineer-month**
> Closes FreeBalance PECT.

**Scope:** `SupplierCatalogue` and `CatalogueItem` with validity dates and
framework-agreement pricing, catalogue-driven requisition that pre-fills price
and specification, and price-history comparison across suppliers.

**Depends on:** `procurement`, `inventory`.

**When off:** requisition lines are entered free-text, as today.

---

### 14. `disclosure` — Asset Declaration

> **Gap G13 · Low · Horizon 3 · 0.5 engineer-month**
> Closes FreeBalance CSFD.

**Scope:** `DeclarationCycle`, `AssetDeclaration` and `DeclarationItem`,
submission and acknowledgement workflow, compliance register by officer and
grade, non-compliance escalation.

**Depends on:** `hrm`.

**When off:** declarations are handled off-system.

**Privacy note:** this module holds the most sensitive personal data in the
product. It requires its own access-control review, field-level encryption for
declared values, and an access log distinct from the general audit trail —
specify before build, not after.

---

### 15. `legal` — Legal, Risk & Case Tracking

> **Gap G13 · Low · Horizon 3 · 1–1.5 engineer-months**
> Closes FreeBalance GPLR and GPCT.

**Scope:** `LegalCase` with parties, court, stage and hearing diary; `CaseCost`
for legal fees and awards; `RiskRegister` with likelihood, impact and mitigation
owner; automatic linkage to `Provision` and `ContingentLiability`
(`accounting/models/provision.py`), which already implement IPSAS 19 — so a
judgement debt raises the provision rather than being tracked separately.

**Depends on:** `accounting`.

**When off:** provisions and contingent liabilities are recorded manually, as today.

---

## 6. Dependency graph

```
                          ┌─────────────────┐
                          │  dimensions     │  (NCoA — existing)
                          └────────┬────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
   ┌────▼─────┐             ┌──────▼──────┐            ┌──────▼──────┐
   │ budget   │             │ accounting  │            │ reporting   │
   │(existing)│             │ (existing)  │            │ (existing)  │
   └────┬─────┘             └──┬───┬───┬──┘            └──────┬──────┘
        │                      │   │   │                      │
   ┌────▼───────────┐   ┌──────▼─┐ │ ┌─▼──────────────┐  ┌────▼──────────┐
   │ budget_prep    │   │ debt   │ │ │ staff_advances │  │ transparency  │
   └────┬───────────┘   └───┬────┘ │ └────────────────┘  └───────────────┘
        │                   │      │
        │              ┌────▼──────▼────┐        ┌──────────────┐
        │              │ cash_planning  │◄───────│  treasury    │
        │              └────────────────┘        │  (existing)  │
        │                                        └──────────────┘
   ┌────▼───────┐
   │  results   │
   └────────────┘

   ┌──────────────┐        ┌──────────────┐       ┌──────────────────┐
   │ procurement  │───────►│    egp       │──────►│   catalogue      │
   │  (existing)  │        └──────┬───────┘       └──────────────────┘
   └──────┬───────┘               │
          │                       ▼
   ┌──────▼───────┐        ┌──────────────┐
   │  contracts   │        │ revenue_admin│◄──── revenue (existing)
   │  (existing)  │        └──────────────┘
   └──────────────┘

   ┌──────────────┐        ┌────────────────────┐
   │  hrm         │───────►│ personnel_budget   │────► budget, accounting
   │  (existing)  │        └────────────────────┘
   └──────┬───────┘
          │                ┌──────────────┐
          └───────────────►│  disclosure  │
                           └──────────────┘

   ┌──────────────┐        ┌────────────────┐     ┌──────────────┐
   │  audit       │───────►│ internal_audit │     │    legal     │────► accounting
   │  (existing)  │        └────────────────┘     └──────────────┘
   └──────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │  integrations — cross-cutting; each connector declares its   │
   │  own dependency (Remita→revenue, NIBSS→treasury,             │
   │  IPPIS→hrm, GIFMIS→accounting)                               │
   └──────────────────────────────────────────────────────────────┘

   ┌──────────────┐
   │    fleet     │────► accounting (fixed assets)
   └──────────────┘
```

**Hard dependencies** (activation rejected if unmet): `personnel_budget`,
`egp`, `revenue_admin`, `catalogue`, `disclosure`, `internal_audit`.
All others degrade gracefully per §3 invariant 4.

---

## 7. Delivery horizons

Ordered by commercial return, not technical dependency.

### Horizon 1 — 0 to 4 months · "Make the current claim true"

Nothing new is sold. Everything here protects the deal already in front of us.

- **§2 backend enforcement** — blocking prerequisite for every module.
- `personnel_budget` — closes the one expenditure stream that escapes commitment control.
- `cash_planning` — turns dormant forecast models into a working engine.
- `staff_advances` — highest-volume everyday gap in an MDA accounts department.
- Correct the MTEF claim in `README.md` and any proposal generated from it.

### Horizon 2 — 4 to 10 months · "Match the pillars"

Close the gaps that appear as empty cells in a side-by-side evaluation matrix.

- `budget_prep` — highest-value single build; converts an OAG product into a Ministry of Finance product.
- `transparency` — cheapest procurement points available.
- `debt` — feeds the cash plan built in Horizon 1.
- `integrations` — turns reference fields into demonstrable integrations.

### Horizon 3 — 10 to 18 months · "Compete head-on"

The builds that let Quot PSA bid against FreeBalance for a whole-of-government scope.

- `egp` — with the public supplier portal.
- `results` — on the existing programme segment.
- `internal_audit` — opens a second buyer inside the OAG.
- `revenue_admin` — build-versus-partner decision at the **start** of this horizon.
- `fleet`, `catalogue`, `disclosure`, `legal` — remaining checklist modules.

---

## 8. What is deliberately not a module

Not every gap in the review is a licensable feature. Recording these here so
they are not lost when the module list is worked through.

| Item | Gap | Why not a module | Owner |
|---|---|---|---|
| Test coverage 32% → 60%, DB-tier tests in CI, IPSAS services above 80% | G12 | Engineering assurance, not a customer-visible feature. Nobody buys it, and it cannot be switched off. It is the evidence a State's technical committee asks for. | Platform |
| Multilingual UI (backend already configured, frontend has no translation bundle) | — | Cross-cutting concern across every module. Building it per module guarantees inconsistency. | Platform |
| Accessibility conformance | — | Same reasoning. Increasingly a procurement requirement. | Platform |
| Backend module enforcement (§2) | — | Infrastructure the module system itself depends on. | Platform |
| README/proposal correction on MTEF | G1 | Documentation accuracy, and a warranty exposure while it stands. Do it in Horizon 1 regardless of when `budget_prep` ships. | Product |

---

## 9. Definition of done

A module is not complete until **all** of the following hold.

**Registry and commercial**
- [ ] `AVAILABLE_MODULES` tuple added; key final and documented here
- [ ] `ModulePricing` row with price, tagline, feature bullets, icon
- [ ] Added to the relevant `SubscriptionPlan.allowed_modules` tiers
- [ ] Seeded in `setup_state_tenant` with the correct default state

**Enforcement**
- [ ] Every ViewSet declares `module_key`; `audit_module_gating` passes
- [ ] `ModuleEnabled` composed with `RBACPermission` on all endpoints
- [ ] Hard dependencies validated at activation with a named error
- [ ] Frontend `MODULE_META` entry and `ModuleGuard` route group
- [ ] Sidebar nav group hidden when off

**Disable safety (§3)**
- [ ] Activation-cycle test passes: activate → post to GL → deactivate →
      reports still balance → reactivate → data intact
- [ ] No cross-module reference crashes when a dependency is off
- [ ] IPSAS statements render correctly with the module off

**Quality**
- [ ] Line coverage ≥ 60% for the module; ≥ 80% for any service that produces
      audit-signed output
- [ ] Permissions registered in the permission catalogue; SoD rules declared
      where the module introduces a new incompatible duty pair
- [ ] Migrations reversible
- [ ] `docs/USER_GUIDE.md` chapter for the role that owns the module
- [ ] OpenAPI schema clean under `drf-spectacular`

**Sign-off**
- [ ] Security review for any module handling personal data, unauthenticated
      traffic or external credentials — `transparency`, `disclosure`,
      `integrations`, `egp` at minimum

---

## Revision history

| Date | Change |
|---|---|
| 2026-09-02 | Initial specification, derived from the FreeBalance competitive review gap register (G1–G13) |
