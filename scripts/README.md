# Scripts

Utility scripts relocated from the repository root.

## Layout

- **`dev/`** — Developer onboarding helpers. Safe to run in dev against a local
  database.
- **`diagnostics/`** — Ad-hoc diagnostic snippets written during live
  debugging. These are **not maintained** and may reference schema that has
  since changed. Read before running.

## Entries

### `dev/create_superuser.py`
Creates an initial Django superuser for local development.

### `dev/create_test_tenant.py`
Provisions a test tenant in the `django-tenants` setup so new checkouts can
boot into a multi-tenant URL without running the full onboarding flow.

### `diagnostics/debug.py`, `debug2.py`
One-off debug scripts — check before running, may be stale.

### `diagnostics/capture_check.py`
Prints auth-state + tenant-role fixtures.

### `diagnostics/check_auth_state.py`
Dumps `auth_state.txt` contents for a saved session debug.

### `diagnostics/deep_check_0038.py`
Validation/inspection script tied to a specific historical migration (0038).

### `diagnostics/append.py`, `append_props.py`
Ad-hoc string-append helpers used for inventory property migration. Safe to
delete if nobody claims them.

## What's missing here

The following files were purged from the repository root and should **stay
purged** — they were sensitive or transient:

| File | Reason |
|------|--------|
| `auth_state.txt` | Captured session state — likely PII / credentials. |
| `users_tenants_roles.txt` | Dump of user-tenant mappings — PII. |
| `django_crash.log`, `error.log`, `error8.log` | Runtime logs; noise + size. |
| `error_page.html` | Static error capture; no source value. |

If any of these reappear, they are covered by the repository `.gitignore`
rules added alongside this cleanup.
