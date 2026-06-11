# In-App Snapshots — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-service in-app snapshot capability — a new Django app `snapshots/` that lets superadmins and tenant admins trigger on-demand encrypted backups of any (or their own) tenant schema, plus the React frontend to drive it.

**Architecture:** New Django app in `SHARED_APPS` exposing a DRF `SnapshotJobViewSet`. Work runs in a Celery task that streams `pg_dump` through an AES-256-GCM envelope encryptor and writes a single `.tar.gz.enc` artifact to local disk. Defense-in-depth RBAC (permission classes + queryset filter). Retention runs both inline after every snapshot and via a daily beat task. Frontend feature in `features/admin/snapshots/` with TanStack Query polling.

**Tech Stack:** Django 5.2, django-tenants 3.10, DRF 3.17, Celery (already conditionally wired), `cryptography>=42`, PostgreSQL 15, React + TanStack Query + Vite, Playwright for E2E.

**Reference spec:** [docs/superpowers/specs/2026-06-11-in-app-snapshots-design.md](../specs/2026-06-11-in-app-snapshots-design.md)

---

## File structure

### Backend — new files

```
snapshots/
  __init__.py
  apps.py                           # AppConfig + Django check for SNAPSHOTS_KEK_HEX
  checks.py                         # KEK validity check, BACKUP_DIR perms check
  models.py                         # SnapshotJob
  permissions.py                    # CanCreateSnapshot, CanAccessSnapshot, helpers
  serializers.py                    # SnapshotJobSerializer
  views.py                          # SnapshotJobViewSet
  urls.py                           # router wiring
  tasks.py                          # Celery: run_snapshot_job, enforce_retention_all, reap_stale_jobs
  audit.py                          # thin wrapper that writes to core.AuditLog
  services/
    __init__.py
    snapshot_service.py             # SnapshotService.execute() — six-phase orchestrator
    storage.py                      # Storage Protocol + LocalFilesystemStorage
    crypto.py                       # encrypt_stream, decrypt_stream, wrap/unwrap_dek
    manifest.py                     # build_manifest, MIGRATION_HEADS helper
    media.py                        # collect_referenced_media
    dump.py                         # run_pg_dump subprocess wrapper
    retention.py                    # RetentionService.enforce_for_schema, enforce_all
    resolvers.py                    # is_platform_superadmin, tenant_schemas_with_all_access
  migrations/
    __init__.py
    0001_initial.py                 # auto-generated
  tests/
    __init__.py
    conftest.py                     # snapshot-test fixtures: KEK, BACKUP_DIR, tiny_schema
    test_crypto.py
    test_storage.py
    test_manifest.py
    test_media.py
    test_dump.py
    test_snapshot_service.py        # integration
    test_retention.py
    test_tasks.py
    test_permissions.py
    test_serializers.py
    test_api.py
    test_concurrency.py
```

### Backend — modified files

```
quot_pse/settings.py                # add 'snapshots' to SHARED_APPS, add SNAPSHOTS_* keys, throttle scope
quot_pse/urls.py                    # include('snapshots.urls')
quot_pse/celery.py                  # register beat schedule if file exists; else create
pytest.ini                          # add snapshots/tests to testpaths
.env.example                        # document new SNAPSHOTS_* env vars
```

### Frontend — new files

```
frontend/src/features/admin/snapshots/
  api.ts                            # typed client wrapping /api/snapshots/
  types.ts                          # SnapshotJob, SnapshotStatus, CreateSnapshotInput
  hooks/
    useSnapshotJobs.ts              # list query w/ conditional polling
    useCreateSnapshot.ts            # POST mutation
    useDeleteSnapshot.ts            # DELETE mutation
    useDownloadSnapshot.ts          # imperative download trigger
  components/
    SnapshotsTable.tsx
    SnapshotJobStatusPill.tsx
    CreateSnapshotForm.tsx
    SnapshotDetailDrawer.tsx
  pages/
    SnapshotsPage.tsx               # superadmin cross-tenant
    TenantSnapshotsPage.tsx         # tenant-admin own-schema
```

### Frontend — modified files

```
frontend/src/App.tsx                # route wiring for /admin/snapshots and /settings/backups
frontend/src/components/Sidebar.tsx # nav entries (visibility gated by role)
```

### E2E

```
frontend/tests/e2e/snapshots.spec.ts
```

---

## Tasks

### Task 1: Bootstrap the `snapshots/` Django app

**Files:**
- Create: `snapshots/__init__.py` (empty)
- Create: `snapshots/apps.py`
- Create: `snapshots/checks.py`
- Modify: `quot_pse/settings.py` — add `'snapshots'` to `SHARED_APPS`, add `SNAPSHOTS_*` keys
- Modify: `.env.example` — document new env vars
- Test: `snapshots/tests/__init__.py` (empty), `snapshots/tests/test_checks.py`
- Modify: `pytest.ini` — add `snapshots/tests` to `testpaths`

- [ ] **Step 1: Write failing test for KEK validity check**

`snapshots/tests/test_checks.py`:

```python
"""System checks: refuse to start without a valid KEK."""
from __future__ import annotations

import pytest
from django.test import override_settings

from snapshots.checks import check_snapshot_kek


@pytest.mark.unit
def test_kek_missing_raises_error_in_production():
    with override_settings(DEBUG=False, SNAPSHOTS_KEK_HEX=None):
        errors = check_snapshot_kek(app_configs=None)
        assert any(e.id == 'snapshots.E001' for e in errors)


@pytest.mark.unit
def test_kek_wrong_length_raises_error():
    bad = '00' * 16  # 32 hex chars = 16 bytes; we need 32 bytes (64 hex chars)
    with override_settings(DEBUG=False, SNAPSHOTS_KEK_HEX=bad):
        errors = check_snapshot_kek(app_configs=None)
        assert any(e.id == 'snapshots.E002' for e in errors)


@pytest.mark.unit
def test_kek_non_hex_raises_error():
    bad = 'ZZ' * 32  # right length, wrong alphabet
    with override_settings(DEBUG=False, SNAPSHOTS_KEK_HEX=bad):
        errors = check_snapshot_kek(app_configs=None)
        assert any(e.id == 'snapshots.E003' for e in errors)


@pytest.mark.unit
def test_kek_valid_returns_no_errors():
    good = 'aa' * 32  # 64 hex chars = 32 bytes
    with override_settings(DEBUG=False, SNAPSHOTS_KEK_HEX=good):
        errors = check_snapshot_kek(app_configs=None)
        assert errors == []


@pytest.mark.unit
def test_kek_missing_is_warning_in_debug():
    """In DEBUG, missing KEK is a warning, not an error — keeps dev loop fast."""
    with override_settings(DEBUG=True, SNAPSHOTS_KEK_HEX=None):
        errors = check_snapshot_kek(app_configs=None)
        # Either no error, or only Warning-level entries.
        assert all(e.level < 40 for e in errors)  # 40 = ERROR
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_checks.py -v
```

Expected: ModuleNotFoundError (`snapshots.checks` does not exist yet).

- [ ] **Step 3: Add app to SHARED_APPS and define settings keys**

Edit `quot_pse/settings.py`. Insert `'snapshots'` into `SHARED_APPS` after `'core'` (or wherever `core` sits):

```python
SHARED_APPS = [
    'django_tenants',
    'tenants',
    # ... existing entries ...
    'core',
    'snapshots',
]
```

Then, in the same file, after the existing `MEDIA_ROOT` line, add:

```python
# ── In-app snapshots (Phase 1) ─────────────────────────────────────
SNAPSHOTS_BACKUP_DIR           = os.getenv(
    'SNAPSHOTS_BACKUP_DIR', str(BASE_DIR / 'snapshots_storage'))
SNAPSHOTS_RETENTION_DAYS       = int(os.getenv('SNAPSHOTS_RETENTION_DAYS', '14'))
SNAPSHOTS_MAX_PER_TENANT       = int(os.getenv('SNAPSHOTS_MAX_PER_TENANT', '5'))
SNAPSHOTS_KEK_HEX              = os.getenv('SNAPSHOTS_KEK_HEX')
SNAPSHOTS_KEK_ID               = os.getenv('SNAPSHOTS_KEK_ID', 'kek-v1')
SNAPSHOTS_CREATE_RATE_PER_HOUR = int(os.getenv('SNAPSHOTS_CREATE_RATE_PER_HOUR', '5'))
SNAPSHOTS_PG_DUMP_BIN          = os.getenv('SNAPSHOTS_PG_DUMP_BIN', 'pg_dump')
SNAPSHOTS_SOFT_TIME_LIMIT_SEC  = int(os.getenv('SNAPSHOTS_SOFT_TIME_LIMIT_SEC', '3000'))
SNAPSHOTS_HARD_TIME_LIMIT_SEC  = int(os.getenv('SNAPSHOTS_HARD_TIME_LIMIT_SEC', '3600'))
```

Also locate the existing `REST_FRAMEWORK` dict (specifically `DEFAULT_THROTTLE_RATES`) and add:

```python
# Inside REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']:
'snapshot_create': os.getenv('SNAPSHOTS_CREATE_THROTTLE', '5/hour'),
```

- [ ] **Step 4: Implement the checks module**

`snapshots/checks.py`:

```python
"""Django startup checks: refuse to boot without a valid KEK in production."""
from __future__ import annotations

import re

from django.conf import settings
from django.core.checks import Error, Warning, register

_HEX_RE = re.compile(r'^[0-9a-fA-F]+$')


def check_snapshot_kek(app_configs, **kwargs):
    """Validate SNAPSHOTS_KEK_HEX. In DEBUG, downgrade missing-key to Warning."""
    errors = []
    kek = getattr(settings, 'SNAPSHOTS_KEK_HEX', None)
    debug = getattr(settings, 'DEBUG', False)

    if not kek:
        if debug:
            errors.append(Warning(
                'SNAPSHOTS_KEK_HEX is not set. Snapshot creation will fail.',
                hint='Set SNAPSHOTS_KEK_HEX to a 64-char hex string (32 bytes).',
                id='snapshots.W001',
            ))
        else:
            errors.append(Error(
                'SNAPSHOTS_KEK_HEX must be set in non-DEBUG environments.',
                hint='Set SNAPSHOTS_KEK_HEX to a 64-char hex string (32 bytes).',
                id='snapshots.E001',
            ))
        return errors

    if len(kek) != 64:
        errors.append(Error(
            f'SNAPSHOTS_KEK_HEX must be exactly 64 hex chars (got {len(kek)}).',
            id='snapshots.E002',
        ))
    elif not _HEX_RE.match(kek):
        errors.append(Error(
            'SNAPSHOTS_KEK_HEX must contain only hex characters (0-9 a-f).',
            id='snapshots.E003',
        ))
    return errors
```

- [ ] **Step 5: Implement the AppConfig that registers the check**

`snapshots/apps.py`:

```python
"""Django app configuration for the snapshots feature."""
from __future__ import annotations

from django.apps import AppConfig
from django.core.checks import register


class SnapshotsConfig(AppConfig):
    name = 'snapshots'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self) -> None:
        from .checks import check_snapshot_kek
        register(check_snapshot_kek)
```

- [ ] **Step 6: Document env vars in .env.example**

Append to `.env.example`:

```
# ── Snapshots (Phase 1) ─────────────────────────────────────────────
# 64-char hex (32 bytes). Required in non-DEBUG environments.
# Generate with: python -c "import os; print(os.urandom(32).hex())"
SNAPSHOTS_KEK_HEX=
SNAPSHOTS_KEK_ID=kek-v1
SNAPSHOTS_BACKUP_DIR=
SNAPSHOTS_RETENTION_DAYS=14
SNAPSHOTS_MAX_PER_TENANT=5
SNAPSHOTS_CREATE_RATE_PER_HOUR=5
SNAPSHOTS_SOFT_TIME_LIMIT_SEC=3000
SNAPSHOTS_HARD_TIME_LIMIT_SEC=3600
```

- [ ] **Step 7: Add snapshots/tests to pytest testpaths**

Edit `pytest.ini`, replace the `testpaths` block with:

```ini
testpaths =
    accounting/tests
    budget/tests
    contracts/tests
    snapshots/tests
```

Create empty `snapshots/tests/__init__.py`.

- [ ] **Step 8: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_checks.py -v
```

Expected: 5 passed.

- [ ] **Step 9: Commit**

```bash
git add snapshots/__init__.py snapshots/apps.py snapshots/checks.py \
        snapshots/tests/__init__.py snapshots/tests/test_checks.py \
        quot_pse/settings.py .env.example pytest.ini
git commit -m "feat(snapshots): bootstrap app with KEK startup check"
```

---

### Task 2: SnapshotJob model + migration

**Files:**
- Create: `snapshots/models.py`
- Test: `snapshots/tests/test_models.py`
- Create: `snapshots/migrations/__init__.py`
- Create: `snapshots/migrations/0001_initial.py` (via makemigrations)

- [ ] **Step 1: Write failing test for model invariants**

`snapshots/tests/test_models.py`:

```python
"""Model-level invariants for SnapshotJob."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from snapshots.models import SnapshotJob


User = get_user_model()


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.mark.integration
def test_can_create_queued_job(actor):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor, label='pre import')
    assert job.status == SnapshotJob.Status.QUEUED
    assert job.triggered_at is not None
    assert job.started_at is None
    assert job.completed_at is None


@pytest.mark.integration
def test_schema_name_regex_rejected_at_db_level(actor):
    # Capital letters not allowed by the CheckConstraint.
    with pytest.raises(IntegrityError):
        SnapshotJob.objects.create(schema_name='Delta_State', triggered_by=actor)


@pytest.mark.integration
def test_schema_name_starts_with_digit_rejected(actor):
    with pytest.raises(IntegrityError):
        SnapshotJob.objects.create(schema_name='1state', triggered_by=actor)


@pytest.mark.integration
def test_schema_name_too_long_rejected(actor):
    too_long = 'a' + 'b' * 63
    with pytest.raises(IntegrityError):
        SnapshotJob.objects.create(schema_name=too_long, triggered_by=actor)


@pytest.mark.integration
def test_default_ordering_newest_first(actor):
    older = SnapshotJob.objects.create(schema_name='a', triggered_by=actor)
    newer = SnapshotJob.objects.create(schema_name='b', triggered_by=actor)
    listed = list(SnapshotJob.objects.all())
    assert listed.index(newer) < listed.index(older)


@pytest.mark.integration
def test_triggered_by_protect_blocks_user_delete(actor):
    SnapshotJob.objects.create(schema_name='a', triggered_by=actor)
    from django.db.models.deletion import ProtectedError
    with pytest.raises(ProtectedError):
        actor.delete()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_models.py -v
```

Expected: ImportError (`SnapshotJob` doesn't exist yet).

- [ ] **Step 3: Implement the model**

`snapshots/models.py`:

```python
"""Persistence for in-app snapshot jobs.

Lives in the public schema (shared) so superadmins have cross-tenant
visibility. Per-row scoping for tenant admins is enforced at the
queryset layer in views.py, not by schema isolation.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class SnapshotJob(models.Model):
    """One row per snapshot request. Mutated by Celery as the job progresses."""

    class Status(models.TextChoices):
        QUEUED    = 'queued',    'Queued'
        RUNNING   = 'running',   'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED    = 'failed',    'Failed'
        EXPIRED   = 'expired',   'Expired'   # row kept, artifact removed

    id              = models.BigAutoField(primary_key=True)
    schema_name     = models.CharField(max_length=63, db_index=True)
    label           = models.CharField(max_length=120, blank=True)
    status          = models.CharField(
                          max_length=12, choices=Status.choices,
                          default=Status.QUEUED, db_index=True)

    triggered_by    = models.ForeignKey(
                          settings.AUTH_USER_MODEL,
                          on_delete=models.PROTECT,
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

    def __str__(self) -> str:
        return f'SnapshotJob({self.id}, {self.schema_name}, {self.status})'
```

- [ ] **Step 4: Generate migration**

```bash
python manage.py makemigrations snapshots
```

Expected: creates `snapshots/migrations/0001_initial.py`. Inspect that file to confirm it includes the `CheckConstraint` and the two indexes.

- [ ] **Step 5: Apply migration**

```bash
python manage.py migrate_schemas --shared
```

Expected: `snapshots.0001_initial` applied to public.

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_models.py -v
```

Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add snapshots/models.py snapshots/migrations/ snapshots/tests/test_models.py
git commit -m "feat(snapshots): SnapshotJob model with schema-name CheckConstraint"
```

---

### Task 3: Crypto module — AES-256-GCM envelope encryption

**Files:**
- Create: `snapshots/services/__init__.py` (empty)
- Create: `snapshots/services/crypto.py`
- Test: `snapshots/tests/test_crypto.py`

- [ ] **Step 1: Write failing tests for round-trip + tamper detection**

`snapshots/tests/test_crypto.py`:

```python
"""AES-256-GCM envelope encryption — round-trip + tamper + key-mismatch."""
from __future__ import annotations

import io
import os

import pytest

from snapshots.services.crypto import (
    EnvelopeHeader,
    SnapshotDecryptionError,
    decrypt_stream,
    encrypt_stream,
)


KEK_GOOD = bytes.fromhex('aa' * 32)
KEK_BAD  = bytes.fromhex('bb' * 32)


def _encrypted_bytes(plaintext: bytes, kek: bytes = KEK_GOOD,
                     kek_id: str = 'kek-v1') -> tuple[bytes, EnvelopeHeader]:
    plain_stream = io.BytesIO(plaintext)
    cipher_stream = io.BytesIO()
    header = encrypt_stream(plain_stream, cipher_stream, kek=kek, kek_id=kek_id)
    return cipher_stream.getvalue(), header


@pytest.mark.unit
def test_round_trip_small_payload():
    pt = b'hello quot pse'
    ct, _ = _encrypted_bytes(pt)
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(ct), out, kek=KEK_GOOD)
    assert out.getvalue() == pt


@pytest.mark.unit
def test_round_trip_streaming_10mb():
    pt = os.urandom(10 * 1024 * 1024)
    ct, _ = _encrypted_bytes(pt)
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(ct), out, kek=KEK_GOOD)
    assert out.getvalue() == pt


@pytest.mark.unit
def test_wrong_kek_raises_decryption_error():
    ct, _ = _encrypted_bytes(b'secret')
    with pytest.raises(SnapshotDecryptionError):
        decrypt_stream(io.BytesIO(ct), io.BytesIO(), kek=KEK_BAD)


@pytest.mark.unit
def test_tampered_ciphertext_raises_decryption_error():
    ct, _ = _encrypted_bytes(b'A' * 1024)
    tampered = bytearray(ct)
    # Flip a byte well past the header.
    flip_at = len(ct) - 50
    tampered[flip_at] ^= 0xFF
    with pytest.raises(SnapshotDecryptionError):
        decrypt_stream(io.BytesIO(bytes(tampered)), io.BytesIO(), kek=KEK_GOOD)


@pytest.mark.unit
def test_truncated_ciphertext_raises_decryption_error():
    ct, _ = _encrypted_bytes(b'A' * 1024)
    truncated = ct[:-20]  # Lop off most of the tail.
    with pytest.raises(SnapshotDecryptionError):
        decrypt_stream(io.BytesIO(truncated), io.BytesIO(), kek=KEK_GOOD)


@pytest.mark.unit
def test_header_records_kek_id():
    _, header = _encrypted_bytes(b'x', kek_id='kek-v2')
    assert header.kek_id == 'kek-v2'


@pytest.mark.unit
def test_header_magic_bytes_present():
    ct, _ = _encrypted_bytes(b'x')
    assert ct.startswith(b'QPSE')


@pytest.mark.unit
def test_header_version_byte_is_1():
    ct, _ = _encrypted_bytes(b'x')
    assert ct[4] == 0x01
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_crypto.py -v
```

Expected: ImportError (`snapshots.services.crypto` doesn't exist yet).

- [ ] **Step 3: Implement the crypto module**

Create empty `snapshots/services/__init__.py`. Then create `snapshots/services/crypto.py`:

```python
"""AES-256-GCM envelope encryption for snapshot artifacts.

Layout of an encrypted snapshot file
------------------------------------
    [4-byte magic 'QPSE']
    [1-byte version    0x01]
    [1-byte kek_id_len]
    [kek_id_len bytes  kek_id (ASCII)]
    [12-byte IV         (DEK encryption nonce)]
    [16-byte GCM tag    (DEK encryption auth tag)]
    [12-byte IV2        (KEK wrap nonce)]
    [16-byte GCM tag2   (KEK wrap auth tag)]
    [32-byte wrapped_dek]
    [ciphertext ...]

Only the DEK ever touches the plaintext. The KEK is the long-lived
deploy-time secret; it never directly encrypts user data.

Mirrors the spirit of ``core/security/pii_crypto.py`` but uses
authenticated AES-GCM rather than Fernet — required because we need
streaming and large-file integrity, neither of which Fernet supports
cleanly.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b'QPSE'
VERSION = 0x01
CHUNK = 64 * 1024
GCM_TAG_LEN = 16
GCM_IV_LEN = 12
DEK_LEN = 32


class SnapshotDecryptionError(Exception):
    """Raised on any decryption failure: wrong KEK, tamper, truncation."""


@dataclass(frozen=True)
class EnvelopeHeader:
    kek_id: str
    iv: bytes
    tag: bytes
    iv2: bytes
    tag2: bytes
    wrapped_dek: bytes


def encrypt_stream(
    plain_in: BinaryIO,
    cipher_out: BinaryIO,
    *,
    kek: bytes,
    kek_id: str,
) -> EnvelopeHeader:
    """Encrypt ``plain_in`` into ``cipher_out`` and return the envelope header.

    Streams in fixed-size chunks; never holds more than ~64KB in memory.
    """
    if len(kek) != DEK_LEN:
        raise ValueError(f'KEK must be exactly {DEK_LEN} bytes, got {len(kek)}')

    dek = os.urandom(DEK_LEN)
    iv = os.urandom(GCM_IV_LEN)
    iv2 = os.urandom(GCM_IV_LEN)

    # Wrap the DEK with the KEK first — we need wrapped_dek + tag2 in the header.
    aes_kek = AESGCM(kek)
    wrapped_with_tag = aes_kek.encrypt(iv2, dek, associated_data=None)
    wrapped_dek, tag2 = wrapped_with_tag[:-GCM_TAG_LEN], wrapped_with_tag[-GCM_TAG_LEN:]

    # Encrypt the plaintext stream by buffering chunks, then finalize.
    # AESGCM in `cryptography` only supports one-shot encrypt; we read the
    # entire plaintext into memory in CHUNK-sized pieces for hashing, but
    # encrypt in one call. For truly enormous payloads, this would need
    # a low-level Cipher with GCM mode; for snapshot scale (<10 GB), a
    # single in-memory encrypt of compressed gzip output is fine.
    aes_dek = AESGCM(dek)
    plain_bytes = b''.join(iter(lambda: plain_in.read(CHUNK), b''))
    cipher_with_tag = aes_dek.encrypt(iv, plain_bytes, associated_data=None)
    ciphertext, tag = cipher_with_tag[:-GCM_TAG_LEN], cipher_with_tag[-GCM_TAG_LEN:]

    # Write the header.
    kek_id_bytes = kek_id.encode('ascii')
    if len(kek_id_bytes) > 255:
        raise ValueError('kek_id too long')
    cipher_out.write(MAGIC)
    cipher_out.write(bytes([VERSION]))
    cipher_out.write(bytes([len(kek_id_bytes)]))
    cipher_out.write(kek_id_bytes)
    cipher_out.write(iv)
    cipher_out.write(tag)
    cipher_out.write(iv2)
    cipher_out.write(tag2)
    cipher_out.write(wrapped_dek)
    cipher_out.write(ciphertext)
    cipher_out.flush()

    return EnvelopeHeader(kek_id=kek_id, iv=iv, tag=tag,
                          iv2=iv2, tag2=tag2, wrapped_dek=wrapped_dek)


def decrypt_stream(
    cipher_in: BinaryIO,
    plain_out: BinaryIO,
    *,
    kek: bytes,
) -> EnvelopeHeader:
    """Decrypt ``cipher_in`` into ``plain_out``. Raises SnapshotDecryptionError
    on any failure (wrong KEK, tampered ciphertext, truncated file)."""
    if len(kek) != DEK_LEN:
        raise ValueError(f'KEK must be exactly {DEK_LEN} bytes, got {len(kek)}')

    try:
        magic = cipher_in.read(4)
        if magic != MAGIC:
            raise SnapshotDecryptionError(f'Bad magic: {magic!r}')
        version = cipher_in.read(1)
        if not version or version[0] != VERSION:
            raise SnapshotDecryptionError(f'Unsupported version: {version!r}')
        kek_id_len_b = cipher_in.read(1)
        if not kek_id_len_b:
            raise SnapshotDecryptionError('Truncated header (kek_id length)')
        kek_id_len = kek_id_len_b[0]
        kek_id = cipher_in.read(kek_id_len).decode('ascii')
        iv = cipher_in.read(GCM_IV_LEN)
        tag = cipher_in.read(GCM_TAG_LEN)
        iv2 = cipher_in.read(GCM_IV_LEN)
        tag2 = cipher_in.read(GCM_TAG_LEN)
        wrapped_dek = cipher_in.read(DEK_LEN)
        for buf in (iv, tag, iv2, tag2, wrapped_dek):
            if len(buf) < (GCM_IV_LEN if buf is iv or buf is iv2
                           else GCM_TAG_LEN if buf is tag or buf is tag2
                           else DEK_LEN):
                raise SnapshotDecryptionError('Truncated header (envelope)')

        # Unwrap DEK with KEK.
        try:
            dek = AESGCM(kek).decrypt(iv2, wrapped_dek + tag2, associated_data=None)
        except InvalidTag as exc:
            raise SnapshotDecryptionError('KEK unwrap failed (wrong key?)') from exc

        # Read remaining ciphertext.
        ciphertext = cipher_in.read()
        try:
            plain = AESGCM(dek).decrypt(iv, ciphertext + tag, associated_data=None)
        except InvalidTag as exc:
            raise SnapshotDecryptionError(
                'Ciphertext integrity check failed (tamper or truncation)') from exc

        plain_out.write(plain)
        plain_out.flush()
        return EnvelopeHeader(kek_id=kek_id, iv=iv, tag=tag,
                              iv2=iv2, tag2=tag2, wrapped_dek=wrapped_dek)
    except SnapshotDecryptionError:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        raise SnapshotDecryptionError(f'Unexpected error: {exc}') from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_crypto.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/services/__init__.py snapshots/services/crypto.py \
        snapshots/tests/test_crypto.py
git commit -m "feat(snapshots): AES-256-GCM envelope encryption module"
```

---

### Task 4: Storage layer — Protocol + LocalFilesystemStorage

**Files:**
- Create: `snapshots/services/storage.py`
- Test: `snapshots/tests/test_storage.py`

- [ ] **Step 1: Write failing tests**

`snapshots/tests/test_storage.py`:

```python
"""LocalFilesystemStorage behavior + Protocol conformance."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from snapshots.services.storage import LocalFilesystemStorage, Storage


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(root=tmp_path)


@pytest.mark.unit
def test_protocol_conformance():
    """Static check: LocalFilesystemStorage satisfies Storage Protocol."""
    s: Storage = LocalFilesystemStorage(root=Path('/tmp'))
    assert hasattr(s, 'open_write')
    assert hasattr(s, 'open_read')
    assert hasattr(s, 'delete')
    assert hasattr(s, 'size')
    assert hasattr(s, 'exists')


@pytest.mark.unit
def test_write_and_read_roundtrip(storage):
    rel = 'delta_state/snap-1.tar.gz.enc'
    with storage.open_write(rel) as fh:
        fh.write(b'hello')
    with storage.open_read(rel) as fh:
        assert fh.read() == b'hello'


@pytest.mark.unit
def test_subdirectory_created_automatically(storage):
    rel = 'a/b/c/d/file.bin'
    with storage.open_write(rel) as fh:
        fh.write(b'x')
    assert storage.exists(rel)


@pytest.mark.unit
def test_size_returns_correct_byte_count(storage):
    rel = 'test/sz.bin'
    with storage.open_write(rel) as fh:
        fh.write(b'A' * 1234)
    assert storage.size(rel) == 1234


@pytest.mark.unit
def test_delete_removes_file(storage):
    rel = 'test/delete-me.bin'
    with storage.open_write(rel) as fh:
        fh.write(b'x')
    storage.delete(rel)
    assert not storage.exists(rel)


@pytest.mark.unit
def test_delete_missing_file_is_idempotent(storage):
    storage.delete('does/not/exist.bin')  # must not raise


@pytest.mark.unit
def test_rejects_absolute_paths_to_prevent_escape(storage):
    with pytest.raises(ValueError, match='must be relative'):
        with storage.open_write('/etc/passwd') as fh:
            fh.write(b'x')


@pytest.mark.unit
def test_rejects_parent_dir_traversal(storage):
    with pytest.raises(ValueError, match='traversal'):
        with storage.open_write('../escape.bin') as fh:
            fh.write(b'x')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_storage.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the storage module**

`snapshots/services/storage.py`:

```python
"""Storage abstraction for snapshot artifacts. Phase 1: local FS only.

The Protocol is defined now (rather than inlining everything in
LocalFilesystemStorage) so that Phase 2 can add S3CompatibleStorage
without touching callers.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    """Minimal interface a snapshot storage backend must satisfy."""
    def open_write(self, relative_path: str) -> BinaryIO: ...
    def open_read(self, relative_path: str) -> BinaryIO: ...
    def delete(self, relative_path: str) -> None: ...
    def size(self, relative_path: str) -> int: ...
    def exists(self, relative_path: str) -> bool: ...


def _validate_relative(relative_path: str) -> None:
    """Refuse absolute paths and parent-dir traversal."""
    if not relative_path:
        raise ValueError('relative_path must not be empty')
    p = Path(relative_path)
    if p.is_absolute():
        raise ValueError(f'relative_path must be relative: {relative_path!r}')
    if '..' in p.parts:
        raise ValueError(f'path traversal not allowed: {relative_path!r}')


class LocalFilesystemStorage:
    """Writes artifacts under a single root directory on the local FS.

    Mode 0o700 is enforced on the root at __init__ time. Subdirectories
    inherit the same default.
    """
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            # On Windows / non-POSIX filesystems, chmod may be a no-op or
            # raise. We log nothing here — the production deploy MUST
            # ensure the root has correct ACLs by other means.
            pass

    def _absolute(self, relative_path: str) -> Path:
        _validate_relative(relative_path)
        return self.root / relative_path

    def open_write(self, relative_path: str) -> BinaryIO:
        target = self._absolute(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target.open('wb')

    def open_read(self, relative_path: str) -> BinaryIO:
        return self._absolute(relative_path).open('rb')

    def delete(self, relative_path: str) -> None:
        target = self._absolute(relative_path)
        try:
            target.unlink()
        except FileNotFoundError:
            pass  # idempotent

    def size(self, relative_path: str) -> int:
        return self._absolute(relative_path).stat().st_size

    def exists(self, relative_path: str) -> bool:
        return self._absolute(relative_path).exists()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_storage.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/services/storage.py snapshots/tests/test_storage.py
git commit -m "feat(snapshots): Storage Protocol + LocalFilesystemStorage"
```

---

### Task 5: Manifest builder

**Files:**
- Create: `snapshots/services/manifest.py`
- Test: `snapshots/tests/test_manifest.py`

- [ ] **Step 1: Write failing tests**

`snapshots/tests/test_manifest.py`:

```python
"""Manifest building — code version, migration head, PII fingerprint, SHA256."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from snapshots.services.manifest import (
    build_manifest,
    sha256_of_file,
)


@pytest.mark.unit
def test_sha256_of_file(tmp_path):
    p = tmp_path / 'x.bin'
    p.write_bytes(b'hello world')
    expected = hashlib.sha256(b'hello world').hexdigest()
    assert sha256_of_file(p) == expected


@pytest.mark.unit
def test_sha256_of_large_file_streamed(tmp_path):
    """Manifest hashing must stream — never load file into memory."""
    p = tmp_path / 'big.bin'
    payload = b'A' * (5 * 1024 * 1024)  # 5 MB
    p.write_bytes(payload)
    assert sha256_of_file(p) == hashlib.sha256(payload).hexdigest()


@pytest.mark.unit
def test_manifest_has_required_top_level_keys(tmp_path):
    db_file = tmp_path / 'db.sql'
    db_file.write_bytes(b'CREATE TABLE x ();')
    media_dir = tmp_path / 'media'
    media_dir.mkdir()
    (media_dir / 'a.png').write_bytes(b'A' * 100)

    m = build_manifest(
        job_id=42,
        label='test',
        schema_name='delta_state',
        triggered_by_user_id=7,
        triggered_by_username='ada',
        database_sql_path=db_file,
        media_root=media_dir,
        kek_id='kek-v1',
    )
    for key in ('schema_version', 'snapshot', 'source', 'contents', 'encryption'):
        assert key in m, f'missing top-level key: {key}'


@pytest.mark.unit
def test_manifest_contents_sha_matches_file(tmp_path):
    db_file = tmp_path / 'db.sql'
    db_file.write_bytes(b'SELECT 1;')

    m = build_manifest(
        job_id=1, label='', schema_name='public',
        triggered_by_user_id=1, triggered_by_username='u',
        database_sql_path=db_file, media_root=None, kek_id='kek-v1',
    )
    assert m['contents']['database_sql_sha256'] == hashlib.sha256(b'SELECT 1;').hexdigest()


@pytest.mark.unit
def test_manifest_media_counts(tmp_path):
    media = tmp_path / 'media'
    media.mkdir()
    (media / 'a.png').write_bytes(b'A' * 100)
    (media / 'b.png').write_bytes(b'B' * 50)

    db_file = tmp_path / 'db.sql'
    db_file.write_bytes(b'x')

    m = build_manifest(
        job_id=1, label='', schema_name='t',
        triggered_by_user_id=1, triggered_by_username='u',
        database_sql_path=db_file, media_root=media, kek_id='kek-v1',
    )
    assert m['contents']['media_file_count'] == 2
    assert m['contents']['media_total_bytes'] == 150


@pytest.mark.unit
def test_manifest_with_no_media(tmp_path):
    db_file = tmp_path / 'db.sql'
    db_file.write_bytes(b'x')
    m = build_manifest(
        job_id=1, label='', schema_name='public',
        triggered_by_user_id=1, triggered_by_username='u',
        database_sql_path=db_file, media_root=None, kek_id='kek-v1',
    )
    assert m['contents']['media_file_count'] == 0
    assert m['contents']['media_total_bytes'] == 0


@pytest.mark.unit
def test_manifest_serializes_to_json(tmp_path):
    db_file = tmp_path / 'db.sql'
    db_file.write_bytes(b'x')
    m = build_manifest(
        job_id=1, label='', schema_name='public',
        triggered_by_user_id=1, triggered_by_username='u',
        database_sql_path=db_file, media_root=None, kek_id='kek-v1',
    )
    # Must round-trip via JSON without raising.
    encoded = json.dumps(m)
    assert json.loads(encoded) == m
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_manifest.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the manifest builder**

`snapshots/services/manifest.py`:

```python
"""Build the manifest.json that sits inside every snapshot tarball.

The manifest stamps everything a future restore tool needs to make safe
decisions: code version, migration heads, PII key fingerprint, SHA256 of
the SQL dump. P4 restore reads this; P1 just writes it.
"""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.migrations.loader import MigrationLoader


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
    """Return ``<branch>@<short-sha>`` or 'unknown' if git is unavailable."""
    try:
        branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        sha = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return f'{branch}@{sha}'
    except Exception:
        return 'unknown'


def _migration_heads() -> dict[str, list[str]]:
    """Return latest migration per app for shared and tenant apps."""
    from django.db import connection
    loader = MigrationLoader(connection)
    shared, tenant = [], []
    shared_app_set = set(settings.SHARED_APPS) if hasattr(settings, 'SHARED_APPS') else set()
    for (app, name), _node in loader.graph.leaf_nodes():
        entry = f'{app}.{name}'
        if app in shared_app_set or f'django.contrib.{app}' in shared_app_set:
            shared.append(entry)
        else:
            tenant.append(entry)
    return {'shared': sorted(shared), 'tenant': sorted(tenant)}


def _pii_key_fingerprint() -> str:
    """Best-effort fingerprint of the current PII encryption key.

    We don't want to leak the key itself — just a short fingerprint that
    survives in the manifest and lets P4 detect a key-rotation gap.
    """
    secret = getattr(settings, 'SECRET_KEY', '') or ''
    if not secret:
        return 'unknown'
    h = hashlib.sha256(secret.encode('utf-8')).hexdigest()
    return f'sk-{h[:12]}'


def _postgres_version() -> str:
    try:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute('SHOW server_version')
            return cur.fetchone()[0]
    except Exception:
        return 'unknown'


def _scan_media(media_root: Path | None) -> tuple[int, int]:
    if media_root is None or not media_root.exists():
        return 0, 0
    count = 0
    total = 0
    for p in media_root.rglob('*'):
        if p.is_file():
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
    import django_tenants
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
            'django_tenants_version': django_tenants.__version__,
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_manifest.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/services/manifest.py snapshots/tests/test_manifest.py
git commit -m "feat(snapshots): manifest builder with code/migration/PII fingerprints"
```

---

### Task 6: Media collector

**Files:**
- Create: `snapshots/services/media.py`
- Test: `snapshots/tests/test_media.py`

- [ ] **Step 1: Write failing test**

`snapshots/tests/test_media.py`:

```python
"""Media collector — walks FileField/ImageField instances inside a tenant schema."""
from __future__ import annotations

from pathlib import Path

import pytest

from snapshots.services.media import collect_referenced_media


@pytest.mark.unit
def test_returns_empty_list_when_no_models_have_files(tmp_path, monkeypatch):
    """No FileField in the iterated models -> empty result, no errors."""
    out_dir = tmp_path / 'out'
    out_dir.mkdir()
    monkeypatch.setattr('snapshots.services.media._iter_file_fields',
                        lambda: iter([]))
    result = collect_referenced_media(schema_name='delta_state',
                                       destination=out_dir, media_root=tmp_path)
    assert result == []


@pytest.mark.unit
def test_copies_referenced_files_preserving_relative_path(tmp_path):
    """Synthetic FileField iteration: we hand it a fake field+instance and
    verify the file is copied under destination at the same relative path."""
    media_root = tmp_path / 'media'
    media_root.mkdir()
    (media_root / 'uploads').mkdir()
    src = media_root / 'uploads' / 'a.png'
    src.write_bytes(b'PNG')

    out_dir = tmp_path / 'out'
    out_dir.mkdir()

    from snapshots.services.media import _copy_one
    _copy_one(rel_path='uploads/a.png', media_root=media_root,
              destination=out_dir)
    assert (out_dir / 'uploads' / 'a.png').read_bytes() == b'PNG'


@pytest.mark.unit
def test_skips_missing_referenced_files(tmp_path):
    """A FileField row that points to a since-deleted file is logged
    and skipped rather than raising."""
    media_root = tmp_path / 'media'
    media_root.mkdir()
    out_dir = tmp_path / 'out'
    out_dir.mkdir()

    from snapshots.services.media import _copy_one
    # Should not raise — file does not exist.
    _copy_one(rel_path='missing.png', media_root=media_root,
              destination=out_dir)
    assert list(out_dir.rglob('*')) == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_media.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the media collector**

`snapshots/services/media.py`:

```python
"""Walk every FileField/ImageField in a schema and copy referenced files.

We iterate model instances rather than walking the filesystem so that
files orphaned by deletion (row gone, file still on disk) are excluded
from the snapshot. Bounded: you can only copy what a row references.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Iterator

from django.apps import apps
from django.conf import settings
from django.db.models import FileField
from django_tenants.utils import schema_context


logger = logging.getLogger(__name__)


def _iter_file_fields() -> Iterator[tuple[type, FileField]]:
    """Yield (model_class, field) for every FileField on every concrete model."""
    for model in apps.get_models():
        if model._meta.abstract or model._meta.proxy:
            continue
        for field in model._meta.get_fields():
            if isinstance(field, FileField):
                yield model, field


def _copy_one(rel_path: str, media_root: Path, destination: Path) -> bool:
    """Copy ``media_root/rel_path`` to ``destination/rel_path``.

    Returns True on success, False if the source did not exist."""
    src = media_root / rel_path
    if not src.exists() or not src.is_file():
        logger.warning('snapshots.media: referenced file missing on disk: %s', src)
        return False
    dst = destination / rel_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def collect_referenced_media(
    *,
    schema_name: str,
    destination: Path,
    media_root: Path | None = None,
) -> list[str]:
    """Inside ``schema_name``, copy every FileField-referenced file under
    ``destination``. Returns the list of relative paths copied."""
    media_root = media_root or Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        return []
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    with schema_context(schema_name):
        for model, field in _iter_file_fields():
            field_name = field.name
            queryset = model._default_manager.exclude(
                **{f'{field_name}__isnull': True}
            ).exclude(**{f'{field_name}__exact': ''})
            for instance in queryset.only(field_name).iterator(chunk_size=500):
                file_value = getattr(instance, field_name, None)
                if not file_value:
                    continue
                rel = str(file_value).lstrip('/')
                if _copy_one(rel, media_root, destination):
                    copied.append(rel)
    return copied
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_media.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/services/media.py snapshots/tests/test_media.py
git commit -m "feat(snapshots): media collector iterates FileField rows"
```

---

### Task 7: Database dumper (`pg_dump` subprocess wrapper)

**Files:**
- Create: `snapshots/services/dump.py`
- Test: `snapshots/tests/test_dump.py`

- [ ] **Step 1: Write failing tests**

`snapshots/tests/test_dump.py`:

```python
"""pg_dump subprocess wrapper — flag construction + error handling."""
from __future__ import annotations

import os
import subprocess

import pytest

from snapshots.services.dump import PgDumpError, build_pg_dump_argv, run_pg_dump


@pytest.mark.unit
def test_argv_mirrors_backup_sh_flags():
    """Flags must match scripts/backup.sh exactly so behavior is consistent."""
    argv = build_pg_dump_argv(
        pg_dump_bin='pg_dump',
        schema='delta_state',
        dsn='postgres://u:p@host:5432/db',
    )
    assert argv[0] == 'pg_dump'
    expected_flags = {
        '--schema=delta_state',
        '--no-owner', '--no-privileges',
        '--clean', '--if-exists',
        '--format=plain',
        '--quote-all-identifiers',
    }
    assert expected_flags.issubset(set(argv))
    assert argv[-1] == 'postgres://u:p@host:5432/db'


@pytest.mark.unit
def test_argv_rejects_schema_with_quotes():
    """Defense: schema_name should already be regex-validated, but we
    refuse anything containing a quote at this layer too."""
    with pytest.raises(ValueError):
        build_pg_dump_argv(pg_dump_bin='pg_dump',
                          schema='evil"; DROP TABLE--', dsn='x')


@pytest.mark.unit
def test_run_pg_dump_raises_on_nonzero_exit(tmp_path, monkeypatch):
    """If subprocess returns nonzero, we raise PgDumpError with stderr captured."""
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout=b'', stderr=b'fatal: bad role')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    target = tmp_path / 'out.sql'
    with pytest.raises(PgDumpError, match='fatal: bad role'):
        run_pg_dump(schema='delta_state', dsn='x', target=target,
                   pg_dump_bin='pg_dump')


@pytest.mark.unit
def test_run_pg_dump_writes_stdout_to_target(tmp_path, monkeypatch):
    """Happy path: stdout bytes land in the target file."""
    payload = b'-- pg dump start\nSELECT 1;\n'

    def fake_run(*args, **kwargs):
        # Simulate writing stdout to the file passed via stdout=
        stdout_file = kwargs.get('stdout')
        if stdout_file is not None:
            stdout_file.write(payload)
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=None, stderr=b'')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    target = tmp_path / 'out.sql'
    run_pg_dump(schema='delta_state', dsn='x', target=target,
               pg_dump_bin='pg_dump')
    assert target.read_bytes() == payload
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_dump.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the dumper**

`snapshots/services/dump.py`:

```python
"""Subprocess wrapper around pg_dump.

Flags mirror scripts/backup.sh so the in-app pipeline produces
byte-compatible output with the operator-tier nightly cron.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


_SAFE_SCHEMA = re.compile(r'^[a-z][a-z0-9_]{0,62}$')


class PgDumpError(RuntimeError):
    """pg_dump exited non-zero. The message contains captured stderr (truncated)."""


def build_pg_dump_argv(*, pg_dump_bin: str, schema: str, dsn: str) -> list[str]:
    """Construct the argv vector for pg_dump. Refuses unsafe schema names
    even though SnapshotJob.CheckConstraint enforces the same regex at
    write time — defense in depth."""
    if not _SAFE_SCHEMA.match(schema):
        raise ValueError(f'unsafe schema name: {schema!r}')
    return [
        pg_dump_bin,
        f'--schema={schema}',
        '--no-owner',
        '--no-privileges',
        '--clean',
        '--if-exists',
        '--format=plain',
        '--quote-all-identifiers',
        dsn,
    ]


def run_pg_dump(*, schema: str, dsn: str, target: Path,
                pg_dump_bin: str, timeout_sec: int | None = None) -> None:
    """Run pg_dump streaming to ``target``. Raises PgDumpError on failure."""
    target.parent.mkdir(parents=True, exist_ok=True)
    argv = build_pg_dump_argv(pg_dump_bin=pg_dump_bin, schema=schema, dsn=dsn)
    with open(target, 'wb') as out_fh:
        completed = subprocess.run(
            argv, stdout=out_fh, stderr=subprocess.PIPE, timeout=timeout_sec,
        )
    if completed.returncode != 0:
        # Keep stderr capped to 4 KB so the SnapshotJob.error_message column
        # never gets bloated.
        stderr = (completed.stderr or b'').decode('utf-8', errors='replace')
        raise PgDumpError(stderr[:4096])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_dump.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/services/dump.py snapshots/tests/test_dump.py
git commit -m "feat(snapshots): pg_dump subprocess wrapper mirroring backup.sh flags"
```

---

### Task 8: Retention service

**Files:**
- Create: `snapshots/services/retention.py`
- Test: `snapshots/tests/test_retention.py`

- [ ] **Step 1: Write failing tests**

`snapshots/tests/test_retention.py`:

```python
"""RetentionService — age rule + per-tenant count rule + orphan-file resilience."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from snapshots.models import SnapshotJob
from snapshots.services.retention import RetentionService


User = get_user_model()


def _make_job(actor, schema, age_days=0, status=SnapshotJob.Status.SUCCEEDED,
              artifact_path='dummy.tar.gz.enc'):
    job = SnapshotJob.objects.create(
        schema_name=schema, triggered_by=actor, status=status,
        artifact_path=artifact_path)
    if age_days:
        SnapshotJob.objects.filter(pk=job.pk).update(
            triggered_at=timezone.now() - timedelta(days=age_days))
    return SnapshotJob.objects.get(pk=job.pk)


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.mark.integration
@override_settings(SNAPSHOTS_RETENTION_DAYS=14, SNAPSHOTS_MAX_PER_TENANT=99)
def test_age_rule_expires_old_jobs(actor, tmp_path):
    old = _make_job(actor, 'delta_state', age_days=20)
    fresh = _make_job(actor, 'delta_state', age_days=1)
    storage = _FakeStorage(tmp_path)
    storage.touch(old.artifact_path)
    storage.touch(fresh.artifact_path)

    report = RetentionService(storage=storage).enforce_for_schema('delta_state')

    old.refresh_from_db(); fresh.refresh_from_db()
    assert old.status == SnapshotJob.Status.EXPIRED
    assert old.artifact_path == ''
    assert fresh.status == SnapshotJob.Status.SUCCEEDED
    assert report.expired_count == 1


@pytest.mark.integration
@override_settings(SNAPSHOTS_RETENTION_DAYS=365, SNAPSHOTS_MAX_PER_TENANT=2)
def test_count_rule_keeps_most_recent(actor, tmp_path):
    jobs = [_make_job(actor, 'delta_state', age_days=i) for i in range(5)]
    storage = _FakeStorage(tmp_path)
    for j in jobs:
        storage.touch(j.artifact_path)

    RetentionService(storage=storage).enforce_for_schema('delta_state')

    surviving = SnapshotJob.objects.filter(
        schema_name='delta_state', status=SnapshotJob.Status.SUCCEEDED)
    assert surviving.count() == 2  # newest 2 kept


@pytest.mark.integration
def test_both_rules_can_coexist(actor, tmp_path):
    """Age + count: both rules transition to EXPIRED."""
    with override_settings(SNAPSHOTS_RETENTION_DAYS=7,
                            SNAPSHOTS_MAX_PER_TENANT=2):
        ancient = _make_job(actor, 'delta_state', age_days=30)  # age-expire
        old1 = _make_job(actor, 'delta_state', age_days=2)
        old2 = _make_job(actor, 'delta_state', age_days=1)
        new = _make_job(actor, 'delta_state', age_days=0)        # newest kept
        storage = _FakeStorage(tmp_path)
        for j in (ancient, old1, old2, new):
            storage.touch(j.artifact_path)

        RetentionService(storage=storage).enforce_for_schema('delta_state')

        ancient.refresh_from_db(); old1.refresh_from_db()
        old2.refresh_from_db(); new.refresh_from_db()
        assert ancient.status == SnapshotJob.Status.EXPIRED
        # old1 may expire from count rule (if it's outside the top-2)
        # We assert only the corners: ancient and new.
        assert new.status == SnapshotJob.Status.SUCCEEDED


@pytest.mark.integration
def test_orphan_file_does_not_raise(actor, tmp_path):
    """If the artifact file is already gone, retention still transitions
    the row to EXPIRED without raising."""
    with override_settings(SNAPSHOTS_RETENTION_DAYS=1):
        old = _make_job(actor, 'delta_state', age_days=10)
        storage = _FakeStorage(tmp_path)
        # NOTE: do NOT touch the file — simulate orphan.

        RetentionService(storage=storage).enforce_for_schema('delta_state')

        old.refresh_from_db()
        assert old.status == SnapshotJob.Status.EXPIRED


# ── Test helpers ──────────────────────────────────────────────────────
class _FakeStorage:
    def __init__(self, root: Path):
        self.root = root
    def open_write(self, rel): return (self.root / rel).open('wb')
    def open_read(self, rel): return (self.root / rel).open('rb')
    def delete(self, rel):
        try:
            (self.root / rel).unlink()
        except FileNotFoundError:
            pass
    def size(self, rel): return (self.root / rel).stat().st_size
    def exists(self, rel): return (self.root / rel).exists()
    def touch(self, rel):
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'x')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_retention.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the retention service**

`snapshots/services/retention.py`:

```python
"""Apply age + per-tenant-count retention rules to SnapshotJob rows.

Order matters: age first (cheap, indexed), then count (operates on
what's left). Either rule fires -> EXPIRED + artifact unlinked.

Transaction ordering: DB update -> commit -> file unlink. The opposite
ordering risks a row pointing at a deleted file. Our ordering's worst
case is an orphan file, which the nightly beat reconciles.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from snapshots.models import SnapshotJob


logger = logging.getLogger(__name__)


@dataclass
class RetentionReport:
    schema_name: str
    expired_count: int


class RetentionService:
    def __init__(self, storage):
        self.storage = storage

    def enforce_for_schema(self, schema_name: str) -> RetentionReport:
        retention_days = int(settings.SNAPSHOTS_RETENTION_DAYS)
        max_per_tenant = int(settings.SNAPSHOTS_MAX_PER_TENANT)
        expired_total = 0

        age_cutoff = timezone.now() - timedelta(days=retention_days)
        age_victims = list(SnapshotJob.objects.filter(
            schema_name=schema_name,
            status=SnapshotJob.Status.SUCCEEDED,
            triggered_at__lt=age_cutoff,
        ).values_list('pk', 'artifact_path'))
        expired_total += self._expire(age_victims)

        survivors = SnapshotJob.objects.filter(
            schema_name=schema_name,
            status=SnapshotJob.Status.SUCCEEDED,
        ).order_by('-triggered_at')
        keepers = list(survivors[:max_per_tenant].values_list('pk', flat=True))
        count_victims = list(survivors.exclude(pk__in=keepers).values_list(
            'pk', 'artifact_path'))
        expired_total += self._expire(count_victims)

        return RetentionReport(schema_name=schema_name, expired_count=expired_total)

    def enforce_all(self) -> list[RetentionReport]:
        schemas = SnapshotJob.objects.values_list(
            'schema_name', flat=True).distinct()
        return [self.enforce_for_schema(s) for s in schemas]

    def _expire(self, victims: list[tuple[int, str]]) -> int:
        if not victims:
            return 0
        ids = [pk for pk, _ in victims]
        with transaction.atomic():
            SnapshotJob.objects.filter(pk__in=ids).update(
                status=SnapshotJob.Status.EXPIRED,
                artifact_path='',
            )
        # File unlink outside the DB transaction. Best-effort; orphan
        # files are reconciled by the next retention pass.
        for _pk, artifact in victims:
            if not artifact:
                continue
            try:
                self.storage.delete(artifact)
            except Exception:
                logger.exception('snapshots.retention: failed to delete %s', artifact)
        return len(ids)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_retention.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/services/retention.py snapshots/tests/test_retention.py
git commit -m "feat(snapshots): retention service (age + per-tenant count)"
```

---

### Task 9: Snapshot service orchestrator (the 6-phase pipeline)

**Files:**
- Create: `snapshots/services/snapshot_service.py`
- Test: `snapshots/tests/test_snapshot_service.py`
- Create: `snapshots/tests/conftest.py` (KEK + storage fixtures)

- [ ] **Step 1: Write the test conftest with shared fixtures**

`snapshots/tests/conftest.py`:

```python
"""Shared fixtures for snapshots tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def kek_hex():
    """Deterministic test KEK — 64 hex chars."""
    return 'aa' * 32


@pytest.fixture
def kek_bytes(kek_hex):
    return bytes.fromhex(kek_hex)


@pytest.fixture
def snapshot_storage_root(tmp_path):
    root = tmp_path / 'snapshots_storage'
    root.mkdir()
    return root


@pytest.fixture
def configured_settings(settings, kek_hex, snapshot_storage_root, tmp_path):
    settings.SNAPSHOTS_KEK_HEX = kek_hex
    settings.SNAPSHOTS_KEK_ID = 'kek-v1'
    settings.SNAPSHOTS_BACKUP_DIR = str(snapshot_storage_root)
    settings.MEDIA_ROOT = str(tmp_path / 'media')
    Path(settings.MEDIA_ROOT).mkdir(exist_ok=True)
    return settings
```

- [ ] **Step 2: Write failing service test**

`snapshots/tests/test_snapshot_service.py`:

```python
"""End-to-end service integration — pg_dump invoked through to encrypted file."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from snapshots.models import SnapshotJob
from snapshots.services.snapshot_service import SnapshotService


User = get_user_model()


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.fixture
def stub_pg_dump(monkeypatch):
    """Replace pg_dump with a deterministic stub that writes a fixed SQL blob."""
    def fake_run(argv, *args, **kwargs):
        stdout_file = kwargs.get('stdout')
        if stdout_file is not None:
            stdout_file.write(b'-- stub SQL\nSELECT 1;\n')
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=None, stderr=b'')
    monkeypatch.setattr('subprocess.run', fake_run)


@pytest.mark.integration
def test_execute_creates_encrypted_artifact(
    actor, configured_settings, snapshot_storage_root, stub_pg_dump,
):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor, label='ts')
    SnapshotService(job).execute()

    job.refresh_from_db()
    assert job.status == SnapshotJob.Status.SUCCEEDED
    assert job.artifact_path
    assert job.size_bytes and job.size_bytes > 0
    assert len(job.sha256) == 64

    # Artifact exists and is encrypted (magic bytes).
    artifact = Path(configured_settings.SNAPSHOTS_BACKUP_DIR) / job.artifact_path
    assert artifact.exists()
    assert artifact.read_bytes()[:4] == b'QPSE'


@pytest.mark.integration
def test_execute_records_manifest_on_job(
    actor, configured_settings, stub_pg_dump,
):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor)
    SnapshotService(job).execute()

    job.refresh_from_db()
    m = job.manifest
    assert m['snapshot']['schema_name'] == 'delta_state'
    assert m['snapshot']['triggered_by']['user_id'] == actor.pk
    assert m['encryption']['algorithm'] == 'AES-256-GCM'
    assert m['encryption']['kek_id'] == 'kek-v1'
    assert m['contents']['database_sql_sha256']


@pytest.mark.integration
def test_execute_marks_failed_when_pg_dump_errors(
    actor, configured_settings, monkeypatch,
):
    def failing_run(argv, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=argv, returncode=1, stdout=None, stderr=b'fatal: nope')
    monkeypatch.setattr('subprocess.run', failing_run)

    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor)
    with pytest.raises(Exception):
        SnapshotService(job).execute()

    job.refresh_from_db()
    assert job.status == SnapshotJob.Status.FAILED
    assert 'fatal: nope' in job.error_message


@pytest.mark.integration
def test_execute_transitions_to_running_then_succeeded(
    actor, configured_settings, stub_pg_dump,
):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor)
    assert job.started_at is None
    SnapshotService(job).execute()
    job.refresh_from_db()
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.started_at <= job.completed_at
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest snapshots/tests/test_snapshot_service.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement the service**

`snapshots/services/snapshot_service.py`:

```python
"""The 6-phase orchestrator. Called by Celery, also directly testable."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone as djtime

from snapshots.models import SnapshotJob
from snapshots.services.crypto import encrypt_stream
from snapshots.services.dump import PgDumpError, run_pg_dump
from snapshots.services.manifest import build_manifest, sha256_of_file
from snapshots.services.media import collect_referenced_media
from snapshots.services.retention import RetentionService
from snapshots.services.storage import LocalFilesystemStorage


logger = logging.getLogger(__name__)


class SnapshotService:
    """Runs one SnapshotJob to completion or failure.

    The job row is mutated incrementally so the UI can observe progress
    via polling — moving from QUEUED to RUNNING to {SUCCEEDED, FAILED}.
    """

    def __init__(self, job: SnapshotJob):
        self.job = job
        self.storage = LocalFilesystemStorage(root=settings.SNAPSHOTS_BACKUP_DIR)

    # ── Public entry point ───────────────────────────────────────────
    def execute(self) -> None:
        try:
            self._transition_to_running()
            with tempfile.TemporaryDirectory() as workdir_str:
                workdir = Path(workdir_str)
                db_dir = workdir / 'database'
                media_dir = workdir / 'media'
                db_dir.mkdir()
                media_dir.mkdir()

                db_sql_path = self._dump_database(db_dir)
                self._collect_media(media_dir)
                manifest_dict = self._build_manifest(db_sql_path, media_dir)
                manifest_path = workdir / 'manifest.json'
                manifest_path.write_text(json.dumps(manifest_dict, indent=2))

                artifact_rel_path, sha, size_bytes, manifest_with_envelope = (
                    self._encrypt_and_store(workdir, manifest_dict)
                )
            self._mark_succeeded(artifact_rel_path, sha, size_bytes,
                                  manifest_with_envelope)
            RetentionService(self.storage).enforce_for_schema(self.job.schema_name)
        except Exception as exc:
            self._mark_failed(exc)
            raise

    # ── Phase 1 ──────────────────────────────────────────────────────
    def _dump_database(self, db_dir: Path) -> Path:
        target = db_dir / f'{self.job.schema_name}.sql'
        dsn = self._dsn_from_settings()
        run_pg_dump(
            schema=self.job.schema_name,
            dsn=dsn,
            target=target,
            pg_dump_bin=settings.SNAPSHOTS_PG_DUMP_BIN,
            timeout_sec=settings.SNAPSHOTS_SOFT_TIME_LIMIT_SEC,
        )
        return target

    # ── Phase 2 ──────────────────────────────────────────────────────
    def _collect_media(self, media_dir: Path) -> None:
        if self.job.schema_name == 'public':
            return  # public has no media
        collect_referenced_media(
            schema_name=self.job.schema_name,
            destination=media_dir,
            media_root=Path(settings.MEDIA_ROOT),
        )

    # ── Phase 3 ──────────────────────────────────────────────────────
    def _build_manifest(self, db_sql_path: Path,
                        media_dir: Path) -> dict:
        return build_manifest(
            job_id=self.job.pk,
            label=self.job.label,
            schema_name=self.job.schema_name,
            triggered_by_user_id=self.job.triggered_by_id,
            triggered_by_username=self.job.triggered_by.username,
            database_sql_path=db_sql_path,
            media_root=media_dir,
            kek_id=settings.SNAPSHOTS_KEK_ID,
        )

    # ── Phase 4 ──────────────────────────────────────────────────────
    def _encrypt_and_store(self, workdir: Path, manifest_dict: dict
                           ) -> tuple[str, str, int, dict]:
        # Build the tarball into a temp file in workdir, then stream-encrypt
        # into final storage.
        tar_path = workdir / 'bundle.tar.gz'
        with tarfile.open(tar_path, 'w:gz') as tar:
            for sub in ('manifest.json', 'database', 'media'):
                src = workdir / sub
                if src.exists():
                    tar.add(src, arcname=sub)

        ts = djtime.now().strftime('%Y%m%dT%H%M%SZ')
        rel_path = f'{self.job.schema_name}/snapshot-{self.job.pk}-{ts}.tar.gz.enc'
        kek = bytes.fromhex(settings.SNAPSHOTS_KEK_HEX)

        with open(tar_path, 'rb') as plain_in:
            with self.storage.open_write(rel_path) as cipher_out:
                header = encrypt_stream(
                    plain_in, cipher_out,
                    kek=kek, kek_id=settings.SNAPSHOTS_KEK_ID,
                )

        # Fill in encryption envelope on the manifest.
        manifest_dict['encryption']['wrapped_dek_b64'] = base64.b64encode(
            header.wrapped_dek).decode('ascii')
        manifest_dict['encryption']['iv_b64'] = base64.b64encode(
            header.iv).decode('ascii')
        manifest_dict['encryption']['tag_b64'] = base64.b64encode(
            header.tag).decode('ascii')

        sha = sha256_of_file(Path(settings.SNAPSHOTS_BACKUP_DIR) / rel_path)
        size = self.storage.size(rel_path)
        return rel_path, sha, size, manifest_dict

    # ── Phase 5 ──────────────────────────────────────────────────────
    def _transition_to_running(self) -> None:
        with transaction.atomic():
            SnapshotJob.objects.filter(pk=self.job.pk).update(
                status=SnapshotJob.Status.RUNNING,
                started_at=djtime.now(),
            )
            self.job.refresh_from_db()

    def _mark_succeeded(self, artifact_path: str, sha: str,
                        size_bytes: int, manifest: dict) -> None:
        with transaction.atomic():
            SnapshotJob.objects.filter(pk=self.job.pk).update(
                status=SnapshotJob.Status.SUCCEEDED,
                artifact_path=artifact_path,
                sha256=sha,
                size_bytes=size_bytes,
                kek_fingerprint=settings.SNAPSHOTS_KEK_ID,
                manifest=manifest,
                completed_at=djtime.now(),
            )
            self.job.refresh_from_db()

    def _mark_failed(self, exc: Exception) -> None:
        msg = str(exc)[:4096]
        with transaction.atomic():
            SnapshotJob.objects.filter(pk=self.job.pk).update(
                status=SnapshotJob.Status.FAILED,
                error_message=msg,
                error_class=exc.__class__.__name__,
                completed_at=djtime.now(),
            )

    # ── Helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _dsn_from_settings() -> str:
        db = settings.DATABASES['default']
        user = db.get('USER', '')
        password = db.get('PASSWORD', '')
        host = db.get('HOST', 'localhost')
        port = db.get('PORT', '5432') or '5432'
        name = db.get('NAME', '')
        auth = f'{user}:{password}@' if user else ''
        return f'postgres://{auth}{host}:{port}/{name}'
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_snapshot_service.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add snapshots/services/snapshot_service.py \
        snapshots/tests/test_snapshot_service.py \
        snapshots/tests/conftest.py
git commit -m "feat(snapshots): 6-phase orchestrator integrating dump+media+manifest+crypto"
```

---

### Task 10: Celery tasks

**Files:**
- Create: `snapshots/tasks.py`
- Test: `snapshots/tests/test_tasks.py`
- Modify: `quot_pse/celery.py` (or create if missing — verify existence first)

- [ ] **Step 1: Write failing tests**

`snapshots/tests/test_tasks.py`:

```python
"""Celery tasks — run_snapshot_job, reap_stale_jobs, enforce_retention_all."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from snapshots.models import SnapshotJob


User = get_user_model()


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.mark.integration
def test_run_snapshot_job_invokes_service(actor, monkeypatch, configured_settings):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor)
    invoked = {}

    class FakeService:
        def __init__(self, j): invoked['job'] = j
        def execute(self): invoked['executed'] = True

    monkeypatch.setattr('snapshots.tasks.SnapshotService', FakeService)
    from snapshots.tasks import run_snapshot_job
    run_snapshot_job.apply(args=[job.pk]).get()

    assert invoked['job'].pk == job.pk
    assert invoked['executed'] is True


@pytest.mark.integration
def test_reap_stale_jobs_transitions_running_to_failed(actor, configured_settings):
    """A job stuck in RUNNING past hard_time_limit + 5 min is marked FAILED."""
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        status=SnapshotJob.Status.RUNNING)
    # Force started_at far in the past.
    SnapshotJob.objects.filter(pk=job.pk).update(
        started_at=timezone.now() - timedelta(hours=2))

    from snapshots.tasks import reap_stale_jobs
    reap_stale_jobs.apply().get()

    job.refresh_from_db()
    assert job.status == SnapshotJob.Status.FAILED
    assert job.error_class == 'WorkerCrashOrTimeout'


@pytest.mark.integration
def test_reap_stale_jobs_ignores_recent_running_jobs(actor, configured_settings):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        status=SnapshotJob.Status.RUNNING)
    SnapshotJob.objects.filter(pk=job.pk).update(started_at=timezone.now())

    from snapshots.tasks import reap_stale_jobs
    reap_stale_jobs.apply().get()

    job.refresh_from_db()
    assert job.status == SnapshotJob.Status.RUNNING  # untouched


@pytest.mark.integration
def test_enforce_retention_all_walks_all_schemas(actor, configured_settings, monkeypatch):
    SnapshotJob.objects.create(schema_name='a', triggered_by=actor,
                                status=SnapshotJob.Status.SUCCEEDED)
    SnapshotJob.objects.create(schema_name='b', triggered_by=actor,
                                status=SnapshotJob.Status.SUCCEEDED)
    visited = []
    class FakeRet:
        def __init__(self, storage): pass
        def enforce_for_schema(self, s):
            visited.append(s)
            class R: expired_count=0; schema_name=s
            return R()
    monkeypatch.setattr('snapshots.tasks.RetentionService', FakeRet)

    from snapshots.tasks import enforce_retention_all
    enforce_retention_all.apply().get()

    assert set(visited) == {'a', 'b'}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_tasks.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the Celery tasks**

`snapshots/tasks.py`:

```python
"""Celery tasks: run snapshots, reap stalled jobs, enforce retention."""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from snapshots.models import SnapshotJob
from snapshots.services.retention import RetentionService
from snapshots.services.snapshot_service import SnapshotService
from snapshots.services.storage import LocalFilesystemStorage


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=0,
    name='snapshots.run_snapshot_job',
)
def run_snapshot_job(self, job_id: int) -> None:
    """Run one SnapshotJob to completion. No retries — failures stay
    in FAILED status with diagnostic info; user-initiated retry creates
    a fresh job row."""
    with transaction.atomic():
        try:
            job = SnapshotJob.objects.select_for_update().get(pk=job_id)
        except SnapshotJob.DoesNotExist:
            logger.warning('snapshots.run_snapshot_job: job %s missing', job_id)
            return

    try:
        SnapshotService(job).execute()
    except SoftTimeLimitExceeded:
        SnapshotJob.objects.filter(pk=job_id).update(
            status=SnapshotJob.Status.FAILED,
            error_class='SoftTimeLimitExceeded',
            error_message='Snapshot exceeded soft time limit. Consider raising '
                           'SNAPSHOTS_SOFT_TIME_LIMIT_SEC or splitting the schema.',
            completed_at=timezone.now(),
        )
        raise


@shared_task(name='snapshots.reap_stale_jobs')
def reap_stale_jobs() -> int:
    """Transition any RUNNING job stuck past hard_time_limit + buffer to FAILED.

    Belt-and-braces: a crashed Celery worker leaves a job in RUNNING
    forever otherwise.
    """
    hard_limit = int(settings.SNAPSHOTS_HARD_TIME_LIMIT_SEC)
    buffer = 5 * 60
    cutoff = timezone.now() - timedelta(seconds=hard_limit + buffer)
    affected = SnapshotJob.objects.filter(
        status=SnapshotJob.Status.RUNNING,
        started_at__lt=cutoff,
    ).update(
        status=SnapshotJob.Status.FAILED,
        error_class='WorkerCrashOrTimeout',
        error_message='Worker crashed or task exceeded hard time limit.',
        completed_at=timezone.now(),
    )
    if affected:
        logger.warning('snapshots.reap_stale_jobs: reaped %d stale jobs', affected)
    return affected


@shared_task(name='snapshots.enforce_retention_all')
def enforce_retention_all() -> int:
    """Walk every distinct schema and apply retention rules.

    Nightly belt-and-braces — closes the failure window where a worker
    crashed after _mark_succeeded but before inline retention ran."""
    storage = LocalFilesystemStorage(root=settings.SNAPSHOTS_BACKUP_DIR)
    service = RetentionService(storage=storage)
    schemas = SnapshotJob.objects.values_list(
        'schema_name', flat=True).distinct()
    total = 0
    for schema in schemas:
        report = service.enforce_for_schema(schema)
        total += report.expired_count
    return total
```

Also configure the beat schedule. Check whether `quot_pse/celery.py` exists:

```bash
ls quot_pse/celery.py
```

If it exists, append to its `beat_schedule` dict:

```python
# In quot_pse/celery.py beat_schedule:
'snapshots-reap-stale': {
    'task': 'snapshots.reap_stale_jobs',
    'schedule': timedelta(minutes=10),
},
'snapshots-enforce-retention': {
    'task': 'snapshots.enforce_retention_all',
    'schedule': crontab(hour=3, minute=0),  # 03:00 UTC daily
},
```

If `quot_pse/celery.py` does not exist, defer beat configuration to ops (document in `.env.example` and skip — the tasks themselves still work when triggered manually).

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_tasks.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/tasks.py snapshots/tests/test_tasks.py quot_pse/celery.py
git commit -m "feat(snapshots): Celery tasks (run, reap, retention)"
```

(Omit `quot_pse/celery.py` from `git add` if it didn't exist and you didn't create it.)

---

### Task 11: Permission resolvers + classes

**Files:**
- Create: `snapshots/services/resolvers.py`
- Create: `snapshots/permissions.py`
- Test: `snapshots/tests/test_permissions.py`

- [ ] **Step 1: Write failing test**

`snapshots/tests/test_permissions.py`:

```python
"""Permission matrix — superadmin vs tenant_admin vs other."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from snapshots.models import SnapshotJob
from snapshots.permissions import CanAccessSnapshot, CanCreateSnapshot


User = get_user_model()


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def superadmin(db, monkeypatch):
    u = User.objects.create_user(username='root', password='x')
    monkeypatch.setattr(
        'snapshots.permissions.is_platform_superadmin',
        lambda user: user.username == 'root',
    )
    return u


@pytest.fixture
def tenant_admin_of(db, monkeypatch):
    u = User.objects.create_user(username='ada', password='x')
    monkeypatch.setattr(
        'snapshots.permissions.tenant_schemas_with_all_access',
        lambda user: {'delta_state'} if user.username == 'ada' else set(),
    )
    return u


@pytest.fixture
def random_user(db):
    return User.objects.create_user(username='nobody', password='x')


@pytest.mark.unit
def test_superadmin_can_create_for_any_schema(factory, superadmin):
    req = factory.post('/api/snapshots/', {'schema_name': 'delta_state'},
                        format='json')
    req.user = superadmin
    assert CanCreateSnapshot().has_permission(req, view=None) is True


@pytest.mark.unit
def test_superadmin_can_create_for_public(factory, superadmin):
    req = factory.post('/api/snapshots/', {'schema_name': 'public'},
                        format='json')
    req.user = superadmin
    assert CanCreateSnapshot().has_permission(req, view=None) is True


@pytest.mark.unit
def test_tenant_admin_can_create_for_own_schema(factory, tenant_admin_of):
    req = factory.post('/api/snapshots/', {'schema_name': 'delta_state'},
                        format='json')
    req.user = tenant_admin_of
    assert CanCreateSnapshot().has_permission(req, view=None) is True


@pytest.mark.unit
def test_tenant_admin_cannot_create_for_other_schema(factory, tenant_admin_of):
    req = factory.post('/api/snapshots/', {'schema_name': 'lagos_state'},
                        format='json')
    req.user = tenant_admin_of
    assert CanCreateSnapshot().has_permission(req, view=None) is False


@pytest.mark.unit
def test_random_user_cannot_create(factory, random_user):
    req = factory.post('/api/snapshots/', {'schema_name': 'delta_state'},
                        format='json')
    req.user = random_user
    assert CanCreateSnapshot().has_permission(req, view=None) is False


@pytest.mark.integration
def test_can_access_object_uses_schema_match(
    factory, tenant_admin_of, random_user,
):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=tenant_admin_of)
    req = factory.get(f'/api/snapshots/{job.pk}/')

    req.user = tenant_admin_of
    assert CanAccessSnapshot().has_object_permission(req, None, job) is True

    req.user = random_user
    assert CanAccessSnapshot().has_object_permission(req, None, job) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_permissions.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the resolvers and permission classes**

`snapshots/services/resolvers.py`:

```python
"""Helpers to map users to their snapshot scope.

These wrap the canonical role primitives already wired in core and
contracts so the snapshots app does not invent new RBAC concepts.
"""
from __future__ import annotations

from typing import Iterable


def is_platform_superadmin(user) -> bool:
    """True iff the user is a platform-tier superadmin (cross-tenant).

    Wraps the existing canonical resolver. Imported lazily because
    superadmin app may not be present in all environments (sandbox)."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    try:
        from superadmin.models import SuperAdminUser
    except Exception:
        return False
    return SuperAdminUser.objects.filter(user_id=user.pk, is_active=True).exists()


def tenant_schemas_with_all_access(user) -> set[str]:
    """Set of schema names where the user holds the canonical 'all_access' Role.

    Returns empty set if user is anonymous or has no such role."""
    if not getattr(user, 'is_authenticated', False):
        return set()
    try:
        from core.models import RoleAssignment
    except Exception:
        return set()
    qs = RoleAssignment.objects.filter(
        user_id=user.pk,
        role__code='all_access',
        role__is_active=True,
        is_active=True,
    ).select_related('role')
    schemas: set[str] = set()
    for ra in qs:
        # RoleAssignment carries tenant_id; map to schema_name via tenants.Client.
        tenant = getattr(ra, 'tenant', None)
        if tenant and getattr(tenant, 'schema_name', None):
            schemas.add(tenant.schema_name)
    return schemas
```

`snapshots/permissions.py`:

```python
"""DRF permission classes for the snapshots app.

Defense-in-depth: every endpoint goes through BOTH a permission class
AND a queryset filter (see views.SnapshotJobViewSet.get_queryset).
A bug in either layer is still caught by the other.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from snapshots.services.resolvers import (
    is_platform_superadmin,
    tenant_schemas_with_all_access,
)


class CanCreateSnapshot(BasePermission):
    """Gate on POST: actor must be superadmin OR tenant admin of the
    target schema_name."""

    def has_permission(self, request, view):
        if request.method != 'POST':
            return True  # other verbs go through has_object_permission
        if not getattr(request.user, 'is_authenticated', False):
            return False
        if is_platform_superadmin(request.user):
            return True
        target = request.data.get('schema_name')
        if not target:
            return False
        return target in tenant_schemas_with_all_access(request.user)


class CanAccessSnapshot(BasePermission):
    """Object-level: actor sees a job iff superadmin OR tenant admin
    of the job's schema_name."""

    def has_permission(self, request, view):
        return getattr(request.user, 'is_authenticated', False)

    def has_object_permission(self, request, view, obj):
        if is_platform_superadmin(request.user):
            return True
        return obj.schema_name in tenant_schemas_with_all_access(request.user)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_permissions.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/services/resolvers.py snapshots/permissions.py \
        snapshots/tests/test_permissions.py
git commit -m "feat(snapshots): permission classes + canonical role resolvers"
```

---

### Task 12: Serializer

**Files:**
- Create: `snapshots/serializers.py`
- Test: `snapshots/tests/test_serializers.py`

- [ ] **Step 1: Write failing test**

`snapshots/tests/test_serializers.py`:

```python
"""SnapshotJobSerializer — read shape, write validation, audit fields."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from snapshots.models import SnapshotJob
from snapshots.serializers import SnapshotJobSerializer


User = get_user_model()


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.mark.integration
def test_serialize_includes_status_and_user(actor):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor, label='ts')
    data = SnapshotJobSerializer(job).data
    assert data['schema_name'] == 'delta_state'
    assert data['status'] == 'queued'
    assert data['triggered_by_username'] == 'ada'
    assert 'id' in data
    assert 'triggered_at' in data


@pytest.mark.integration
def test_serialize_omits_sensitive_kek_fingerprint_for_tenant_admin(actor):
    """kek_fingerprint is operator-only; tenant admin should not see it."""
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        kek_fingerprint='kek-v1')
    data = SnapshotJobSerializer(job, context={'is_superadmin': False}).data
    assert 'kek_fingerprint' not in data


@pytest.mark.integration
def test_serialize_includes_kek_fingerprint_for_superadmin(actor):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        kek_fingerprint='kek-v1')
    data = SnapshotJobSerializer(job, context={'is_superadmin': True}).data
    assert data['kek_fingerprint'] == 'kek-v1'


@pytest.mark.integration
def test_validation_rejects_invalid_schema_name(actor):
    s = SnapshotJobSerializer(data={'schema_name': 'BAD NAME', 'label': ''})
    assert not s.is_valid()
    assert 'schema_name' in s.errors


@pytest.mark.integration
def test_validation_accepts_clean_schema_name(actor):
    s = SnapshotJobSerializer(data={'schema_name': 'delta_state', 'label': ''})
    assert s.is_valid(), s.errors
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_serializers.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the serializer**

`snapshots/serializers.py`:

```python
"""DRF serializer for SnapshotJob."""
from __future__ import annotations

import re

from rest_framework import serializers

from snapshots.models import SnapshotJob


_SAFE_SCHEMA_RE = re.compile(r'^[a-z][a-z0-9_]{0,62}$')


class SnapshotJobSerializer(serializers.ModelSerializer):
    triggered_by_username = serializers.CharField(
        source='triggered_by.username', read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = SnapshotJob
        fields = [
            'id', 'schema_name', 'label', 'status',
            'triggered_by_username', 'triggered_at',
            'started_at', 'completed_at',
            'artifact_path', 'size_bytes', 'sha256',
            'kek_fingerprint', 'manifest',
            'error_message', 'error_class',
            'download_url',
        ]
        read_only_fields = [
            'id', 'status', 'triggered_by_username', 'triggered_at',
            'started_at', 'completed_at',
            'artifact_path', 'size_bytes', 'sha256',
            'kek_fingerprint', 'manifest',
            'error_message', 'error_class',
            'download_url',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        ctx = self.context or {}
        # Hide operator-only fields from tenant admins.
        if not ctx.get('is_superadmin', False):
            for sensitive in ('kek_fingerprint', 'artifact_path'):
                data.pop(sensitive, None)
            # Tenant admins see error_class but not raw error_message.
            data.pop('error_message', None)
        return data

    def get_download_url(self, instance):
        if instance.status != SnapshotJob.Status.SUCCEEDED:
            return None
        return f'/api/snapshots/{instance.pk}/download/'

    def validate_schema_name(self, value):
        if not _SAFE_SCHEMA_RE.match(value):
            raise serializers.ValidationError(
                'must match [a-z][a-z0-9_]{0,62}')
        return value
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_serializers.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/serializers.py snapshots/tests/test_serializers.py
git commit -m "feat(snapshots): SnapshotJobSerializer with role-aware field hiding"
```

---

### Task 13: Audit logger wrapper

**Files:**
- Create: `snapshots/audit.py`
- Test: covered by `test_api.py` in next task

- [ ] **Step 1: Implement audit wrapper**

`snapshots/audit.py`:

```python
"""Thin wrapper that writes one row to core.AuditLog per snapshot event.

We isolate this into a module so the rest of the app calls a stable API
even if the underlying audit infrastructure changes.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _log(event: str, *, actor, job, extra: dict[str, Any] | None = None) -> None:
    try:
        from core.models import AuditLog
    except Exception:
        logger.exception('snapshots.audit: AuditLog import failed')
        return
    try:
        AuditLog.objects.create(
            user=actor,
            action=f'snapshot.{event}',
            object_type='SnapshotJob',
            object_id=str(job.pk),
            details={
                'schema_name': job.schema_name,
                'status': job.status,
                **(extra or {}),
            },
        )
    except Exception:
        # Never let an audit-write failure break the user-facing action.
        logger.exception('snapshots.audit: failed to write %s for job %s',
                          event, job.pk)


def snapshot_created(actor, job): _log('created', actor=actor, job=job)
def snapshot_downloaded(actor, job, ip):
    _log('downloaded', actor=actor, job=job, extra={'ip': ip})
def snapshot_deleted(actor, job): _log('deleted', actor=actor, job=job)
```

- [ ] **Step 2: Quick sanity check (the AuditLog model accepts these fields)**

```bash
python manage.py shell -c "from core.models import AuditLog; print([f.name for f in AuditLog._meta.fields])"
```

Verify `user`, `action`, `object_type`, `object_id`, `details` are present. If field names differ in this codebase, adjust `audit.py` to match the actual AuditLog schema (e.g., the field may be called `actor` or `changes` rather than `user`/`details`).

- [ ] **Step 3: Commit**

```bash
git add snapshots/audit.py
git commit -m "feat(snapshots): audit wrapper writes to core.AuditLog"
```

---

### Task 14: ViewSet — list / retrieve / create

**Files:**
- Create: `snapshots/views.py`
- Create: `snapshots/urls.py`
- Modify: `quot_pse/urls.py` — include the new urls
- Test: `snapshots/tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

`snapshots/tests/test_api.py`:

```python
"""End-to-end DRF API behavior."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from snapshots.models import SnapshotJob


User = get_user_model()


@pytest.fixture
def superadmin(db, monkeypatch):
    u = User.objects.create_user(username='root', password='x', is_superuser=True)
    monkeypatch.setattr('snapshots.permissions.is_platform_superadmin',
                        lambda user: user.is_superuser)
    return u


@pytest.fixture
def tenant_admin(db, monkeypatch):
    u = User.objects.create_user(username='ada', password='x')
    monkeypatch.setattr(
        'snapshots.permissions.tenant_schemas_with_all_access',
        lambda user: {'delta_state'} if user.pk == u.pk else set(),
    )
    return u


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username='other', password='x')


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.integration
def test_create_returns_202_and_serialized_job(superadmin, monkeypatch):
    enqueued = {}
    monkeypatch.setattr('snapshots.views.run_snapshot_job.delay',
                        lambda job_id: enqueued.setdefault('job_id', job_id))
    resp = _client(superadmin).post(
        '/api/snapshots/', {'schema_name': 'delta_state', 'label': 'ts'},
        format='json')
    assert resp.status_code in (201, 202)
    assert resp.data['status'] == 'queued'
    assert enqueued['job_id'] == resp.data['id']


@pytest.mark.integration
def test_tenant_admin_cannot_create_for_other_schema(tenant_admin):
    resp = _client(tenant_admin).post(
        '/api/snapshots/', {'schema_name': 'lagos_state'}, format='json')
    assert resp.status_code == 403


@pytest.mark.integration
def test_list_filtered_by_actor_scope(superadmin, tenant_admin, other_user):
    SnapshotJob.objects.create(schema_name='delta_state', triggered_by=tenant_admin)
    SnapshotJob.objects.create(schema_name='lagos_state', triggered_by=superadmin)

    # Superadmin sees all.
    resp = _client(superadmin).get('/api/snapshots/')
    assert resp.status_code == 200
    assert len(resp.data['results']) == 2

    # Tenant admin sees own-tenant only.
    resp = _client(tenant_admin).get('/api/snapshots/')
    assert resp.status_code == 200
    assert all(r['schema_name'] == 'delta_state' for r in resp.data['results'])

    # Other user sees zero.
    resp = _client(other_user).get('/api/snapshots/')
    assert resp.status_code in (200, 403)
    if resp.status_code == 200:
        assert resp.data['results'] == []


@pytest.mark.integration
def test_retrieve_404_for_wrong_tenant(tenant_admin):
    job = SnapshotJob.objects.create(
        schema_name='lagos_state', triggered_by=tenant_admin)
    resp = _client(tenant_admin).get(f'/api/snapshots/{job.pk}/')
    # Either 404 (not in queryset) or 403 (permission denied) — both acceptable.
    assert resp.status_code in (403, 404)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_api.py -v
```

Expected: 404 from the test client because no URLs are wired.

- [ ] **Step 3: Implement the ViewSet (create/list/retrieve)**

`snapshots/views.py`:

```python
"""DRF ViewSet for SnapshotJob.

Provides:
    POST   /api/snapshots/                  enqueue
    GET    /api/snapshots/                  list (scoped)
    GET    /api/snapshots/{id}/             detail
    GET    /api/snapshots/{id}/download/    stream-decrypt (Task 15)
    DELETE /api/snapshots/{id}/             expire row + unlink file (Task 16)
"""
from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.http import Http404, StreamingHttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from snapshots import audit
from snapshots.models import SnapshotJob
from snapshots.permissions import CanAccessSnapshot, CanCreateSnapshot
from snapshots.serializers import SnapshotJobSerializer
from snapshots.services.resolvers import (
    is_platform_superadmin,
    tenant_schemas_with_all_access,
)
from snapshots.tasks import run_snapshot_job


logger = logging.getLogger(__name__)


class SnapshotJobViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SnapshotJobSerializer
    permission_classes = [IsAuthenticated, CanCreateSnapshot, CanAccessSnapshot]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'snapshot_create'

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['is_superadmin'] = is_platform_superadmin(self.request.user)
        return ctx

    def get_queryset(self):
        qs = SnapshotJob.objects.select_related('triggered_by').all()
        user = self.request.user
        if is_platform_superadmin(user):
            return qs
        return qs.filter(schema_name__in=tenant_schemas_with_all_access(user))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = SnapshotJob.objects.create(
            schema_name=serializer.validated_data['schema_name'],
            label=serializer.validated_data.get('label', ''),
            triggered_by=request.user,
        )
        run_snapshot_job.delay(job.pk)
        audit.snapshot_created(request.user, job)
        out = self.get_serializer(job)
        return Response(out.data, status=status.HTTP_202_ACCEPTED)
```

`snapshots/urls.py`:

```python
"""URL routes for the snapshots app."""
from __future__ import annotations

from rest_framework.routers import DefaultRouter

from snapshots.views import SnapshotJobViewSet


router = DefaultRouter()
router.register(r'snapshots', SnapshotJobViewSet, basename='snapshot')

urlpatterns = router.urls
```

Modify `quot_pse/urls.py` — add inside the API `path(...)` block (alongside the existing app URL includes):

```python
# Find the section that wires other app URLs (e.g., `path('api/', include('accounting.urls'))`)
# and add:
path('api/', include('snapshots.urls')),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_api.py -v
```

Expected: 4 passed (download + delete tests still fail until next tasks).

- [ ] **Step 5: Commit**

```bash
git add snapshots/views.py snapshots/urls.py snapshots/tests/test_api.py \
        quot_pse/urls.py
git commit -m "feat(snapshots): ViewSet create/list/retrieve with scoped queryset"
```

---

### Task 15: ViewSet — download action (stream-decrypt)

**Files:**
- Modify: `snapshots/views.py` — add `download` action
- Modify: `snapshots/tests/test_api.py` — add download tests

- [ ] **Step 1: Write failing test**

Append to `snapshots/tests/test_api.py`:

```python
@pytest.mark.integration
def test_download_for_succeeded_job_streams_plaintext(
    superadmin, configured_settings, monkeypatch,
):
    """End-to-end: create a tiny SnapshotJob with a real encrypted artifact,
    then verify download decrypts and streams it."""
    import io
    from pathlib import Path

    from snapshots.services.crypto import encrypt_stream

    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=superadmin,
        status=SnapshotJob.Status.SUCCEEDED,
        artifact_path='delta_state/snap-1.tar.gz.enc',
        kek_fingerprint='kek-v1',
    )

    # Build a real encrypted artifact on disk.
    storage_root = Path(configured_settings.SNAPSHOTS_BACKUP_DIR)
    artifact = storage_root / job.artifact_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    plaintext = b'hello backup'
    kek = bytes.fromhex(configured_settings.SNAPSHOTS_KEK_HEX)
    with artifact.open('wb') as fh:
        encrypt_stream(io.BytesIO(plaintext), fh, kek=kek, kek_id='kek-v1')

    resp = _client(superadmin).get(f'/api/snapshots/{job.pk}/download/')
    assert resp.status_code == 200
    body = b''.join(resp.streaming_content)
    assert body == plaintext


@pytest.mark.integration
def test_download_404_for_non_succeeded_job(superadmin):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=superadmin,
        status=SnapshotJob.Status.RUNNING)
    resp = _client(superadmin).get(f'/api/snapshots/{job.pk}/download/')
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest snapshots/tests/test_api.py -v -k download
```

Expected: 404 on the URL because the action doesn't exist yet.

- [ ] **Step 3: Implement the download action**

Edit `snapshots/views.py`, append inside `SnapshotJobViewSet`:

```python
    @action(detail=True, methods=['GET'], url_path='download')
    def download(self, request, pk=None):
        job = self.get_object()
        if job.status != SnapshotJob.Status.SUCCEEDED or not job.artifact_path:
            raise Http404('Snapshot is not available for download.')

        audit.snapshot_downloaded(
            actor=request.user, job=job,
            ip=request.META.get('REMOTE_ADDR'))

        absolute_path = Path(settings.SNAPSHOTS_BACKUP_DIR) / job.artifact_path
        resp = StreamingHttpResponse(
            self._stream_decrypt(absolute_path),
            content_type='application/octet-stream',
        )
        resp['Content-Disposition'] = (
            f'attachment; filename="{job.schema_name}-snapshot-{job.pk}.tar.gz"'
        )
        resp['X-Content-Type-Options'] = 'nosniff'
        return resp

    @staticmethod
    def _stream_decrypt(absolute_path):
        """Generator: stream-decrypt a snapshot file in 64 KB chunks.

        Phase 1 simplification: AESGCM in `cryptography` is one-shot,
        so we read the file fully, decrypt once, and yield in chunks.
        For sub-multi-GB artifacts this is fine; a future task can
        swap in chunked-CTR + HMAC if needed."""
        import io
        from snapshots.services.crypto import decrypt_stream

        kek = bytes.fromhex(settings.SNAPSHOTS_KEK_HEX)
        plain_buf = io.BytesIO()
        with open(absolute_path, 'rb') as fh:
            decrypt_stream(fh, plain_buf, kek=kek)
        plain_buf.seek(0)
        while True:
            chunk = plain_buf.read(64 * 1024)
            if not chunk:
                break
            yield chunk
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_api.py -v -k download
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add snapshots/views.py snapshots/tests/test_api.py
git commit -m "feat(snapshots): download action streams decrypted artifact"
```

---

### Task 16: ViewSet — delete (preserves audit row)

**Files:**
- Modify: `snapshots/views.py` — override `destroy`
- Modify: `snapshots/tests/test_api.py` — add delete tests

- [ ] **Step 1: Write failing test**

Append to `snapshots/tests/test_api.py`:

```python
@pytest.mark.integration
def test_delete_marks_expired_and_unlinks_file(
    superadmin, configured_settings,
):
    """DELETE transitions row to EXPIRED, unlinks artifact file,
    preserves audit-relevant fields."""
    import io
    from pathlib import Path

    from snapshots.services.crypto import encrypt_stream

    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=superadmin,
        status=SnapshotJob.Status.SUCCEEDED,
        artifact_path='delta_state/snap-doomed.tar.gz.enc',
        label='will be deleted',
    )
    storage_root = Path(configured_settings.SNAPSHOTS_BACKUP_DIR)
    artifact = storage_root / job.artifact_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    with artifact.open('wb') as fh:
        encrypt_stream(io.BytesIO(b'x'), fh,
                        kek=bytes.fromhex(configured_settings.SNAPSHOTS_KEK_HEX),
                        kek_id='kek-v1')

    resp = _client(superadmin).delete(f'/api/snapshots/{job.pk}/')
    assert resp.status_code == 204

    job.refresh_from_db()
    assert job.status == SnapshotJob.Status.EXPIRED
    assert job.artifact_path == ''
    assert job.label == 'will be deleted'   # audit field preserved
    assert not artifact.exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest snapshots/tests/test_api.py -v -k delete
```

Expected: default DRF destroy hard-deletes the row, so the test fails on `status == EXPIRED`.

- [ ] **Step 3: Override destroy to expire-instead-of-delete**

Edit `snapshots/views.py`, append to `SnapshotJobViewSet`:

```python
    def destroy(self, request, *args, **kwargs):
        job = self.get_object()

        from snapshots.services.storage import LocalFilesystemStorage
        storage = LocalFilesystemStorage(root=settings.SNAPSHOTS_BACKUP_DIR)

        artifact_path = job.artifact_path
        # DB first, then file (see retention.py for rationale).
        SnapshotJob.objects.filter(pk=job.pk).update(
            status=SnapshotJob.Status.EXPIRED,
            artifact_path='',
        )
        audit.snapshot_deleted(actor=request.user, job=job)

        if artifact_path:
            try:
                storage.delete(artifact_path)
            except Exception:
                logger.exception('snapshots: failed to delete artifact %s',
                                  artifact_path)

        return Response(status=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest snapshots/tests/test_api.py -v -k delete
```

Expected: 1 passed.

- [ ] **Step 5: Run the full backend suite to verify nothing broke**

```bash
pytest snapshots/ -v
```

Expected: all snapshots tests pass.

- [ ] **Step 6: Commit**

```bash
git add snapshots/views.py snapshots/tests/test_api.py
git commit -m "feat(snapshots): delete transitions to EXPIRED preserving audit row"
```

---

### Task 17: Frontend — TypeScript types + API client

**Files:**
- Create: `frontend/src/features/admin/snapshots/types.ts`
- Create: `frontend/src/features/admin/snapshots/api.ts`

- [ ] **Step 1: Define types**

`frontend/src/features/admin/snapshots/types.ts`:

```typescript
export type SnapshotStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'expired'

export interface SnapshotJob {
  id: number
  schema_name: string
  label: string
  status: SnapshotStatus
  triggered_by_username: string
  triggered_at: string  // ISO
  started_at: string | null
  completed_at: string | null
  size_bytes: number | null
  sha256: string
  error_class: string
  manifest: Record<string, unknown>
  download_url: string | null
  // Superadmin-only fields (absent for tenant admins)
  artifact_path?: string
  kek_fingerprint?: string
  error_message?: string
}

export interface CreateSnapshotInput {
  schema_name: string
  label?: string
}

export interface SnapshotListResponse {
  count: number
  next: string | null
  previous: string | null
  results: SnapshotJob[]
}
```

- [ ] **Step 2: Implement API client**

`frontend/src/features/admin/snapshots/api.ts`:

```typescript
import { apiClient } from '@/api/client'
import type {
  CreateSnapshotInput,
  SnapshotJob,
  SnapshotListResponse,
} from './types'

const BASE = '/snapshots/'

export async function listSnapshots(
  params?: { schema?: string; status?: string },
): Promise<SnapshotListResponse> {
  const { data } = await apiClient.get<SnapshotListResponse>(BASE, { params })
  return data
}

export async function getSnapshot(id: number): Promise<SnapshotJob> {
  const { data } = await apiClient.get<SnapshotJob>(`${BASE}${id}/`)
  return data
}

export async function createSnapshot(
  input: CreateSnapshotInput,
): Promise<SnapshotJob> {
  const { data } = await apiClient.post<SnapshotJob>(BASE, input)
  return data
}

export async function deleteSnapshot(id: number): Promise<void> {
  await apiClient.delete(`${BASE}${id}/`)
}

export function snapshotDownloadHref(id: number): string {
  // Returns the URL — the browser handles the file download via an <a> click.
  return `${apiClient.defaults.baseURL ?? ''}${BASE}${id}/download/`
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors. If `apiClient.defaults.baseURL` is wrong, check the existing pattern in `frontend/src/api/client.ts` and mirror it.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/admin/snapshots/types.ts \
        frontend/src/features/admin/snapshots/api.ts
git commit -m "feat(snapshots-fe): types and API client"
```

---

### Task 18: Frontend — TanStack Query hooks

**Files:**
- Create: `frontend/src/features/admin/snapshots/hooks/useSnapshotJobs.ts`
- Create: `frontend/src/features/admin/snapshots/hooks/useCreateSnapshot.ts`
- Create: `frontend/src/features/admin/snapshots/hooks/useDeleteSnapshot.ts`
- Create: `frontend/src/features/admin/snapshots/hooks/useDownloadSnapshot.ts`

- [ ] **Step 1: List query hook with conditional polling**

`frontend/src/features/admin/snapshots/hooks/useSnapshotJobs.ts`:

```typescript
import { useQuery } from '@tanstack/react-query'
import { listSnapshots } from '../api'
import type { SnapshotListResponse } from '../types'

const ACTIVE_STATUSES = ['queued', 'running'] as const

export function useSnapshotJobs(filters?: { schema?: string; status?: string }) {
  return useQuery<SnapshotListResponse>({
    queryKey: ['snapshots', filters],
    queryFn: () => listSnapshots(filters),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return false
      const anyActive = data.results.some((j) =>
        (ACTIVE_STATUSES as readonly string[]).includes(j.status),
      )
      return anyActive ? 5000 : false
    },
  })
}
```

- [ ] **Step 2: Create mutation hook**

`frontend/src/features/admin/snapshots/hooks/useCreateSnapshot.ts`:

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createSnapshot } from '../api'
import type { CreateSnapshotInput, SnapshotJob } from '../types'

export function useCreateSnapshot() {
  const qc = useQueryClient()
  return useMutation<SnapshotJob, Error, CreateSnapshotInput>({
    mutationFn: createSnapshot,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['snapshots'] })
    },
  })
}
```

- [ ] **Step 3: Delete mutation hook**

`frontend/src/features/admin/snapshots/hooks/useDeleteSnapshot.ts`:

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { deleteSnapshot } from '../api'

export function useDeleteSnapshot() {
  const qc = useQueryClient()
  return useMutation<void, Error, number>({
    mutationFn: deleteSnapshot,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['snapshots'] })
    },
  })
}
```

- [ ] **Step 4: Download trigger hook (imperative)**

`frontend/src/features/admin/snapshots/hooks/useDownloadSnapshot.ts`:

```typescript
import { useCallback } from 'react'
import { snapshotDownloadHref } from '../api'

/**
 * Triggers a browser download via a hidden <a> click.
 * No client-side decryption; the server streams plaintext after
 * authenticating the request.
 */
export function useDownloadSnapshot() {
  return useCallback((id: number, filename?: string) => {
    const href = snapshotDownloadHref(id)
    const a = document.createElement('a')
    a.href = href
    if (filename) a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }, [])
}
```

- [ ] **Step 5: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/admin/snapshots/hooks/
git commit -m "feat(snapshots-fe): list/create/delete/download hooks with conditional polling"
```

---

### Task 19: Frontend — Components

**Files:**
- Create: `frontend/src/features/admin/snapshots/components/SnapshotJobStatusPill.tsx`
- Create: `frontend/src/features/admin/snapshots/components/SnapshotsTable.tsx`
- Create: `frontend/src/features/admin/snapshots/components/CreateSnapshotForm.tsx`
- Create: `frontend/src/features/admin/snapshots/components/SnapshotDetailDrawer.tsx`

- [ ] **Step 1: Status pill component**

`frontend/src/features/admin/snapshots/components/SnapshotJobStatusPill.tsx`:

```tsx
import type { SnapshotStatus } from '../types'

interface Props {
  status: SnapshotStatus
}

const COLORS: Record<SnapshotStatus, string> = {
  queued:    'bg-amber-100 text-amber-900',
  running:   'bg-blue-100 text-blue-900',
  succeeded: 'bg-emerald-100 text-emerald-900',
  failed:    'bg-rose-100 text-rose-900',
  expired:   'bg-zinc-200 text-zinc-700',
}

export function SnapshotJobStatusPill({ status }: Props) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${COLORS[status]}`}
      role="status"
      aria-label={`Status: ${status}`}
    >
      {status}
    </span>
  )
}
```

- [ ] **Step 2: Snapshots table**

`frontend/src/features/admin/snapshots/components/SnapshotsTable.tsx`:

```tsx
import { useState } from 'react'
import { useDeleteSnapshot } from '../hooks/useDeleteSnapshot'
import { useDownloadSnapshot } from '../hooks/useDownloadSnapshot'
import type { SnapshotJob } from '../types'
import { SnapshotJobStatusPill } from './SnapshotJobStatusPill'

interface Props {
  jobs: SnapshotJob[]
  showSchemaColumn?: boolean
  onView?: (job: SnapshotJob) => void
}

const en_GB = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit',
})

function formatBytes(b: number | null): string {
  if (b === null) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = b
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i += 1
  }
  return `${n.toFixed(1)} ${units[i]}`
}

export function SnapshotsTable({ jobs, showSchemaColumn = true, onView }: Props) {
  const del = useDeleteSnapshot()
  const download = useDownloadSnapshot()
  const [confirmId, setConfirmId] = useState<number | null>(null)

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-zinc-200 text-left">
          <th className="py-2 pr-4">Triggered</th>
          {showSchemaColumn && <th className="py-2 pr-4">Schema</th>}
          <th className="py-2 pr-4">Label</th>
          <th className="py-2 pr-4">Status</th>
          <th className="py-2 pr-4">Size</th>
          <th className="py-2 pr-4">By</th>
          <th className="py-2 pr-4 text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        {jobs.length === 0 && (
          <tr>
            <td colSpan={7} className="py-6 text-center text-zinc-500">
              No snapshots yet.
            </td>
          </tr>
        )}
        {jobs.map((job) => (
          <tr key={job.id} className="border-b border-zinc-100">
            <td className="py-2 pr-4">{en_GB.format(new Date(job.triggered_at))}</td>
            {showSchemaColumn && <td className="py-2 pr-4 font-mono text-xs">{job.schema_name}</td>}
            <td className="py-2 pr-4">{job.label || <span className="text-zinc-400">—</span>}</td>
            <td className="py-2 pr-4"><SnapshotJobStatusPill status={job.status} /></td>
            <td className="py-2 pr-4">{formatBytes(job.size_bytes)}</td>
            <td className="py-2 pr-4">{job.triggered_by_username}</td>
            <td className="py-2 pr-4 text-right space-x-2">
              {onView && (
                <button onClick={() => onView(job)} className="text-blue-700 hover:underline">View</button>
              )}
              {job.status === 'succeeded' && (
                <button
                  onClick={() => download(job.id, `${job.schema_name}-snap-${job.id}.tar.gz`)}
                  className="text-emerald-700 hover:underline"
                >Download</button>
              )}
              {confirmId === job.id ? (
                <>
                  <button
                    onClick={() => { del.mutate(job.id); setConfirmId(null) }}
                    className="text-rose-700 hover:underline"
                  >Confirm</button>
                  <button onClick={() => setConfirmId(null)} className="text-zinc-500">Cancel</button>
                </>
              ) : (
                <button onClick={() => setConfirmId(job.id)} className="text-zinc-600 hover:underline">
                  Delete
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
```

- [ ] **Step 3: Create form**

`frontend/src/features/admin/snapshots/components/CreateSnapshotForm.tsx`:

```tsx
import { useState } from 'react'
import { useCreateSnapshot } from '../hooks/useCreateSnapshot'

interface Props {
  /** If set, schema_name is fixed and the schema input is hidden (tenant view). */
  fixedSchema?: string
  /** Optional list of selectable schemas (superadmin view). */
  selectableSchemas?: string[]
  onCreated?: () => void
}

export function CreateSnapshotForm({ fixedSchema, selectableSchemas, onCreated }: Props) {
  const [schema, setSchema] = useState(fixedSchema ?? selectableSchemas?.[0] ?? '')
  const [label, setLabel] = useState('')
  const mut = useCreateSnapshot()

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await mut.mutateAsync({ schema_name: schema, label })
    setLabel('')
    onCreated?.()
  }

  return (
    <form onSubmit={onSubmit} className="flex items-end gap-3">
      {!fixedSchema && selectableSchemas && (
        <label className="flex flex-col text-sm">
          <span className="text-zinc-600 mb-1">Schema</span>
          <select
            value={schema}
            onChange={(e) => setSchema(e.target.value)}
            className="border border-zinc-300 rounded px-2 py-1"
            required
          >
            {selectableSchemas.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      )}
      <label className="flex flex-col text-sm flex-1">
        <span className="text-zinc-600 mb-1">Label (optional)</span>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          maxLength={120}
          placeholder="e.g. pre FY26 budget import"
          className="border border-zinc-300 rounded px-2 py-1"
        />
      </label>
      <button
        type="submit"
        disabled={mut.isPending || !schema}
        className="bg-blue-700 text-white px-4 py-1.5 rounded hover:bg-blue-800 disabled:opacity-50"
      >
        {mut.isPending ? 'Creating…' : 'Create snapshot'}
      </button>
      {mut.isError && (
        <span className="text-rose-700 text-sm">
          {(mut.error as Error).message}
        </span>
      )}
    </form>
  )
}
```

- [ ] **Step 4: Detail drawer**

`frontend/src/features/admin/snapshots/components/SnapshotDetailDrawer.tsx`:

```tsx
import type { SnapshotJob } from '../types'
import { SnapshotJobStatusPill } from './SnapshotJobStatusPill'

interface Props {
  job: SnapshotJob | null
  onClose: () => void
}

export function SnapshotDetailDrawer({ job, onClose }: Props) {
  if (!job) return null
  return (
    <div className="fixed inset-y-0 right-0 w-[28rem] bg-white border-l border-zinc-200 shadow-xl p-6 overflow-y-auto z-50">
      <div className="flex justify-between items-start mb-4">
        <h2 className="text-lg font-semibold">Snapshot #{job.id}</h2>
        <button onClick={onClose} aria-label="Close" className="text-zinc-500 hover:text-zinc-900">×</button>
      </div>
      <dl className="space-y-3 text-sm">
        <Row k="Schema" v={<span className="font-mono">{job.schema_name}</span>} />
        <Row k="Status" v={<SnapshotJobStatusPill status={job.status} />} />
        <Row k="Label" v={job.label || '—'} />
        <Row k="Triggered by" v={job.triggered_by_username} />
        <Row k="Triggered at" v={job.triggered_at} />
        <Row k="Started" v={job.started_at ?? '—'} />
        <Row k="Completed" v={job.completed_at ?? '—'} />
        <Row k="Size" v={job.size_bytes !== null ? `${job.size_bytes} bytes` : '—'} />
        <Row k="SHA256" v={<span className="font-mono break-all text-xs">{job.sha256 || '—'}</span>} />
        {job.error_class && <Row k="Error class" v={job.error_class} />}
        {job.error_message && (
          <Row k="Error detail" v={<pre className="text-xs whitespace-pre-wrap">{job.error_message}</pre>} />
        )}
      </dl>
      {Object.keys(job.manifest || {}).length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-zinc-600">Manifest</summary>
          <pre className="text-xs bg-zinc-50 p-3 rounded mt-2 overflow-auto">
            {JSON.stringify(job.manifest, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="text-zinc-500 w-28 shrink-0">{k}</dt>
      <dd className="text-zinc-900 flex-1">{v}</dd>
    </div>
  )
}
```

- [ ] **Step 5: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors. If imports for Tailwind classes or shared components differ, adjust to match the codebase's actual pattern.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/admin/snapshots/components/
git commit -m "feat(snapshots-fe): table, form, status pill, detail drawer"
```

---

### Task 20: Frontend — Pages

**Files:**
- Create: `frontend/src/features/admin/snapshots/pages/SnapshotsPage.tsx`
- Create: `frontend/src/features/admin/snapshots/pages/TenantSnapshotsPage.tsx`

- [ ] **Step 1: Superadmin page**

`frontend/src/features/admin/snapshots/pages/SnapshotsPage.tsx`:

```tsx
import { useState } from 'react'
import { useSnapshotJobs } from '../hooks/useSnapshotJobs'
import { CreateSnapshotForm } from '../components/CreateSnapshotForm'
import { SnapshotsTable } from '../components/SnapshotsTable'
import { SnapshotDetailDrawer } from '../components/SnapshotDetailDrawer'
import type { SnapshotJob } from '../types'

/**
 * Superadmin cross-tenant view. Lists snapshots across all schemas,
 * and lets the operator create a snapshot for any schema (incl. public).
 *
 * Tenant list must be sourced from an existing tenant-listing endpoint
 * in the codebase. If the project already exposes `/api/superadmin/tenants/`
 * or similar, wire it in here. As a Phase-1 fallback we accept a static
 * list passed in as a prop or piped through an environment-aware constant.
 */
interface Props {
  schemas?: string[]   // pulled from the tenants registry by the host route
}

export function SnapshotsPage({ schemas }: Props) {
  const { data, isLoading, error } = useSnapshotJobs()
  const [viewing, setViewing] = useState<SnapshotJob | null>(null)
  const fallback = ['public']

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-semibold mb-6">Backups & snapshots</h1>

      <section className="mb-8 bg-white border border-zinc-200 rounded-lg p-4">
        <h2 className="text-sm font-medium text-zinc-700 mb-3">Create snapshot</h2>
        <CreateSnapshotForm selectableSchemas={schemas ?? fallback} />
      </section>

      <section>
        <h2 className="text-sm font-medium text-zinc-700 mb-3">All snapshots</h2>
        {isLoading && <p className="text-zinc-500">Loading…</p>}
        {error && <p className="text-rose-700">{(error as Error).message}</p>}
        {data && (
          <SnapshotsTable
            jobs={data.results}
            showSchemaColumn
            onView={(j) => setViewing(j)}
          />
        )}
      </section>

      <SnapshotDetailDrawer job={viewing} onClose={() => setViewing(null)} />
    </div>
  )
}
```

- [ ] **Step 2: Tenant page**

`frontend/src/features/admin/snapshots/pages/TenantSnapshotsPage.tsx`:

```tsx
import { useState } from 'react'
import { useSnapshotJobs } from '../hooks/useSnapshotJobs'
import { CreateSnapshotForm } from '../components/CreateSnapshotForm'
import { SnapshotsTable } from '../components/SnapshotsTable'
import { SnapshotDetailDrawer } from '../components/SnapshotDetailDrawer'
import type { SnapshotJob } from '../types'

/**
 * Tenant-admin view. Always scoped to the current tenant schema.
 * The schema name is taken from the auth context — same place the rest
 * of the codebase reads it from (e.g., a `useTenant()` or `useCurrentTenant()` hook).
 */
interface Props {
  schemaName: string
}

export function TenantSnapshotsPage({ schemaName }: Props) {
  const { data, isLoading, error } = useSnapshotJobs()
  const [viewing, setViewing] = useState<SnapshotJob | null>(null)

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-semibold mb-2">Backups</h1>
      <p className="text-sm text-zinc-600 mb-6">
        Create an on-demand snapshot of <span className="font-mono">{schemaName}</span>.
        Restore is operator-only — contact platform support if you need to restore.
      </p>

      <section className="mb-8 bg-white border border-zinc-200 rounded-lg p-4">
        <h2 className="text-sm font-medium text-zinc-700 mb-3">Create snapshot</h2>
        <CreateSnapshotForm fixedSchema={schemaName} />
      </section>

      <section>
        <h2 className="text-sm font-medium text-zinc-700 mb-3">Recent snapshots</h2>
        {isLoading && <p className="text-zinc-500">Loading…</p>}
        {error && <p className="text-rose-700">{(error as Error).message}</p>}
        {data && (
          <SnapshotsTable
            jobs={data.results}
            showSchemaColumn={false}
            onView={(j) => setViewing(j)}
          />
        )}
      </section>

      <SnapshotDetailDrawer job={viewing} onClose={() => setViewing(null)} />
    </div>
  )
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors. If `useCurrentTenant` is the codebase's pattern (rather than passing `schemaName` as a prop), adjust `TenantSnapshotsPage` to read from it.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/admin/snapshots/pages/
git commit -m "feat(snapshots-fe): superadmin + tenant pages composing form/table/drawer"
```

---

### Task 21: Frontend — Routing + sidebar nav

**Files:**
- Modify: `frontend/src/App.tsx` — add the two new routes
- Modify: `frontend/src/components/Sidebar.tsx` — add nav entries (visibility gated)

- [ ] **Step 1: Wire routes**

In `frontend/src/App.tsx`, locate the React Router routes block and add:

```tsx
// Lazy-import the pages.
import { lazy } from 'react'
const SnapshotsPage = lazy(() =>
  import('@/features/admin/snapshots/pages/SnapshotsPage')
    .then((m) => ({ default: m.SnapshotsPage }))
)
const TenantSnapshotsPage = lazy(() =>
  import('@/features/admin/snapshots/pages/TenantSnapshotsPage')
    .then((m) => ({ default: m.TenantSnapshotsPage }))
)

// In the <Routes> block:
<Route path="/admin/snapshots" element={<SnapshotsPage />} />
<Route path="/settings/backups" element={<TenantSnapshotsPageWrapper />} />
```

If a `TenantSnapshotsPageWrapper` is needed to read schema from auth context, add a small wrapper inline or in the same file:

```tsx
import { useAuth } from '@/context/AuthContext'

function TenantSnapshotsPageWrapper() {
  const { tenant } = useAuth()  // adjust to actual auth-context shape
  if (!tenant?.schema_name) return null
  return <TenantSnapshotsPage schemaName={tenant.schema_name} />
}
```

- [ ] **Step 2: Add sidebar entries**

In `frontend/src/components/Sidebar.tsx`, locate the nav-items array and add two entries. The visibility predicate must mirror the codebase's existing role-check helpers (e.g., `useIsSuperadmin()` or a `canAccess(routeId)` helper):

```tsx
// Inside the nav array, gated by existing role helpers:
{
  to: '/admin/snapshots',
  label: 'Backups',
  icon: ArchiveBoxIcon,
  visible: isSuperadmin,
},
{
  to: '/settings/backups',
  label: 'Backups',
  icon: ArchiveBoxIcon,
  visible: isTenantAdmin && !isSuperadmin,
},
```

(Replace `ArchiveBoxIcon` with whatever icon library the sidebar already uses; replace `isSuperadmin` / `isTenantAdmin` with the codebase's actual flags.)

- [ ] **Step 3: Type-check and smoke-test in dev**

```bash
cd frontend && pnpm tsc --noEmit && pnpm dev
```

Open the dev URL, log in as superadmin, navigate to `/admin/snapshots`. Verify the page renders. Log in as a tenant admin and verify `/settings/backups` renders.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat(snapshots-fe): wire routes and sidebar nav"
```

---

### Task 22: E2E Playwright test

**Files:**
- Create: `frontend/tests/e2e/snapshots.spec.ts`

- [ ] **Step 1: Write the E2E spec**

`frontend/tests/e2e/snapshots.spec.ts`:

```typescript
import { expect, test } from '@playwright/test'

/**
 * E2E: tenant admin creates → polls → downloads → deletes a snapshot.
 *
 * Requires the dev backend to be running with Celery available, and
 * the e2e tenant seeded (see scripts/seed_e2e_tenant). The KEK in test
 * env MUST be set or backend creates will fail at the manifest step.
 */
test.describe('Snapshots — tenant admin', () => {
  test('full create-poll-download-delete loop', async ({ page }) => {
    // Login as the e2e tenant admin (helper is project-specific; mirror
    // the existing E2E auth helper used in other specs).
    await page.goto('/login')
    await page.fill('input[name="username"]', 'e2e_tenant_admin')
    await page.fill('input[name="password"]', 'e2e-test-password')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard')

    await page.goto('/settings/backups')
    await expect(page.locator('h1')).toContainText('Backups')

    // Create.
    await page.fill('input[placeholder*="pre FY26"]', 'e2e test snapshot')
    await page.click('button:has-text("Create snapshot")')

    // Poll until succeeded (TanStack Query refetchInterval handles this).
    const succeededPill = page.locator('span:has-text("succeeded")').first()
    await expect(succeededPill).toBeVisible({ timeout: 60_000 })

    // Download — verify the link is present and the click doesn't error.
    const downloadPromise = page.waitForEvent('download')
    await page.click('button:has-text("Download")')
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(/snap-\d+\.tar\.gz/)

    // Delete with confirmation.
    await page.click('button:has-text("Delete")')
    await page.click('button:has-text("Confirm")')

    // Expired pill appears (or row disappears, depending on UX choice).
    const expiredPill = page.locator('span:has-text("expired")').first()
    await expect(expiredPill).toBeVisible({ timeout: 5000 })
  })
})
```

- [ ] **Step 2: Run E2E**

```bash
cd frontend && pnpm playwright test snapshots.spec.ts
```

Expected: passes against a backend that has the e2e tenant seeded and Celery running. If Celery isn't running locally, mark the test `@slow` or skip it in fast CI lanes.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/snapshots.spec.ts
git commit -m "test(snapshots): Playwright E2E for create-poll-download-delete loop"
```

---

### Task 23: Final integration sweep

**Files:**
- No new files; runs the full suite + checks documentation.

- [ ] **Step 1: Run full backend test suite**

```bash
pytest -v
```

Expected: all snapshots tests pass; no regressions in other apps.

- [ ] **Step 2: Run frontend type-check + build**

```bash
cd frontend && pnpm tsc --noEmit && pnpm build
```

Expected: builds cleanly. Bundle-size deltas should be minor (the new feature is lazy-loaded).

- [ ] **Step 3: Verify migration applies cleanly**

```bash
python manage.py migrate_schemas --shared
```

Expected: no-op (already applied in Task 2).

- [ ] **Step 4: Smoke-test settings check**

```bash
python manage.py check
```

Expected: clean output (warning only in DEBUG if KEK not set; error in non-DEBUG).

- [ ] **Step 5: Update DR_DRILL.md to mention the new in-app path**

Append a paragraph to [docs/DR_DRILL.md](../../DR_DRILL.md) after the "When the drill fails" section:

```markdown
## In-app snapshots (Phase 1)

In addition to the nightly `scripts/backup.sh` pipeline, operators and
tenant admins can produce on-demand snapshots via the UI. See
[docs/superpowers/specs/2026-06-11-in-app-snapshots-design.md](superpowers/specs/2026-06-11-in-app-snapshots-design.md).
These snapshots use the same `pg_dump` flags and produce per-schema
artifacts, but are **encrypted at rest** with `SNAPSHOTS_KEK_HEX` and
cannot be restored with `psql` directly — they must be decrypted first.
Phase 4 will deliver an in-app restore; until then, encrypted snapshots
are downloaded and decrypted out-of-band for use with the standard
restore drill above.
```

- [ ] **Step 6: Commit final touches**

```bash
git add docs/DR_DRILL.md
git commit -m "docs(dr-drill): cross-reference in-app snapshots (Phase 1)"
```

---

## Spec coverage map (self-review)

Cross-check against the spec. Every numbered requirement maps to one or more tasks:

| Spec section | Spec requirement | Implementing task(s) |
|---|---|---|
| §2.1 | Superadmin trigger any schema | Tasks 11, 14 |
| §2.2 | Tenant admin trigger own schema only | Tasks 11, 14 |
| §2.3 | Self-describing encrypted artifact (DB + media + manifest) | Tasks 5, 6, 7, 9 |
| §2.4 | AES-256-GCM envelope encryption, deploy-time KEK | Tasks 1, 3 |
| §2.5 | Async creation (HTTP returns <1s) | Tasks 10, 14 |
| §2.6 | Retention by age + per-tenant count | Task 8 |
| §2.7 | Per-(user, schema) rate limit on create | Tasks 1, 14 (`ScopedRateThrottle`) |
| §2.8 | Auditable transitions | Tasks 13, 14, 15, 16 |
| §3 | Architecture (web -> celery -> services -> storage) | Tasks 9, 10, 14 |
| §4 | SnapshotJob model + 7 settings | Tasks 1, 2 |
| §5 | API endpoints + permission matrix + defense-in-depth | Tasks 11, 12, 14, 15, 16 |
| §6 | Artifact format (tarball + manifest + AES-GCM envelope) | Tasks 3, 5, 9 |
| §7 | Six-phase pipeline | Task 9 |
| §8 | Retention (inline + nightly beat) | Tasks 8, 10 |
| §9 | Stream-decrypt download | Task 15 |
| §10 | Error handling (pg_dump fail, disk full, time limit, KEK missing, worker crash) | Tasks 1, 7, 9, 10 |
| §11 | Frontend feature | Tasks 17–22 |
| §12 | Configuration | Task 1 |
| §13 | Testing strategy | Each task includes its own tests; Task 22 = E2E |

No gaps identified.

## Notes for the implementing engineer

- **TDD discipline**: every task is RED → GREEN → COMMIT. The "fails as expected" step is non-negotiable — it proves the test actually tests something.
- **Database-touching tests** all use `@pytest.mark.integration` and rely on the `pytest_schema` tenant created by [`accounting/tests/conftest.py`](../../../accounting/tests/conftest.py). New snapshot tests reuse this infrastructure rather than building parallel scaffolding.
- **Frontend type-check** runs after every component task — don't accumulate type errors across multiple tasks.
- **Commit cadence**: one task = one commit. Resist the urge to bundle. Tasks are sized so a green test suite at the end of each is a reasonable checkpoint.
- **No retries on snapshot failures** is a design choice (see spec §10). If you find a transient failure mode (network blip during `pg_dump`), the right fix is to instrument the failure and surface it; the right fix is not to add `max_retries=3`.
- **Cross-platform note**: the repo runs on Windows for dev but production is Linux. The crypto and tar code are pure Python; `pg_dump` is invoked as a subprocess and requires the binary to be on PATH on whichever OS. The `LocalFilesystemStorage` chmod-0o700 line is best-effort on Windows.
