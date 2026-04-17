# Disaster-Recovery Drill — Quot PSE

**Purpose**: verify that the nightly backup produced by
`scripts/backup.sh` can be restored into an empty PostgreSQL
instance and that the application returns to a healthy state without
operator heroics. Run this drill **quarterly** and record the
measured RTO/RPO in the table at the bottom.

## RTO / RPO targets

| Metric | Target | Rationale |
|---|---|---|
| **RPO** (data loss window) | ≤ 24 h | Nightly backup cadence; matches typical state-government close-of-business |
| **RTO** (time to restored service) | ≤ 2 h | Cold restore of a mid-sized tenant (≈ 1 M journal lines). Budget for 30 min DB provision + 60 min restore + 30 min verification |

If a drill exceeds the target, open a ticket to investigate
(compression, parallel dump, or WAL-based PITR).

## Prerequisites

- Backup files in `$BACKUP_DIR` (either local or rclone'd from S3)
- An **empty** PostgreSQL 15 instance — **never** restore over a
  live database. A throwaway docker container is recommended:

  ```bash
  docker run --rm -d --name pg-drill \
    -e POSTGRES_USER=quot -e POSTGRES_PASSWORD=quot \
    -e POSTGRES_DB=quot_drill \
    -p 55432:5432 postgres:15
  export DRILL_DATABASE_URL="postgres://quot:quot@localhost:55432/quot_drill"
  ```

- `psql` on the PATH
- Same Django version the backup came from (check `requirements.txt`
  or the Docker image tag)

## Restore procedure — 9 steps

### 1. Inventory the backup archive

```bash
ls -l $BACKUP_DIR/quotpse-*.sql.gz | tail -20
```

Pick the timestamp you intend to restore. All schemas in the drill
MUST come from the **same timestamp** — mixing public and tenant
schemas from different nights produces FK-orphaned rows.

```bash
DRILL_TS="2026-04-17T02-00"
```

### 2. Record the start time

```bash
date +"%Y-%m-%dT%H:%M:%S" > /tmp/drill_start
```

### 3. Restore the public schema **first**

Public holds `tenants_client` + `tenants_domain` + the auth tables.
Every tenant schema FKs into public, so it has to land first.

```bash
gunzip -c $BACKUP_DIR/quotpse-public-${DRILL_TS}.sql.gz \
  | psql "$DRILL_DATABASE_URL"
```

### 4. Restore each tenant schema

```bash
for f in $BACKUP_DIR/quotpse-*-${DRILL_TS}.sql.gz; do
  schema=$(basename "$f" | sed -E "s/quotpse-(.*)-${DRILL_TS}\.sql\.gz/\1/")
  [ "$schema" = "public" ] && continue
  echo "Restoring $schema"
  gunzip -c "$f" | psql "$DRILL_DATABASE_URL"
done
```

### 5. Apply pending migrations

Restored data is at the *source-backup* migration state. If the
current code has shipped newer migrations since the backup, apply
them now:

```bash
DATABASE_URL=$DRILL_DATABASE_URL python manage.py migrate_schemas --shared
DATABASE_URL=$DRILL_DATABASE_URL python manage.py migrate_schemas --tenant
```

### 6. Smoke-test the drill instance

```bash
DATABASE_URL=$DRILL_DATABASE_URL python manage.py runserver 0.0.0.0:8000 &
sleep 5
curl -fsS http://localhost:8000/healthz || echo "HEALTHZ FAILED"
curl -fsS http://localhost:8000/readyz  || echo "READYZ FAILED"
curl -fsS http://localhost:8000/metrics | grep quotpse_tenants_total
```

Expected: `healthz=200`, `readyz=200`, `tenants_total >= 3`.

### 7. Data sanity checks

Per tenant, verify a few high-signal numbers match the live system
(within the RPO window):

```bash
DATABASE_URL=$DRILL_DATABASE_URL python manage.py shell -c "
from django_tenants.utils import schema_context
from accounting.models import JournalHeader
for s in ['delta_state', 'test_state']:
    with schema_context(s):
        posted = JournalHeader.objects.filter(status='Posted').count()
        print(f'{s}: {posted} posted journals')
"
```

Compare to the live Data Quality dashboard (`/accounting/data-quality`)
on the source instance. Counts should match the backup timestamp.

### 8. Record the end time

```bash
date +"%Y-%m-%dT%H:%M:%S" > /tmp/drill_end
echo "Start: $(cat /tmp/drill_start)"
echo "End:   $(cat /tmp/drill_end)"
echo "Duration: $(( $(date -d "$(cat /tmp/drill_end)" +%s) \
                   - $(date -d "$(cat /tmp/drill_start)" +%s) )) seconds"
```

Log this into the drill history table below.

### 9. Tear down the drill instance

```bash
docker stop pg-drill
```

## Drill history

Append one row per quarterly exercise. Keep it terse; the point is
the trend, not the story.

| Date | Operator | Backup TS | Schemas | Duration | RTO met? | Notes |
|---|---|---|---|---|---|---|
| 2026-04-17 | (template) | 2026-04-16T02-00 | public + 3 | 45 min | ✓ | First run — ritual only |

## When the drill fails

- **`psql` errors on public restore** → backup file truncated. Check
  `gunzip -t`. Re-fetch from off-site if corrupt.
- **Tenant schema FK errors** → public was restored from a different
  timestamp. Start over with matched files.
- **`/readyz` returns 503 with `migrations pending`** → the code
  version that produced the backup is older than the current code.
  Either roll the code back to the backup's version OR run the
  migration step (#5) — these are two different decisions; do not do
  both.
- **`tenants_total` = 0 in `/metrics`** → `tenants_client` table
  empty. Likely the public restore failed partway; re-run.

## Automation roadmap

Not yet done — flagged for a future sprint:

1. GitHub Actions workflow that runs steps 1–8 weekly against the
   latest S3 backup and posts the RTO to a Slack channel.
2. `restore.sh` companion to `backup.sh` that performs steps 3–4
   automatically given a timestamp argument.
3. Point-in-time-recovery via WAL shipping to reduce RPO from 24 h
   to 15 min. Requires a PostgreSQL replica or managed-service
   feature (Amazon RDS, Cloud SQL).
