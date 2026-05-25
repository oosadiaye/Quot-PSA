# Quot PSE — Module Process Flows

> Public-sector IFMIS (Integrated Financial Management Information System) for
> Nigerian state governments. Multi-tenant Django + DRF backend with a React 19
> + Vite frontend. Each tenant is a PostgreSQL schema (`django-tenants`).
>
> This document maps each module's domain process flow and the points where it
> integrates with other modules. Diagrams are Mermaid; render in any
> Markdown viewer that supports Mermaid (GitHub, VS Code with extension,
> MkDocs Material, etc.).
>
> **Last revalidated:** 2026-05-08 — after the 9-finding audit fix-set
> (see `docs/AUDIT/2026-05-08-fix-set.md` if present, or the session
> summary).

---

## Table of contents

1. [System overview](#1-system-overview)
2. [Cross-module integration map](#2-cross-module-integration-map)
3. [Tenants module](#3-tenants-module)
4. [Core module](#4-core-module)
5. [Superadmin module](#5-superadmin-module)
6. [Budget module](#6-budget-module)
7. [Accounting module](#7-accounting-module)
8. [Procurement module](#8-procurement-module)
9. [Contracts module](#9-contracts-module)
10. [Inventory module](#10-inventory-module)
11. [HRM module](#11-hrm-module)
12. [Workflow module](#12-workflow-module)
13. [End-to-end canonical flows](#13-end-to-end-canonical-flows)

---

## 1. System overview

```mermaid
flowchart LR
    subgraph PUBLIC[Public schema]
        TEN[tenants<br/>Client / Domain<br/>UserTenantRole]
        SA[superadmin<br/>Subscriptions / Webhooks<br/>Email templates]
    end

    subgraph TENANT[Per-tenant schema]
        CORE[core<br/>AuditBaseModel<br/>RBAC / AuditLog]
        BUD[budget<br/>Appropriation / Warrant<br/>Virement]
        ACC[accounting<br/>GL / NCoA / Treasury<br/>IPSAS journal engine]
        PROC[procurement<br/>PR / PO / GRN<br/>3-way match]
        CON[contracts<br/>Contract / IPC<br/>Mobilisation / Retention]
        INV[inventory<br/>Items / Stock<br/>Warehouses]
        HR[hrm<br/>Employees / Payroll<br/>Leave]
        WF[workflow<br/>Approval engine<br/>SLA / Delegation]
    end

    TEN -.cache invalidation.-> CORE
    TEN -.enforce_warrant flag.-> BUD

    PROC --> ACC
    PROC --> INV
    PROC --> BUD
    CON --> ACC
    CON --> BUD
    HR --> ACC
    INV --> ACC
    ACC --> BUD
    WF -.signals.-> PROC
    WF -.signals.-> CON
    WF -.signals.-> HR
    WF -.signals.-> BUD

    classDef public fill:#fde68a,stroke:#92400e
    classDef tenant fill:#dbeafe,stroke:#1e40af
    class TEN,SA public
    class CORE,BUD,ACC,PROC,CON,INV,HR,WF tenant
```

**Key architectural facts:**
- `tenants` and `superadmin` live in the **public** schema. Everything else
  is per-tenant (one PostgreSQL schema per state government / MDA).
- `core` is the leaf dependency — every domain module inherits
  `AuditBaseModel` / `StatusTransitionMixin` / `ImmutableModelMixin`
  from it. Core has no domain logic.
- `accounting` is the GL hub. Procurement, Contracts, HRM, Inventory all
  ultimately call `IPSASJournalService.post_journal()` to land their
  effects in the ledger.
- `budget` is the spending gate. Every `JournalHeader → Posted` triggers
  `accounting.signals.budget_enforcement` which calls into
  `budget.services` for STRICT / WARNING / NONE policy decisions.
- `workflow` is a generic multi-step approval engine that any document
  in any module can opt into via a Generic Foreign Key.

---

## 2. Cross-module integration map

```mermaid
flowchart TB
    subgraph TXNAL[Transactional modules]
        PROC[procurement]
        CON[contracts]
        HR[hrm]
        INV[inventory]
    end

    subgraph CTRL[Control modules]
        BUD[budget]
        WF[workflow]
    end

    subgraph LEDGER[Ledger]
        ACC[accounting]
    end

    PROC -- "create_commitment_for_po()" --> ACC
    PROC -- "mark_commitment_invoiced_for_po()" --> ACC
    PROC -- "IPSASJournalService.post_journal()" --> ACC
    PROC -- "StockMovement create()" --> INV
    PROC -- "validate_budget() → check_policy()" --> BUD

    CON -- "IPSASJournalService.post_journal()" --> ACC
    CON -- "PaymentVoucherGov create()" --> ACC
    CON -- "_enforce_appropriation_gate() → check_policy()" --> BUD

    HR -- "PayrollPostingService.post_payroll_run()" --> ACC

    INV -- "InventoryPostingService" --> ACC

    ACC -- "pre_save signal: budget_enforcement" --> BUD
    ACC -- "post_save: refresh_totals(appropriation)" --> BUD

    WF -. "document_approval_completed signal" .-> PROC
    WF -. "document_approval_completed signal" .-> CON
    WF -. "sync_document_status_on_approval" .-> PROC
    WF -. "sync_document_status_on_approval" .-> CON
    WF -. "sync_document_status_on_approval" .-> HR
    WF -. "sync_document_status_on_approval" .-> BUD

    classDef hub fill:#fde68a,stroke:#92400e,stroke-width:2px
    class ACC hub
```

**Integration patterns used:**

| Pattern | Where | Purpose |
|---|---|---|
| **Direct service call** | `IPCService → IPSASJournalService.post_journal()` | Synchronous, atomic GL posting |
| **Django signal** | `JournalHeader.pre_save → check_policy()` | Cross-cutting budget enforcement |
| **Custom Signal** | `workflow.signals.document_approval_completed` | Decoupled post-approval auto-actions |
| **Generic FK** | `workflow.Approval.content_type / object_id` | One approval engine for any document |
| **Helper service** | `inventory.services.get_default_warehouse_for_mda()` | Cross-module lookup without circular import |

---

## 3. Tenants module

**Purpose:** Multi-tenant bootstrap. Each Nigerian state government (or MDA)
gets its own PostgreSQL schema. `Client` rows in the public schema describe
each tenant; `django-tenants` middleware routes requests to the right schema.

### Key models

| Model | File:Line | Role |
|---|---|---|
| `Client` | `tenants/models.py:61` | Tenant root — schema name, branding, feature flags |
| `Domain` | `tenants/models.py:257` | Hostnames mapping to `Client` |
| `TenantModule` | `tenants/models.py:278` | Per-tenant feature toggles (HR, contracts, etc.) |
| `TenantSubscription` | `tenants/models.py:378` | Plan / billing lifecycle |
| `UserTenantRole` | `tenants/models.py:408` | User ↔ tenant ↔ role mapping |
| `SubscriptionPlan` | `tenants/models.py:307` | Pricing tier definitions |

### Process flow

```mermaid
stateDiagram-v2
    [*] --> Provisioned : Client.objects.create()
    Provisioned --> SchemaMigrated : migrate_schemas --tenant
    SchemaMigrated --> ModulesActivated : TenantModule.is_enabled = True
    ModulesActivated --> Subscribed : TenantSubscription created
    Subscribed --> Active
    Active --> Suspended : payment overdue
    Suspended --> Active : payment received
    Active --> Cancelled : tenant offboarded
    Cancelled --> [*]
```

### Integration points

- **Out:** `UserTenantRole` save/delete fires `core.permissions.invalidate_permission_cache()` and `core.cache_utils.invalidate_access_cache()`.
- **Out:** `TenantSubscription` save fires `core.cache_utils.invalidate_subscription_cache()`.
- **In:** `budget.services._is_warrant_enforced()` reads `connection.tenant.enforce_warrant` at posting time.
- **In:** Every request: `django-tenants` middleware sets `connection.tenant` from the hostname; all per-tenant ORM operations rely on this.

---

## 4. Core module

**Purpose:** Pure infrastructure — base model mixins, RBAC, audit log, MFA,
session management, and cross-cutting utilities. **No domain business logic.**

### Key abstractions

| Abstraction | File:Line | Role |
|---|---|---|
| `AuditBaseModel` | `core/models.py:26` | `created_at` / `updated_at` / `created_by` / `updated_by` on every domain model |
| `StatusTransitionMixin` | `core/models.py:86` | Declarative `ALLOWED_TRANSITIONS` dict; gate at `save()` |
| `ImmutableModelMixin` | `core/models.py:48` | Block field edits once a record is `Posted` / `Approved` |
| `AuditLog` | `core/models.py:118` | Append-only audit trail (who-did-what-when) |
| `Role` / `RoleAssignment` | `core/models.py:476 / 610` | RBAC primitives — used by every module's permissions |
| `Organization` | `core/models.py:929` | Optional org structure for non-government tenants |

### Process flow

Core has no state machine of its own — it provides building blocks. The
*pattern* every domain module follows:

```mermaid
sequenceDiagram
    participant U as User / API
    participant V as Domain ViewSet
    participant M as Domain Model<br/>(inherits AuditBaseModel<br/>+ StatusTransitionMixin)
    participant A as core.AuditLog

    U->>V: POST /domain/<id>/transition
    V->>M: instance.status = 'Approved'<br/>instance.save()
    M->>M: validate_status_transition()<br/>(StatusTransitionMixin)
    M->>M: super().save()<br/>(updated_at, updated_by)
    M->>A: AuditLog.objects.create(...)
    A-->>U: 200 OK
```

### Integration points

- **Out:** None — leaf dependency.
- **In:** Every domain module imports from `core`. `accounting`, `procurement`,
  `budget`, `contracts`, `hrm`, `inventory`, `workflow` all inherit
  `AuditBaseModel` / `StatusTransitionMixin` / `ImmutableModelMixin`.

---

## 5. Superadmin module

**Purpose:** Platform-operator (SaaS) layer. Manages tenants, subscriptions,
support tickets, email templates, webhooks, referral commissions, and
global announcements. Lives in the **public** schema.

### Key models

| Model | File:Line | Role |
|---|---|---|
| `SuperAdminProfile` | `superadmin/models.py:14` | Platform staff user profile |
| `ImpersonationLog` | `superadmin/models.py:144` | Audit trail when staff "log in as" tenant user |
| `Referral` / `Commission` | `superadmin/models.py:220 / 248` | Partner / referral payouts |
| `SupportTicket` | `superadmin/models.py:331` | Inbound support queue |
| `WebhookConfig` / `WebhookDelivery` | `superadmin/models.py:590 / 631` | Outbound webhook + retry tracking |
| `EmailTemplate` | `superadmin/models.py:79` | Multi-language editable templates |

### Process flow — typical operator workflow

```mermaid
flowchart LR
    A[Onboard tenant] --> B[Create Client<br/>+ Domain]
    B --> C[migrate_schemas<br/>--tenant]
    C --> D[Activate TenantModule<br/>flags]
    D --> E[Create initial<br/>UserTenantRole]
    E --> F[Tenant goes live]
    F -.support.-> G[SupportTicket queue]
    F -.billing.-> H[TenantSubscription<br/>state machine]
    F -.events.-> I[WebhookDelivery<br/>fan-out + retry]
```

### Integration points

- Largely self-contained at the public schema. Reads `tenants.Client` for
  impersonation and subscription reporting.
- No inbound module dependencies (per-tenant modules don't reach into
  superadmin).

---

## 6. Budget module

**Purpose:** Nigerian IFMIS budget lifecycle — annual appropriation enacted by
the State House of Assembly, then released in tranches as Warrants (AIE —
Authority to Incur Expenditure). Enforces spending gates against the
Appropriation register.

### Key models

| Model | File:Line | Role |
|---|---|---|
| `UnifiedBudget` | `budget/models.py:29` | Logical budget container — wraps Appropriation, Revenue, Virement |
| `Appropriation` | `budget/models.py:660` | The legal spending authority for one (MDA × economic × fund × FY) tuple |
| `Warrant` | `budget/models.py:1223` | AIE — releases cash within `[effective_from, effective_to]` |
| `AppropriationVirement` | `budget/models.py:1521` | Reallocation between appropriation lines |
| `RevenueBudget` | `budget/models.py:1432` | Revenue targets (separate from expenditure budget) |
| `WarrantPrintoutSettings` | `budget/models.py` | Tenant-wide letterhead/signatures config for printed AIEs |

### Process flow — Appropriation

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED : submit_for_approval()
    SUBMITTED --> APPROVED : workflow approval
    APPROVED --> ENACTED : House of Assembly enacts<br/>Appropriation Act
    ENACTED --> ACTIVE : auto on FY start
    ACTIVE --> CLOSED : FY end + final close

    note right of ACTIVE
      Spending allowed:
      total_expended +
      total_committed
      <= amount_approved
    end note
```

### Process flow — Warrant (AIE)

```mermaid
stateDiagram-v2
    [*] --> PENDING : Warrant created
    PENDING --> RELEASED : AG signs
    RELEASED --> EXHAUSTED : sum(payments) == amount_released
    RELEASED --> EXPIRED : effective_to date passed<br/>(daily expire_warrants sweep)
    RELEASED --> SUSPENDED : AG suspends
    SUSPENDED --> RELEASED : reinstated

    note right of EXPIRED
      Marked by daily Task
      Scheduler job:
      expire_warrants_all_tenants
    end note
```

### Process flow — spend authorisation

```mermaid
flowchart TB
    A[Any expenditure attempt<br/>PR / PO / IPC / JV] --> B{find_matching_appropriation<br/>by MDA × Economic × Fund × FY}
    B -- no match --> C[BudgetCheckRule.policy:<br/>STRICT / WARNING / NONE]
    B -- match found --> D[check_policy<br/>amount_approved -<br/>committed - expended<br/>>= requested?]
    D -- yes --> E{Warrant pre-payment<br/>enforced?<br/>Client.enforce_warrant}
    D -- no --> X[BudgetExceededError]
    E -- yes --> F[check_warrant_availability<br/>against released warrants]
    E -- no --> G[Pass]
    F -- exceeded --> X
    F -- ok --> G
    C -- STRICT --> X
    C -- WARNING/NONE --> G
    X --> Z[Transaction rolls back]
```

### Integration points

- **Out:** `budget.services.BudgetValidationService.validate_expenditure()` — called by accounting, procurement, contracts before any expenditure.
- **Out:** `_is_warrant_enforced()` reads `tenants.Client.enforce_warrant`.
- **In:** `accounting.signals.budget_enforcement.pre_save(JournalHeader)` calls `check_policy()` and `check_warrant_availability()`.
- **In:** `accounting.signals.budget_enforcement.post_save(JournalHeader)` calls `appropriation_totals.refresh_totals(appropriation)` to keep `cached_total_committed` / `cached_total_expended` fresh.
- **In:** `procurement.PurchaseRequest.validate_budget()` and `PurchaseOrder.process_budget_encumbrance()` call `accounting.services.budget_check_rules.check_policy()`.
- **In:** `contracts.IPCService._enforce_appropriation_gate()` calls `check_policy()` before posting the IPC accrual journal.

---

## 7. Accounting module

**Purpose:** Single source of truth for the General Ledger. Implements the
6-segment Nigerian Chart of Accounts (NCoA), IPSAS-accrual journal engine,
TSA / treasury cash management, fixed assets, payroll posting (delegated
target), tax / WHT, period close, and statutory reporting.

### Key models

| Model | File:Line | Role |
|---|---|---|
| `JournalHeader` / `JournalLine` | `accounting/models/gl.py:263` | The GL — DR=CR enforced |
| `Account` | `accounting/models/gl.py:128` | Chart of Accounts row |
| `NCoACode` | `accounting/models/ncoa.py:389` | 6-segment classification (admin, economic, functional, programme, fund, geo) |
| `PaymentVoucherGov` | `accounting/models/treasury.py:124` | Government payment voucher — primary cash-out document |
| `TreasuryAccount` | `accounting/models/treasury.py:16` | TSA hierarchy (Main, Sub-Account, Zero-Balance) |
| `PaymentInstruction` | `accounting/models/treasury.py:308` | Bank-bound instruction (NIBSS / RTGS) |
| `BudgetCheckRule` | `accounting/models/...` | Per-account policy: STRICT / WARNING / NONE |

### Process flow — Journal Header

```mermaid
stateDiagram-v2
    [*] --> Draft : JournalHeader.objects.create()
    Draft --> Pending : submit_for_approval()
    Pending --> Approved : workflow approval
    Approved --> Posted : IPSASJournalService.post_journal()<br/>(DR=CR, NCoA valid, no control-acct,<br/>budget gate via signal)
    Posted --> Reversed : JournalReversal<br/>(creates mirror journal)

    note right of Posted
      ImmutableModelMixin
      blocks any field edits
      after Posted.
    end note
```

### Process flow — Payment Voucher (PV)

```mermaid
stateDiagram-v2
    [*] --> DRAFT : created from IPC / VendorInvoice / Payroll
    DRAFT --> CHECKED : voucher checker
    CHECKED --> AUDITED : internal audit
    AUDITED --> APPROVED : AG / authoriser
    APPROVED --> SCHEDULED : queued for bank file
    SCHEDULED --> PAID : PaymentInstruction processed<br/>TSABalanceService.process_payment()
    APPROVED --> CANCELLED : pre-payment cancel
    PAID --> REVERSED : exceptional reversal
```

### Process flow — IPSAS journal posting

```mermaid
sequenceDiagram
    participant Caller as Caller<br/>(procurement / contracts / hrm)
    participant Service as IPSASJournalService
    participant Sig as accounting.signals<br/>budget_enforcement
    participant Bud as budget.services<br/>check_policy
    participant DB as PostgreSQL

    Caller->>Service: post_journal(journal, actor)
    Service->>Service: validate DR == CR
    Service->>Service: validate NCoA tags
    Service->>Service: forbid posting to<br/>control accounts
    Service->>DB: JournalHeader.status = 'Posted'<br/>(triggers signal)
    DB->>Sig: pre_save signal
    Sig->>Bud: check_policy(account, amount, appropriation)
    alt policy.blocked
        Bud-->>Sig: BudgetExceededError
        Sig-->>DB: rollback
        DB-->>Caller: ValidationError
    else allowed
        Bud-->>Sig: ok
        DB-->>Sig: post_save
        Sig->>Bud: refresh_totals(appropriation)
        DB-->>Service: committed
        Service-->>Caller: journal returned
    end
```

### Integration points

- **Out:** `accounting/signals/budget_enforcement.py` → `budget.models.Appropriation` (refresh totals).
- **Out:** `accounting/signals/coa_to_ncoa.py` on `Account` save → upserts `NCoACode / EconomicSegment` (internal CoA ↔ NCoA mirror).
- **In (procurement):** `ProcurementPostingService`, `create_commitment_for_po()`, `mark_commitment_invoiced_for_po()`, `_post_matching_to_gl_inner()`.
- **In (contracts):** `IPSASJournalService.post_journal()` from `IPCService.approve()`, `PaymentVoucherGov.objects.create()` from `IPCService.create_draft_voucher()`.
- **In (hrm):** `PayrollPostingService.post_payroll_run()` from `PayrollRun.save()` on Approved.
- **In (inventory):** `InventoryPostingService` on `StockMovement` create.

---

## 8. Procurement module

**Purpose:** Procurement-to-payment (P2P) cycle. Vendor registry, purchase
requests, purchase orders with budget commitment, goods received notes,
3-way invoice match, and vendor performance.

### Key models

| Model | File:Line | Role |
|---|---|---|
| `Vendor` | `procurement/models.py:77` | Supplier master (with KYC, bank, tax IDs) |
| `PurchaseRequest` | `procurement/models.py:244` | Internal request — pre-PO |
| `PurchaseOrder` | `procurement/models.py:448` | Authorised order to vendor — budget commitment |
| `GoodsReceivedNote` | `procurement/models.py:926` | Receipt confirmation — feeds inventory |
| `InvoiceMatching` | `procurement/models.py:1431` | 3-way match: PO ↔ GRN ↔ Vendor Invoice |
| `ProcurementBudgetLink` | (in accounting models) | Per-PO encumbrance row in Appropriation register |

### Process flow — full P2P cycle

```mermaid
stateDiagram-v2
    state PR {
        [*] --> Draft_PR : Draft
        Draft_PR --> Pending_PR : Pending<br/>submit_for_approval()<br/>+ auto_route_approval
        Pending_PR --> Approved_PR : Approved<br/>(SoD: requester ≠ approver)
        Pending_PR --> Rejected_PR : Rejected
        Rejected_PR --> Draft_PR
    }

    state PO {
        [*] --> Draft_PO : Draft
        Draft_PO --> Pending_PO : Pending
        Pending_PO --> Approved_PO : Approved<br/>process_budget_encumbrance()<br/>+ create_commitment_for_po()
        Approved_PO --> PartiallyReceived
        PartiallyReceived --> Received
        Approved_PO --> Cancelled
    }

    state GRN {
        [*] --> Draft_GRN : Draft
        Draft_GRN --> Posted_GRN : Posted<br/>StockMovement created<br/>mark_commitment_invoiced_for_po()
        Draft_GRN --> Cancelled_GRN : Cancelled
    }

    state Inv {
        [*] --> Draft_INV : Draft
        Draft_INV --> Pending_INV : Pending
        Pending_INV --> Approved_INV : Approved (3-way match)<br/>workflow signal fires<br/>_post_matching_to_gl_inner()<br/>commitment → CLOSED
    }

    Approved_PR --> Draft_PO : convert PR → PO
    Approved_PO --> Draft_GRN : goods delivered
    Posted_GRN --> Draft_INV : vendor invoice received
    Approved_INV --> [*] : Payment Voucher path
```

### Process flow — sequence (PR → Payment)

```mermaid
sequenceDiagram
    participant U as Requester
    participant PR as PurchaseRequest
    participant W as workflow.Approval
    participant PO as PurchaseOrder
    participant BCR as budget.check_policy
    participant ACC as accounting<br/>(commitment + GL)
    participant INV as inventory
    participant GRN as GoodsReceivedNote
    participant IM as InvoiceMatching
    participant PV as PaymentVoucherGov

    U->>PR: create + submit_for_approval
    PR->>W: auto_route_approval()
    W->>PR: Approved (SoD enforced)
    PR->>PO: convert (Draft)
    PO->>PO: approve()
    PO->>BCR: check_policy() w/ select_for_update
    BCR-->>PO: ok
    PO->>ACC: create_commitment_for_po()<br/>ProcurementBudgetLink.ACTIVE

    Note over PO,GRN: Goods delivered
    GRN->>GRN: Post()
    GRN->>INV: StockMovement create
    GRN->>ACC: mark_commitment_invoiced_for_po()<br/>ProcurementBudgetLink.INVOICED

    Note over GRN,IM: Vendor invoice arrives
    IM->>IM: 3-way match (PO=GRN=Invoice)
    IM->>BCR: check_policy(invoice_amount)
    IM->>W: submit_for_approval
    W-->>IM: Approved (signal)
    IM->>ACC: _post_matching_to_gl_inner()<br/>DR GR/IR Clearing, CR AP<br/>ProcurementBudgetLink.CLOSED
    ACC->>PV: spawn PaymentVoucherGov(DRAFT)
    PV->>PV: CHECKED → AUDITED → APPROVED → PAID
```

### Integration points

- **Out (accounting):** `create_commitment_for_po()`, `mark_commitment_invoiced_for_po()`, `cancel_commitment_for_po()`, `IPSASJournalService.post_journal()`, `ProcurementPostingService`.
- **Out (inventory):** `StockMovement` created inline in `GoodsReceivedNote.save()`; `inventory.services.get_default_warehouse_for_mda()` resolves MDA → Warehouse.
- **Out (budget):** `PurchaseRequest.validate_budget()` and `PurchaseOrder.process_budget_encumbrance()` call `accounting.services.budget_check_rules.check_policy()`.
- **In (workflow):** `workflow.signals.document_approval_completed` → `procurement.signals.auto_post_invoicematching_on_approval`.

---

## 9. Contracts module

**Purpose:** Capital / infrastructure contract management — activation,
milestones, measurement books, Interim Payment Certificates (IPCs) with
**ten** structural overpayment-prevention controls, mobilisation advances,
retention holdback, and variations / write-ups.

### Key models

| Model | File:Line | Role |
|---|---|---|
| `Contract` | `contracts/models/contract.py:78` | Aggregate root — vendor, NCoA, fiscal year, ceiling |
| `ContractBalance` | `contracts/models/contract.py:324` | Real-time spending ledger (locked per IPC) |
| `ContractYearPlan` | `contracts/models/year_plan.py` | Multi-year split — one row per fiscal year |
| `MilestoneSchedule` | `contracts/models/contract.py:465` | Deliverables + payment triggers |
| `MeasurementBook` | `contracts/models/payment.py:42` | On-site quantity record |
| `InterimPaymentCertificate` | `contracts/models/payment.py:161` | Periodic payment certificate |
| `MobilizationPayment` | `contracts/models/payment.py:414` | Up-front advance |
| `RetentionRelease` | `contracts/models/payment.py:470` | Practical / final retention release |
| `Variation` | `contracts/models/variation.py` | "Write-up" — upward contract revision |

### Process flow — Contract lifecycle

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> ACTIVATED : ContractActivationService.activate()<br/>+ ContractYearPlan rows<br/>+ ContractBalance row<br/>SoD: activator ≠ creator
    ACTIVATED --> IN_PROGRESS : first IPC submitted
    IN_PROGRESS --> PRACTICAL_COMPLETION
    PRACTICAL_COMPLETION --> DEFECTS_LIABILITY : retention partially released
    DEFECTS_LIABILITY --> FINAL_COMPLETION : final retention release
    FINAL_COMPLETION --> CLOSED
```

### Process flow — IPC lifecycle (the 10-control engine)

```mermaid
stateDiagram-v2
    [*] --> DRAFT : IPC created
    DRAFT --> SUBMITTED : IPCService.submit_ipc()<br/>Controls 1, 3, 7, 8 fire<br/>SELECT FOR UPDATE on ContractBalance
    SUBMITTED --> CERTIFIER_REVIEWED : IPCService.certify()<br/>Control 9 (3-way w/ MeasurementBook)<br/>SoD: certifier ≠ drafter
    CERTIFIER_REVIEWED --> APPROVED : IPCService.approve()<br/>Controls 1, 2 re-checked<br/>_enforce_appropriation_gate()<br/>_post_accrual_journal()<br/>SoD: approver ≠ drafter ≠ certifier
    APPROVED --> VOUCHER_RAISED : IPCService.raise_voucher()<br/>spawns PaymentVoucherGov(DRAFT)<br/>SoD: raiser ≠ above
    VOUCHER_RAISED --> PAID : IPCService.mark_paid()<br/>VAT / WHT recognised at cash<br/>SoD: payer ≠ above
    PAID --> [*]
```

**Ten structural controls (enforced by `IPCService`):**
1. Ceiling — certified + pending ≤ contract_ceiling
2. Coherence — net_payable recomputed and reconciled
3. Monotonicity — cumulative work-done never decreases
4. Mobilization recovery — delegated to `MobilizationService`
5. Retention cap — delegated to `RetentionService`
6. Variation approval — only APPROVED variations count
7. Duplicate IPC — `integrity_hash` uniqueness (DB partial index)
8. Fiscal-year boundary — `posting_date` inside `year_plan.fiscal_year`
9. Three-way match — IPC ↔ MeasurementBook ↔ PaymentVoucher
10. Segregation of Duties — submitter ≠ certifier ≠ approver ≠ voucher-raiser ≠ payer

### Process flow — IPC approval sequence

```mermaid
sequenceDiagram
    participant A as Approver
    participant I as IPCService
    participant CB as ContractBalance
    participant V as VariationService
    participant Mob as MobilizationService
    participant Ret as RetentionService
    participant BCR as budget.check_policy
    participant J as IPSASJournalService

    A->>I: approve(ipc, actor)
    I->>I: SoD check (approver ≠ drafter ≠ certifier)
    I->>CB: SELECT FOR UPDATE
    CB-->>I: locked balance
    I->>V: refresh_contract_ceiling()
    I->>I: Control 2 — coherence check
    I->>I: Control 1 — re-check ceiling
    I->>Mob: apply_recovery()
    I->>Ret: apply_deduction()
    I->>CB: UPDATE certified += gross<br/>version += 1 (PG trigger)
    I->>BCR: _enforce_appropriation_gate()<br/>(audit fix #1)
    BCR-->>I: ok or BudgetExceededError
    I->>J: _post_accrual_journal()<br/>DR Expense, CR Mob/Retention/AP<br/>(document_number set, audit fix #6)
    J-->>I: posted journal
    I->>I: ipc.transition_to(APPROVED)
    I-->>A: ipc returned
```

### Integration points

- **Out (accounting):** `IPSASJournalService.post_journal()` (IPC approval), `PaymentVoucherGov.objects.create()` (voucher raise), `accounting.services.procurement_posting.get_vendor_ap_account()`.
- **Out (budget):** `IPCService._enforce_appropriation_gate()` calls `find_matching_appropriation()` + `check_policy()` against the IPSAS Appropriation register before the accrual journal is created.
- **Out (workflow):** `Variation` and `IPC` approval steps optionally route via `workflow.Approval`.
- **In (workflow):** `workflow.signals.sync_document_status_on_approval` writes back into `ContractApprovalStep.status`.

---

## 10. Inventory module

**Purpose:** Item / stock master, warehouse stock ledger, reservations,
batch / serial tracking, reorder alerts, inter-warehouse transfers.

### Key models

| Model | File:Line | Role |
|---|---|---|
| `Item` | `inventory/models.py:11` | Item master — SKU, unit, GL accounts |
| `ItemStock` | `inventory/models.py:264` | Per-warehouse quantity + reserved snapshot |
| `StockMovement` | `inventory/models.py:503` | Atomic IN / OUT / ADJ / TRF event |
| `ItemBatch` | `inventory/models.py:207` | Batch / lot tracking with expiry |
| `Warehouse` | `inventory/models.py:675` | Physical / virtual location |
| `Reservation` | `inventory/models.py:766` | Soft-allocation against a future need |

### Process flow — stock movement

```mermaid
flowchart LR
    A[Trigger:<br/>GRN posted /<br/>issue / transfer] --> B[StockMovement<br/>.objects.create]
    B --> C{movement_type}
    C -- IN --> D[update_stock_on_movement<br/>ItemStock.quantity += qty<br/>F-expression atomic]
    C -- OUT --> E[update_stock_on_movement<br/>ItemStock.quantity -= qty<br/>+ decrement_batch_on_out]
    C -- ADJ --> F[adjustment line<br/>+/- qty]
    C -- TRF --> G[paired OUT + IN]
    D --> H[InventoryPostingService<br/>JournalHeader<br/>DR Inventory / CR GR/IR]
    E --> H
    F --> H
    G --> H
```

### Process flow — reservation

```mermaid
stateDiagram-v2
    [*] --> Active : Reservation created
    Active --> Fulfilled : stock issued against it
    Active --> Cancelled : released manually
    Fulfilled --> [*]
    Cancelled --> [*]

    note right of Active
      sync_reserved_quantity
      keeps ItemStock.reserved
      in sync via signal
    end note
```

### Integration points

- **Out (accounting):** `InventoryPostingService` creates `JournalHeader` / `JournalLine` for stock movements (capitalised inventory accounting).
- **In (procurement):** `GoodsReceivedNote.save()` creates `StockMovement` rows inline; calls `inventory.services.get_default_warehouse_for_mda()`.

---

## 11. HRM module

**Purpose:** Employee master, leave / attendance, recruitment pipeline,
payroll runs with salary structures and Nigerian statutory deductions
(PAYE, pension, NHF, NSITF).

### Key models

| Model | File:Line | Role |
|---|---|---|
| `Employee` | `hrm/models.py:56` | Staff master — grade, MDA, bank, tax IDs |
| `SalaryStructure` | `hrm/models.py:460` | Grade × component matrix |
| `PayrollPeriod` | `hrm/models.py:544` | Monthly payroll cycle row |
| `PayrollRun` | `hrm/models.py:573` | One run = one MDA × one period |
| `PayrollLine` | `hrm/models.py:632` | Per-employee gross / deductions / net |
| `LeaveRequest` | `hrm/models.py:171` | Leave application + balance tracking |

### Process flow — Payroll Run

```mermaid
stateDiagram-v2
    [*] --> Draft : PayrollRun created<br/>for (MDA, PayrollPeriod)
    Draft --> InProgress : compute()<br/>generates PayrollLine rows<br/>applies SalaryStructure + deductions
    InProgress --> Approved : workflow approval<br/>(typically AG / HR Director)
    Approved --> Paid : PayrollPostingService.post_payroll_run()<br/>creates JournalHeader<br/>spawns PaymentVoucherGov(s)
    Paid --> [*]

    note right of Approved
      DR Salary Expense
      CR Payroll Liability
      CR Tax Payable (PAYE)
      CR Pension Payable
      CR NHF Payable
    end note
```

### Process flow — Leave Request

```mermaid
stateDiagram-v2
    [*] --> Pending : Employee submits
    Pending --> Approved : manager approves<br/>(deducts from leave balance)
    Pending --> Rejected
    Approved --> Cancelled : pre-start cancel<br/>(refunds balance)
    Approved --> Taken : auto on end_date
```

### Integration points

- **Out (accounting):** `PayrollPostingService.post_payroll_run()` creates `JournalHeader`; `PayrollRun.payroll_expense_account` is a FK to `accounting.Account`; `PayrollRun.journal_entry` FK is set on completion.
- **In:** None — no other module calls into HRM.

---

## 12. Workflow module

**Purpose:** Generic multi-step approval engine. Any document in any module
can attach an `Approval` (via `ContentType` GFK) with one or more
`ApprovalStep`s, SLA tracking, and delegation.

### Key models

| Model | File:Line | Role |
|---|---|---|
| `Approval` | `workflow/models.py:162` | The approval instance, points at any document |
| `ApprovalStep` | `workflow/models.py:218` | One reviewer's step |
| `ApprovalTemplate` | `workflow/models.py:116` | Named template (e.g. "PO ≥ ₦10M") |
| `ApprovalTemplateStep` | `workflow/models.py:148` | Template step definition (tier, role, threshold) |
| `ApprovalDelegation` | `workflow/models.py:340` | "While I'm on leave, route to X" |
| `ApprovalSLAViolation` | `workflow/models.py:298` | SLA breach record for reporting |

### Process flow — generic approval

```mermaid
stateDiagram-v2
    [*] --> Draft : auto_route_approval(doc)<br/>resolves ApprovalTemplate<br/>creates Approval + Steps
    Draft --> Pending : first step assigned
    Pending --> Pending : intermediate step approved<br/>+ next step assigned
    Pending --> Approved : final step approved<br/>signal: document_approval_completed
    Pending --> Rejected : any step rejected<br/>signal: document_approval_completed
    Approved --> [*]
    Rejected --> [*]

    note right of Approved
      sync_document_status_on_approval
      writes back to doc.status
      respecting ALLOWED_TRANSITIONS
    end note
```

### Process flow — multi-tier approval (example: PO ≥ ₦10M)

```mermaid
sequenceDiagram
    participant U as Requester
    participant Doc as PurchaseOrder
    participant W as auto_route_approval
    participant A as Approval
    participant S1 as Step 1 (HOD)
    participant S2 as Step 2 (Director)
    participant S3 as Step 3 (AG)
    participant Sig as Signal Bus

    U->>Doc: submit_for_approval
    Doc->>W: auto_route_approval(Doc)
    W->>A: resolve template by amount
    W->>S1: assign first step
    S1-->>A: approve
    A->>S2: assign next step
    S2-->>A: approve
    A->>S3: assign final step
    S3-->>A: approve
    A->>A: status = Approved
    A->>Sig: document_approval_completed.send(...)
    Sig->>Doc: sync_document_status<br/>(Doc.status = Approved)
    Sig->>Doc: auto_post_invoicematching_on_approval<br/>(if applicable)
```

### Integration points

- **Out:** Custom Django Signal `document_approval_completed` (consumed by `procurement.signals.auto_post_invoicematching_on_approval`).
- **Out:** `sync_document_status_on_approval` writes back to any document with a `status` field across all modules.
- **In:** Every module that wants workflow-gated approval calls `auto_route_approval(document, ...)` from its `submit_for_approval` action — `procurement`, `contracts`, `budget`, `hrm` all use this.

---

## 13. End-to-end canonical flows

### 13.1 Procurement-to-Payment (P2P) — full flow

```mermaid
flowchart TD
    Start([User: I need to buy laptops]) --> PR[PurchaseRequest<br/>Draft]
    PR --> PRSub[submit_for_approval]
    PRSub --> WF1[workflow.Approval<br/>routes to approver]
    WF1 --> PRApp[PR Approved<br/>+ check_policy gate]

    PRApp --> PO[PurchaseOrder<br/>Draft]
    PO --> POApp[PO Approved<br/>process_budget_encumbrance<br/>create_commitment_for_po<br/>SELECT FOR UPDATE Appropriation]

    POApp --> Vendor([Vendor delivers goods])
    Vendor --> GRN[GoodsReceivedNote<br/>Posted]
    GRN --> StockMv[StockMovement created<br/>ItemStock += qty]
    GRN --> Commit2[ProcurementBudgetLink<br/>ACTIVE → INVOICED]

    Commit2 --> InvoiceArr([Vendor invoice arrives])
    InvoiceArr --> IM[InvoiceMatching<br/>Draft → 3-way match]
    IM --> IMVar{variance ≤ 5%?}
    IMVar -- yes --> IMApp[Submit for approval]
    IMVar -- no --> Hold[payment_hold = True<br/>variance review]
    Hold --> Override[manual override<br/>+ reason]
    Override --> IMApp
    IMApp --> WF2[workflow.Approval]
    WF2 --> Posted[Auto-post via signal:<br/>DR GR/IR, CR AP<br/>+ PPV journal if variance]
    Posted --> CommitClose[ProcurementBudgetLink<br/>→ CLOSED]

    Posted --> PV[PaymentVoucherGov<br/>DRAFT spawned]
    PV --> PVCheck[CHECKED]
    PVCheck --> PVAud[AUDITED]
    PVAud --> PVApp[APPROVED]
    PVApp --> PVSched[SCHEDULED]
    PVSched --> PI[PaymentInstruction<br/>NIBSS / RTGS]
    PI --> PVPaid[PAID<br/>TSABalanceService.process_payment<br/>DR AP, CR TSA Bank]
    PVPaid --> Done([Vendor paid])

    classDef gate fill:#fef3c7,stroke:#92400e
    class POApp,Posted,PVPaid gate
```

### 13.2 Contract-to-Payment (C2P) — full flow

```mermaid
flowchart TD
    Start([Capital project awarded]) --> CDraft[Contract<br/>DRAFT]
    CDraft --> CAct[ContractActivationService<br/>.activate]
    CAct --> CYP[ContractYearPlan rows<br/>created — multi-year split]
    CAct --> CB[ContractBalance row<br/>created]
    CAct --> CActive[Contract<br/>ACTIVATED]

    CActive --> Mob[MobilizationPayment<br/>up-front advance<br/>spawns PaymentVoucher]
    CActive --> MS[MilestoneSchedule<br/>defined]

    MS --> Work([Contractor delivers work])
    Work --> MB[MeasurementBook<br/>posted on-site qty]
    MB --> IPCDraft[IPC Draft<br/>compute net_payable]

    IPCDraft --> IPCSub[IPCService.submit_ipc<br/>Controls 1, 3, 7, 8<br/>SELECT FOR UPDATE ContractBalance]
    IPCSub --> IPCCert[Certifier review<br/>Control 9: 3-way w/ MB]
    IPCCert --> IPCApp[Approver review<br/>Controls 1, 2 re-check<br/>_enforce_appropriation_gate<br/>= check_policy + Appropriation]

    IPCApp --> Accrual[_post_accrual_journal<br/>DR Expense<br/>CR Mob Advance<br/>CR Retention Held<br/>CR AP<br/>document_number set]

    Accrual --> Voucher[create_draft_voucher<br/>TSA routed by MDA<br/>spawns PaymentVoucherGov]
    Voucher --> PVFlow[PV: DRAFT → CHECKED →<br/>AUDITED → APPROVED →<br/>SCHEDULED → PAID]
    PVFlow --> Cash[VAT / WHT recognised<br/>at cash time<br/>cumulative_gross_paid += net]
    Cash --> Repeat{more milestones?}
    Repeat -- yes --> Work
    Repeat -- no --> Final[Final IPC<br/>+ RetentionRelease<br/>+ Contract → CLOSED]
    Final --> Done([Contract complete])

    classDef gate fill:#fef3c7,stroke:#92400e
    class IPCApp,PVFlow gate
```

### 13.3 Budget enactment → Spend gate

```mermaid
flowchart TD
    Bill([Annual Appropriation Bill]) --> AD[Appropriation<br/>DRAFT]
    AD --> AS[SUBMITTED]
    AS --> AA[APPROVED<br/>by Cabinet]
    AA --> AE[ENACTED<br/>House of Assembly<br/>Appropriation Act]
    AE --> AAct[ACTIVE<br/>at FY start]

    AAct --> WPlan[Quarterly cash plan]
    WPlan --> WP[Warrant<br/>PENDING]
    WP --> WR[RELEASED<br/>by AG]

    WR --> Spend{Any expenditure<br/>attempt}
    Spend --> CP[check_policy<br/>amount_approved<br/>- committed - expended<br/>>= requested?]
    CP -- yes --> WE{enforce_warrant?}
    CP -- no --> Block[BudgetExceededError]
    WE -- yes --> CW[check_warrant_availability<br/>against released warrants]
    WE -- no --> Pass[Allow]
    CW -- ok --> Pass
    CW -- exceeded --> Block
    Pass --> Posted[JournalHeader → Posted<br/>refresh_totals fires]

    WR --> ExpireCheck{effective_to<br/>< today?}
    ExpireCheck -- yes --> WE2[Daily sweep:<br/>expire_warrants_all_tenants<br/>→ EXPIRED]
    ExpireCheck -- no --> WR

    classDef gate fill:#fef3c7,stroke:#92400e
    class CP,CW gate
```

### 13.4 Payroll → GL → Treasury

```mermaid
flowchart LR
    A[PayrollPeriod opens] --> B[PayrollRun<br/>Draft<br/>for MDA × Period]
    B --> C[Compute<br/>Apply SalaryStructure<br/>Apply statutory deductions]
    C --> D[InProgress]
    D --> E[Workflow approval<br/>HR Director / AG]
    E --> F[Approved]
    F --> G[PayrollPostingService<br/>.post_payroll_run]
    G --> H[JournalHeader Posted<br/>DR Salary Expense<br/>CR Payroll Liability<br/>CR PAYE / Pension / NHF]
    H --> I[Spawn PaymentVoucherGov<br/>per beneficiary group]
    I --> J[PV → SCHEDULED → PAID]
    J --> K[TSA Bank balance<br/>decremented]

    classDef gate fill:#fef3c7,stroke:#92400e
    class H,J gate
```

---

## Appendix A — Files map (where to look)

| Concern | Primary location |
|---|---|
| GL posting engine | `accounting/services/ipsas_journal_service.py` |
| Budget policy resolver | `accounting/services/budget_check_rules.py` |
| Budget enforcement signal | `accounting/signals/budget_enforcement.py` |
| Procurement commitments | `accounting/services/procurement_commitments.py` |
| Contract IPC engine | `contracts/services/ipc_service.py` |
| Contract activation | `contracts/services/contract_activation.py` |
| Mobilisation / retention | `contracts/services/mobilization_service.py`, `retention_service.py` |
| Workflow auto-routing | `workflow/views.py: auto_route_approval()` |
| Workflow signals | `workflow/signals.py` |
| TSA cash service | `accounting/services/tsa_balance_service.py` |
| Payroll posting | `accounting/services/payroll_posting.py` |
| Inventory posting | `accounting/services/inventory_posting.py` |
| Tenant-scope routing | `tenants/middleware.py` (django-tenants) |
| Daily warrant expiry | `budget/management/commands/expire_warrants_all_tenants.py` |

## Appendix B — Status palette (UI reference)

| Status | Hex | Used by |
|---|---|---|
| DRAFT / Pending | `#f59e0b` (amber) | All modules |
| APPROVED / RELEASED / POSTED | `#22c55e` (green) | All modules |
| REJECTED / FAILED / CANCELLED | `#ef4444` (red) | All modules |
| EXPIRED / SUSPENDED | `#b45309` (rust) | budget.Warrant |
| EXHAUSTED | `#64748b` (slate) | budget.Warrant |
| Posted (immutable) | `#166534` (deep green) | accounting.JournalHeader |
| PAID | `#16a34a` (emerald) | accounting.PaymentVoucherGov |

---

*End of document.*
