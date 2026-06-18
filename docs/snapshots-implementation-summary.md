# In-App Snapshots — Phase 1 Implementation Summary

Generated: 2026-06-18  
Branch: `fix/comprehensive-review-remediation`  
Tasks completed: 1–23 of 23

---

## Backend files created / modified

### App skeleton
| File | Purpose |
|------|---------|
| `snapshots/__init__.py` | Package marker |
| `snapshots/apps.py` | AppConfig — registers system checks |
| `snapshots/constants.py` | Shared enumerations and limits |
| `snapshots/models.py` | `SnapshotJob` model (schema_name, status, artifact_path, …) |
| `snapshots/permissions.py` | `IsPlatformSuperAdmin`, `CanAccessSnapshotJob` DRF permission classes |
| `snapshots/serializers.py` | Read + create serializers; strips artifact_path and kek_fingerprint |
| `snapshots/views.py` | `SnapshotJobViewSet` (list, create, retrieve, delete, download) |
| `snapshots/urls.py` | Router wiring → `/api/snapshots/` |
| `snapshots/tasks.py` | Celery tasks: `run_snapshot_job`, `enforce_retention_all`, `reap_stale_jobs` |
| `snapshots/audit.py` | `record_*` helpers writing to Django structured logger |
| `snapshots/checks.py` | Django system check: warns/errors if `SNAPSHOTS_KEK_HEX` not set |

### Services
| File | Purpose |
|------|---------|
| `snapshots/services/snapshot_service.py` | Orchestrator: dump → encrypt → manifest → store |
| `snapshots/services/crypto.py` | AES-256-GCM envelope with KEK wrapping; magic bytes + version header |
| `snapshots/services/dump.py` | `pg_dump` subprocess wrapper; strips password from DSN into env |
| `snapshots/services/manifest.py` | SHA-256 checksums + JSON manifest builder |
| `snapshots/services/media.py` | Collects referenced media files; rejects path-traversal |
| `snapshots/services/retention.py` | Age-based and count-based retention rules |
| `snapshots/services/storage.py` | `LocalFileStorage` (protocol-conformant); rejects path-traversal + symlink escapes |

### Migrations
| File | Description |
|------|-------------|
| `snapshots/migrations/0001_initial.py` | Creates `snapshots_snapshotjob` table |
| `snapshots/migrations/0002_alter_snapshotjob_options_and_more.py` | Adds label field, ordering, verbose names |

### Integration wiring
- `quot_pse/settings.py` — `snapshots` added to `INSTALLED_APPS`
- `quot_pse/urls.py` — `/api/snapshots/` route included
- `deploy/postgresql_tuning.sql` — advisory-lock SQL note

---

## Frontend files created / modified

| File | Purpose |
|------|---------|
| `frontend/src/types/snapshots.ts` | TypeScript types (`SnapshotJob`, `CreateSnapshotPayload`) |
| `frontend/src/api/snapshots.ts` | API client functions (list, create, delete, download) |
| `frontend/src/features/admin/snapshots/SnapshotsPage.tsx` | Super-admin view: all tenants |
| `frontend/src/features/admin/snapshots/TenantSnapshotsPage.tsx` | Tenant-admin view: own schema only |
| `frontend/src/features/admin/snapshots/index.ts` | Barrel re-export |
| `frontend/src/features/admin/snapshots/components/CreateSnapshotForm.tsx` | Modal form |
| `frontend/src/features/admin/snapshots/components/SnapshotDetailDrawer.tsx` | Detail side-drawer |
| `frontend/src/features/admin/snapshots/components/SnapshotJobStatusPill.tsx` | Status badge |
| `frontend/src/features/admin/snapshots/components/SnapshotsTable.tsx` | Paginated table |
| `frontend/src/features/admin/snapshots/hooks/useCreateSnapshot.ts` | React Query mutation |
| `frontend/src/features/admin/snapshots/hooks/useDeleteSnapshot.ts` | React Query mutation |
| `frontend/src/features/admin/snapshots/hooks/useSnapshotJobs.ts` | React Query query |
| `frontend/e2e/modules/snapshots.spec.ts` | Playwright E2E spec (list, create, delete, download flows) |
| `frontend/src/App.tsx` | Route wiring for snapshots pages |
| `frontend/src/components/Sidebar.tsx` | Navigation entry |

---

## Test counts

| Layer | Count | Result |
|-------|-------|--------|
| Backend (pytest) | 133 passed, 1 skipped | PASS |
| Frontend tsc | 0 errors | PASS |
| Frontend build | Clean (22.72 s) | PASS |

The single skipped test (`test_is_tenant_admin_of_returns_false_when_no_utr`) is expected: it requires a django-tenants `TenantProfile` which is not wired in the test database.

---

## Migration state

`python manage.py makemigrations --dry-run snapshots` → **No changes detected** (fully migrated).

---

## `manage.py check` output

```
WARNINGS:
?: (snapshots.W001) SNAPSHOTS_KEK_HEX is not set. Snapshot creation will fail.
    HINT: Set SNAPSHOTS_KEK_HEX to a 64-char hex string (32 bytes).

System check identified 1 issue (0 silenced).
```

This warning is expected in development. Production deployments must supply `SNAPSHOTS_KEK_HEX` in the environment (or secrets manager). The check escalates to an **error** when `DEBUG=False`.

---

## URL routing

```
list:   /api/snapshots/
detail: /api/snapshots/{id}/
```

Both routes resolved correctly via `reverse()`.

---

## Known limitations (Phase 1 scope)

The following are documented design decisions, not defects:

1. **Single KEK** — There is one Key Encryption Key per deployment (`SNAPSHOTS_KEK_HEX`). No key rotation or multi-KEK support in Phase 1.
2. **Local storage only** — Artifacts are stored on the server filesystem under `MEDIA_ROOT/snapshots/`. No S3 / object-storage back-end in Phase 1.
3. **No streaming upload** — The pg_dump output is written to a temp file before encryption; very large databases may require additional disk headroom.
4. **No incremental snapshots** — Each job is a full logical dump of the tenant schema.
5. **Celery required** — Snapshot jobs are dispatched as Celery tasks. Synchronous fallback is not implemented.
6. **No download resumption** — The download endpoint streams the decrypted artifact in a single HTTP response.
7. **Audit log is stdout/structured-log only** — There is no dedicated UI for the audit trail in Phase 1.
8. **E2E tests require a running server** — The Playwright spec (`e2e/modules/snapshots.spec.ts`) is wired but not integrated into CI yet.
