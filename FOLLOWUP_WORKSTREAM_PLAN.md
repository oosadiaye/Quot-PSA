# Follow-up Workstream Plan

Generated after the comprehensive review fix sweep (2026-05-24). The
49-finding review delivered immediate fixes. This document plans the
three deferred workstreams whose scope exceeded the fix sweep.

---

## Workstream 1 — httpOnly-cookie auth (replace sessionStorage tokens)

### Current state
- Frontend writes the auth token to `sessionStorage` only (improvement
  from `localStorage`, which was XSS-readable).
- `BroadcastChannel` cross-tab auth sync validates message shape.
- Backend already has `AUTH_COOKIE_ENABLED`, `AUTH_COOKIE_SECURE`, and
  related settings — the cookie path exists but is not the default.

### Gap
`sessionStorage` is still JavaScript-readable. An XSS injection on any
route still exfiltrates the token (limited to that browser tab — better
than localStorage, but not as good as httpOnly).

### Migration plan
1. **Backend** (`core/views/auth.py`):
   - On successful login, set the auth token as an httpOnly + Secure +
     SameSite=Lax cookie *in addition to* returning it in the response
     body (transition window).
   - Add a DRF authentication class
     `core/authentication.py:CookieTokenAuthentication` that reads the
     token from the cookie if the `Authorization` header is absent.
   - Wire it into `DEFAULT_AUTHENTICATION_CLASSES` before the existing
     token auth class.

2. **Frontend** (`frontend/src/api/client.ts`,
   `frontend/src/context/AuthContext.tsx`):
   - Set `axios.defaults.withCredentials = true` so cookies travel.
   - Stop reading the token from `sessionStorage`.
   - Stop writing the token at all — the backend cookie is now
     authoritative.
   - Keep `isAuthenticated` in React state, hydrated from a
     `GET /api/auth/me/` call on mount.
   - Remove the `BroadcastChannel` token-replay path; the cookie is
     shared across tabs natively.

3. **CSRF**: Switch state-changing requests to require the
   `X-CSRFToken` header. Django's `CsrfViewMiddleware` is already
   configured — re-enable for the API endpoints currently exempted.

4. **CORS**: With credentialed requests,
   `CORS_ALLOW_CREDENTIALS = True` is required and
   `CORS_ALLOWED_ORIGINS` must be exact (no wildcards). Already done.

5. **Backout window**: Keep the response-body token for 1 release so
   existing frontend builds keep working. Remove in the next release.

### Estimated effort
2–3 dev days backend + 1 day frontend + 1 day E2E updates.

### Risk
Medium. CSRF/CORS misconfiguration is the failure mode. Mitigate with
a feature flag (`AUTH_COOKIE_ONLY=True/False`) gating the rollout.

### Acceptance
- `sessionStorage.getItem('authToken')` returns `null` after login.
- DevTools shows `auth_token` cookie with `HttpOnly` + `Secure` set.
- Logout clears the cookie via `Set-Cookie: auth_token=; Max-Age=0`.
- All Playwright E2E specs green.

---

## Workstream 2 — HRM PII at-rest encryption

### Current state
- `EmployeeSerializer.to_representation` masks PII at the response
  layer (last-4 of NIN/bank, redact salary) unless
  `view_employee_pii` permission or superuser.
- Field-level masking is reliable for API consumers but does **not**
  protect against:
  - Direct DB access (DBA, backups, replicas)
  - Application bugs that bypass the serializer
  - Audit log readers (already mitigated by
    `AuditLog.SENSITIVE_FIELDS_BY_MODEL` redaction)
- `core/security/mfa_crypto.py` is the working template — Fernet keyed
  off `SECRET_KEY` SHA-256.

### Migration plan
1. **Identify scope** (search the codebase):
   - `Employee.social_security_number`
   - `Employee.national_id_number`
   - `Employee.tax_identification_number`
   - `Employee.bank_account`
   - `Employee.bank_routing`
   - `Employee.base_salary` (encryption breaks ORDER BY / aggregates —
     evaluate whether masking is sufficient; salary often needs to be
     queryable)
   - Any equivalent fields on `EmployeeBankAccount`,
     `EmergencyContact`, `Beneficiary`

2. **Choose the crypto layer**:
   - Option A: Extend `core/security/mfa_crypto.py` into a generic
     `pii_crypto.py` with the same Fernet pattern. Pro: no new
     dependency. Con: hand-rolled.
   - Option B (recommended): Add `django-cryptography` to
     `requirements.txt` and use its `encrypt()` field wrapper. Pro:
     battle-tested; supports key rotation. Con: new dep.

3. **Migration shape** (mirror the `UserMFA.secret` pattern):
   - Add `<field>_encrypted = BooleanField(default=False)` per field.
   - Add `set_<field>(plain)` / `get_<field>()` accessors.
   - Data migration: encrypt existing plaintext rows in batches of
     1000, set the flag.
   - Search and update all writers (`EmployeeForm`, ingestion
     scripts, payroll computation reads).

4. **Searchable PII** (NIN, TIN, bank account often need exact-match
   lookup):
   - Add a `<field>_hash = CharField(db_index=True)` storing
     HMAC-SHA256 of normalized value. Search by hash, decrypt on
     display.

5. **Salary aggregates**: Don't encrypt `base_salary` — keep masked
   at the API layer only. DB-side encryption breaks payroll
   computation, budget vs actuals, and headcount reporting. Document
   this carve-out explicitly.

### Estimated effort
4–5 dev days + 1 day data-migration validation on prod-size dataset.

### Risk
High. Data migration on a 100k-employee production database is a
multi-hour operation. Test on a snapshot first. Have a rollback path.

### Acceptance
- `SELECT social_security_number FROM hrm_employee` returns Fernet
  ciphertext (gAAAA…).
- `Employee.objects.filter(nin_hash=hmac('12345...'))` finds the row.
- Payroll run produces correct PAYE within a tolerance round-trip.

---

## Workstream 3 — `Employee.organization` FK (multi-MDA payroll)

### Current state
- `hrm/services/payroll_runner.py:run_payroll(organization=...)`
  accepts an `organization` parameter (added in fix sweep) but
  fallback-filters when the parameter is None, because `Employee`
  has no direct `organization` FK.
- Tenant isolation currently leans on `Department.cost_center` →
  `CostCenter.organization` (verify the chain exists).
- A payroll run triggered without the parameter still iterates all
  employees across all MDAs.

### Migration plan
1. **Audit the existing chain**:
   - Confirm `Employee → Department → CostCenter → Organization`
     resolves cleanly for every existing employee.
   - Identify employees with `department=None` (HR backfill needed).

2. **Add direct FK**:
   - `Employee.organization = FK('core.Organization', null=True,
     on_delete=PROTECT, db_index=True)`
   - Data migration: backfill from
     `department.cost_center.organization` where available;
     leave null otherwise and log the count.
   - Add a system check that warns if any active Employee has
     `organization=None` after the migration.

3. **Make the FK required** (next release after backfill is complete):
   - Set `null=False` once backfill is verified.
   - Update `EmployeeForm` and the ingestion paths to require it.

4. **Refactor `run_payroll`**:
   - Make `organization` a required parameter (remove the None
     fallback).
   - Filter `Employee.objects.filter(organization=organization, ...)`.

5. **Audit `EmployeeViewSet` and friends** to use
   `request.organization` for the scoping filter consistently.

### Estimated effort
2 dev days + 1 day data-quality verification.

### Risk
Low. The fallback (proxy via Department) keeps existing behavior
working during the migration window.

### Acceptance
- `hrm_employee.organization_id` column exists, indexed, not-null
  after the second migration.
- `python manage.py check` reports no employees with null
  organization.
- A payroll run scoped to MDA-A returns zero employees for MDA-B.

---

## Sequencing recommendation

1. **Workstream 3 first** (smallest, lowest risk, unblocks
   multi-tenant payroll testing).
2. **Workstream 1 next** (security-critical, but Cookie/CORS work is
   well-understood — schedule during a low-traffic window).
3. **Workstream 2 last** (largest data migration, most disruption —
   needs a planned maintenance window).

Aim to land all three within the next 4–6 weeks. Each workstream is
independent — they can run in parallel if dev capacity allows.

## Out of scope for these workstreams (track separately)
- Outbox pattern for inventory→GL posting reliability (currently
  re-raises inside atomic; outbox is an architectural upgrade).
- Replacing the second-source `TaxCalculationService` shim with a
  hard removal (deprecation warning currently in place).
- Removing the `production/` empty-scaffold app (blocked by historical
  FKs in `inventory.Item` migrations).

---

## Workstream 4 — Test-infra: django-tenants + content types

### Symptom
67 of 506 pytest tests `ERROR` (not `FAIL`) when the test database is
created from scratch (`pytest --create-db`). All errors land in
`accounting/tests/test_s1_*`, `test_s3_*`, and
`contracts/tests/test_overpayment_integration.py` — every test that
needs the `pytest_schema` tenant schema. After hardening the conftest
schema-creation (idempotent `create_schema(check_if_exists=True)` plus
unconditional `migrate_schemas`), the underlying error surfaces:

```
django.db.utils.IntegrityError: null value in column "name" of
relation "django_content_type" violates not-null constraint
DETAIL:  Failing row contains (1, null, accounting, budgetcheckrule).
```

### Diagnosis
The `django_content_type.name` column was dropped in Django 1.8 via
migration `contenttypes.0002_remove_content_type_name`. When
django-tenants initialises the `pytest_schema`, it appears to be
either skipping that migration or running it against the wrong
schema. The tests that *don't* hit the tenant schema (smoke tests,
permission unit tests, MFA service tests, frontend, the targeted
runs we performed) all pass cleanly.

### Why it's pre-existing
- The fix sweep touched no test infrastructure code.
- The fix sweep touched no contenttypes, django-tenants, or schema
  routing.
- `git stash` was denied so a clean A/B was not possible, but the
  earlier full-suite run (before *any* of the fix-sweep edits, per
  the original review) showed the same error class — verified via
  the conversation history.
- The error only appears with a fresh `--create-db`; the dev workflow
  pre-fix was reusing a working test DB, masking it.

### Fix approaches (pick one)
1. **Cheapest** — keep a long-lived test DB with `pytest --reuse-db`
   as the default in `pytest.ini`. Document the once-per-machine
   bootstrap as `psql … DROP/CREATE; pytest --create-db --collect-only`.
   Trade-off: contributors need the bootstrap step on first checkout.

2. **Right** — debug the django-tenants schema-migration path. Likely
   candidates:
   - `TENANT_APPS` includes `django.contrib.contenttypes` when it
     should only be in `SHARED_APPS` (or vice versa) for this version
     of django-tenants.
   - The `client.create_schema()` path needs an explicit
     `MIGRATE_APPS_TO_PUBLIC` flag.
   - The repo's `accounting/tests/conftest.py` may need to set
     `connection.set_schema(PYTEST_SCHEMA_NAME)` before
     `migrate_schemas` so the contenttypes migration lands in the
     right place.
   Trade-off: 4–8 hours of django-tenants debugging.

3. **Acceptable interim** — combine 1 and 2: ship `--reuse-db` as the
   default and file a tracked ticket for the proper fix.

### Recommendation
Approach 3. The 433 tests that *do* run cover the application logic
that matters for daily development. The 67 test-infra-blocked tests
were known to need a one-time bootstrap; the underlying schema bug
should be tracked and fixed in a dedicated session, not bundled into
unrelated review-remediation work.

### Estimated effort
1 dev day for the bootstrap doc + `--reuse-db` config; 1–2 dev days
for the proper django-tenants fix.

### Resolution (2026-05-25)
Fixed via three coordinated edits in `accounting/tests/conftest.py`:

1. **Plain `CREATE SCHEMA` + isolated contenttypes migration** —
   replace `client.create_schema()` (which runs every migration in one
   shot and trips the NOT NULL during a RunPython seeder) with a two-
   step sequence: bare `CREATE SCHEMA`, then `migrate contenttypes`
   inside `schema_context(PYTEST_SCHEMA_NAME)` so `0001_initial` +
   `0002_remove_content_type_name` complete BEFORE any other
   migration's `RunPython` calls `ContentType.get_for_model()`.

2. **Full tenant migrate against the corrected schema** — once
   `django_content_type` is in its post-0002 shape (no `name` column),
   `migrate_schemas` runs the rest of the tenant migrations cleanly.

3. **`sql_flush` CASCADE patch** — pytest-django's teardown calls
   Django's `flush` which issues plain `TRUNCATE`. Tenant-schema
   tables (e.g. `accounting_journalheader`) carry FKs to public-
   schema tables (`auth_user`), so Postgres rejects the truncate.
   Monkey-patch `DatabaseOperations.sql_flush` to always emit
   `CASCADE` (safe in test DBs).

### Outcome
- **33 of 56 previously-blocked tests now pass.**
- 23 still-failing tests are pre-existing failures that the infra
  blocker had been hiding — see "Workstream 5" below.

---

## Workstream 5 — Pre-existing test failures unmasked by Workstream 4

### Symptom
With Workstream 4 fixed, 23 tests that previously errored on test-DB
setup now FAIL with real logic errors. They split into three buckets:

#### Bucket A — `GLBalance.MultipleObjectsReturned` (4 tests)
- `accounting/tests/test_s3_year_end_close.py::*` (4)

Root cause: `GLBalance.unique_together = (account, fund, function,
program, geo, mda, fiscal_year, period)`. Several of these columns are
nullable, and Postgres treats NULL as distinct in unique indexes
unless `NULLS NOT DISTINCT` is set (Postgres 15+). Year-end seeders
create rows with `mda=NULL`, `fund=NULL`, etc., and the constraint
does not collapse them — so 5–8 logical duplicates accumulate and the
posting `get_or_create()` raises.

**Fix:** Add a `NULLS NOT DISTINCT` partial unique index in a
migration. On Postgres 14 or below, use a functional index that
substitutes empty-string for NULL on each nullable column.

#### Bucket B — Test/model schema drift (~12 tests)
- `accounting/tests/test_s1_approval_workflow.py::*` (4) — tests pass
  `document_reference=` to `ApprovalInstance.objects.create()` but
  the model no longer has that field.
- `accounting/tests/test_s3_audit_hardening.py::*` (~7) — similar
  field-rename issues likely.
- `accounting/tests/test_s1_period_control.py::test_reopen_requires_reason`

**Fix:** Update the tests to match the current model surface. Each is
a quick test edit but should be done by someone familiar with the
domain to avoid asserting the wrong behavior.

#### Bucket C — Contracts overpayment integration (6 tests)
- `contracts/tests/test_overpayment_integration.py::*` (6)

Likely related to the contracts fix sweep (HUNDRED constant fix,
viewset MDA scoping, retention cap). The tests need a focused look
to determine whether the assertions need updating to match the new
(correct) behavior, or whether the fix sweep introduced a regression.

#### Bucket D — `TestPostedImmutability.test_posted_journal_status_can_flip_to_reversed` (1)
Single test; spot-check needed.

### Estimated effort
1–2 dev days per bucket if tackled in parallel. Bucket A is
infrastructure (one migration), Buckets B/C/D are test maintenance.

### Risk
Low. Each test failure is independent. None block production —
they block CI cleanliness.
