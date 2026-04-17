# Accounting Test Suite

## Layout

```
accounting/tests/
├── conftest.py                      # Fixtures (users, accounts, periods, journal factory)
├── test_smoke.py                    # Fast, no-DB import + logic checks  ← CI baseline
├── test_s1_model_integrity.py       # Sprint 1: DB constraints, immutability, uniqueness
├── test_s1_period_control.py        # Sprint 1: fiscal period enforcement
├── test_s1_approval_workflow.py     # Sprint 1: maker-checker + dual control
├── test_s3_audit_hardening.py       # Sprint 3: tamper evidence, write-once, redaction
└── test_s3_year_end_close.py        # Sprint 3: year-end closing journal
```

## Running

### Fast tier (CI baseline — always green)

```bash
pytest accounting/tests/test_smoke.py
```

Five no-DB tests that validate imports and pure helpers. Runs in < 2 s.

### Full DB tier (local developer workflow)

```bash
pytest accounting/tests/
```

Requires a correctly-provisioned tenant-aware test database. See
**"Known limitation"** below before running.

## Known limitation (django-tenants × pytest-django)

The DB-dependent tests (S1 and S3 suites) require a multi-tenant test
database in which both the `public` and `pytest_schema` schemas have been
migrated. This needs care because:

* `core/migrations/0007_organization_userorganization.py` declares a
  cross-schema FK (`core.Organization → accounting.AdministrativeSegment`).
* `core` appears in BOTH `SHARED_APPS` and `TENANT_APPS`, which means
  standard `python manage.py migrate` tries to apply the core migration
  in the `public` schema — but `accounting.administrativesegment` lives
  only in tenant schemas. The migration fails with
  `relation "accounting_administrativesegment" does not exist`.

This is a pre-existing project issue, not something introduced by the
test suite. In production, the bootstrap sequence is
`migrate_schemas --shared` then `migrate_schemas --tenant`, which side-
steps the cross-schema FK. pytest-django's default flow doesn't know
about this distinction.

### Workaround — local dev

```bash
# 1. Create the test DB yourself, run both schema phases, THEN pytest with --reuse-db.
createdb test_public_sector
DJANGO_SETTINGS_MODULE=quot_pse.settings DATABASE_URL=postgres://.../test_public_sector \
    python manage.py migrate_schemas --shared
DJANGO_SETTINGS_MODULE=quot_pse.settings DATABASE_URL=postgres://.../test_public_sector \
    python manage.py migrate_schemas --tenant
pytest accounting/tests/ --reuse-db
```

### Workaround — CI

The GitHub Actions workflow in `.github/workflows/ci.yml` currently runs
the smoke tier only. To extend CI to the DB tier, add a step BEFORE
`pytest`:

```yaml
- name: Create tenant-aware test database
  run: |
    psql -h localhost -U quot -c 'CREATE DATABASE test_public_sector;'
    python manage.py migrate_schemas --shared
    # pytest_schema tenant is created by conftest.django_db_setup.
```

### Longer-term fix (out of scope for Sprint 4)

Move `core` out of `SHARED_APPS` (tenant-only) OR refactor
`core.Organization` to reference `accounting.MDA` (which lives in
both schemas) instead of the NCoA segment. Either change is a
one-line schema refactor but requires a data migration for existing
production tenants.

## Fixtures reference

See `conftest.py` for the full list. Key fixtures:

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `maker_user` | function | User who SUBMITS (cannot self-approve). |
| `checker_user` | function | User who APPROVES (different from maker). |
| `superuser` | function | Bypasses maker-checker (emergency override). |
| `cash_account` | function | Asset account, NCoA 10100000. |
| `expense_account` | function | Expense account, NCoA 50100000. |
| `revenue_account` | function | Income account, NCoA 40100000. |
| `accumulated_fund_account` | function | Equity account for year-end close target. |
| `open_fiscal_period` | function | Currently-open monthly period. |
| `closed_fiscal_period` | function | Closed period in 2020 for lock tests. |
| `raw_journal` | function | Factory: `([(account, dr, cr), ...], reference=..., status=...) → JournalHeader`. |

## Markers

```python
@pytest.mark.integration   # Hits the DB (runs in the DB tier)
@pytest.mark.slow          # > 1 s; excluded from pre-commit fast lane
@pytest.mark.ipsas         # IPSAS compliance regression
@pytest.mark.audit         # Audit-trail tamper-evidence regression
```

Filter by marker:

```bash
pytest -m "not slow"
pytest -m "audit"
```
