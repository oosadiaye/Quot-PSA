"""
pytest fixtures for snapshots/tests.

SnapshotJob lives in the PUBLIC schema (snapshots is in SHARED_APPS).
No tenant-schema plumbing is needed here: pytest-django's built-in
django_db_setup runs ``migrate`` against the default database, which
covers all SHARED_APPS tables (including snapshots_snapshotjob) before
any integration test touches the DB.
"""
from __future__ import annotations

import pytest
from django.test import override_settings


KEK_HEX = 'aa' * 32   # 64 hex chars = 32 bytes


@pytest.fixture
def kek_hex() -> str:
    return KEK_HEX


@pytest.fixture
def snapshots_storage_root(tmp_path):
    """tmp_path subdir; the SnapshotService will mkdir it."""
    return tmp_path / 'snapshots_storage'


@pytest.fixture
def configured_settings(snapshots_storage_root):
    """Override SNAPSHOTS_* settings for the duration of one test."""
    with override_settings(
        SNAPSHOTS_KEK_HEX=KEK_HEX,
        SNAPSHOTS_KEK_ID='kek-test',
        SNAPSHOTS_BACKUP_DIR=str(snapshots_storage_root),
        SNAPSHOTS_RETENTION_DAYS=14,
        SNAPSHOTS_MAX_PER_TENANT=5,
        SNAPSHOTS_PG_DUMP_BIN='pg_dump',
        SNAPSHOTS_SOFT_TIME_LIMIT_SEC=60,
        SNAPSHOTS_HARD_TIME_LIMIT_SEC=120,
    ):
        yield
