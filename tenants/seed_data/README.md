# Tenant default-seed data

JSON files loaded by `tenants.services.default_seeder` when a new tenant
is provisioned (or via `manage.py seed_tenant_defaults` to backfill an
existing tenant).

## Files

| File | What it seeds | Idempotency key |
|---|---|---|
| `fiscal_year.json` | Single `FiscalYear` row marked `is_active=True` for the current calendar year. | `year` (unique) |
| `fiscal_periods.json` | 12 `FiscalPeriod` rows (monthly) within the active FY. | `(fiscal_year, period_number, period_type)` |
| `budget_periods.json` | 12 monthly + 4 quarterly + 1 annual `BudgetPeriod` rows. | `(fiscal_year, period_type, period_number)` |
| `accounts.json` | Structural CoA accounts — recon-tagged AP, AR, Bank, Inventory, Asset, plus a generic Expense and Income group. Industry-specific accounts are layered on top by `industry_seed_service`. | `code` (unique) |
| `budget_check_rules.json` | NCoA-aligned ranges: 21xx Personnel STRICT, 22xx Overhead WARNING, 23xx Capital STRICT, default 0-99999999 WARNING. | `(gl_from, gl_to)` |
| `treasury_account.json` | Placeholder Main TSA account so a fresh tenant can post any PV. Operator edits the real bank-of-CBN account number through the UI on day 1. | `account_number` |

## Placeholder substitution

Strings in the JSON can use these tokens — substituted at load time:

- `{{current_fy_year}}` — `date.today().year`
- `{{current_fy_start}}` — `YYYY-01-01` for the current year
- `{{current_fy_end}}` — `YYYY-12-31` for the current year
- `{{month_start:N}}` — first day of month N for current FY (N=1..12)
- `{{month_end:N}}` — last day of month N for current FY
- `{{quarter_start:N}}` / `{{quarter_end:N}}` — N=1..4

This means a tenant provisioned in 2030 gets `FY 2030` automatically —
no annual data-file edit.

## Overriding per deployment

Operators who want a different default chart of accounts (e.g. a
state-specific NCoA cut) can drop their own `accounts.json` into
`tenants/seed_data/` before the first provision. The loader reads the
file fresh on every run; no Python code change required.

## Adding a new seed file

1. Drop the JSON under `tenants/seed_data/<name>.json`.
2. Add a `seed_<name>()` method to `tenants.services.default_seeder.TenantDefaultsSeeder`.
3. Call it from `seed_all()`.
4. Add a regression test asserting (a) idempotency, (b) row count.
