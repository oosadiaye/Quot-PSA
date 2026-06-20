# High‑Traffic Readiness — Review & Remediation Plan

**Date:** 11/06/2026 · **Scope:** QUOT PSA (Django/DRF + React/Vite + PostgreSQL 15 + Redis + Celery)
**Purpose:** Review the application for high user traffic (indexing, caching, query efficiency, concurrency, frontend) and lay out a prioritized plan to resolve the residual gaps.

> **Headline:** the fundamentals are already strong. This is a **scale‑hardening** plan, not a rescue. The items below close the *remaining* gaps that matter only as concurrency and data volume climb well beyond the current 40‑user/single‑tenant target.

---

## 1. Current State — what's already in place (verified)

> **Correction (after deeper review):** several items first drafted as "gaps" are in fact **already implemented** — connection pooling config, read‑replica routing, slow‑query logging, gunicorn/Postgres tuning, and per‑scope throttling. The table below reflects the *actual* (more mature) state; the gap list in §2 has been narrowed accordingly.

| Area | Status | Evidence |
|---|---|---|
| **Indexing** | ✅ Strong | ~324 `db_index` fields + composite indexes (`jrn_line_header_account_idx`, `jrn_line_header_ncoa_idx`, `vi_status_date_idx`) with **EXPLAIN ANALYZE before/after (11× gains)** — [docs/PERFORMANCE_AUDIT.md](PERFORMANCE_AUDIT.md), migration `0079_perf_indexes` |
| **Report caching** | ✅ Good | Redis cache‑aside with generation‑counter invalidation + Redis‑down fallback, wired into IPSAS + GL views — [accounting/services/report_cache.py](../accounting/services/report_cache.py) |
| **Query hygiene** | ✅ Good | 401 `select_related` / 35 `prefetch_related` across apps |
| **Denormalised sums** | ✅ Done | `Appropriation.total_committed/.total_expended` (P6‑T2) |
| **Connection pooling** | ✅ Config present | `deploy/pgbouncer.ini` (1000 clients → ~50 server conns, **session mode** — deliberate for django‑tenants); `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS` |
| **Read replica** | ✅ Implemented | `TenantAwareReadReplicaRouter` + `DATABASES['replica']` gated by `DB_REPLICA_HOST`; reports/dashboards/lists route to replica, writes to primary ([quot_pse/db_router.py](../quot_pse/db_router.py)) |
| **Throttling** | ✅ Scoped | Global (anon 100/h, user 1000/h, login 3/min) **plus scopes**: `writes` 300/h, `bulk_import` 10/h, `approve` 120/h, `signup`, `impersonate` |
| **Web/DB tuning** | ✅ Done | gunicorn gthread (2×CPU+1 workers, 4 threads, `max_requests` recycle, preload) — [deploy/gunicorn.conf.py](../deploy/gunicorn.conf.py); Postgres `max_connections=200`, memory/WAL, `statement_timeout`, `lock_timeout`, parallel query, **`log_min_duration_statement=1000` (slow‑query log ON)** — [deploy/postgresql_tuning.sql](../deploy/postgresql_tuning.sql) |
| **Observability** | 🟡 Improving | Sentry SDK wired; slow‑query log on; **`pg_stat_statements` + autovacuum tuning just added** to `postgresql_tuning.sql`; cache‑hit/p95 dashboards still TODO |
| **Load testing** | ✅ Harness exists | Locust `loadtests/load/` (P6‑T3, 100u×10rps) |

---

## 2. Gap Analysis — residual risks for high traffic

| # | Gap (genuine, remaining) | Risk at scale | Severity |
|---|---|---|---|
| G2 | **Unbounded page cap** — `max_page_size = 10000`. Audit: fetch‑all is pervasive (**21 callers at 10000, 15 at 9999, VendorList 99999**), so the cap can't be lowered until callers move to server‑side search. ✅ **Enabling foundation built (verified, non‑breaking):** `SearchableSelect` gained a strictly‑additive `onSearch` async mode (existing consumers byte‑for‑byte unchanged), and `makeAccountSearch` ([useAccountSearch.ts](../frontend/src/features/accounting/hooks/useAccountSearch.ts)) wires the existing `/accounting/accounts/?search=` endpoint (backend already supports it). **Remaining:** migrate the account/vendor/customer pickers to `onSearch` (one form at a time, UX‑validated with the app running), then lower the cap. | Memory/CPU spikes, slow payloads, abuse vector | **High** (foundation done; FE migration = testable next step) |
| G3 | **Caching breadth** — only reports are cached. Hot **reference/lookup data** (NCoA, COA, vendors, fiscal years, settings) and **dashboards** recompute every request; no HTTP `ETag`/`Cache‑Control` on GET lists. | Redundant DB load on every page nav | **Medium‑High** |
| G4 | **N+1 residual.** ✅ **Fixed:** Vendor + Customer invoice list endpoints now `prefetch_related('lines')` (was N queries/page for nested lines). **Remaining:** `VendorInvoiceSerializer._linked_pv` does a `PaymentVoucherGov` lookup **per invoice** on the AP list (1 query/row) — needs batching via a context map. Other list serializers verified clean (Payment/Receipt already prefetch `allocations`; contracts prefetch `milestones__ipc`). | Query storms on list endpoints | **Medium** |
| G5 | **Frontend virtualization** used in only **one** place (`GLReports`). Big tables (Journals, Vendors, COA, Invoices) render all rows. | DOM bloat / jank on large lists | **Medium** |
| G6 | **Heavy exports — confirmed SYNCHRONOUS** (openpyxl in‑request). ✅ **Backend async path BUILT (additive, existing sync endpoints untouched):** `AsyncExportJob` model + migration `0107`, a Celery task (`tasks_export.run_async_export`) that renders via the existing `ReportRenderer` and stores the artifact, and `POST /accounting/exports/` + `GET …/<id>/` + `…/download/` (owner‑scoped, `exports` throttle). Django check clean; regression test added. **Remaining:** frontend export buttons to adopt the async path (poll + download) — UX step. | Worker starvation under concurrent exports | **Medium** → backend done |
| G7 | **Multi‑node app tier** — read replica is done; the app tier is still single‑node (no LB / horizontal scale), static served by the app node. | Throughput ceiling | **Medium** (scale‑out) |
| G8 | **DB volume** — `JournalLine` (hottest table) unpartitioned; multi‑year × multi‑MDA growth → millions of rows per scan. | Slow aggregates as data grows | **Medium** (future) |
| G9 | **Observability dashboards** — slow‑query log + `pg_stat_statements` (just added) cover the DB; still missing **cache hit‑rate / p95 latency dashboards** and **Locust‑in‑CI** regression gate. | Slower to spot regressions | **Low‑Medium** |
| G10 | **Throttle scopes** — ✅ **Done:** added `reports` (600/h) + `exports` (300/h) env‑overridable rates and applied the `exports` scope to the statutory exporter base view. IPSAS report views can adopt the `reports` scope via the same one‑line pattern. | One heavy user degrades reports | **Low** → resolved |
| G11 | **Transaction‑pooling decision** — PgBouncer ships in **session mode** (safe for django‑tenants). Transaction mode (max multiplexing) needs `DISABLE_SERVER_SIDE_CURSORS=True` + verified per‑request `search_path` isolation before adopting. | Lower pool efficiency at very high client counts | **Low** (operational) |

> **Already implemented (removed from the gap list after review):** connection‑pooler config (`deploy/pgbouncer.ini`), read‑replica routing, slow‑query logging, gunicorn/Postgres tuning, and per‑scope throttling. `pg_stat_statements` + autovacuum tuning were **added in this pass**.

---

## 3. Remediation Plan (phased, prioritized)

### Phase A — Quick wins / safety rails (1–2 weeks, low risk)

**A1 — Operationalise pooling + observability (mostly config).** *(G9, G11)*
- ✅ **Done in this pass:** `pg_stat_statements` + autovacuum tuning added to `deploy/postgresql_tuning.sql` (needs a Postgres **restart** for `shared_preload_libraries`, then `CREATE EXTENSION pg_stat_statements` per tenant DB).
- Make `deploy/pgbouncer.ini` part of the **standard** deploy (Django `DB_PORT=6432`). Keep **session mode** (safe for django‑tenants). Only evaluate `pool_mode=transaction` (with `DISABLE_SERVER_SIDE_CURSORS=True` + verified per‑request `search_path` isolation) if client counts demand max multiplexing.
- **Verify:** `pgbouncer SHOW POOLS`; `pg_stat_statements` top‑20 query report renders; sustain Locust 200u with no `too many connections`.

**A2 — Cap pagination safely (differentiate, don't blanket‑lower).** *(G2)*
- Introduce a dedicated `ReferencePagination` (higher cap, e.g. 5000) for the few **lightweight fetch‑all** endpoints that need it (COA, NCoA segments), and lower the **general** `AccountingPagination.max_page_size` 10000 → **500** for transactional lists. First fix the **coupled** frontend `page_size=9999` callers: move **vendor‑history totals to a server‑side summary** so the modal no longer needs every row (then it can paginate), and page/stream the NCoA import.
- **Verify:** heavy transactional list `?page_size=10000` returns ≤500; COA picker still returns the full chart; vendor‑history totals match before/after.

**A3 — Cache reference/lookup data + HTTP cache headers.** *(G3)*
- Wrap read‑mostly lookups (NCoA segments, COA, fiscal years, currencies, settings, vendor/customer pickers) in `report_cache.get_or_compute` (short TTL 5–15 min) with invalidation on write. Add `ETag` + `Cache‑Control: private, max‑age=…` to GET list/detail responses (a small DRF mixin).
- **Verify:** repeat page navigations show cache hits; conditional GETs return 304.

**A4 — Apply existing throttle scopes to report/export endpoints.** *(G10)*
- The `writes`/`bulk_import`/`approve` scopes already exist; add a `reports`/`exports` scope and set `throttle_scope` on the IPSAS/statutory/export views so a report flood can't degrade CRUD.
- **Verify:** export/report floods hit 429 without throttling normal CRUD.

### Phase B — Query & frontend hardening (2–4 weeks)

**B1 — N+1 sweep on list endpoints.** *(G4)*
- Add `assertNumQueries`/`nplusone` (or django‑debug‑toolbar in dev) over the top list endpoints (vendor/customer invoices, journals, contracts, IPCs, payments). Add `prefetch_related('lines', …)` / `Prefetch(...)` where nested serializers iterate.
- **Verify:** each list endpoint is O(1) queries regardless of page size (assert in tests).

**B2 — Virtualize large tables.** *(G5)*
- Extend the existing `@tanstack/react-virtual` pattern (already in `GLReports`) to Journals, Vendors, COA, AP/AR registers. Tune React Query `staleTime`/`gcTime` to cut refetch storms; keep server pagination as the primary guard.
- **Verify:** 1,000‑row list scrolls at 60fps; DOM node count bounded.

**B3 — Offload heavy exports to Celery.** *(G6)*
- Move Excel/PDF/statutory exports to a Celery task → store artifact (object storage) → return a job id + download link (poll/notify). Keep small CSVs synchronous.
- **Verify:** 20 concurrent exports don't reduce web‑worker availability; web p95 latency stable.

**B4 — Observability.** *(G9)*
- Enable `pg_stat_statements` + `log_min_duration_statement=500ms`; emit cache hit‑rate + slow‑endpoint metrics (Sentry performance traces are already wired — turn on `traces_sample_rate`). Run the Locust harness in CI on a perf branch with a regression budget.
- **Verify:** dashboard shows top‑N slow queries, cache hit‑rate, p95 latency; CI fails on >X% regression.

### Phase C — Scale‑out (when sustained load / multi‑tenant grows)

**C1 — Horizontal app tier.** *(G7)* Multiple Gunicorn nodes (gevent/uvicorn workers for IO‑bound report waits) behind a load balancer; shared Redis; sticky‑less sessions (already token/JWT). Serve the React build + static via Nginx cache / CDN with far‑future hashing (already content‑hashed by Vite).

**C2 — Read replica for reporting.** *(G7)* Add a Postgres streaming replica; route IPSAS/dashboard reads to it via a DB router (writes stay on primary). Reports are the heaviest read load and tolerate slight replica lag.

**C3 — Partition the hot table.** *(G8)* Range‑partition `JournalLine`/`JournalHeader` by `fiscal_year` (or posting_date) once a tenant crosses ~1–2M lines; keeps index/scan sizes bounded per period. Pair with autovacuum tuning (`autovacuum_vacuum_scale_factor` lower on hot tables) and consider **materialized views** for the most‑hit dashboards (refresh on post).

---

## 4. Capacity guidance (sizing vs. concurrency)

| Concurrent users | Topology | Notes |
|---|---|---|
| ≤ ~16 (≈40 named) | 1 node · 4 vCPU / 16 GB / NVMe | Current target; Phase A only |
| ~40–80 | 1 node · 8 vCPU / 32 GB · **PgBouncer** | Phase A + B |
| 100–250 | App node(s) + **PgBouncer** + **read replica** | Phase B + C1/C2 |
| 250+ / multi‑tenant | LB + N app nodes + replica + partitioning + CDN | Full Phase C |

---

## 5. Acceptance criteria (definition of done)
- Locust **200 users × 10 rps** sustained for 30 min: web **p95 < 500 ms** on CRUD, **< 1.5 s** on cold reports, **0** `too many connections`, error rate **< 0.1%**.
- No list endpoint exceeds **O(1)** queries (asserted in tests); no response streams **> 500** rows to a browser.
- Cache hit‑rate **> 80%** on hot reports/lookups during a dashboard burst.
- Heavy exports never block web workers (run async).

---

## 6. Effort & sequencing summary
| Phase | Theme | Effort | Risk | Unlocks |
|---|---|---|---|---|
| **A** | Pooling, pagination cap, lookup cache, throttles | ~1–2 wks | Low | Safe to 80 concurrent |
| **B** | N+1 sweep, virtualization, async exports, observability | ~2–4 wks | Low‑Med | Safe to ~150 concurrent |
| **C** | Horizontal app, read replica, partitioning, CDN | as needed | Med | 250+ / multi‑tenant |

> Start with **Phase A** — PgBouncer (A1) and the pagination cap (A2) are the two highest‑value, lowest‑risk changes and remove the only two *hard* failure modes under load.
