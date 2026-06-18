# Deployment Playbook — `fix/comprehensive-review-remediation`

This playbook covers the production deployment of the
`fix/comprehensive-review-remediation` branch (9 commits, 94 findings
closed across two reviews, 8 migrations). It is written for the
operator running the deploy plus their DBA.

> **Do not** run any of the migrations below without a verified DB
> backup. Migration `hrm/0019_backfill_employee_pii_encryption` is
> **irreversible** without a custom decrypt migration.

---

## 0. Pre-flight (do this once, before anything)

### 0.1 Verify the branch state

```bash
git fetch origin
git checkout fix/comprehensive-review-remediation
git log --oneline -10
```

Expected top of log (newest first):
```
55a37d8 fix(WS6-followup): close H12 view-layer aging duplicates
5c29b1d fix: Workstream 6 (continued) — 26-file payload
986a99e fix: Workstream 6 — close 45 findings from comprehensive integration review
4de6474 fix: close 2 surfaced production regressions from comprehensive review
40b9fbd chore(frontend): extract AmountInput component with thousand-separator display
5ec6fa7 feat: Workstream 2 — HRM PII at-rest encryption
e2ab765 feat: Workstream 1 — httpOnly auth cookie rollout (behind feature flag)
65ce21e fix: Workstream 5 — resolve 23 test failures unmasked by WS-4 (56/56 pass)
e7a0fb6 fix: comprehensive codebase review remediation (49 findings) + Workstreams 3 & 4
```

If `40b9fbd` (AmountInput chore) is **not wanted** in this release, do
the drop NOW (not after deploy):
```bash
git rebase -i e7a0fb6   # in editor, delete the 40b9fbd line
git push --force-with-lease origin fix/comprehensive-review-remediation
```

### 0.2 Lock `SECRET_KEY`

Two migrations encrypt at rest using a Fernet key derived from
`SECRET_KEY`:

- `core/0014_usermfa_secret_encrypted` — re-encrypts every existing
  `UserMFA.secret` in place.
- `hrm/0019_backfill_employee_pii_encryption` — encrypts NIN, TIN,
  BVN, bank account, bank routing on every Employee row.

**After these migrations run, `SECRET_KEY` becomes irreversibly
load-bearing.** Rotating it without a re-encrypt migration permanently
corrupts all encrypted columns.

Actions:
1. Confirm with the team that `SECRET_KEY` will NOT be rotated for at
   least 30 days post-deploy.
2. If you have any automated SECRET_KEY rotation jobs (e.g., a periodic
   cron), disable them and document the disable.
3. Verify the production `SECRET_KEY` is committed to your secret
   manager (not just on-host), with an audit log of who can read it.

### 0.3 Verified DB backup

```bash
# Logical backup (preferred for selective restore)
pg_dump -h <prod-host> -U <prod-user> -F c -f pre_ws6_remediation.dump <dbname>

# Verify restore works on a staging DB
createdb staging_restore_test
pg_restore -h <staging-host> -d staging_restore_test pre_ws6_remediation.dump
```

Do not proceed until the staging-restore-test confirms a clean restore.
A backup you've never restored is not a backup.

### 0.4 Capture pre-deploy baseline metrics

```sql
-- Sub-ledger / GL reconciliation baseline (so post-deploy diffs are
-- attributable to the deploy itself, not pre-existing drift).
SELECT
    COUNT(*) FILTER (WHERE status='Posted') AS posted_invoices,
    COUNT(*) FILTER (WHERE status='Sent') AS sent_invoices,
    SUM(total_amount - paid_amount) FILTER (WHERE status IN ('Sent','Partially Paid')) AS open_ar_subledger
FROM accounting_customerinvoice;

SELECT
    SUM(debit_balance - credit_balance) AS ar_gl_balance
FROM accounting_glbalance
WHERE account_id = (
    SELECT id FROM accounting_account WHERE code = '12010101'
);

-- Save the diff. If reconciliation_diff > 1 kobo, you have
-- pre-existing drift; document it so the M3 GL-reconciliation
-- warning post-deploy isn't blamed on the deploy.
```

Capture the same for AP control account `41010001`.

### 0.5 Identify and audit `check_warrant_availability` callers

The default flipped from `strict=False` to `strict=True` (finding C7).
Callers that legitimately want soft mode (validation previews,
dashboard projections, what-if calculators) must pass `strict=False`
explicitly.

```bash
# From the project root
grep -rn "check_warrant_availability" --include="*.py" \
  --exclude-dir=.venv --exclude-dir=migrations --exclude-dir=tests
```

Review each hit. For each one that is a **preview / projection**
(non-blocking), explicitly add `strict=False`. The production posting
paths (payables, PO, journals) are already correct by default.

---

## 1. Deployment sequence

### 1.1 Maintenance window

Plan for **30–60 minutes** of maintenance:
- 8 migrations apply in ~10 min on a typical mid-sized DB.
- `hrm/0019` PII backfill takes ~5–10 min per 100k Employee rows.
- `accounting/0103` GLBalance dedupe SQL is the second-largest step.

### 1.2 Deploy code

```bash
# Standard deploy steps for your infra
# (PR merge to main → CI/CD pipeline → blue/green or rolling)
```

### 1.3 Apply migrations IN ORDER

```bash
python manage.py migrate
```

Migration plan (Django auto-orders these correctly via dependencies,
but for review:)

| # | Migration | Risk | Reversible? | Notes |
|---|---|---|---|---|
| 1 | `contracts/0011_contract_retention_cap_percent` | Low | Yes | Adds nullable field with default 0.10. No data migration. |
| 2 | `core/0014_usermfa_secret_encrypted` | **High** | **No** | Re-encrypts every `UserMFA.secret`. Idempotent via `secret_encrypted` flag. |
| 3 | `hrm/0016_employee_organization` | Low | Yes | Adds nullable FK. No data. |
| 4 | `hrm/0017_backfill_employee_organization` | Medium | Reverses to nullify FKs | Backfills from `UserOrganization`. Batched (500 rows/chunk). Idempotent. |
| 5 | `hrm/0018_employee_pii_encrypted_columns` | Low | Yes | Widens 5 CharField columns + adds 5 BooleanField flags + 3 hash columns. |
| 6 | `hrm/0019_backfill_employee_pii_encryption` | **CRITICAL** | **No (irreversible)** | Encrypts NIN/TIN/SSN/bank_account/bank_routing in place. Idempotent via `<field>_encrypted` flag. Reverse op is noop. |
| 7 | `workflow/0011_approval_organization` | Low | Yes | Adds nullable FK. |
| 8 | `workflow/0012_backfill_approval_organization` | Medium | Reverses to nullify FKs | Backfills from `requested_by`. |
| 9 | `accounting/0103_glbalance_unique_nulls_not_distinct` | Medium | Yes | Dedupes existing duplicate `GLBalance` rows (sums into lowest-pk keeper, deletes rest) then replaces `unique_together` with `UniqueConstraint(nulls_distinct=False)`. Requires Postgres 15+. |

### 1.4 Verify migrations applied

```bash
python manage.py showmigrations contracts core hrm workflow accounting | grep -E "0011|0014|0016|0017|0018|0019|0103"
```

Every line must show `[X]`. If any shows `[ ]`, do NOT continue —
abort and investigate.

### 1.5 Run the new system check

```bash
python manage.py check --tag=database
```

Expected: 0 issues. If `accounting.W001` fires ("Header accounts with
`is_postable=True`"), it means migration `accounting/0101` backfill
did not run on this tenant. Investigate and run the backfill manually
before proceeding.

---

## 2. Post-deploy verification

### 2.1 Smoke test the funnel

The biggest architectural change is **9 journal-writing call sites
now route through `IPSASJournalService.post_journal`** (Group A).
Verify each one still works end-to-end:

1. Create a draft Credit Note via the UI → click Post Note → confirm
   journal appears in Trial Balance with `source_module='workflow.credit_note'`
2. Same for Debit Note, Bad Debt Provision, Bad Debt Write-Off,
   Petty Cash Voucher, Petty Cash Replenishment
3. Create a draft AR Invoice → click Post → confirm `source_module='ar.invoice'`
4. Same for AR Credit Memo (`ar.credit_memo`) and Receipt (`ar.receipt`)
5. Create a manual JE via the Core GL UI → confirm
   `source_module='gl.manual_je'`

If any of these fails with a 400 referencing a header account being
non-postable, that's the intended new behavior — the operator must
re-map to a postable child account. Document and surface to users.

### 2.2 Smoke test idempotency

Open Postman or similar. POST `post_invoice` for the same VendorInvoice
twice in quick succession.

Expected: the second request returns 400 with a "already posted" or
409 idempotency error. **Not** a duplicate journal.

### 2.3 Verify FY+1 opening journal

If your tenant just ran a year-end close (C9 fix), check that the
opening journal exists:

```sql
SELECT id, reference_number, posting_date, description, status, source_module
FROM accounting_journalheader
WHERE source_module = 'year_end_close.opening'
ORDER BY posting_date DESC
LIMIT 5;
```

Expected: one row per closed FY, dated 01/01/FY+1, status=Posted.

### 2.4 Verify GL ↔ sub-ledger reconciliation surface

Hit the new AR/AP aging endpoints and inspect the response for
`_warnings`:

```bash
curl -s -H "Authorization: Token <admin-token>" \
  "https://<prod-host>/api/v1/accounting/customer-invoices/aging_report/?as_of_date=$(date +%F)" \
  | jq '._warnings, .gl_receivables_balance, .gl_reconciliation_diff'
```

If `_warnings` is non-null, you have sub-ledger ↔ GL drift. Compare
against the pre-deploy baseline (step 0.4):
- **If diff matches baseline** → pre-existing; document.
- **If diff is new or larger** → STOP and investigate. The deploy
  may have triggered a real divergence.

### 2.5 Verify HRM PII encryption

```bash
# Authenticate as an HR admin with view_employee_pii permission
curl -s -H "Authorization: Token <hr-admin-token>" \
  "https://<prod-host>/api/v1/hrm/employees/<id>/" \
  | jq '.national_id_number, ._pii_decryption_errors'
```

Expected:
- `national_id_number` returns the decrypted plaintext (you have the
  permission) — but the actual stored value is now Fernet ciphertext.
- `_pii_decryption_errors` is empty (`[]` or absent).

Confirm directly in the DB that ciphertext is stored:
```sql
SELECT id,
       LEFT(national_id_number, 10) AS nin_prefix,
       national_id_number_encrypted,
       LEFT(national_id_number_hash, 12) AS nin_hash_prefix
FROM hrm_employee
WHERE national_id_number IS NOT NULL AND national_id_number != ''
LIMIT 5;
```

Expected:
- `nin_prefix` starts with `gAAAA` (Fernet token magic).
- `national_id_number_encrypted` is `true` (boolean).
- `nin_hash_prefix` is a hex string (HMAC).

Search by hash should work (the `actor=` kwarg is now mandatory — V5):
```bash
# In Django shell
python manage.py shell
>>> from hrm.models import Employee
>>> from django.contrib.auth.models import User
>>> me = User.objects.get(username='admin')  # must hold hrm.search_employee_pii or be superuser
>>> emp = Employee.find_by_pii_hash('national_id_number', 'A12345678901', actor=me).first()
>>> emp.get_national_id_number()
'A12345678901'
```

### 2.6 Verify period control enforcement

Attempt to post a journal dated inside a Closed period (use a test
manual JE):

Expected: 400 with period-closed error. Previously this could slip
through the manual-JE path; now it's gated.

### 2.7 Verify line-level 3-way match

Create a PO for 50 units @ ₦20 (total ₦1000). Create a GRN for 50
units. Create a VendorInvoice with one line "100 × 10" (same total
but different qty/price). Run `verify_and_post`.

Expected: `match_type='Partial'`, `status='Variance'`, `payment_hold=True`,
`gl_post_error` populated with "per-line cross-check failed: …".

Before this deploy, the invoice would have matched as `Full`. After,
it's caught.

---

## 3. Feature-flag rollout (separate from migrations)

These flags ship as `False`. Flipping them is the rollout sequence
for the cookie auth change.

### 3.1 `AUTH_COOKIE_ONLY` (backend)

After the deploy is stable for **at least 24 hours**:
1. Verify the cookie path is working: log in via web; in browser
   DevTools, confirm `Set-Cookie: auth_token=…; HttpOnly; Secure; SameSite=Lax`
   in the login response.
2. Set `AUTH_COOKIE_ONLY=True` in the backend env. Restart workers.
3. Cookie is now the sole carrier; the response body no longer
   includes the token.

### 3.2 `VITE_AUTH_COOKIE_ONLY` (frontend)

After step 3.1:
1. Rebuild frontend with `VITE_AUTH_COOKIE_ONLY=true`.
2. Deploy frontend bundle.
3. Frontend now hydrates from `GET /core/users/me/` on mount instead
   of reading the token from `sessionStorage`.

### 3.3 Backout

Either layer can flip back to `False` without disruption. The cookie
auth class still accepts the legacy `Authorization` header path.

---

## 4. Rollback procedures

### 4.1 Code rollback

Standard. Deploy the previous Git tag / release pointer.

### 4.2 Migration rollback (most → reversible)

| Migration | Rollback |
|---|---|
| `contracts/0011` | `python manage.py migrate contracts 0010` |
| `core/0014` | **Not reversible.** Restore from backup. The schema is the data. |
| `hrm/0016` | `python manage.py migrate hrm 0015` |
| `hrm/0017` | `python manage.py migrate hrm 0016` (nullifies the FK; safe) |
| `hrm/0018` | `python manage.py migrate hrm 0017` |
| `hrm/0019` | **Not reversible.** Restore from backup. |
| `workflow/0011` | `python manage.py migrate workflow 0010` |
| `workflow/0012` | `python manage.py migrate workflow 0011` |
| `accounting/0103` | `python manage.py migrate accounting 0102` (drops the constraint; dedupe is unrolled but rows are not re-split — original duplicates are gone) |

**If you need to roll back past `core/0014` or `hrm/0019`, you MUST
restore from the pre-deploy backup.** There is no incremental path.

### 4.3 Partial rollback (config only)

If a specific finding-fix is causing a problem but you can't roll back
migrations:

| Symptom | Mitigation |
|---|---|
| `check_warrant_availability` rejecting legitimate posts | Identify the caller, pass `strict=False` |
| `InvoiceMatching.match_lines` flagging legitimate invoices | Operator overrides via the existing approval workflow |
| `close_periods` 409 on pending journals | Pass `force=True` with a reason ≥10 chars |
| FY+1 opening journal posted incorrectly | Reverse it via the standard journal-reversal workflow |
| Statutory return raising `StatutoryReturnError` | Investigate the misconfigured mapping (the error message identifies it) |

---

## 5. Hand-off

Post-deploy artefacts to capture for the audit trail:
- `git rev-parse HEAD` of the deployed branch
- `python manage.py showmigrations` output
- Pre-deploy and post-deploy reconciliation diffs (step 0.4 vs step 2.4)
- Screenshots / curl output from the verification steps above
- The 207 Multi-Status response from a deliberately-broken PV payment
  (verify the H2 cascade surface works in your environment)

File these in your incident-management or change-management system.

---

## 6. References

- Branch: `fix/comprehensive-review-remediation`
- PR URL: https://github.com/oosadiaye/Quot-PSA/pull/new/fix/comprehensive-review-remediation
- Total findings closed: 94 (49 + 45 across two reviews)
- Test result: 94/94 regression pass in 790s
- Followup workstreams: `FOLLOWUP_WORKSTREAM_PLAN.md`
- Commit-by-commit rationale: each commit message in the stack
