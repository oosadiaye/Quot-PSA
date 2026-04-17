#!/usr/bin/env bash
# Quot PSE nightly backup — pg_dump per schema with rotation.
#
# Usage
# -----
#   ./scripts/backup.sh                     # all schemas, default retention
#   ./scripts/backup.sh --schema=delta_state  # one schema only
#   BACKUP_DIR=/mnt/backups ./scripts/backup.sh
#
# Env vars
# --------
#   DATABASE_URL       postgres://user:pass@host:5432/dbname (REQUIRED)
#   BACKUP_DIR         destination directory (default: ./backups)
#   BACKUP_RETENTION   days to keep (default: 14)
#   BACKUP_PREFIX      filename prefix (default: quotpse)
#
# Output layout
# -------------
#   $BACKUP_DIR/
#     quotpse-public-2026-04-17T02-00.sql.gz
#     quotpse-delta_state-2026-04-17T02-00.sql.gz
#     quotpse-test_state-2026-04-17T02-00.sql.gz
#
# Retention
# ---------
# Files older than $BACKUP_RETENTION days (by mtime) are deleted AFTER
# the new backup completes, so a failed run never empties the archive.
#
# Exit codes
# ----------
#   0   all schemas dumped successfully
#   1   DATABASE_URL missing or malformed
#   2   pg_dump failed for at least one schema (partial backup kept,
#       message on stderr lists which schemas failed)
#
# Integrity check
# ---------------
# Every dump is gzipped then immediately test-decompressed with
# `gunzip -t` to catch truncation. A file that can't be decompressed
# is deleted and the schema counted as a failure.

set -uo pipefail

# ── Argument parsing (BEFORE env guards so --help works) ──────────
SINGLE_SCHEMA=""
for arg in "$@"; do
  case "$arg" in
    --schema=*) SINGLE_SCHEMA="${arg#*=}" ;;
    --help|-h)
      sed -n '3,35p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

# ── Config (env guards after args so --help is always usable) ─────
: "${DATABASE_URL:?DATABASE_URL env var is required}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_RETENTION="${BACKUP_RETENTION:-14}"
BACKUP_PREFIX="${BACKUP_PREFIX:-quotpse}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M)"

# ── Discover schemas ───────────────────────────────────────────────
# Query django-tenants' registry table (public.tenants_client) for
# every tenant schema. Public is always included.
schemas=()
if [ -n "$SINGLE_SCHEMA" ]; then
  schemas=("$SINGLE_SCHEMA")
else
  schemas+=("public")
  tenant_schemas=$(
    psql "$DATABASE_URL" -At -c \
      "SELECT schema_name FROM tenants_client WHERE schema_name != 'public' ORDER BY schema_name;"
  ) || {
    echo "Failed to enumerate tenant schemas via psql" >&2
    exit 2
  }
  while IFS= read -r s; do
    [ -n "$s" ] && schemas+=("$s")
  done <<< "$tenant_schemas"
fi

echo "[backup] Target schemas: ${schemas[*]}"
echo "[backup] Output directory: $BACKUP_DIR"
echo "[backup] Retention: ${BACKUP_RETENTION} days"

# ── Dump loop ──────────────────────────────────────────────────────
failed_schemas=()
dumped=0
for schema in "${schemas[@]}"; do
  outfile="${BACKUP_DIR}/${BACKUP_PREFIX}-${schema}-${TIMESTAMP}.sql.gz"
  echo "[backup] Dumping schema '$schema' → $outfile"

  if pg_dump \
      --schema="$schema" \
      --no-owner \
      --no-privileges \
      --clean --if-exists \
      --format=plain \
      --quote-all-identifiers \
      "$DATABASE_URL" \
      | gzip -9 > "$outfile"; then
    # Integrity test.
    if gunzip -t "$outfile" 2>/dev/null; then
      size=$(wc -c < "$outfile")
      echo "[backup]   ok — ${size} bytes"
      dumped=$((dumped + 1))
    else
      echo "[backup]   FAILED integrity check — removing $outfile" >&2
      rm -f "$outfile"
      failed_schemas+=("$schema")
    fi
  else
    echo "[backup]   FAILED pg_dump for $schema" >&2
    rm -f "$outfile"
    failed_schemas+=("$schema")
  fi
done

# ── Rotation — only if at least one dump succeeded ─────────────────
if [ "$dumped" -gt 0 ]; then
  echo "[backup] Rotating: deleting files older than ${BACKUP_RETENTION} days"
  find "$BACKUP_DIR" -maxdepth 1 -type f \
    -name "${BACKUP_PREFIX}-*.sql.gz" \
    -mtime "+${BACKUP_RETENTION}" \
    -print -delete
else
  echo "[backup] Skipping rotation — no successful dumps this run." >&2
fi

# ── Summary ────────────────────────────────────────────────────────
echo "[backup] Summary: ${dumped}/${#schemas[@]} schemas dumped."
if [ "${#failed_schemas[@]}" -gt 0 ]; then
  echo "[backup] FAILED: ${failed_schemas[*]}" >&2
  exit 2
fi

exit 0
