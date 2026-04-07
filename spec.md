# DTSG ERP — Full System Specification

> Multi-Tenant SaaS Enterprise Resource Planning System
> Tech Stack: Django 5/6 + DRF | React 19 + TypeScript + Vite | PostgreSQL | django-tenants

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Blueprint](#2-architecture-blueprint)
3. [Backend — Models & APIs](#3-backend--models--apis)
4. [Frontend — Pages & Components](#4-frontend--pages--components)
5. [Authentication & Authorization](#5-authentication--authorization)
6. [Security Requirements](#6-security-requirements)
7. [Mobile Optimization](#7-mobile-optimization)
8. [Performance & Speed](#8-performance--speed)
9. [CI/CD Pipeline & GitHub Deployment](#9-cicd-pipeline--github-deployment)
10. [AI Development Guidelines](#10-ai-development-guidelines)
11. [Testing Strategy](#11-testing-strategy)
12. [Production Checklist](#12-production-checklist)

---

## 1. System Overview

### 1.1 What Has Been Built

DTSG ERP is a **production-grade, multi-tenant SaaS ERP** with 11 business modules, centralized authentication, role-based access control, and a modern glassmorphism UI.

**Core Capabilities:**
- Schema-per-tenant isolation via `django-tenants`
- Centralized user pool in public schema with token-based auth (24h TTL)
- RBAC with Django model permissions (view/add/change/delete per model)
- Subscription plans, tenant modules, and payment management
- Dark/light theme with glassmorphism design system
- Lazy-loaded routes with vendor code splitting
- TanStack Query for server-state caching and synchronization
- Audit trail on all business models (created_by, updated_by, timestamps)
- Immutable posted transactions (journals, POs, SOs — edit via reversal only)

### 1.2 Module Summary

| # | Module | Status | Models | ViewSets | Frontend Pages |
|---|--------|--------|--------|----------|----------------|
| 1 | **Accounting** | Full | 90+ | 75+ | 25+ |
| 2 | **Budget** | Full | 10 | 10 | 4 |
| 3 | **Procurement** | Full | 14 | 5 | 6 |
| 4 | **Inventory** | Full | 13 | 10 | 14 |
| 5 | **Sales** | Full | 9 | 6 | 7 |
| 6 | **Service** | Full | 9 | 8 | 5 |
| 7 | **Workflow** | Full | 10 | 7 | 5 |
| 8 | **HRM** | Full | 45+ | 30+ | 17 |
| 9 | **Production** | Backend | 8 | 8 | Placeholder |
| 10 | **Quality** | Backend | 8 | 8 | Placeholder |
| 11 | **Tenants** | Full | 7 | 6 | SuperAdmin |

### 1.3 Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend Framework | Django + DRF | 5/6 |
| Database | PostgreSQL | 14+ |
| Multi-Tenancy | django-tenants | Latest |
| Audit Trail | django-simple-history | Latest |
| Frontend Framework | React | 19.2.0 |
| Type System | TypeScript | 5.9.3 |
| Build Tool | Vite | 7.3.1 |
| UI Library | Ant Design | 6.3.0 |
| State Management | TanStack React Query | 5.90+ |
| HTTP Client | Axios | 1.13.5 |
| Routing | react-router-dom | 7.13.0 |
| Charts | Recharts | 3.7.0 |
| Animations | Framer Motion | 12.34.0 |
| Icons | Lucide React | 0.564.0 |

---

## 2. Architecture Blueprint

### 2.1 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CDN (CloudFront/Cloudflare)             │
│               Static assets, gzip, cache headers            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Nginx Reverse Proxy                       │
│   ┌─────────────────┐     ┌───────────────────────────┐     │
│   │  /  → React SPA │     │  /api/  → Gunicorn:8000   │     │
│   │  (dist/ folder)  │     │  /admin/ → Gunicorn:8000  │     │
│   └─────────────────┘     └───────────────────────────┘     │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Gunicorn (4 workers × 2 threads)                │
│                    Django/DRF Application                     │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────────────┐     │
│  │ Auth     │ │ Tenant       │ │ Business Logic       │     │
│  │ (public) │ │ Middleware   │ │ (per-tenant schema)  │     │
│  └──────────┘ └──────────────┘ └──────────────────────┘     │
└──────────────────────────┬──────────────────────────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
┌──────▼──────┐  ┌─────────▼─────────┐  ┌─────▼─────┐
│ PostgreSQL  │  │   Redis Cache     │  │  S3/Minio  │
│ (tenants)   │  │  (sessions, cache)│  │  (media)   │
└─────────────┘  └───────────────────┘  └───────────┘
```

### 2.2 Multi-Tenant Schema Architecture

```
PostgreSQL Database: dtsg_erp
├── public (schema)
│   ├── auth_user              ← All users (centralized)
│   ├── authtoken_token        ← All auth tokens
│   ├── tenants_client         ← Tenant registry
│   ├── tenants_domain         ← Domain mappings
│   ├── tenants_userrole       ← User → Tenant → Role
│   ├── tenants_subscription   ← Billing/plans
│   └── tenants_payment        ← Payment records
│
├── tenant_acme (schema)       ← Tenant "Acme Corp"
│   ├── accounting_account
│   ├── accounting_journalheader
│   ├── procurement_vendor
│   ├── inventory_item
│   └── ... (all TENANT_APPS tables)
│
├── tenant_globex (schema)     ← Tenant "Globex Inc"
│   ├── accounting_account     ← Completely isolated
│   └── ...
```

### 2.3 Request Flow

```
Browser → Nginx → Gunicorn → Django
   │
   ├─ 1. CorsMiddleware (CORS headers)
   ├─ 2. TenantHeaderMiddleware
   │     ├─ Public path? → skip tenant resolution
   │     └─ Read X-Tenant-Domain header → resolve schema
   ├─ 3. SecurityMiddleware (XSS, HSTS, etc.)
   ├─ 4. SessionMiddleware
   ├─ 5. CsrfViewMiddleware
   ├─ 6. AuthenticationMiddleware
   │     └─ ExpiringTokenAuthentication → public schema lookup
   ├─ 7. TenantAccessMiddleware
   │     └─ Verify UserTenantRole exists for user + tenant
   ├─ 8. RBACPermission
   │     └─ Check Django model permissions (view/add/change/delete)
   └─ 9. ViewSet → Serializer → Model → Response
```

### 2.4 Frontend Architecture

```
App.tsx
├── ThemeProvider (dark/light)
├── QueryClientProvider (TanStack Query)
├── ErrorBoundary
├── Router
│   ├── /login → Login.tsx (credentials + tenant picker)
│   ├── /dashboard → Dashboard.tsx (module hub)
│   └── /accounting/* → Lazy-loaded modules
│       ├── AccountingLayout (Sidebar + content)
│       ├── Feature hooks (useJournal, useBudgets, etc.)
│       └── Components (GlassCard, StatusBadge, etc.)
│
├── API Client (axios)
│   ├── Request: inject Authorization + X-Tenant-Domain
│   └── Response: 401 → redirect to /login
│
└── State Management
    ├── Server state: TanStack Query (stale: 5min, gc: 10min)
    ├── Auth state: localStorage (token, user, tenant)
    └── Theme state: React Context + localStorage
```

### 2.5 Directory Structure

```
DTSG erp/
├── dtsg_erp/                  # Django project config
│   ├── settings.py            # Full settings (security, DB, cache, logging)
│   ├── urls.py                # Root URL router → 12 app routers
│   ├── wsgi.py / asgi.py      # Server entry points
│
├── core/                      # Auth, middleware, permissions
│   ├── authentication.py      # PublicSchemaBackend, ExpiringTokenAuth
│   ├── middleware.py           # TenantHeaderMiddleware, TenantAccessMiddleware
│   ├── permissions.py         # RBACPermission
│   ├── models.py              # AuditBaseModel, ImmutableModelMixin
│   ├── views.py               # Login, logout, select-tenant, UserViewSet
│   ├── serializers.py         # UserSerializer, ChangePasswordSerializer
│   └── tests.py               # Auth, RBAC, tenant selection tests
│
├── accounting/                # 90+ models, 75+ ViewSets
├── budget/                    # Budget allocation & variance
├── procurement/               # PO, PR, vendors, GRN, 3-way matching
├── inventory/                 # Items, stock, warehouses, batch tracking
├── sales/                     # CRM, quotations, SO, delivery notes
├── service/                   # Tickets, work orders, SLA, maintenance
├── workflow/                  # Approval templates, workflow engine
├── hrm/                       # 45+ models: employees, payroll, leave, etc.
├── production/                # BOM, work centers, job cards
├── quality/                   # Inspections, NCR, complaints
├── tenants/                   # Client, Domain, UserTenantRole, subscriptions
├── superadmin/                # Super admin dashboard & management
│
├── frontend/
│   ├── src/
│   │   ├── api/client.ts      # Axios with interceptors
│   │   ├── components/        # Sidebar, ProtectedRoute, ErrorBoundary
│   │   ├── context/           # ThemeContext
│   │   ├── features/          # 11 feature modules
│   │   │   └── accounting/
│   │   │       ├── hooks/     # useJournal, useFiscalYear, useMultiCompany
│   │   │       ├── multi-company/
│   │   │       │   └── MultiCompanyPage.tsx  (2026)
│   │   │       └── ...
│   │   ├── hooks/             # usePermissions, useTenantModules
│   │   ├── pages/             # Login, Dashboard, SuperAdminDashboard
│   │   ├── App.tsx            # Router + providers
│   │   ├── main.tsx           # React root
│   │   └── index.css          # Global styles + theme vars
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── requirements.txt
├── manage.py
├── .env
└── spec.md                    # This file
```

---

## 3. Backend — Models & APIs

### 3.1 Core App

**Models:**
- `AuditBaseModel` (abstract) — created_at, updated_at, created_by, updated_by
- `ImmutableModelMixin` (abstract) — status field, prevents editing/deleting Posted records

**Auth Classes:**
- `PublicSchemaBackend` — authenticates against public schema only
- `ExpiringTokenAuthentication` — token lookup in public schema with 24h TTL
- `RBACPermission` — DjangoModelPermissions with GET→view enforcement

**Middleware:**
- `TenantHeaderMiddleware` — resolves X-Tenant-Domain → schema
- `TenantAccessMiddleware` — validates user has UserTenantRole for tenant

**Endpoints:**
```
POST   /api/core/auth/login/
POST   /api/core/auth/logout/
POST   /api/core/auth/select-tenant/
GET    /api/core/auth/my-tenants/
GET    /api/core/users/me/
POST   /api/core/users/register/
POST   /api/core/users/change-password/
```

### 3.2 Tenants App

**Models:**
- `Client` (TenantMixin) — name, auto_create_schema
- `Domain` (DomainMixin) — domain, tenant, is_primary
- `UserTenantRole` — user→tenant→role mapping (admin/manager/user/viewer)
- `TenantModule` — feature flags per tenant
- `SubscriptionPlan` — free/basic/standard/premium/enterprise with allowed_modules
- `TenantSubscription` — plan assignment, status, billing dates
- `TenantPayment` — payment records with receipt upload and approval workflow

**Endpoints:** 15+ endpoints for tenant management, subscriptions, payments, modules

### 3.3 Accounting App (Largest Module)

**Backend Services (accounting/services.py):**
- `InterCompanyPostingService` - Auto-create journal entries for IC transactions
  - `post_ic_invoice()` - Post IC sales/purchase invoice  
  - `post_ic_transfer()` - Post IC inventory transfer
  - `post_ic_cash_transfer()` - Post IC cash transfer
- `ConsolidationService` - Execute consolidation for a group
  - `run_consolidation()` - Run consolidation with elimination entries

**Dimension Models:** Fund, Function, Program, Geo, MDA (5 models)

**Core GL:** Account, JournalHeader, JournalLine, JournalReversal, GLBalance, Currency (6 models)

**Budget:** BudgetPeriod, Budget (with cost_center FK), BudgetEncumbrance, BudgetAmendment, BudgetTransfer, BudgetForecast, BudgetAnomaly, BudgetCheckLog (8 models)

**AP/AR:** VendorInvoice, Payment, PaymentAllocation, CustomerInvoice, Receipt, ReceiptAllocation (6 models)

**Fixed Assets:** FixedAsset, AssetClass, AssetCategory, AssetConfiguration, AssetLocation, AssetInsurance, AssetMaintenance, AssetTransfer, AssetDepreciationSchedule, AssetRevaluation, AssetDisposal, AssetImpairment (12 models)

**Cost Centers:** CostCenter, ProfitCenter, CostAllocationRule, JournalLineCostCenter (4 models)

**Bank & Cash:** BankAccount, Checkbook, Check, BankReconciliation, CashFlowCategory, CashFlowForecast (6 models)

**Tax:** TaxRegistration, TaxExemption, TaxReturn, WithholdingTax, TaxCode (5 models)

**Intercompany:** Company, InterCompany, InterCompanyConfig, InterCompanyInvoice, InterCompanyTransfer, InterCompanyAllocation, InterCompanyCashTransfer, InterCompanyAccountMapping, InterCompanyTransaction, InterCompanyElimination (10 models)

**New Multi-Company & IC Modules (2026):**
- `Company` - Entity master data with hierarchy (Holding, Subsidiary, Branch, Division)
- `InterCompanyConfig` - IC relationship config with AR/AP account mapping
- `InterCompanyInvoice` - IC sales/purchase invoices with auto-posting
- `InterCompanyTransfer` - IC inventory transfers
- `InterCompanyAllocation` - IC expense allocation
- `InterCompanyCashTransfer` - IC cash transfers
- `InterCompanyPostingService` - Auto-create journal entries for IC transactions
- `ConsolidationGroup` - Groups for consolidation with elimination rules
- `ConsolidationRun` - Consolidation execution records with status tracking
- `ConsolidationService` - Execute consolidation for a group

**Consolidation:** ConsolidationGroup, ConsolidationRun, Consolidation (3 models)

**Deferred/Lease:** DeferredRevenue, DeferredExpense, AmortizationSchedule, Lease, LeasePayment (5 models)

**Treasury:** TreasuryForecast, Investment, Loan, LoanRepayment (4 models)

**Currency:** ExchangeRateHistory, ForeignCurrencyRevaluation (2 models)

**Period Management:** FiscalPeriod, FiscalYear, PeriodAccess, PeriodCloseCheck (4 models)

**Advanced:** RecurringJournal, RecurringJournalLine, RecurringJournalRun, Accrual, Deferral, DeferralRecognition, PeriodStatus, YearEndClosing, CurrencyRevaluation, RetainedEarnings, AccountingSettings, AccountingDocument, DocumentSignature (13 models)

**Financial Reports:** BalanceSheet, IncomeStatement, CashFlowStatement, TrialBalance, GeneralLedger, BudgetVsActual (6 report ViewSets)

**Custom Endpoints:**
- `POST /api/accounting/journals/{id}/post/` — Post journal entry
- `POST /api/accounting/journals/{id}/reverse/` — Reverse posted journal
- `GET /api/accounting/currencies/defaults/` — Default currency settings
- `POST /api/accounting/currencies/convert/` — Currency conversion
- `GET /api/accounting/exchange-rates/import-template/` — CSV template
- `POST /api/accounting/exchange-rates/bulk-import/` — Bulk import rates
- `GET /api/accounting/exchange-rates/export/` — Export rates

**Multi-Company & IC Endpoints (2026):**
- `GET /api/accounting/companies/` — Company CRUD
- `GET /api/accounting/ic-configs/` — IC configuration CRUD
- `GET /api/accounting/ic-invoices/` — IC invoice CRUD
- `POST /api/accounting/ic-invoices/{id}/post_invoice/` — Post IC invoice
- `GET /api/accounting/ic-transfers/` — IC inventory transfer CRUD
- `GET /api/accounting/ic-allocations/` — IC expense allocation CRUD
- `GET /api/accounting/ic-cash-transfers/` — IC cash transfer CRUD
- `GET /api/accounting/consolidation-groups/` — Consolidation group CRUD
- `GET /api/accounting/consolidation-runs/` — Consolidation run CRUD
- `POST /api/accounting/consolidation-runs/{id}/run_consolidation/` — Execute consolidation

### 3.4 Procurement App

**Models (14):** PurchaseType, Vendor, PurchaseRequest, PurchaseRequestLine, PurchaseOrder, PurchaseOrderLine, GoodsReceivedNote, GoodsReceivedNoteLine, InvoiceMatching, VendorCreditNote, VendorDebitNote, PurchaseReturn, PurchaseReturnLine, VendorPerformanceMetrics

**Key Feature:** Three-way matching (PO→GRN→Invoice) with variance threshold

### 3.5 Inventory App

**Models (13):** Warehouse, ProductType, ProductCategory, ItemCategory, Item, ItemStock, ItemBatch, StockMovement, StockReconciliation, StockReconciliationLine, ReorderAlert, ItemSerialNumber, BatchExpiryAlert

**Key Features:** Batch/lot tracking, serial number tracking, expiry alerts, valuation methods (WA/FIFO/LIFO)

### 3.6 Sales App

**Models (9):** Customer, Lead, Opportunity, Quotation, QuotationLine, SalesOrder, SalesOrderLine, DeliveryNote, DeliveryNoteLine

**Key Features:** CRM pipeline (Lead→Opportunity→Quotation→SO), credit limit enforcement

### 3.7 Service App

**Models (9):** ServiceAsset, Technician, ServiceTicket, SLATracking, WorkOrder, WorkOrderMaterial, CitizenRequest, ServiceMetric, MaintenanceSchedule

### 3.8 Workflow App

**Models (10):** ApprovalGroup, ApprovalTemplate, ApprovalTemplateStep, Approval, ApprovalStep, ApprovalLog, WorkflowDefinition, WorkflowStep, WorkflowInstance, WorkflowLog

### 3.9 HRM App

**Models (45+):** Department, Position, Employee, LeaveType, LeaveRequest, LeaveBalance, Attendance, Holiday, JobPost, Candidate, Interview, OnboardingTask, OnboardingProgress, SalaryStructure, SalaryComponent, PayrollPeriod, PayrollRun, PayrollLine, PayrollEarning, PayrollDeduction, Payslip, PerformanceCycle, PerformanceGoal, PerformanceReview, Competency, CompetencyRating, Promotion, TrainingProgram, TrainingEnrollment, Skill, EmployeeSkill, TrainingPlan, TrainingPlanLine, Policy, PolicyAcknowledgement, ComplianceRecord, ComplianceTask, AuditLog, ExitRequest, ExitInterview, ExitClearance, FinalSettlement, ExperienceCertificate, AssetReturn

### 3.10 Production App

**Models (8):** WorkCenter, BillOfMaterials, BOMLine, ProductionOrder, MaterialIssue, MaterialReceipt, JobCard, Routing

### 3.11 Quality App

**Models (8):** QualityInspection, InspectionLine, NonConformance, CustomerComplaint, QualityChecklist, QualityChecklistLine, CalibrationRecord, SupplierQuality

---

## 4. Frontend — Pages & Components

### 4.1 Route Map (140+ routes)

**Authentication:** `/login`

**Dashboard:** `/dashboard` (module hub with 12 cards)

**Accounting (25+ pages):**
- `/accounting/dashboard`, `/accounting` (journals), `/accounting/new` (journal form)
- `/accounting/coa`, `/accounting/ap`, `/accounting/ar`, `/accounting/fixed-assets`
- `/accounting/asset-categories`, `/accounting/cost-centers`
- `/accounting/reports`, `/accounting/bank-cash`, `/accounting/cash-accounts`
- `/accounting/tax`, `/accounting/fiscal-year`
- `/accounting/recurring-journals`, `/accounting/accruals-deferrals`
- `/accounting/intercompany`, `/accounting/multi-company`, `/accounting/consolidation`

**New Accounting Pages (2026):**
- `/accounting/multi-company` — MultiCompanyPage.tsx (Companies, IC Config tabs)

**Dimensions:** `/accounting/dimensions`, `/accounting/dimensions/funds|functions|programs|geos`

**Budget:** `/accounting/budget/dashboard|entry|variance`

**Procurement:** `/procurement/dashboard|vendors|requisitions|orders/new|grn|matching|vendor-performance`

**New Procurement Pages (2026):**
- `/procurement/grn` - GoodsReceivedNotes.tsx (GRN listing with post action)
- `/procurement/matching` - InvoiceMatchingPage.tsx (3-way matching)
- `/procurement/vendor-performance` - VendorPerformance.tsx (vendor metrics)

**Inventory (14 pages):** `/inventory/dashboard|items|valuation|product-types|categories|warehouses|stocks|batches|movements|reconciliations|reorder-alerts|serial-numbers|expiry-alerts`

**Sales:** `/sales/dashboard|crm|quotations|orders|delivery-notes|invoicing|credit-limits`

**Service:** `/service/dashboard|work-orders|citizen-requests|metrics|assets|technicians|tickets|schedules`

**New Service Pages (2026):**
- `/service/dashboard` - ServiceDashboard.tsx with metrics, ticket listing, technician assignment
- `/service/assets` - ServiceAssets.tsx (asset CRUD, warranty tracking)
- `/service/technicians` - Technicians.tsx (technician CRUD, availability toggle)
- `/service/tickets` - ServiceTickets.tsx (ticket CRUD, assign, resolve)
- `/service/schedules` - MaintenanceSchedules.tsx (schedule CRUD, generate ticket)
- ServiceLayout.tsx - New dedicated layout for Service module

**HRM (17 pages):** `/hrm/dashboard|employees|departments|positions|leave|attendance|holidays|job-posts|candidates|payroll|payslips|performance|training|skills|policies|compliance|exit`

**Workflow:** `/approvals/dashboard|inbox|groups|templates|history`, `/workflow/dashboard|definitions|instances`

**Settings:** `/settings/accounting|accounting/currencies|bank-accounts|fiscal-year|tax`

### 4.2 Shared Components

| Component | Purpose |
|-----------|---------|
| `Sidebar.tsx` | 260px nav with module filtering, expand/collapse, theme toggle, logout |
| `ProtectedRoute.tsx` | Auth guard, checks localStorage token |
| `ErrorBoundary.tsx` | React error boundary with fallback UI |
| `LoadingScreen.tsx` | Full-page or inline loading spinner |
| `BackButton.tsx` | Navigation back button |
| `CurrencySelector.tsx` | Currency dropdown for reports |

### 4.3 Accounting Shared Components

| Component | Purpose |
|-----------|---------|
| `GlassCard.tsx` | Glassmorphism card wrapper |
| `MetricCard.tsx` | Financial metric display |
| `AnimatedButton.tsx` | Button with ripple effect |
| `StatusBadge.tsx` | Color-coded status pills |
| `Modal.tsx` | Dialog/modal wrapper |
| `DimensionManager.tsx` | Dimension CRUD with import/export |

### 4.4 Custom Hooks

**Shared:**
- `usePermissions()` — user permissions + hasPermission() utility
- `useTenantModules()` — enabled modules for current tenant
- `useIsDimensionsEnabled()` — check if dimensions module is active

**Accounting:**
- `useJournal()` — journal CRUD + posting
- `useDimensions()` — Fund/Function/Program/Geo CRUD + import/export
- `useCostCenters()` — cost center CRUD
- `useAccountingEnhancements()` — AP/AR/assets/tax hooks
- `useAccrualDeferral()`, `useFiscalYear()`, `useMultiCompany()`, `useRecurringJournal()`

**New Multi-Company Hooks (2026):**
- `useMultiCompany()` - Companies, IC Configs, IC transactions CRUD

**Budget:**
- `useBudgets()` — budget CRUD + bulk import/export
- `useBudgetPeriods()`, `useBudgetAnalytics()`, `useEncumbrances()`

**Service (2026):**
- `useServiceTickets()`, `useCreateTicket()`, `useResolveTicket()`, `useAssignTechnician()`
- `useServiceAssets()`, `useCreateServiceAsset()`, `useUpdateServiceAsset()`
- `useTechnicians()`, `useCreateTechnician()`, `useUpdateTechnician()`
- `useWorkOrders()`, `useCreateWorkOrder()`, `useCompleteWorkOrder()`, `useUpdateWorkOrder()`
- `useMaintenanceSchedules()`, `useCreateSchedule()`, `useGenerateTicketFromSchedule()`
- `useServiceDashboard()`, `useServiceMetrics()`, `useGenerateMetrics()`

**Per-module:** `useProcurement()`, `useInventory()`, `useSales()`, `useService()`, `useHrm()`, `useBankAccounts()`

### 4.5 Styling System

**Architecture:** CSS custom properties + glassmorphism + inline styles

**Theme Variables:**
```css
/* Dark (default) */
--color-primary: #3B82F6;
--color-background: #0f172a;
--color-surface: #1e293b;
--color-text: #e2e8f0;
--color-border: rgba(148, 163, 184, 0.1);

/* Light */
--color-primary: #2563eb;
--color-background: #f8fafc;
--color-surface: #ffffff;
--color-text: #1e293b;
```

**Design Patterns:**
- Cards: rounded corners, borders, shadows, glassmorphism blur
- Tables: sortable headers, hover rows, monospace numbers
- Modals: backdrop blur, centered, escape-to-close
- Badges: color-coded by status/type
- Buttons: primary (CTA), outline, ghost

---

## 5. Authentication & Authorization

### 5.1 Login Flow

```
1. POST /api/core/auth/login/ {username, password}
   ↓ PublicSchemaBackend authenticates in public schema
   ↓ Returns: {token, user, tenants[]}

2. Frontend stores authToken + user in localStorage

3. If multiple tenants → show tenant picker
   POST /api/core/auth/select-tenant/ {tenant_id}
   ↓ Validates UserTenantRole exists
   ↓ Returns: {domain, tenant_info}

4. Frontend stores tenantDomain in localStorage

5. All subsequent requests include:
   Authorization: Token {authToken}
   X-Tenant-Domain: {tenantDomain}
```

### 5.2 Permission Model

```
UserTenantRole.role:
├── admin    → Full access to tenant
├── manager  → Module-level management
├── user     → Standard CRUD operations
└── viewer   → Read-only access

Django Model Permissions:
├── GET    → {app}.view_{model}
├── POST   → {app}.add_{model}
├── PUT    → {app}.change_{model}
└── DELETE → {app}.delete_{model}

Superuser → bypasses all permission checks
```

### 5.3 Token Lifecycle

- Created on login (old token deleted if exists)
- Validated on every request via ExpiringTokenAuthentication
- Expires after 24 hours (configurable via TOKEN_EXPIRATION_HOURS)
- Deleted on logout
- 401 response → frontend clears localStorage, redirects to /login

---

## 6. Security Requirements

### 6.1 Current Security Measures

| Category | Implementation | Status |
|----------|---------------|--------|
| Authentication | Token-based with 24h expiration | Done |
| Authorization | RBAC with Django model permissions | Done |
| Tenant Isolation | Schema-per-tenant (django-tenants) | Done |
| XSS Protection | SECURE_BROWSER_XSS_FILTER | Done |
| Content Sniffing | SECURE_CONTENT_TYPE_NOSNIFF | Done |
| Clickjacking | X_FRAME_OPTIONS = 'DENY' | Done |
| CSRF | CsrfViewMiddleware enabled | Done |
| CORS | Whitelist-based CORS_ALLOWED_ORIGINS | Done |
| Rate Limiting | 100/hr anon, 1000/hr user, 5/min login | Done |
| Session Security | httpOnly, secure (prod) cookies | Done |
| Audit Trail | AuditBaseModel + django-simple-history | Done |
| Immutable Records | ImmutableModelMixin prevents edit of Posted records | Done |
| Secret Key | Loaded from environment variable | Done |
| SQL Injection | Django ORM (parameterized queries) | Done |

### 6.2 Required for Production

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| **HTTPS Everywhere** | Critical | Nginx SSL termination + SECURE_SSL_REDIRECT |
| **HSTS** | Critical | SECURE_HSTS_SECONDS=31536000, preload |
| **Environment Secrets** | Critical | Use vault/secrets manager, never commit .env |
| **Password Hashing** | Critical | Django PBKDF2 (default, already active) |
| **Input Validation** | Critical | DRF serializer validation on all endpoints |
| **File Upload Scanning** | High | Validate MIME types, limit size, scan for malware |
| **API Input Sanitization** | High | Strip HTML/scripts from text inputs |
| **Database Encryption** | High | PostgreSQL TDE or application-level encryption for PII |
| **Backup Encryption** | High | Encrypt database backups at rest |
| **WAF** | High | Web Application Firewall (CloudFlare/AWS WAF) |
| **Dependency Scanning** | Medium | Dependabot + pip-audit + npm audit |
| **Penetration Testing** | Medium | Annual pentest by third party |
| **2FA/MFA** | Medium | TOTP via django-otp or pyotp |
| **Session Fixation** | Medium | Rotate session on login (Django default) |
| **Content Security Policy** | Medium | CSP headers via django-csp |
| **Subresource Integrity** | Low | SRI hashes for CDN assets |

### 6.3 Security Headers (Production Nginx)

```nginx
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' https://api.example.com;" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
```

---

## 7. Mobile Optimization

### 7.1 Current State

The UI uses fixed-width sidebar (260px) and is primarily desktop-optimized. Mobile responsiveness requires the following work:

### 7.2 Required Changes

| Area | Requirement | Implementation |
|------|-------------|----------------|
| **Sidebar** | Collapsible/off-canvas on mobile | Hamburger menu, slide-in drawer below 768px |
| **Layout** | Responsive breakpoints | `@media (max-width: 768px)` for tablet, `480px` for phone |
| **Tables** | Horizontal scroll or card view | `overflow-x: auto` wrapper, card layout on mobile |
| **Forms** | Stack fields vertically | `grid-template-columns: 1fr` on small screens |
| **Modals** | Full-screen on mobile | `max-width: 100vw; max-height: 100vh` on small screens |
| **Touch** | Touch-friendly targets | Minimum 44x44px touch targets (WCAG 2.5.5) |
| **Typography** | Readable font sizes | Min 16px for body, 14px for secondary text |
| **Charts** | Responsive containers | `ResponsiveContainer` wrapper from Recharts |
| **PWA** | Offline-capable shell | Service worker, manifest.json, app icons |
| **Viewport** | Proper meta tag | `<meta name="viewport" content="width=device-width, initial-scale=1">` |

### 7.3 Responsive Breakpoints

```css
/* Mobile first */
@media (max-width: 480px)  { /* Phone */  }
@media (max-width: 768px)  { /* Tablet */ }
@media (max-width: 1024px) { /* Small desktop */ }
@media (min-width: 1025px) { /* Desktop (current design) */ }
```

### 7.4 PWA Requirements

```json
// manifest.json
{
  "name": "DTSG ERP",
  "short_name": "DTSG",
  "start_url": "/dashboard",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#3B82F6",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

---

## 8. Performance & Speed

### 8.1 Current Optimizations

| Category | Implementation | Status |
|----------|---------------|--------|
| DB Connection Pooling | CONN_MAX_AGE=600 | Done |
| DB Indexes | On dimension models, JournalHeader, Item | Done |
| select_related/prefetch_related | On all ViewSets | Done |
| Pagination | PageNumberPagination, PAGE_SIZE=20 | Done |
| Caching | LocMem cache (300s TTL) | Done |
| Frontend Code Splitting | vendor-react, vendor-antd, vendor-query | Done |
| Lazy Loading | All routes via React.lazy() | Done |
| TanStack Query | 5min stale time, 10min GC time | Done |
| Serializer Optimization | Explicit fields (no `__all__`) | Done |
| Bulk Operations | bulk_create for PO/SO lines | Done |

### 8.2 Required for Production

| Optimization | Priority | Implementation |
|-------------|----------|----------------|
| **Redis Cache** | Critical | Replace LocMemCache with Redis for multi-process |
| **pgBouncer** | High | Connection pooler for PostgreSQL |
| **CDN** | High | Static assets via CloudFront/Cloudflare |
| **Gzip/Brotli** | High | Nginx compression for API + static |
| **Database Query Optimization** | High | Django Debug Toolbar, EXPLAIN ANALYZE on slow queries |
| **Frontend Bundle Analysis** | Medium | `vite-plugin-bundle-visualizer` |
| **Image Optimization** | Medium | WebP format, lazy loading, srcset |
| **API Response Compression** | Medium | DRF + GZip middleware |
| **Database Read Replicas** | Low | PostgreSQL streaming replication |
| **Celery Task Queue** | Medium | Async tasks (reports, imports, emails) |
| **WebSocket** | Low | Real-time updates via Django Channels |

### 8.3 Performance Targets

| Metric | Target | Tool |
|--------|--------|------|
| Time to First Byte (TTFB) | < 200ms | Lighthouse |
| First Contentful Paint (FCP) | < 1.5s | Lighthouse |
| Largest Contentful Paint (LCP) | < 2.5s | Lighthouse |
| Cumulative Layout Shift (CLS) | < 0.1 | Lighthouse |
| API Response (list) | < 300ms | Django Debug Toolbar |
| API Response (detail) | < 100ms | Django Debug Toolbar |
| Bundle Size (gzipped) | < 500KB initial | Vite build |
| Database Queries per Request | < 10 | Django Debug Toolbar |

---

## 9. CI/CD Pipeline & GitHub Deployment

### 9.1 GitHub Actions Workflow

Create `.github/workflows/ci-cd.yml`:

```yaml
name: DTSG ERP CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: '3.12'
  NODE_VERSION: '22'
  POSTGRES_DB: dtsg_erp_test
  POSTGRES_USER: postgres
  POSTGRES_PASSWORD: postgres

jobs:
  # ──────────────────────────────────────────────
  # Stage 1: Backend Tests
  # ──────────────────────────────────────────────
  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: ${{ env.POSTGRES_DB }}
          POSTGRES_USER: ${{ env.POSTGRES_USER }}
          POSTGRES_PASSWORD: ${{ env.POSTGRES_PASSWORD }}
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run migrations
        env:
          DB_NAME: ${{ env.POSTGRES_DB }}
          DB_USER: ${{ env.POSTGRES_USER }}
          DB_PASSWORD: ${{ env.POSTGRES_PASSWORD }}
          DB_HOST: localhost
          DB_PORT: 5432
          SECRET_KEY: test-secret-key-ci-only
          DEBUG: 'True'
        run: |
          python manage.py migrate --skip-checks --noinput
      - name: Run tests
        env:
          DB_NAME: ${{ env.POSTGRES_DB }}
          DB_USER: ${{ env.POSTGRES_USER }}
          DB_PASSWORD: ${{ env.POSTGRES_PASSWORD }}
          DB_HOST: localhost
          DB_PORT: 5432
          SECRET_KEY: test-secret-key-ci-only
          DEBUG: 'True'
        run: |
          python manage.py test --verbosity=2 --failfast
      - name: Check for migration conflicts
        run: python manage.py makemigrations --check --dry-run --skip-checks

  # ──────────────────────────────────────────────
  # Stage 2: Backend Security Scan
  # ──────────────────────────────────────────────
  backend-security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: pip install -r requirements.txt pip-audit safety bandit
      - name: Dependency audit
        run: pip-audit --strict
      - name: Safety check
        run: safety check
        continue-on-error: true
      - name: Bandit security scan
        run: bandit -r . -x ./venv,./frontend,./.git --severity-level medium

  # ──────────────────────────────────────────────
  # Stage 3: Frontend Build & Lint
  # ──────────────────────────────────────────────
  frontend-build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        run: npm ci
      - name: TypeScript type check
        run: npx tsc --noEmit
      - name: ESLint
        run: npm run lint
      - name: Build production
        run: npm run build
      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: frontend-dist
          path: frontend/dist/
          retention-days: 7

  # ──────────────────────────────────────────────
  # Stage 4: Frontend Security Scan
  # ──────────────────────────────────────────────
  frontend-security:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
      - name: Install dependencies
        run: npm ci
      - name: npm audit
        run: npm audit --audit-level=high
        continue-on-error: true

  # ──────────────────────────────────────────────
  # Stage 5: Deploy to Production
  # ──────────────────────────────────────────────
  deploy:
    needs: [backend-test, backend-security, frontend-build, frontend-security]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - name: Download frontend artifacts
        uses: actions/download-artifact@v4
        with:
          name: frontend-dist
          path: frontend/dist/
      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd /var/www/dtsg-erp
            git pull origin main
            source venv/bin/activate
            pip install -r requirements.txt
            python manage.py migrate --skip-checks --noinput
            python manage.py collectstatic --noinput
            sudo systemctl restart gunicorn
            sudo systemctl reload nginx
```

### 9.2 Branch Strategy

```
main        → Production (auto-deploy on merge)
develop     → Staging (CI runs on push)
feature/*   → Feature branches (CI runs on PR to main/develop)
hotfix/*    → Emergency fixes (CI runs, fast-track to main)
```

### 9.3 Required GitHub Secrets

```
DEPLOY_HOST         → Production server IP/hostname
DEPLOY_USER         → SSH username
DEPLOY_SSH_KEY      → SSH private key
DB_PASSWORD         → Production database password
SECRET_KEY          → Production Django secret key
```

### 9.4 Pre-commit Hooks (Recommended)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: detect-private-key
  - repo: https://github.com/PyCQA/bandit
    hooks:
      - id: bandit
        args: ['--severity-level', 'medium']
  - repo: https://github.com/psf/black
    hooks:
      - id: black
  - repo: https://github.com/PyCQA/isort
    hooks:
      - id: isort
```

---

## 10. AI Development Guidelines

### 10.1 Critical Rules — Never Skip These

```
RULE 1: NO UNRESOLVED ERRORS
- Every file must compile without TypeScript errors
- Every Python file must pass syntax check
- Run `npx tsc --noEmit` after frontend changes
- Run `python manage.py check --skip-checks` after backend changes
- NEVER leave TODO/FIXME without a tracking issue

RULE 2: NO BROKEN IMPORTS
- Every import must resolve to an existing file/module
- After creating a new file, update all import paths
- After renaming/moving a file, grep for old import paths
- Verify lazy() imports in App.tsx match actual file paths

RULE 3: NO SECURITY VULNERABILITIES
- NEVER use raw SQL — always use Django ORM
- NEVER store passwords in plaintext
- NEVER commit .env files or secrets
- NEVER use eval(), exec(), or dangerouslySetInnerHTML
- ALWAYS validate user input on both frontend and backend
- ALWAYS use CSRF protection for state-changing operations
- ALWAYS check permissions in ViewSets (never use AllowAny for data endpoints)

RULE 4: NO BROKEN MIGRATIONS
- After model changes, ALWAYS create a migration
- Test migration forward AND backward
- NEVER delete or modify applied migrations
- If makemigrations prompts interactively, write manual migration

RULE 5: TENANT ISOLATION
- NEVER query across tenant schemas
- ALWAYS use schema_context('public') for auth operations
- NEVER store tenant-specific data in public schema
- ALWAYS test with multiple tenants
```

### 10.2 Code Quality Standards

```
BACKEND:
- Use AuditBaseModel for all business models
- Use ImmutableModelMixin for financial transactions
- Use select_related/prefetch_related in all ViewSets
- Use explicit serializer fields (never fields = '__all__')
- Add db_index=True on fields used in WHERE/ORDER BY
- Write docstrings for all ViewSets and custom actions
- Use DRF serializer validation (not view-level validation)
- Return proper HTTP status codes (201 for create, 204 for delete)

FRONTEND:
- Use TypeScript interfaces for all API response types
- Use TanStack Query for all API calls (never raw axios in components)
- Use lazy() for all route components
- Invalidate relevant queries after mutations
- Handle loading, error, and empty states in all pages
- Use CSS custom properties for colors (never hardcoded hex in components)
- Use semantic HTML elements (nav, main, section, article)
```

### 10.3 File Creation Checklist

When creating a new feature, verify ALL of the following:

```
Backend:
□ Model created in {app}/models.py
□ Model registered in {app}/admin.py
□ Migration created and applied
□ Serializer created in {app}/serializers.py
□ ViewSet created in {app}/views.py with proper queryset optimization
□ ViewSet registered in {app}/urls.py router
□ Permissions configured (RBACPermission by default)

Frontend:
□ TypeScript interface defined
□ API hook created (useQuery + useMutation)
□ Page component created with loading/error/empty states
□ Route added to App.tsx (lazy import + ProtectedRoute)
□ Sidebar entry added (if applicable)
□ Existing imports verified (no broken references)
□ Page works in both dark and light theme
```

### 10.4 Common Pitfalls to Avoid

```
1. MIGRATION CONFLICTS
   Problem: makemigrations prompts about renames or unrelated model issues
   Solution: Write manual migration files, never use --noinput blindly

2. TENANT SCHEMA ISSUES
   Problem: Model in SHARED_APPS but referenced from TENANT_APPS
   Solution: Use settings.AUTH_USER_MODEL, never import User directly

3. EDIT TOOL STRING MATCHING
   Problem: Special characters (dashes, quotes) differ between editor and file
   Solution: Always Read file first, copy exact strings for Edit operations

4. CIRCULAR IMPORTS
   Problem: Model A imports from Model B which imports from Model A
   Solution: Use string references for ForeignKey ('app.Model')

5. STALE FRONTEND STATE
   Problem: Mutation succeeds but UI doesn't update
   Solution: Always invalidateQueries in onSuccess callback

6. AUTHENTICATION BYPASS
   Problem: New endpoint accidentally uses AllowAny
   Solution: RBACPermission is default; only override for public endpoints

7. MISSING FOREIGN KEY PROTECTION
   Problem: Deleting referenced record causes cascade deletion
   Solution: Use on_delete=models.PROTECT for financial references

8. INLINE STYLES INCONSISTENCY
   Problem: Hardcoded colors instead of CSS variables
   Solution: Always use var(--color-*) for theme compatibility
```

### 10.5 Testing Requirements for AI

```
Before marking a feature complete:

1. BACKEND VERIFICATION
   □ python manage.py check --skip-checks → no errors
   □ python manage.py showmigrations → all applied
   □ python manage.py test {app} → all pass
   □ API endpoint returns correct data (manual curl test)

2. FRONTEND VERIFICATION
   □ npx tsc --noEmit → no TypeScript errors
   □ npm run build → builds successfully
   □ Page renders without console errors
   □ CRUD operations work (create, read, update, delete)
   □ Loading states display correctly
   □ Error states display correctly
   □ Empty states display correctly
   □ Dark theme works
   □ Light theme works

3. INTEGRATION VERIFICATION
   □ Frontend connects to correct API endpoint
   □ Auth token sent with requests
   □ Tenant header sent with requests
   □ 401 redirects to login
   □ Permissions enforced (non-admin can't delete)
```

---

## 11. Testing Strategy

### 11.1 Test Pyramid

```
         ┌──────────┐
         │   E2E    │  ← Playwright/Cypress (future)
         │  Tests   │     Full user flows
        ┌┴──────────┴┐
        │ Integration │  ← DRF APITestCase
        │   Tests     │     API endpoint validation
       ┌┴─────────────┴┐
       │   Unit Tests   │  ← Django TestCase
       │                │     Model methods, serializers, permissions
      ┌┴────────────────┴┐
      │  Static Analysis  │  ← TypeScript, ESLint, Bandit
      │                   │     Compile-time error catching
      └───────────────────┘
```

### 11.2 Existing Test Files

```
core/tests.py           ← Auth, RBAC, tenant selection (most complete)
accounting/tests.py     ← GL, journal posting
budget/tests.py
procurement/tests.py
inventory/tests.py
sales/tests.py
service/tests.py
workflow/tests.py
hrm/tests.py
production/tests.py
quality/tests.py
tenants/tests.py
```

### 11.3 Test Commands

```bash
# Run all tests
python manage.py test --verbosity=2

# Run specific app
python manage.py test core --failfast

# Run specific test class
python manage.py test core.tests.AuthenticationTests

# Run with coverage
pip install coverage
coverage run manage.py test
coverage report --show-missing
coverage html  # Generates htmlcov/index.html

# Frontend (future)
cd frontend
npx vitest run
npx playwright test
```

---

## 12. Production Checklist

### 12.1 Pre-Deployment

```
Environment:
□ SECRET_KEY is unique and not in version control
□ DEBUG=False
□ ALLOWED_HOSTS restricted to production domains
□ CORS_ALLOWED_ORIGINS restricted to production frontend URL
□ Database credentials in secrets manager (not .env file)

Security:
□ SECURE_SSL_REDIRECT=True
□ SECURE_HSTS_SECONDS=31536000
□ SECURE_HSTS_INCLUDE_SUBDOMAINS=True
□ SECURE_HSTS_PRELOAD=True
□ SESSION_COOKIE_SECURE=True
□ CSRF_COOKIE_SECURE=True
□ X_FRAME_OPTIONS='DENY'
□ SECURE_CONTENT_TYPE_NOSNIFF=True
□ SECURE_BROWSER_XSS_FILTER=True
□ SSL certificate installed and auto-renewing

Database:
□ PostgreSQL 14+ with dedicated server
□ pgBouncer connection pooling configured
□ Automated daily backups with retention policy
□ Backup restoration tested
□ Database user has minimal required permissions

Performance:
□ Redis configured for caching and sessions
□ Gunicorn with workers = 2 × CPU cores + 1
□ Nginx serving static files with cache headers
□ Frontend built with npm run build (no sourcemaps)
□ CDN configured for static assets
□ Gzip/Brotli compression enabled

Monitoring:
□ Application error tracking (Sentry)
□ Server monitoring (CPU, memory, disk)
□ Database performance monitoring
□ Uptime monitoring with alerting
□ Log aggregation (ELK stack or similar)

CI/CD:
□ GitHub Actions workflow configured
□ All tests passing on main branch
□ Security scans passing
□ Automated deployment on merge to main
□ Rollback procedure documented and tested
```

### 12.2 Server Setup

```bash
# Ubuntu 22.04+ server setup
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
  postgresql-16 postgresql-contrib-16 \
  nginx certbot python3-certbot-nginx \
  redis-server supervisor

# Application setup
cd /var/www
git clone https://github.com/your-org/dtsg-erp.git
cd dtsg-erp

# Python environment
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Database
sudo -u postgres createdb dtsg_erp
sudo -u postgres createuser dtsg --password
python manage.py migrate --skip-checks --noinput
python manage.py createsuperuser
python manage.py collectstatic --noinput

# Frontend
cd frontend
npm ci
npm run build
cd ..

# Gunicorn (via supervisor)
# /etc/supervisor/conf.d/dtsg-erp.conf
[program:dtsg-erp]
command=/var/www/dtsg-erp/venv/bin/gunicorn dtsg_erp.wsgi:application --bind 127.0.0.1:8000 --workers 4 --timeout 60
directory=/var/www/dtsg-erp
user=www-data
autostart=true
autorestart=true
stdout_logfile=/var/log/dtsg-erp/gunicorn.log
stderr_logfile=/var/log/dtsg-erp/gunicorn-error.log

# Nginx
# /etc/nginx/sites-available/dtsg-erp
server {
    listen 80;
    server_name erp.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name erp.example.com;

    ssl_certificate /etc/letsencrypt/live/erp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/erp.example.com/privkey.pem;

    # Frontend SPA
    location / {
        root /var/www/dtsg-erp/frontend/dist;
        try_files $uri $uri/ /index.html;
        expires 1h;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 10M;
    }

    # Django Admin
    location /admin/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # Static files
    location /static/ {
        alias /var/www/dtsg-erp/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;
}

# SSL certificate
sudo certbot --nginx -d erp.example.com

# Start services
sudo supervisorctl reread
sudo supervisorctl update
sudo systemctl restart nginx
sudo systemctl enable redis-server
```

### 12.3 Maintenance Commands

```bash
# Database backup
pg_dump -U dtsg dtsg_erp | gzip > backup_$(date +%Y%m%d).sql.gz

# Database restore
gunzip -c backup_20260301.sql.gz | psql -U dtsg dtsg_erp

# View logs
tail -f /var/log/dtsg-erp/gunicorn.log
tail -f /var/log/nginx/error.log

# Restart services
sudo supervisorctl restart dtsg-erp
sudo systemctl reload nginx

# Update application
cd /var/www/dtsg-erp
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --skip-checks --noinput
python manage.py collectstatic --noinput
cd frontend && npm ci && npm run build && cd ..
sudo supervisorctl restart dtsg-erp
```

---

## Appendix A: API Endpoint Reference

### Accounting Endpoints (200+)
```
/api/accounting/accounts/
/api/accounting/journals/
/api/accounting/journals/{id}/post/
/api/accounting/journals/{id}/reverse/
/api/accounting/currencies/
/api/accounting/currencies/defaults/
/api/accounting/currencies/convert/
/api/accounting/exchange-rates/
/api/accounting/exchange-rates/import-template/
/api/accounting/exchange-rates/bulk-import/
/api/accounting/exchange-rates/export/
/api/accounting/funds/
/api/accounting/functions/
/api/accounting/programs/
/api/accounting/geos/
/api/accounting/mdas/
/api/accounting/budgets/
/api/accounting/budget-periods/
/api/accounting/vendor-invoices/
/api/accounting/payments/
/api/accounting/customer-invoices/
/api/accounting/receipts/
/api/accounting/fixed-assets/
/api/accounting/asset-categories/
/api/accounting/cost-centers/
/api/accounting/profit-centers/
/api/accounting/bank-accounts/
/api/accounting/tax-codes/
/api/accounting/gl-balances/
/api/accounting/fiscal-years/
/api/accounting/fiscal-periods/
... (75+ more ViewSets registered)
```

### Core Endpoints
```
POST   /api/core/auth/login/
POST   /api/core/auth/logout/
POST   /api/core/auth/select-tenant/
GET    /api/core/auth/my-tenants/
GET    /api/core/users/
GET    /api/core/users/me/
POST   /api/core/users/register/
POST   /api/core/users/change-password/
GET    /api/core/menu/
GET    /api/core/modules/
```

### Tenant Management Endpoints
```
GET    /api/tenants/tenants/
GET    /api/tenants/user-roles/
GET    /api/tenants/modules/
GET    /api/tenants/plans/
GET    /api/tenants/subscriptions/
GET    /api/tenants/payments/
GET    /api/tenants/enabled-modules/
GET    /api/tenants/settings/
GET    /api/tenants/superadmin-dashboard/
```

### Module Endpoints
```
/api/procurement/vendors|requests|orders|grns|invoice-matching/
/api/inventory/items|warehouses|stocks|batches|movements|reconciliations/
/api/sales/customers|leads|opportunities|quotations|orders|delivery-notes/
/api/service/tickets|work-orders|citizen-requests|metrics|schedules/
/api/workflow/approval-groups|templates|approvals|definitions|instances/
/api/hrm/employees|departments|positions|leave|attendance|payroll|payslips/
/api/budget/allocations|lines|variances/
/api/production/work-centers|boms|production-orders|job-cards/
/api/quality/inspections|non-conformances|complaints|checklists|calibrations/
```

---

## Appendix B: Database Schema Count

| App | Models | Migrations | Indexes |
|-----|--------|------------|---------|
| accounting | 90+ | 18 | 15+ |
| budget | 3 | 2 | 3 |
| core | 2 (abstract) | 0 | — |
| hrm | 45+ | 1 | 10+ |
| inventory | 13 | 4 | 8 |
| procurement | 14 | 11 | 6 |
| production | 8 | 1 | 4 |
| quality | 8 | 1 | 4 |
| sales | 9 | 4 | 5 |
| service | 9 | 4 | 5 |
| tenants | 7 | 2 | 5 |
| workflow | 10 | 2 | 5 |
| **Total** | **~220** | **50** | **70+** |

---

*Generated: March 2026 | DTSG ERP v1.0*
