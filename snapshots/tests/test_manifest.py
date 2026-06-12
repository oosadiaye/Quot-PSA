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
