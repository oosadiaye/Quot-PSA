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

- **Backend:** Django 5.2 LTS · Django REST Framework 3.17 · PostgreSQL 15 · `django-tenants` 3.10 (schema-isolated multi-tenancy)
- **Frontend:** React 19 · Vite 7 · TypeScript · Ant Design v6 · TanStack Query · Recharts
- **Authentication:** DRF Token + SimpleJWT · per-tenant role/permission (SoD enforced) · MFA via `UserSession.mfa_verified_at`
- **Background:** Celery + Redis for depreciation runs, bank reconciliation, report generation (optional in dev — `django-celery-beat` import is wrapped in a `try/except` in `quot_pse/settings.py`)
- **OpenAPI / docs:** `drf-spectacular` · live schema at `/api/schema/`
- **Deployment:** Gunicorn + Nginx · PgBouncer connection pooling · See `docs/DEPLOYMENT_ALMALINUX.md`

---

## Multi-tenancy model

Each government body (State, Agency, Parastatal) is a **tenant with its own PostgreSQL schema**. A single deployment can host Delta State, Edo State, FIRS, and a Federal parastatal simultaneously with **zero data crossover**. The `public` schema holds only cross-tenant infrastructure (tenant registry, superadmin, licensing).

---

## Local Development

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 | The codebase uses 3.12 features in some service modules. |
| Node.js | 18+ | Vite 7 requires Node 18 or newer. |
| PostgreSQL | 15 | `django-tenants` is hard-coded to PostgreSQL — SQLite will not work. |
| Redis | 7+ | Optional in dev (used for report cache + Celery broker). |

### First-time setup (Windows · same idea on macOS / Linux)

The repo is at **`C:\Users\USER\Documents\Antigravity\public_sector erp`** on the canonical dev machine. Clone or place the repo there, then:

```powershell
# 1. Backend — recreate venv from scratch in the project folder
cd "C:\Users\USER\Documents\Antigravity\public_sector erp"
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Database — point Django at a Postgres instance via DATABASE_URL or DB_*
#    env vars (see .env.example). Then create the public schema:
.venv\Scripts\python.exe manage.py migrate_schemas --shared

# 3. Onboard at least one tenant (the public schema has no business tables):
#    follow docs/RUNBOOK_ONBOARD_TENANT.md (10 minutes).

# 4. Frontend
cd frontend
npm install
```

### Running both servers

Open two terminals:

```powershell
# Terminal 1 — Django backend on http://localhost:8000
cd "C:\Users\USER\Documents\Antigravity\public_sector erp"
.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000

# Terminal 2 — Vite frontend on http://localhost:5173
cd "C:\Users\USER\Documents\Antigravity\public_sector erp\frontend"
npm run dev
```

The frontend's API client (`frontend/src/api/client.ts`) defaults to
`http://localhost:8000/api/v1` — override via `VITE_API_URL` only if you
need to point at a remote backend.

### Multi-tenant URLs in dev

`django-tenants` resolves the active tenant by hostname. Common patterns:

| URL | Resolves to |
|---|---|
| `http://localhost:8000/` | The **public** schema (admin, tenant registry, superadmin) |
| `http://<schema>.localhost:8000/` | The **`<schema>`** tenant (most modern browsers auto-resolve `*.localhost`) |
| `http://localhost:5173/` | Frontend dev server (proxies API calls to whichever host you load) |

If your browser doesn't resolve `*.localhost`, add a hosts-file entry
(`127.0.0.1 acme.localhost`) for each tenant subdomain you need.

### Gotcha: project-folder rename breaks `.venv`

A Python virtual environment hardcodes the absolute project path into
several internal files (`pyvenv.cfg`, the activate scripts, pip's metadata
trail). **If you rename or move the project folder, the existing `.venv`
becomes silently broken** — `pip install` will report success while
landing packages in a directory the in-process Python can't see. The
classic symptom is `ModuleNotFoundError: No module named '<package>'`
immediately after a clean `pip install <package>`.

Fix: delete `.venv` and recreate it in the new location:

```powershell
rmdir /s /q .venv
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This was the issue when this project was renamed from its earlier
working title to `public_sector erp` — the `.venv` survived the rename
intact on disk but stopped functioning. The fix is to recreate, not to
patch `pyvenv.cfg`.

### Stopping the servers

`Ctrl+C` in each terminal. The Django dev server's auto-reloader leaves
no orphan child processes; Vite likewise terminates cleanly.

---

## Repository

This repository is the canonical home of Quot PSA. It is **not a fork** of any private-sector product and shares **no code lineage, no upstream remote, and no feature roadmap** with any commercial ERP codebase. Issues, pull requests, and releases are tracked here: `github.com/oosadiaye/Quot-PSA`.

---

## Documentation

- `docs/Contracts_Milestone_Payment_Process.docx` — Works contract & IPC payment flow
- `docs/RUNBOOK.md` — Operator runbook (incidents, fail-over, rollback)
- `docs/RUNBOOK_ONBOARD_TENANT.md` — End-to-end tenant onboarding (target: 30 min)
- `docs/DEPLOYMENT_ALMALINUX.md` — Production deploy on AlmaLinux + Gunicorn + Nginx
- `docs/DR_DRILL.md` — Quarterly disaster-recovery drill procedure
- `docs/USER_GUIDE.md` — End-user walkthrough for tenant operators
- `spec.md` — Full functional specification
- `IMPLEMENTATION_TASK_FLOW.md` — Sprint-level build log
- `INTEGRATION_ARCHITECTURE.md` — Cross-module integration contracts

---

## License

Proprietary — Quot Technologies. All rights reserved.
