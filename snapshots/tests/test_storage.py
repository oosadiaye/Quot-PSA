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
