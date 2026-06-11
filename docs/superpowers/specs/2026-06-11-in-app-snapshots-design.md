# In-App Snapshots — Phase 1 Design

**Status:** Draft for review
**Date:** 2026-06-11
**Author:** Quot PSE platform team
**Branch (at authoring):** `fix/comprehensive-review-remediation`
**Supersedes:** —

## 1. Background

The codebase already has an operator-tier backup pipeline:

- [`scripts/backup.sh`](../../../scripts/backup.sh) performs nightly per-schema `pg_dump` with gzip + integrity check + age-based rotation, keyed by `BACKUP_DIR` / `BACKUP_RETENTION` env vars.
- [`docs/DR_DRILL.md`](../../DR_DRILL.md) defines the quarterly restore procedure with RPO ≤ 24 h and RTO ≤ 2 h, and flags three gaps in its "Automation roadmap" (companion `restore.sh`, automated weekly drill, PITR via WAL).

What is missing is an **in-application** surface: there is no way for a superadmin or tenant admin to request, list, download, or delete a backup from inside the product. Today every snapshot is an SSH-and-shell operation.

This document specifies **Phase 1** of an overall four-phase backup capability roadmap:

| Phase | Scope | Status |
|---|---|---|
| 1 | **In-app on-demand snapshots** (this doc) | designing |
| 2 | Ops pipeline hardening (`restore.sh`, automated drill, off-site sync, PITR) | deferred |
| 3 | Tenant data export (portable archive download) | deferred |
| 4 | Self-service restore (destructive, two-person approval) | deferred |

Subsequent phases each get their own brainstorming → spec → plan cycle. Phase 4 in particular MUST NOT be implemented until Phases 1–3 are in production.

## 2. Goals & non-goals

### Goals

1. A **superadmin** can trigger, list, download, and delete snapshots for any tenant schema and for the shared `public` schema.
2. A **tenant admin** (user holding the canonical `all_access` Role on a tenant) can trigger, list, download, and delete snapshots **for their own tenant schema only**.
3. Each snapshot is a single self-describing encrypted artifact containing the database dump, the schema's referenced media files, and a `manifest.json` recording code/migration/PII-key versions.
4. Snapshots are encrypted at rest with a deploy-time KEK using AES-256-GCM envelope encryption.
5. Snapshot creation runs asynchronously; the originating HTTP request returns within milliseconds.
6. Retention is automatic by **age** (default 14 days) AND by **per-tenant count** (default 5). Either limit fires deletion.
7. Per-(user, schema) rate limit on create (default 5/hour) prevents disk-exhaustion abuse.
8. Every state transition is auditable.

### Non-goals (deferred to later phases)

- **Restoring** a snapshot in-app. P4 only.
- **Off-site replication** of snapshots (S3, rclone). P2 only.
- **Cross-tenant snapshot** in a single artifact (e.g., "public + delta_state in one tar"). Superadmin creates two separate jobs.
- **Per-tenant KEKs** or per-tenant encryption keys. Single deploy-time KEK in P1.
- **PITR / WAL shipping**. P2 only.
- **Snapshot scheduling** (cron-like, in-app). Nightly cron still belongs to `scripts/backup.sh`. P1 is on-demand only.

## 3. High-level architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Frontend (React, TanStack Query)                                    │
│  features/admin/snapshots/                                           │
│    SnapshotsPage.tsx       — list + create + download + delete       │
│    SnapshotJobStatusPill   — queued/running/succeeded/failed/expired │
│    useSnapshotJobs()       — polls /api/snapshots/ every 5s while    │
│                              any visible job is queued|running       │
└────────────────────┬─────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────────────┐
│  Django REST API (new app: snapshots/)                               │
│  POST   /api/snapshots/                  create job (202)            │
│  GET    /api/snapshots/                  list (scoped)               │
│  GET    /api/snapshots/{id}/             detail (polled)             │
│  GET    /api/snapshots/{id}/download/    stream-decrypt              │
│  DELETE /api/snapshots/{id}/             expire (preserves audit)    │
└────────────────────┬─────────────────────────────────────────────────┘
                     │  enqueue
┌────────────────────▼─────────────────────────────────────────────────┐
│  Celery                                                              │
│  tasks.run_snapshot_job(job_id)                                      │
│  tasks.enforce_retention_all (beat, daily 03:00 UTC)                 │
│  tasks.reap_stale_jobs       (beat, every 10 min)                    │
└────────────────────┬─────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────────────┐
│  Service layer (pure Python)                                         │
│  services/snapshot_service.py  6-phase orchestrator                  │
│  services/storage.py           Storage Protocol + LocalFilesystem    │
│  services/crypto.py            AES-256-GCM envelope encryption       │
│  services/retention.py         age + count rules                     │
└────────────────────┬─────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────────────┐
│  Persistence                                                         │
│  - PostgreSQL public schema: SnapshotJob row (status + manifest)     │
│  - Local FS:    $SNAPSHOTS_BACKUP_DIR/<schema>/<artifact>.tar.gz.enc │
│  - Audit log:   one row per create / start / succeed / fail /        │
│                 expire / download / delete                           │
└──────────────────────────────────────────────────────────────────────┘
```

### Process distribution

- **Web (gunicorn)**: creates the `SnapshotJob` row, enqueues the Celery task, returns 202. Never blocks.
- **Celery worker**: runs `pg_dump`, gathers media, builds manifest, encrypts, registers completion, runs retention. Soft time limit 50 min, hard 60 min.
- **Celery beat**: runs `enforce_retention_all` nightly and `reap_stale_jobs` every 10 min.
- **Download endpoint**: streams the decrypted artifact in 64 KB chunks; the file stays encrypted at rest.

### Tenant boundary

A snapshot of tenant `delta_state` runs `pg_dump --schema=delta_state` against the shared database. The `SnapshotJob.schema_name` field is validated against `^[a-z][a-z0-9_]{0,62}$` (mirroring [`tenants/tasks.py`](../../../tenants/tasks.py)) to neutralize SQL-identifier injection both at the application layer and via a DB `CheckConstraint`.

## 4. Data model

One new model, in the **public** schema (`snapshots` added to `SHARED_APPS`):

```python
# snapshots/models.py
class SnapshotJob(models.Model):
    class Status(models.TextChoices):
        QUEUED    = 'queued',    'Queued'
        RUNNING   = 'running',   'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED    = 'failed',    'Failed'
        EXPIRED   = 'expired',   'Expired'   # row kept, file removed

    id              = models.BigAutoField(primary_key=True)
    schema_name     = models.CharField(max_length=63, db_index=True)
    label           = models.CharField(max_length=120, blank=True)
    status          = models.CharField(
                          max_length=12, choices=Status.choices,
                          default=Status.QUEUED, db_index=True)

    triggered_by    = models.ForeignKey('auth.User', on_delete=models.PROTECT,
                                        related_name='+')
    triggered_at    = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at      = models.DateTimeField(null=True, blank=True)
    completed_at    = models.DateTimeField(null=True, blank=True)

    artifact_path   = models.CharField(max_length=512, blank=True)
    size_bytes      = models.BigIntegerField(null=True, blank=True)
    sha256          = models.CharField(max_length=64, blank=True)

    kek_fingerprint = models.CharField(max_length=32, blank=True)
    manifest        = models.JSONField(default=dict, blank=True)

    error_message   = models.TextField(blank=True)
    error_class     = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-triggered_at']
        indexes  = [
            models.Index(fields=['schema_name', '-triggered_at']),
            models.Index(fields=['status', '-triggered_at']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(schema_name__regex=r'^[a-z][a-z0-9_]{0,62}$'),
                name='snapshotjob_schema_name_valid',
            ),
        ]
```

**Why these specific choices**:

- `status` distinguishes `SUCCEEDED` (file on disk, downloadable) from `EXPIRED` (file deleted, row kept for audit). Conflating them loses information.
- `triggered_by` uses `on_delete=PROTECT` — audit history outlives user deletion.
- `schema_name` is text (not FK to `tenants.Client`) because the `public` schema also produces snapshots, and a sandbox tenant can be hard-deleted.
- `manifest` is a `JSONField` mirror of the on-disk `manifest.json` for fast DB-side queries (e.g., "show me all snapshots taken against migration head X").

### Settings

```python
# quot_pse/settings.py
SNAPSHOTS_BACKUP_DIR             = os.getenv('SNAPSHOTS_BACKUP_DIR',
                                              BASE_DIR / 'snapshots_storage')
SNAPSHOTS_RETENTION_DAYS         = int(os.getenv('SNAPSHOTS_RETENTION_DAYS', '14'))
SNAPSHOTS_MAX_PER_TENANT         = int(os.getenv('SNAPSHOTS_MAX_PER_TENANT', '5'))
SNAPSHOTS_KEK_HEX                = os.getenv('SNAPSHOTS_KEK_HEX')
SNAPSHOTS_KEK_ID                 = os.getenv('SNAPSHOTS_KEK_ID', 'kek-v1')
SNAPSHOTS_CREATE_RATE_PER_HOUR   = int(os.getenv('SNAPSHOTS_CREATE_RATE_PER_HOUR', '5'))
SNAPSHOTS_PG_DUMP_BIN            = os.getenv('SNAPSHOTS_PG_DUMP_BIN', 'pg_dump')
SNAPSHOTS_SOFT_TIME_LIMIT_SEC    = int(os.getenv('SNAPSHOTS_SOFT_TIME_LIMIT_SEC', '3000'))
SNAPSHOTS_HARD_TIME_LIMIT_SEC    = int(os.getenv('SNAPSHOTS_HARD_TIME_LIMIT_SEC', '3600'))
```

A Django `check` (in `snapshots/apps.py`) verifies `SNAPSHOTS_KEK_HEX` is set and parses to exactly 32 bytes when `DEBUG=False`. App refuses to start otherwise.

## 5. API surface

### Endpoints

| Method | Path | Purpose | Response on success |
|---|---|---|---|
| `POST` | `/api/snapshots/` | Create a snapshot job | `202 Accepted`, body = serialized `SnapshotJob` with `status=queued` |
| `GET` | `/api/snapshots/` | List jobs (scoped, paginated) | `200`, body = paginated list |
| `GET` | `/api/snapshots/{id}/` | Detail (polled while running) | `200`, body = serialized job |
| `GET` | `/api/snapshots/{id}/download/` | Stream the decrypted artifact | `200` + `application/octet-stream` |
| `DELETE` | `/api/snapshots/{id}/` | Expire the job (delete file, keep row) | `204` |

### Request body — `POST /api/snapshots/`

```jsonc
{
  "schema_name": "delta_state",     // required; "public" allowed only for superadmin
  "label": "pre FY26 budget import" // optional, max 120 chars
}
```

### Permission matrix

| Action | Superadmin | Tenant admin (own schema) | Tenant admin (other schema) | Anyone else |
|---|---|---|---|---|
| `POST /` | any schema incl. `public` | own schema only | 403 | 403 |
| `GET /` (list) | sees all rows | sees only own schema | n/a (same query) | 403 |
| `GET /{id}/` | any | own only | 403 | 403 |
| `GET /{id}/download/` | any (audited) | own only (audited) | 403 | 403 |
| `DELETE /{id}/` | any | own only | 403 | 403 |

### Defense in depth

Two independent gates:

1. **Permission classes** — `CanCreateSnapshot.has_permission` cross-checks `request.data['schema_name']` against the actor's tenant scope on `POST`. `CanAccessSnapshot.has_object_permission` checks ownership on retrieve/download/delete.
2. **Queryset filter** — `get_queryset()` filters `SnapshotJob` by `schema_name__in=<tenant schemas where actor holds all_access>` for non-superadmins. A permission-class bug that leaks `has_object_permission=True` is still stopped because the row isn't in the queryset.

Both layers consult the canonical resolvers wired in [`core/permissions.py`](../../../core/permissions.py) (`is_platform_superadmin`) and [`contracts/services/sod.py`](../../../contracts/services/sod.py) (via the `all_access` Role mechanism). No new RBAC primitives.

### Rate limiting

DRF throttle scope `snapshot_create`, keyed by `(user_id, schema_name)`, configured against `SNAPSHOTS_CREATE_RATE_PER_HOUR`. Burst above the limit returns `429`.

### Delete semantics

`DELETE` is non-destructive to the audit row. Transitions: `SUCCEEDED → EXPIRED`. The artifact file is unlinked; the row's `artifact_path` is cleared but `manifest`, `triggered_by`, `triggered_at`, and `error_*` are retained. This mirrors the codebase's reversal-rather-than-delete pattern (e.g., `JournalHeader`).

## 6. Artifact format

### On-disk layout

```
$SNAPSHOTS_BACKUP_DIR/
  <schema_name>/
    snapshot-<job_id>-<utc_timestamp>.tar.gz.enc
```

The `.enc` suffix is a load-bearing marker: tools that try to read `.tar.gz` directly will fail loudly, preventing accidental plaintext mishandling.

### Tarball contents (inside the `.tar.gz`, pre-encryption)

```
snapshot-<job_id>/
  manifest.json
  database/
    <schema_name>.sql              # pg_dump output, --format=plain
  media/
    <relative paths preserved>     # only files referenced from this schema
```

For a **public-schema** snapshot, `database/public.sql` includes shared `auth`, `tenants_client`, `tenants_domain`. The `media/` directory is omitted for public snapshots (public schema has no media references).

For a **tenant-schema** snapshot, the SQL contains only that schema; `media/` mirrors the relative paths under `MEDIA_ROOT` for files referenced from that schema.

### Manifest schema

```jsonc
{
  "schema_version": 1,
  "snapshot": {
    "job_id": 4271,
    "label": "pre FY26 budget import",
    "schema_name": "delta_state",
    "created_at_utc": "2026-06-11T14:22:08Z",
    "triggered_by": { "user_id": 88, "username": "ada.okonkwo" }
  },
  "source": {
    "code_version": "fix/comprehensive-review-remediation@c242b39",
    "django_version": "5.2.4",
    "django_tenants_version": "3.6.1",
    "postgres_version": "15.7",
    "migration_head": {
      "shared": ["tenants.0014_...", "auth.0012_..."],
      "tenant": ["accounting.0107_...", "contracts.0058_..."]
    },
    "pii_key_fingerprint": "pii-v2"
  },
  "contents": {
    "database_sql_sha256": "9c4f...",
    "media_file_count": 412,
    "media_total_bytes": 184223991
  },
  "encryption": {
    "algorithm": "AES-256-GCM",
    "kek_id": "kek-v1",
    "wrapped_dek_b64": "...",
    "iv_b64": "...",
    "tag_b64": "..."
  }
}
```

`migration_head` and `pii_key_fingerprint` are the **load-bearing fields for future P4 restore**. They let restore make informed decisions about migration drift and PII-key rotation. Stamping them here is cheap; retrofitting them later means a restore tool guessing.

### Encryption envelope (AES-256-GCM)

Mirrors the pattern in [`core/security/pii_crypto.py`](../../../core/security/pii_crypto.py).

```
1. Generate a fresh 32-byte DEK for this snapshot.
2. Encrypt the .tar.gz stream with AES-256-GCM(DEK) → ciphertext + tag.
3. Wrap (encrypt) the DEK with AES-256-GCM(KEK) → wrapped_dek.
4. On-disk file format:
       [4-byte magic 'QPSE']
       [1-byte version 0x01]
       [16-byte IV (for DEK GCM)]
       [60-byte wrapped DEK]
       [16-byte GCM tag]
       [ciphertext ...]
   Header bytes are plaintext-readable for tooling.
5. wrapped_dek, IV, and tag are ALSO recorded in manifest.json for forensic
   self-description, but the file header is authoritative on read.
```

### Media collection

For tenant snapshots: with `schema_context(schema)`, iterate every model's `FileField`/`ImageField` instances and copy `.path` into `media/` preserving relative paths under `MEDIA_ROOT`. This is bounded (you can only copy what a row references) and skips deleted-but-not-purged files.

### Streaming pipeline

`pg_dump --stdout → gzip → AES-GCM encryptor → file write`. Nothing buffered in memory beyond a 64 KB working chunk. A 5 GB dump never holds more than 64 KB of plaintext or 64 KB of ciphertext in RAM at once. Required to keep Celery worker memory bounded.

## 7. Orchestration flow

```python
# snapshots/tasks.py
@shared_task(bind=True, max_retries=0,
             time_limit=SNAPSHOTS_HARD_TIME_LIMIT_SEC,
             soft_time_limit=SNAPSHOTS_SOFT_TIME_LIMIT_SEC)
def run_snapshot_job(self, job_id: int) -> None:
    with transaction.atomic():
        job = SnapshotJob.objects.select_for_update().get(pk=job_id)
        SnapshotService(job).execute()
```

```python
# snapshots/services/snapshot_service.py
class SnapshotService:
    def __init__(self, job: SnapshotJob):
        self.job = job

    def execute(self) -> None:
        try:
            self._transition(Status.RUNNING)
            with TemporaryDirectory() as workdir:
                workdir = Path(workdir)
                self._dump_database(workdir / 'database')
                self._collect_media(workdir / 'media')
                manifest = self._build_manifest(workdir)
                (workdir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
                artifact_path = self._encrypt_and_store(workdir, manifest)
            self._mark_succeeded(artifact_path, manifest)
            RetentionService.enforce_for_schema(self.job.schema_name)
        except SoftTimeLimitExceeded:
            self._mark_failed('timeout', 'Snapshot exceeded soft time limit')
        except Exception as exc:
            self._mark_failed(exc.__class__.__name__, str(exc))
            raise  # let Celery log it
```

### Six phases

| # | Method | What it does |
|---|---|---|
| 1 | `_dump_database` | `subprocess.run(['pg_dump', '--schema', schema, '--no-owner', '--no-privileges', '--clean', '--if-exists', '--format=plain', '--quote-all-identifiers', dsn])` streamed to `database/<schema>.sql`. Flags mirror `scripts/backup.sh` exactly. |
| 2 | `_collect_media` | With `schema_context(schema)`, iterate every model's `FileField`/`ImageField` instances; copy `.path` into `media/` preserving relative paths. |
| 3 | `_build_manifest` | Gather `migration_head` via `MigrationLoader`; `code_version` via `git rev-parse HEAD` + branch; `pii_key_fingerprint` from existing PII crypto module; SHA256 each component. |
| 4 | `_encrypt_and_store` | Stream `tar -czf - .` → AES-GCM with fresh DEK → final encrypted file. Wrap DEK with KEK. Compute SHA256 of encrypted bytes. |
| 5 | `_mark_succeeded` | Atomic update: status=SUCCEEDED, artifact_path, size_bytes, sha256, kek_fingerprint, manifest, completed_at. Audit log entry. |
| 6 | Retention | Inline call to `RetentionService.enforce_for_schema(schema)`. |

### Concurrency

`select_for_update()` on the job row prevents two workers racing the same `job_id`. Snapshots of *different* schemas run in parallel, bounded by Celery worker pool size.

## 8. Retention

Two rules, applied in order:

- **Rule A — age**: any `SUCCEEDED` job with `triggered_at < now - SNAPSHOTS_RETENTION_DAYS` → transition to `EXPIRED`, unlink artifact.
- **Rule B — per-tenant count**: within `SUCCEEDED` jobs for a single `schema_name`, keep the most recent `SNAPSHOTS_MAX_PER_TENANT`; transition the rest to `EXPIRED`, unlink artifacts.

Age first (cheap, indexed query); count next (operates only on what remains).

### Transaction ordering

DB update → commit → file unlink. If unlink fails, log a warning and leave the file as orphan; a janitor pass in the nightly beat reconciles. The opposite ordering (delete file, then DB) has a worse failure mode: a crash mid-way leaves the UI showing "download" for a snapshot whose bytes are gone.

### Triggers (belt-and-braces)

- **Inline** — phase 6 of `SnapshotService.execute()` calls `enforce_for_schema(schema)`.
- **Beat** — `enforce_retention_all` runs daily at 03:00 UTC, walking every distinct `schema_name` in `SnapshotJob`. Closes the failure mode where a worker crashes after `_mark_succeeded` but before the inline retention call.

## 9. Download path

```python
# snapshots/views.py
@action(detail=True, methods=['GET'], url_path='download')
def download(self, request, pk=None):
    job = self.get_object()  # already permission-checked
    if job.status != Status.SUCCEEDED:
        raise NotFound('Snapshot is not available for download.')

    audit_log.snapshot_download(
        actor=request.user, job=job,
        ip=request.META.get('REMOTE_ADDR'))

    return StreamingHttpResponse(
        stream_decrypt(job.absolute_path,
                       kek=resolve_kek(job.kek_fingerprint)),
        content_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{job.download_filename()}"',
            'X-Content-Type-Options': 'nosniff',
        },
    )
```

`stream_decrypt` is a generator that reads the encrypted file in 64 KB chunks, feeds them through AES-GCM, and yields plaintext chunks. GCM tag verification happens on the final chunk — if the file was tampered with, the generator raises before the last bytes ship. A truncated response is the right outcome: better than silently delivering corrupt bytes.

## 10. Error handling

| Failure | Where | Recovery |
|---|---|---|
| `pg_dump` non-zero exit | `_dump_database` subprocess | Capture stderr (truncated 4 KB) → `error_message`; status → `FAILED`. **No automatic retry** (`max_retries=0`); UI offers user-initiated "Retry" which creates a fresh job (new audit trail). |
| Disk full | `_encrypt_and_store` | Catch `OSError(ENOSPC)`; status → `FAILED`; `error_class='DiskFullError'`. Sentry alert (operationally urgent). |
| Soft time limit | Celery wrapper | Caught as `SoftTimeLimitExceeded`; status → `FAILED`; `error_message='timeout after N min — consider raising SNAPSHOTS_SOFT_TIME_LIMIT_SEC or splitting the schema'`. `TemporaryDirectory` exit cleans partial files. |
| KEK missing / malformed | App startup | Django `check` framework refuses to start the server when `DEBUG=False` and `SNAPSHOTS_KEK_HEX` is not a valid 64-char hex string. Fail-fast > silent broken backups. |
| Worker crash mid-job | Celery `prefetch_multiplier=1`, `acks_late=True` | Job stays in `RUNNING`. The beat task `reap_stale_jobs` (every 10 min) transitions any job with `started_at < now - hard_time_limit - 5min` to `FAILED`, `error_class='WorkerCrashOrTimeout'`. UI never shows a permanently-stuck job. |

### Error visibility

- Superadmin sees `error_class` + raw `error_message` (a "View error details" expandable).
- Tenant admin sees `error_class` + generic message ("Backup failed — please contact your administrator"). Raw `error_message` can leak schema details and is gated.

### Audit log

Every state transition writes one entry: `created`, `started`, `succeeded`, `failed`, `expired`, `downloaded`, `deleted`. Uses the existing audit infrastructure already wired across the codebase (signals into the `core` audit module).

## 11. Frontend

### Pages

- **Superadmin view**: `/admin/snapshots/` — table of all snapshots across all tenants; filterable by schema, status, date. Create form with a schema selector (all tenants + `public`).
- **Tenant-admin view**: `/settings/backups/` (inside the tenant) — table of own-schema snapshots only; create form with no schema selector (always own).

Both views use the same `<SnapshotsTable>` component with a `scope` prop.

### Components

```
features/admin/snapshots/
  SnapshotsPage.tsx                   # cross-tenant
  pages/TenantSnapshotsPage.tsx       # own-tenant
  components/
    SnapshotsTable.tsx
    SnapshotJobStatusPill.tsx
    CreateSnapshotForm.tsx
    SnapshotDetailDrawer.tsx
  hooks/
    useSnapshotJobs.ts                # list query, conditional polling
    useCreateSnapshot.ts              # mutation
    useDeleteSnapshot.ts              # mutation
    useDownloadSnapshot.ts            # imperative download trigger
```

### Polling strategy

`useSnapshotJobs` uses TanStack Query with a `refetchInterval` that returns `5000` ms iff any visible job has `status ∈ {queued, running}`, else `false`. Stops polling when nothing is in flight; prevents idle-page request storms.

### Download UX

Triggers a hidden `<a href={`/api/snapshots/${id}/download/`} download>` click. Browser handles the file save dialog. Toast on click ("Download starting…"). No client-side decryption; the API decrypts streamed.

## 12. Configuration

| Env var | Default | Purpose |
|---|---|---|
| `SNAPSHOTS_BACKUP_DIR` | `<BASE_DIR>/snapshots_storage` | Root directory for encrypted artifacts. Mode 0700 enforced on app startup. |
| `SNAPSHOTS_RETENTION_DAYS` | `14` | Age-based retention; matches `scripts/backup.sh`. |
| `SNAPSHOTS_MAX_PER_TENANT` | `5` | Count-based retention per schema. |
| `SNAPSHOTS_KEK_HEX` | (required, no default) | 64-char hex (256-bit) KEK. Validated at startup. |
| `SNAPSHOTS_KEK_ID` | `kek-v1` | Logical KEK identifier; stamped in manifest for rotation tracking. |
| `SNAPSHOTS_CREATE_RATE_PER_HOUR` | `5` | Per-(user, schema) creation rate limit. |
| `SNAPSHOTS_PG_DUMP_BIN` | `pg_dump` | Path override for `pg_dump` binary. |
| `SNAPSHOTS_SOFT_TIME_LIMIT_SEC` | `3000` (50 min) | Celery soft time limit. |
| `SNAPSHOTS_HARD_TIME_LIMIT_SEC` | `3600` (60 min) | Celery hard time limit. |

All overridable in `.env`; documented in `.env.example`.

## 13. Testing strategy

| Scope | What it covers | Location |
|---|---|---|
| Unit (services) | `crypto.py` round-trip (encrypt → decrypt → bytes-identical, streamed); `crypto.py` wrong-KEK refusal; `retention.py` rule A only, rule B only, both fired; `retention.py` orphan-file resilience; `manifest.py` field correctness against a fixture | `snapshots/tests/test_crypto.py`, `test_retention.py`, `test_manifest.py` |
| Service integration | `SnapshotService.execute()` against a tiny test schema with 2 tables + 2 media files. Verifies tarball layout, manifest content, file unencryptable without KEK. | `snapshots/tests/test_snapshot_service.py` |
| API (DRF) | `POST` happy path + 403 for wrong-tenant + 429 for rate limit; `GET` list scoped per actor type; `download` for `SUCCEEDED` only + audit row written; `DELETE` transitions + unlinks | `snapshots/tests/test_api.py` |
| RBAC matrix | Parametrized over `(actor_role, target_schema, expected_status)` — covers every cell of the §5 permission table | `snapshots/tests/test_permissions.py` |
| Concurrency | Two workers grabbing same `job_id` — `select_for_update` ensures only one runs the work | `snapshots/tests/test_concurrency.py` |
| Retention beat | Beat task walks N schemas, calls `enforce_for_schema` each; verify idempotent on second call | `snapshots/tests/test_beat.py` |
| E2E (Playwright) | Tenant admin creates a snapshot, polls until SUCCEEDED, downloads, deletes — full UI loop | `frontend/tests/e2e/snapshots.spec.ts` |

### Coverage targets

- `snapshots/services/*`: ≥ 85 %
- `snapshots/views.py`: ≥ 75 %

### Fixtures

A `tiny_schema` pytest fixture creates a 3-row, 2-media-file schema via `schema_context`. Used by service integration + API tests. Avoids dragging full migration head into every test.

## 14. Out of scope (explicit reminders)

- **No restore.** Period. P4 only. Even a `--dry-run` flag on a restore command is out of scope.
- **No S3 / off-site storage.** P2.
- **No per-tenant KEK.** Single deploy-time KEK.
- **No scheduled (cron-like) in-app snapshots.** Nightly belongs to `scripts/backup.sh`. P1 is on-demand only.
- **No browser-side decryption.** Server decrypts streaming.
- **No multi-schema snapshots.** Superadmin creates separate jobs for separate schemas.

## 15. Open questions

None at design time. The two design forks that were considered and resolved:

- **DELETE status label**: `EXPIRED` (chosen) vs distinct `DELETED`. Reusing `EXPIRED` keeps the enum small and the UI logic identical between operator-delete and retention-evict.
- **Tenant admin self-service**: in (chosen) vs deferred. Selected because the original goal-setting call explicitly included "self-service" requirements; quotas + rate limits cap the abuse surface.

## 16. References

- [`scripts/backup.sh`](../../../scripts/backup.sh) — existing operator-tier backup script, P1 mirrors its `pg_dump` flags
- [`docs/DR_DRILL.md`](../../DR_DRILL.md) — quarterly restore drill, RTO/RPO targets
- [`core/security/pii_crypto.py`](../../../core/security/pii_crypto.py) — existing envelope encryption pattern P1 mirrors
- [`core/permissions.py`](../../../core/permissions.py) — `_get_tenant_permissions`, `is_platform_superadmin`
- [`contracts/services/sod.py`](../../../contracts/services/sod.py) — `all_access` Role resolver pattern
- [`tenants/tasks.py`](../../../tenants/tasks.py) — schema-name regex validation
- [`quot_pse/settings.py`](../../../quot_pse/settings.py) — `SHARED_APPS`, conditional Celery wiring
