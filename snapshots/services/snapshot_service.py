"""6-phase orchestrator for in-app snapshot creation.

Phases:
  1. _dump_database     — pg_dump → workdir/database/<schema>.sql
  2. _collect_media     — iterate FileField rows, copy into workdir/media/
  3. _build_manifest    — code/migration/PII fingerprint → manifest dict
  4. write manifest.json into workdir
  5. _encrypt_and_store — tar.gz → AES-GCM → Storage.open_write
  6. _mark_succeeded    — atomic DB update; enforce retention
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.db import transaction
from django.utils import timezone as django_timezone

from snapshots.models import SnapshotJob
from snapshots.services.crypto import encrypt_stream
from snapshots.services.dump import run_pg_dump
from snapshots.services.manifest import build_manifest
from snapshots.services.media import collect_referenced_media
from snapshots.services.retention import RetentionService
from snapshots.services.storage import LocalFilesystemStorage


logger = logging.getLogger(__name__)


def _resolve_kek() -> bytes:
    """Decode the deploy-time KEK from settings.SNAPSHOTS_KEK_HEX."""
    hex_str = getattr(settings, 'SNAPSHOTS_KEK_HEX', None)
    if not hex_str:
        raise RuntimeError(
            'SNAPSHOTS_KEK_HEX is not set — refusing to create snapshot.')
    try:
        kek = bytes.fromhex(hex_str.strip())
    except ValueError as exc:
        raise RuntimeError(f'SNAPSHOTS_KEK_HEX is not valid hex: {exc}') from exc
    if len(kek) != 32:
        raise RuntimeError(
            f'SNAPSHOTS_KEK_HEX must decode to 32 bytes, got {len(kek)}')
    return kek


def _resolve_dsn() -> str:
    """Build a Postgres DSN from settings.DATABASES['default']."""
    db = settings.DATABASES['default']
    user = db.get('USER') or ''
    password = db.get('PASSWORD') or ''
    host = db.get('HOST') or 'localhost'
    port = db.get('PORT') or 5432
    name = db.get('NAME') or ''
    creds = f'{user}:{password}@' if password else (f'{user}@' if user else '')
    return f'postgresql://{creds}{host}:{port}/{name}'


def _artifact_relpath(schema_name: str, job_id: int) -> str:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'{schema_name}/snapshot-{job_id}-{ts}.tar.gz.enc'


class SnapshotService:
    def __init__(self, job: SnapshotJob, storage=None):
        self.job = job
        self.storage = storage or LocalFilesystemStorage(
            root=settings.SNAPSHOTS_BACKUP_DIR)

    def execute(self) -> None:
        """Run all 6 phases. Updates job row in-place. Raises on failure
        (caller — typically the Celery task — is responsible for logging)."""
        try:
            self._transition_running()
            with TemporaryDirectory() as workdir_str:
                workdir = Path(workdir_str)
                db_dir = workdir / 'database'
                media_dir = workdir / 'media'
                db_sql_path = db_dir / f'{self.job.schema_name}.sql'

                # Phase 1: dump database.
                self._dump_database(db_sql_path)

                # Phase 2: collect media (skipped for the public schema).
                self._collect_media(media_dir)

                # Phase 3: build manifest.
                manifest = self._build_manifest(db_sql_path, media_dir)

                # Phase 4: write manifest.json.
                (workdir / 'manifest.json').write_text(
                    json.dumps(manifest, indent=2, sort_keys=True))

                # Phase 5: encrypt + store.
                artifact_relpath, size_bytes, sha256_hex = self._encrypt_and_store(
                    workdir, manifest)

            # Phase 6: mark succeeded + enforce retention.
            self._mark_succeeded(
                artifact_relpath, size_bytes, sha256_hex, manifest)
            RetentionService(storage=self.storage).enforce_for_schema(
                self.job.schema_name)
        except Exception as exc:
            self._mark_failed(exc)
            raise

    # ── phases ─────────────────────────────────────────────────────────

    def _transition_running(self) -> None:
        SnapshotJob.objects.filter(pk=self.job.pk).update(
            status=SnapshotJob.Status.RUNNING,
            started_at=django_timezone.now(),
        )
        self.job.refresh_from_db()

    def _dump_database(self, target: Path) -> None:
        run_pg_dump(
            schema=self.job.schema_name,
            dsn=_resolve_dsn(),
            target=target,
            pg_dump_bin=settings.SNAPSHOTS_PG_DUMP_BIN,
            timeout_sec=settings.SNAPSHOTS_SOFT_TIME_LIMIT_SEC,
        )

    def _collect_media(self, destination: Path) -> None:
        if self.job.schema_name == 'public':
            return
        collect_referenced_media(
            schema_name=self.job.schema_name,
            destination=destination,
        )

    def _build_manifest(self, db_sql_path: Path, media_dir: Path) -> dict:
        return build_manifest(
            job_id=self.job.pk,
            label=self.job.label,
            schema_name=self.job.schema_name,
            triggered_by_user_id=self.job.triggered_by_id,
            triggered_by_username=self.job.triggered_by.username,
            database_sql_path=db_sql_path,
            media_root=media_dir if media_dir.exists() else None,
            kek_id=settings.SNAPSHOTS_KEK_ID,
        )

    def _encrypt_and_store(
        self, workdir: Path, manifest: dict,
    ) -> tuple[str, int, str]:
        """Tar+gzip the workdir, encrypt, write to storage,
        return (artifact_relpath, size_bytes, sha256_hex)."""
        kek = _resolve_kek()
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode='w:gz') as tar:
            tar.add(str(workdir), arcname=f'snapshot-{self.job.pk}')
        tar_buf.seek(0)

        artifact_relpath = _artifact_relpath(self.job.schema_name, self.job.pk)
        buffered = io.BytesIO()
        encrypt_stream(
            tar_buf, buffered,
            kek=kek, kek_id=settings.SNAPSHOTS_KEK_ID,
        )
        ciphertext = buffered.getvalue()
        sha = hashlib.sha256(ciphertext)
        size = len(ciphertext)
        with self.storage.open_write(artifact_relpath) as out_fh:
            out_fh.write(ciphertext)
        return artifact_relpath, size, sha.hexdigest()

    def _mark_succeeded(
        self, artifact_relpath: str, size_bytes: int, sha256_hex: str,
        manifest: dict,
    ) -> None:
        with transaction.atomic():
            SnapshotJob.objects.filter(pk=self.job.pk).update(
                status=SnapshotJob.Status.SUCCEEDED,
                completed_at=django_timezone.now(),
                artifact_path=artifact_relpath,
                size_bytes=size_bytes,
                sha256=sha256_hex,
                kek_fingerprint=settings.SNAPSHOTS_KEK_ID,
                manifest=manifest,
            )
        self.job.refresh_from_db()

    def _mark_failed(self, exc: Exception) -> None:
        msg = str(exc)[:4096]
        try:
            with transaction.atomic():
                SnapshotJob.objects.filter(pk=self.job.pk).update(
                    status=SnapshotJob.Status.FAILED,
                    completed_at=django_timezone.now(),
                    error_class=exc.__class__.__name__,
                    error_message=msg,
                )
        except Exception:
            logger.exception('snapshots: failed to record FAILED state for job %s',
                              self.job.pk)
