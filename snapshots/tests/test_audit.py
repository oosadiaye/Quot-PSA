"""Tests for snapshots.audit — lifecycle event recorders.

All recorders are best-effort: DB write failures must not raise.
Log emission is the primary observable in unit tests.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers / shared fixtures ───────────────────────────────────────────────

def _make_actor(pk: int = 1) -> MagicMock:
    actor = MagicMock()
    actor.pk = pk
    return actor


def _make_job(pk: int = 42, schema_name: str = 'tenant_acme') -> MagicMock:
    job = MagicMock()
    job.pk = pk
    job.schema_name = schema_name
    job.size_bytes = 1024
    return job


# ── Test 1: record_created emits a log with action='snapshot.created' ───────

def test_record_created_emits_log(caplog):
    from snapshots.audit import record_created

    actor = _make_actor()
    job = _make_job()

    with caplog.at_level(logging.INFO, logger='snapshots.audit'):
        with patch('snapshots.audit._write_audit_row'):
            record_created(actor, job)

    assert any(
        'snapshot.created' in r.message
        for r in caplog.records
    ), f"Expected 'snapshot.created' in log records; got: {[r.message for r in caplog.records]}"


# ── Test 2: record_succeeded emits a log ────────────────────────────────────

def test_record_succeeded_emits_log(caplog):
    from snapshots.audit import record_succeeded

    job = _make_job()

    with caplog.at_level(logging.INFO, logger='snapshots.audit'):
        with patch('snapshots.audit._write_audit_row'):
            record_succeeded(job)

    assert any(
        'snapshot.succeeded' in r.message
        for r in caplog.records
    ), f"Expected 'snapshot.succeeded' in log records; got: {[r.message for r in caplog.records]}"


# ── Test 3: record_failed includes error details in the log ─────────────────

def test_record_failed_includes_error_details(caplog):
    from snapshots.audit import record_failed

    job = _make_job()
    error_class = 'RuntimeError'
    error_message = 'pg_dump exited with code 1'

    with caplog.at_level(logging.INFO, logger='snapshots.audit'):
        with patch('snapshots.audit._write_audit_row'):
            record_failed(job, error_class, error_message)

    combined = ' '.join(r.message for r in caplog.records)
    assert 'snapshot.failed' in combined, f"Expected 'snapshot.failed'; got: {combined}"
    assert error_class in combined, f"Expected error_class '{error_class}'; got: {combined}"
    assert error_message in combined, f"Expected error_message in log; got: {combined}"


# ── Test 4: record_downloaded includes ip_address in the log ────────────────

def test_record_downloaded_includes_ip_address(caplog):
    from snapshots.audit import record_downloaded

    actor = _make_actor()
    job = _make_job()
    ip = '203.0.113.5'

    with caplog.at_level(logging.INFO, logger='snapshots.audit'):
        with patch('snapshots.audit._write_audit_row'):
            record_downloaded(actor, job, ip_address=ip)

    combined = ' '.join(r.message for r in caplog.records)
    assert 'snapshot.downloaded' in combined, (
        f"Expected 'snapshot.downloaded'; got: {combined}"
    )
    assert ip in combined, f"Expected IP '{ip}' in log; got: {combined}"


# ── Test 5: record_deleted with a real actor ────────────────────────────────

def test_record_deleted_with_actor(caplog):
    from snapshots.audit import record_deleted

    actor = _make_actor(pk=7)
    job = _make_job(pk=99)

    with caplog.at_level(logging.INFO, logger='snapshots.audit'):
        with patch('snapshots.audit._write_audit_row'):
            record_deleted(actor, job)

    combined = ' '.join(r.message for r in caplog.records)
    assert 'snapshot.deleted' in combined, f"Expected 'snapshot.deleted'; got: {combined}"
    assert 'actor_id=7' in combined, f"Expected actor_id=7 in log; got: {combined}"


# ── Test 6: record_expired — system action, no actor ────────────────────────

def test_record_expired_with_no_actor(caplog):
    from snapshots.audit import record_expired

    job = _make_job(pk=55)

    with caplog.at_level(logging.INFO, logger='snapshots.audit'):
        with patch('snapshots.audit._write_audit_row'):
            record_expired(job)

    combined = ' '.join(r.message for r in caplog.records)
    assert 'snapshot.expired' in combined, f"Expected 'snapshot.expired'; got: {combined}"
    # actor_id must be None for system events
    assert 'actor_id=None' in combined, f"Expected actor_id=None in log; got: {combined}"


# ── Test 7: DB write failure does not raise ──────────────────────────────────

def test_audit_db_write_failure_does_not_raise(caplog):
    """Patching _write_audit_row to raise must not propagate."""
    from snapshots.audit import record_created

    actor = _make_actor()
    job = _make_job()

    with patch(
        'snapshots.audit._write_audit_row',
        side_effect=Exception('DB connection lost'),
    ):
        with caplog.at_level(logging.WARNING, logger='snapshots.audit'):
            # Must NOT raise despite the DB failure.
            record_created(actor, job)

    # A WARNING must have been emitted for the failure.
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any('DB write failed' in msg for msg in warning_messages), (
        f"Expected a 'DB write failed' warning; got: {warning_messages}"
    )
