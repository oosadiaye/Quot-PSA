# Runbook — Onboard a New Tenant

Walk a new state-government tenant from zero to first-login in one
sitting. All commands run from the repo root. Substitute
`<schema>`, `<state_name>`, `<domain>` with tenant-specific values.

Target time: **30 minutes per tenant**.

## Pre-flight checklist

- Tenant name + legal entity confirmed
- Primary subdomain agreed (e.g. `delta.quotpse.ng`)
- First-admin email address on file
- Database host credentials available (backend ops)
- Backup script ran last night (safety net before changes)

## Step 1 — Create the tenant schema

```bash
python manage.py create_tenant \
  --schema_name=<schema> \
  --name="<state_name> Government" \
  --paid_until=2099-12-31 \
  --on_trial=False
```

Creates the row in `tenants_client` and the PostgreSQL schema.

## Step 2 — Bind a domain

```bash
python manage.py shell -c "
from tenants.models import Client, Domain
tenant = Client.objects.get(schema_name='<schema>')
Domain.objects.create(
    tenant=tenant, domain='<domain>',
    is_primary=True,
)
Domain.objects.create(
    tenant=tenant, domain='<schema>.localhost',
    is_primary=False,
)
"
```

The `.localhost` domain lets developers hit the tenant without
editing the hosts file — most modern browsers auto-resolve it.

## Step 3 — Seed the chart of accounts

```bash
# NCoA dimensional segments (admin / economic / functional / programme / fund / geographic).
python manage.py tenant_command seed_ncoa --schema=<schema>

# Create the posting-level Account rows aligned with the NCoA codes.
python manage.py tenant_command seed_ncoa_as_coa --schema=<schema>

# Revenue heads (PAYE, Road Tax, Fees, Grants, FAAC, etc.).
python manage.py tenant_command seed_revenue_heads --schema=<schema>
```

**Verify**: `/admin/roles` → Role Catalogue should be empty until
step 5; `/ncoa-classification` should show ~85 economic-segment rows.

## Step 4 — Open the first fiscal year

```bash
python manage.py tenant_command seed_opening_balance \
  --schema=<schema> --year=<current_year> --amount=<opening_cash>
```

Creates a `FiscalYear` row AND posts a Jan-1 opening-balance journal
(DR Cash, CR Accumulated Fund) so the SoFP shows a non-zero Net
Assets from day one.

## Step 5 — Seed baseline roles + approval rules

```bash
# 6 roles: budget + accounting + procurement × (officer, manager).
python manage.py tenant_command seed_baseline_roles --schema=<schema>

# 9 approval rules tying those roles to document workflows.
python manage.py tenant_command seed_approval_rules --schema=<schema>
```

**Verify**: `/admin/roles` shows 6 roles; `/admin/approval-rules`
shows 9 rules across 6 document types.

## Step 6 — Configure AccountingSettings

In a shell (replace codes to match your seeded CoA):

```bash
python manage.py shell -c "
from django_tenants.utils import schema_context
from accounting.models import AccountingSettings
with schema_context('<schema>'):
    s, _ = AccountingSettings.objects.get_or_create(pk=1)
    s.pension_service_cost_code       = '21100100'   # 21xx personnel
    s.pension_interest_expense_code   = '24100100'   # 24xx debt service
    s.defined_benefit_obligation_code = '42100100'   # 42xx non-current liab
    s.social_benefit_expense_code     = '25100100'   # 25xx transfers
    s.accumulated_fund_account_code   = '43100100'   # 43xx net assets
    s.save()
"
```

## Step 7 — Create the first admin user

```bash
python manage.py createsuperuser
# Enter the email + password for the tenant administrator.
```

Then bind that user to the tenant schema with admin role:

```bash
python manage.py shell -c "
from django.contrib.auth import get_user_model
from tenants.models import Client, UserTenantRole
u = get_user_model().objects.get(username='<admin_username>')
t = Client.objects.get(schema_name='<schema>')
UserTenantRole.objects.create(
    user=u, tenant=t, role='admin', is_active=True,
)
"
```

## Step 8 — Smoke-test the tenant

Open the frontend at **https://<domain>/** (or
**http://<schema>.localhost:5173/** in dev) and verify:

- Login with admin credentials succeeds
- **Financial reports** (Financial Position, Performance, Cash Flow,
  Notes) all load with non-zero numbers
- **Data Quality** dashboard (`/accounting/data-quality`) shows all
  five checks as OK
- **Roles & Permissions** (`/admin/roles`) lists 6 roles
- **Approval Rules** (`/admin/approval-rules`) lists 9 rules

## Step 9 — Operator handover

- Hand the admin credentials to the tenant's finance officer over
  a secure channel (do NOT email plaintext)
- Schedule a 30-minute training walkthrough (see `docs/USER_GUIDE.md`
  when it ships — Phase 7)
- Add the tenant's primary domain to the Prometheus scrape config
  so `/metrics` is collected

## Step 10 — Record the onboarding

Append to `docs/TENANT_REGISTER.md` (create if it doesn't exist):

| Date | Schema | Domain | Admin | Opening cash | Operator | Notes |
|---|---|---|---|---|---|---|
| 2026-04-17 | `delta_state` | `delta.quotpse.ng` | `aminu@delta.gov.ng` | NGN 50 M | (your name) | initial onboarding |

## Troubleshooting

### `create_tenant` fails with "schema already exists"
Another operator onboarded the same tenant concurrently, or an
earlier attempt left a partial schema. Either drop the orphan
schema (`DROP SCHEMA <schema> CASCADE;` — dangerous, verify it's
empty first) or pick a different schema name.

### Financial reports show NGN 0.00 after seed
You skipped Step 4 (opening-balance) or your configured
`accumulated_fund_account_code` doesn't match a real Account row.
Run Step 6 to re-configure, then re-visit the report.

### `/admin/roles` is blank
Step 5 didn't run or hit an error. Re-run
`seed_baseline_roles --schema=<schema>` and check stderr.

### Login succeeds but every API call returns 404
The user logged in to the public schema (no business tables).
Check that the `Domain` record for `<schema>` has
`is_primary=True` and the browser URL matches the domain.
See `.claude/plans/…` or Sprint 21 notes for full diagnosis.

## Roll-back plan

If the tenant needs to be deleted before go-live:

```bash
python manage.py shell -c "
from tenants.models import Client
Client.objects.get(schema_name='<schema>').delete()
"
```

This cascade-deletes the PostgreSQL schema via django-tenants. **No
undo** — take a backup first (`./scripts/backup.sh --schema=<schema>`).
