# Production Readiness Plan — Quot PSE

**Baseline assessment (post-Sprint 25)**: ~50% production-ready for real
state-government deployment, ~70% for internal pilot. Core accounting is
strong; surrounding platform (CI/CD, observability, operator tooling,
regulatory validation) is weak.

This plan closes the gap phase-by-phase. Phases are ordered by dependency:
foundation first (tests + CI create the safety net for everything else), then
data correctness (the actual accounting bugs), then platform (observability +
ops), then the long tail.

**Execution rule: sequential, no skipping.** Each task produces a verification
artifact (passing tests, a runbook, a metric) before we move on.

---

## Summary of tracks

| # | Phase | Tasks | Scope |
|---|---|---:|---|
| 1 | Foundation | 5 | CI/CD, coverage, lint gates, secret scan, rate limiting |
| 2 | Data correctness | 6 | Period close, SoFP close entry, GRN↔MDA wiring, cash-flow seeder, override audit |
| 3 | Observability | 4 | Structured logging, Sentry, health endpoints, metrics |
| 4 | Operator readiness | 6 | Backup, DR drill, FiscalYear UI, Appropriation UI, override viewer, onboarding runbook |
| 5 | Regulatory | 4 | FIRS XSD validation, PENCOM format, email SMTP, notifications |
| 6 | Performance | 4 | Index review, denormalised sums, load-test harness, Redis cache |
| 7 | Documentation | 3 | OpenAPI, operator runbook, user guide |
|   | **Total** | **32** | |

Each task has an ID (`P1-T1` = Phase 1 Task 1).

---

## Phase 1 — Foundation (5 tasks)

| ID | Task | Verification |
|---|---|---|
| **P1-T1** | GitHub Actions CI — `python manage.py check`, `pytest`, `tsc --noEmit` on push | `.github/workflows/ci.yml` green on main |
| **P1-T2** | Test coverage reporter + baseline | `pytest --cov` produces `coverage.xml` in CI; baseline in `COVERAGE_BASELINE.md` |
| **P1-T3** | Ruff + mypy (Python) + ESLint (TypeScript) gates in CI | CI fails on violation; baseline clean |
| **P1-T4** | Secret scan (gitleaks) + `.env.example` audit | Zero findings on current HEAD |
| **P1-T5** | DRF global throttling on mutating endpoints | `DEFAULT_THROTTLE_RATES` applied; 429 at limit confirmed |

---

## Phase 2 — Data correctness (6 tasks)

| ID | Task | Verification |
|---|---|---|
| **P2-T1** | Period-close service — close revenue/expense to Accumulated Fund (43xx) | `close_fiscal_year(year)` service; SoFP `is_balanced=True` after close |
| **P2-T2** | Opening-balance seed so Net Assets non-zero from FY start | `seed_demo_gl` posts FY-open entry; Net Assets > 0 in all 3 tenants |
| **P2-T3** | GRN ↔ MDA + PO lifecycle (INVOICED transition) | GRN picks MDA from PO; `ProcurementBudgetLink.status='INVOICED'` after GRN post |
| **P2-T4** | Cash-flow seeder — populate `PaymentInstruction` + verify IPSAS 2 report | Cash-flow statement shows non-zero ops/investing/financing |
| **P2-T5** | Role-assignment override audit view — surface all `[SOD override]` entries | `/api/v1/core/role-assignments/overrides/` returns list |
| **P2-T6** | Dual-control override review UI | `/admin/dual-control-overrides` page with pending/approved filter |

---

## Phase 3 — Observability (4 tasks)

| ID | Task | Verification |
|---|---|---|
| **P3-T1** | Structured JSON logging with `tenant`, `user`, `request_id`, `operation` | JSON log lines in non-DEBUG; parse sample |
| **P3-T2** | Sentry SDK integration (optional — gated on `SENTRY_DSN`) | Test exception → dashboard |
| **P3-T3** | `/healthz` + `/readyz` endpoints (DB ping, migration check) | 200 from `/healthz`; `/readyz` fails if pending migrations |
| **P3-T4** | `/metrics` Prometheus exporter (request rate, post-latency, approval queue depth) | `/metrics` scrapes successfully |

---

## Phase 4 — Operator readiness (6 tasks)

| ID | Task | Verification |
|---|---|---|
| **P4-T1** | Backup script — `pg_dump` per tenant + public, rotation policy | `scripts/backup.sh`; restore test documented |
| **P4-T2** | DR drill doc — restore into fresh DB, measure RTO/RPO | `docs/DR_DRILL.md` with timing |
| **P4-T3** | FiscalYear admin UI (create/close from React) | `/admin/fiscal-years` page; close triggers P2-T1 service |
| **P4-T4** | Appropriation admin UI — full CRUD with 6 NCoA dims | `/budget/appropriations` page working |
| **P4-T5** | Combined audit panel for `DualControlOverride` + `[SOD override]` assignments | `/admin/audit/overrides` page |
| **P4-T6** | Tenant-onboarding runbook | `docs/RUNBOOK_ONBOARD_TENANT.md` — new tenant from zero via the doc |

---

## Phase 5 — Regulatory + integrations (4 tasks)

| ID | Task | Verification |
|---|---|---|
| **P5-T1** | FIRS WHT/VAT XML validated against XSD | pytest validates export; round-trip passes |
| **P5-T2** | PENCOM pension schedule validated against spec | Same — validated sample export |
| **P5-T3** | Email delivery — real SMTP wired via Django backend | Notification triggers real email |
| **P5-T4** | Notification UI fan-out — unread count + drawer | Sidebar bell + panel working |

---

## Phase 6 — Performance + scale (4 tasks)

| ID | Task | Verification |
|---|---|---|
| **P6-T1** | DB index + `EXPLAIN ANALYZE` review | `docs/PERFORMANCE_AUDIT.md` with before/after |
| **P6-T2** | Denormalise `Appropriation.total_committed` / `.total_expended` | Columns + backfill migration; property still works |
| **P6-T3** | Load-test harness (Locust) — 100 users × 10 req/s | `loadtests/load/` + report |
| **P6-T4** | Redis cache for hot reports (SoFP, SoFPerf) with cache-bust on post | 10× latency improvement on repeat fetches |

---

## Phase 7 — Documentation (3 tasks)

| ID | Task | Verification |
|---|---|---|
| **P7-T1** | OpenAPI 3.1 via drf-spectacular at `/api/schema/` + Swagger at `/api/docs/` | Both URLs render without error |
| **P7-T2** | Operator runbook (10+ scenarios) | `docs/RUNBOOK.md` |
| **P7-T3** | End-user guide — one chapter per baseline role | `docs/USER_GUIDE.md` |

---

## Estimated effort

~16 days of focused work, parallelisable across 3 engineers. Phase 1 is
blocking — all subsequent phases depend on CI being green.

## Execution policy

- Sequential per phase; one task `in_progress` at a time.
- Verification artifact committed before marking complete.
- Phase 1 Task 1 first — no other task ships without CI green.
