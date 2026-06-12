"""Build the manifest.json that sits inside every snapshot tarball.

The manifest stamps everything a future restore tool needs to make safe
decisions: code version, migration heads, PII key fingerprint, SHA256 of
the SQL dump. P4 restore reads this; P1 just writes it.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


MANIFEST_SCHEMA_VERSION = 1
HASH_CHUNK = 64 * 1024


def sha256_of_file(path: Path) -> str:
    """Stream-hash a file in 64 KB chunks. Never loads the file into memory."""
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(HASH_CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def _git_revision() -> str:
    """Return ``<branch>@<short-sha>`` or 'unknown' if git is unavailable.

    Uses a single git invocation pinned to the project's BASE_DIR with
    --no-optional-locks to avoid contention with parallel git processes.
    """
    try:
        base = Path(getattr(settings, 'BASE_DIR', Path.cwd()))
        # git log -1 --format=%D@%h emits "HEAD -> branch, origin/branch@abc1234"
        # Parse to keep only the local branch name + sha.
        result = subprocess.run(
            ['git', '--no-optional-locks', 'rev-parse', '--abbrev-ref', 'HEAD'],
            check=True, capture_output=True, text=True, timeout=5, cwd=base,
        )
        branch = result.stdout.strip()
        result = subprocess.run(
            ['git', '--no-optional-locks', 'rev-parse', '--short', 'HEAD'],
            check=True, capture_output=True, text=True, timeout=5, cwd=base,
        )
        sha = result.stdout.strip()
        logger.debug('manifest: git revision %s@%s', branch, sha)
        return f'{branch}@{sha}'
    except Exception as exc:
        logger.warning('manifest: could not read git revision: %s', exc)
        return 'unknown'


def _migration_heads() -> dict[str, list[str]]:
    """Return latest migration per app for shared and tenant apps."""
    try:
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader
        loader = MigrationLoader(connection)
        shared: list[str] = []
        tenant: list[str] = []
        shared_app_set = set(settings.SHARED_APPS) if hasattr(settings, 'SHARED_APPS') else set()
        for (app, name) in loader.graph.leaf_nodes():
            entry = f'{app}.{name}'
            if app in shared_app_set or f'django.contrib.{app}' in shared_app_set:
                shared.append(entry)
            else:
                tenant.append(entry)
        return {'shared': sorted(shared), 'tenant': sorted(tenant)}
    except Exception as exc:
        logger.warning('manifest: could not read migration heads: %s', exc)
        return {'shared': [], 'tenant': []}


def _pii_key_fingerprint() -> str:
    """Best-effort fingerprint of the current PII encryption key.

    We don't want to leak the key itself — just a short fingerprint that
    survives in the manifest and lets P4 detect a key-rotation gap.
    """
    secret = getattr(settings, 'SECRET_KEY', '') or ''
    if not secret:
        return 'unknown'
    # Domain separation prefix so this fingerprint can't be confused with a
    # SHA256 of SECRET_KEY computed for any other purpose elsewhere.
    h = hashlib.sha256(b'quot-pse-manifest-pii-v1\x00' + secret.encode('utf-8')).hexdigest()
    return f'sk-{h[:12]}'


def _postgres_version() -> str:
    try:
        from django.db import connection
        if connection.vendor != 'postgresql':
            return 'n/a'
        with connection.cursor() as cur:
            cur.execute('SHOW server_version')
            return cur.fetchone()[0]
    except Exception as exc:
        logger.warning('manifest: could not read postgres version: %s', exc)
        return 'unknown'


def _django_tenants_version() -> str:
    """Return the installed django-tenants version string.

    Falls back to importlib.metadata (the canonical way) then to 'unknown'
    if the package metadata is unavailable (e.g. editable install without
    PKG-INFO).
    """
    try:
        import django_tenants
        version = getattr(django_tenants, '__version__', None)
        return version if version is not None else _pkg_version('django-tenants')
    except Exception:
        return 'unknown'


def _pkg_version(package: str) -> str:
    try:
        from importlib.metadata import version
        return version(package)
    except Exception:
        return 'unknown'


def _scan_media(media_root: Path | None) -> tuple[int, int]:
    if media_root is None or not media_root.exists():
        return 0, 0
    count = 0
    total = 0
    for p in media_root.rglob('*'):
        # Skip symlinked files: snapshot tarball is built from a controlled temp
        # copy in Task 9, so symlinks here would indicate something unexpected.
        if p.is_file() and not p.is_symlink():
            count += 1
            total += p.stat().st_size
    return count, total


def build_manifest(
    *,
    job_id: int,
    label: str,
    schema_name: str,
    triggered_by_user_id: int,
    triggered_by_username: str,
    database_sql_path: Path,
    media_root: Path | None,
    kek_id: str,
) -> dict[str, Any]:
    """Build the manifest dict. Encryption-envelope fields are filled in
    later by SnapshotService after the tarball is encrypted (we cannot
    know IV / tag / wrapped_dek until then)."""
    media_count, media_total = _scan_media(media_root)
    import django
    return {
        'schema_version': MANIFEST_SCHEMA_VERSION,
        'snapshot': {
            'job_id': job_id,
            'label': label,
            'schema_name': schema_name,
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'triggered_by': {
                'user_id': triggered_by_user_id,
                'username': triggered_by_username,
            },
        },
        'source': {
            'code_version': _git_revision(),
            'django_version': django.get_version(),
            'django_tenants_version': _django_tenants_version(),
            'postgres_version': _postgres_version(),
            'migration_head': _migration_heads(),
            'pii_key_fingerprint': _pii_key_fingerprint(),
        },
        'contents': {
            'database_sql_sha256': sha256_of_file(database_sql_path),
            'media_file_count': media_count,
            'media_total_bytes': media_total,
        },
        'encryption': {
            'algorithm': 'AES-256-GCM',
            'kek_id': kek_id,
            # Filled in by SnapshotService after _encrypt_and_store:
            'wrapped_dek_b64': None,
            'iv_b64': None,
            'tag_b64': None,
        },
    }
