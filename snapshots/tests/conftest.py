"""
pytest fixtures for snapshots/tests.

SnapshotJob lives in the PUBLIC schema (snapshots is in SHARED_APPS).
No tenant-schema plumbing is needed here: pytest-django's built-in
django_db_setup runs ``migrate`` against the default database, which
covers all SHARED_APPS tables (including snapshots_snapshotjob) before
any integration test touches the DB.
"""
from __future__ import annotations
