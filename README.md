# Quot PSA — Public Sector Accounting

**Quot PSA** is a dedicated, full-stack **Public Sector Accounting** solution purpose-built for Federal, State, and Local Government treasuries, MDAs, parastatals, and revenue agencies operating under Nigeria's IFMIS framework and the IPSAS reporting standard.

> Quot PSA is **not** a private-sector ERP with a "government mode" bolted on. Every module — budgeting, commitments, treasury, revenue, payroll, assets, and reporting — is designed around the constitutional, legal, and fiscal-control requirements that govern public money. It is functionally and architecturally independent from any commercial ERP product.

---

## Scope — what "Public Sector" means here

| Domain | Capability |
|---|---|
| **Budget preparation** | Multi-year MTEF envelope → Sector envelope → MDA ceiling → Line-item budget with functional (COFOG) and programme classification |
| **Appropriation & Warrants** | Appropriation Act loading, AIE issuance, recurrent/capital warrants, MDA releases |
| **Commitment control** | Purchase Requisition → LPO with **budget-line pre-encumbrance**; blocks over-commitment before it reaches AP |
| **Procurement** | BPP-aligned procurement (open tender, selective tender, RFQ, direct procurement), vendor registration, contract register |
| **Contracts & IPCs** | Works/services contracts with Interim Payment Certificates, retention, mobilisation recovery, defects-liability |
| **Treasury Single Account (TSA)** | TSA hierarchy, MDA sub-accounts, zero-balance accounts, deterministic TSA→GL mapping for IPSAS cash-flow reporting |
| **Revenue management** | Revenue heads, collection channels (POS, online, bank), receipts, NCoA economic classification |
| **Payroll & Pension** | IPPIS-style payroll, PAYE, pension contributions (PRA 2014), Group Life, batch pay to TSA |
| **Fixed assets** | IPSAS 17 compliant — asset categories with GL mapping, depreciation (5 methods), revaluation (IAS 16), disposal, impairment |
| **Financial reporting** | IPSAS Cash-Basis & Accrual, Budget vs Actual (GFS 2014), Consolidated Revenue Fund Statement, Notes to FS, Cash Flow Statement |

---

## Why this is separate from private-sector ERP

Public sector accounting differs from commercial accounting in ways that cannot be retrofitted:

1. **Appropriation is law, not policy.** Every expenditure is gated by an Appropriation Act line. No such concept exists in a private P&L.
2. **Fund accounting** — money is restricted by fund source (CRF, Development Fund, IGR, Donor), not general purpose.
3. **Commitment accounting** — encumbrance is recorded at PO/LPO, not invoice. Budget exhaustion must be blocked **before** order.
4. **National Chart of Accounts (NCoA)** — 7-segment classification (Admin–Economic–Functional–Programme–Fund–Geo–Project) that private ERPs have no native concept of.
5. **Treasury Single Account** — all government cash sweeps to one consolidated account; MDA-held sub-accounts report to it.
6. **IPSAS reporting** — Accumulated Fund, Revaluation Surplus on equity, no profit concept, cash-flow statement under direct method.
7. **Statutory reporting to OAGF, OAuGF, CBN, FIRS, Budget Office** — formats and deadlines mandated by the Finance (Control and Management) Act.

Quot PSA implements all of these as first-class primitives, not extensions.

---

## Tech Stack

- **Backend:** Django 4.2 LTS · Django REST Framework · PostgreSQL 15 · `django-tenants` (schema-isolated multi-tenancy)
- **Frontend:** React 18 · Vite · TypeScript · Ant Design v5 · TanStack Query
- **Authentication:** DRF Token · per-tenant role/permission (SOD enforced)
- **Background:** Celery + Redis for depreciation runs, bank reconciliation, report generation
- **Deployment:** Gunicorn + Nginx · PgBouncer connection pooling

---

## Multi-tenancy model

Each government body (State, Agency, Parastatal) is a **tenant with its own PostgreSQL schema**. A single deployment can host Delta State, Edo State, FIRS, and a Federal parastatal simultaneously with **zero data crossover**. The `public` schema holds only cross-tenant infrastructure (tenant registry, superadmin, licensing).

---

## Repository

This repository is the canonical home of Quot PSA. It is **not a fork** of any private-sector product and shares **no code lineage, no upstream remote, and no feature roadmap** with any commercial ERP codebase. Issues, pull requests, and releases are tracked here: `github.com/oosadiaye/Quot-PSA`.

---

## Documentation

- `docs/Contracts_Milestone_Payment_Process.docx` — Works contract & IPC payment flow
- `docs/CODEMAPS/` — Module-by-module architecture maps
- `spec.md` — Full functional specification
- `IMPLEMENTATION_TASK_FLOW.md` — Sprint-level build log
- `INTEGRATION_ARCHITECTURE.md` — Cross-module integration contracts

---

## License

Proprietary — Quot Technologies. All rights reserved.
