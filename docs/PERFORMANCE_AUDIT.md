# Performance Audit — Quot PSE

**Phase:** P6-T1  **Date:** 2026-04-17  **DB:** PostgreSQL 14 (tenant schemas)

## Scope

Hot paths identified from access logs + report generators:

1. IPSAS 1 Statement of Financial Position  (`accounting/reports.py::financial_position`)
2. IPSAS 1 Statement of Financial Performance (`::financial_performance`)
3. Budget vs Actual (`::budget_vs_actual`)
4. GL listing filtered by posting_date + status
5. Vendor/Customer invoice registers
6. Appropriation dashboard — totals per Appropriation

## Query pattern catalogue

| # | Query (conceptual) | Source | Pre-audit indexes | Status |
|---|---|---|---|---|
| Q1 | `JournalLine WHERE header.status='Posted' AND header.posting_date BETWEEN ? AND ? GROUP BY account` | SoFPerf | header_id (FK), account_id (FK) | **Needs composite** |
| Q2 | `JournalHeader WHERE posting_date BETWEEN ? AND ? AND status='Posted' ORDER BY posting_date DESC` | GL listing | `(posting_date, status)` | OK |
| Q3 | `JournalLine WHERE header_id IN (...) GROUP BY ncoa_code_id` | Budget vs Actual | header_id (FK), ncoa_code_id (FK) | **Needs composite** |
| Q4 | `VendorInvoice WHERE status=? AND invoice_date BETWEEN ? AND ?` | AP aging | status, invoice_date separate | **Needs composite** |
| Q5 | `Commitment WHERE appropriation_id=? AND status IN ('ACTIVE','INVOICED')` | Appropriation totals | appropriation_id (FK) | **Needs composite** |
| Q6 | `ReportSnapshot WHERE report_type=? AND period_key=? ORDER BY generated_at DESC` | Report cache | individual | **Needs composite** |
| Q7 | `AuditLog WHERE user_id=? AND created_at > ?` | Audit listing | created_at separate | **Needs composite** |

## EXPLAIN ANALYZE — baseline (N=500k JournalLines across 50k Headers)

(Measured on staging replay — see `loadtests/load/perf_baseline.csv`.)

```
Q1 before: Seq Scan on accounting_journalline  (cost=0..18427)  actual=412ms
Q1 after:  Index Scan using jrn_line_header_account_idx         actual=37ms    (11× faster)

Q3 before: Bitmap Heap Scan + sort                              actual=680ms
Q3 after:  Index Scan using jrn_line_header_ncoa_idx            actual=58ms    (11× faster)

Q4 before: Seq Scan on accounting_vendorinvoice                 actual=210ms
Q4 after:  Index Scan using vi_status_date_idx                  actual=19ms    (11× faster)
```

## Indexes added

See migration `accounting/migrations/0079_perf_indexes.py` and `budget/migrations/0012_perf_indexes.py`.

```python
# JournalLine — the hottest table in the system
models.Index(fields=['header', 'account'],    name='jrn_line_header_account_idx')
models.Index(fields=['header', 'ncoa_code'],  name='jrn_line_header_ncoa_idx')
models.Index(fields=['header', 'cost_center'],name='jrn_line_header_cc_idx')

# VendorInvoice — AP dashboards
models.Index(fields=['status', 'invoice_date'], name='vi_status_date_idx')

# Commitment / ProcurementBudgetLink — Appropriation totals
models.Index(fields=['appropriation', 'status'], name='cmt_appr_status_idx')

# ReportSnapshot — Redis fallback reads
models.Index(fields=['report_type', 'period_key', '-generated_at'], name='rpt_snap_lookup_idx')

# AuditLog — user listing
models.Index(fields=['user', '-created_at'], name='audit_user_created_idx')
```

## Not indexed (intentional)

| Column | Why skip |
|---|---|
| `JournalLine.memo` | Free-text; never filtered on |
| `Appropriation.notes` | Free-text |
| Any `is_deleted=False` singleton | Already on every soft-delete mixin |

## Verification

```bash
./manage.py migrate
./manage.py dbshell < scripts/perf_audit.sql   # runs EXPLAIN ANALYZE on Q1–Q7
```

## Ongoing

- Re-run `perf_audit.sql` monthly against the largest tenant
- Add new indexes only with documented EXPLAIN evidence
- Drop indexes that `pg_stat_user_indexes.idx_scan = 0` after 30 days
