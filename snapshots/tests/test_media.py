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


@pytest.mark.unit
def test_rejects_parent_dir_traversal_in_rel_path(tmp_path):
    """rel_path with ../ must be refused before any filesystem I/O."""
    media_root = tmp_path / 'media'
    media_root.mkdir()
    out_dir = tmp_path / 'out'
    out_dir.mkdir()

    # Create a file outside media_root that the traversal would target.
    outside = tmp_path / 'secret.txt'
    outside.write_bytes(b'SECRET')

    from snapshots.services.media import _copy_one
    result = _copy_one(
        rel_path='../secret.txt',
        media_root=media_root,
        destination=out_dir,
    )
    assert result is False
    # The outside file must NOT have been copied into out_dir.
    assert list(out_dir.rglob('*')) == []


@pytest.mark.unit
def test_rejects_absolute_path_in_rel_path(tmp_path):
    """rel_path that is absolute must be refused."""
    media_root = tmp_path / 'media'
    media_root.mkdir()
    out_dir = tmp_path / 'out'
    out_dir.mkdir()

    from snapshots.services.media import _copy_one
    result = _copy_one(
        rel_path='/etc/passwd',  # absolute
        media_root=media_root,
        destination=out_dir,
    )
    assert result is False
    assert list(out_dir.rglob('*')) == []


@pytest.mark.unit
def test_rejects_symlink_escape_via_resolve(tmp_path):
    """A symlink inside media_root pointing outside must not let a copy escape."""
    media_root = tmp_path / 'media'
    media_root.mkdir()
    out_dir = tmp_path / 'out'
    out_dir.mkdir()

    outside = tmp_path / 'outside_target'
    outside.mkdir()
    secret = outside / 'secret.txt'
    secret.write_bytes(b'SECRET')

    # Create a symlink inside media_root pointing to outside dir.
    link = media_root / 'maybe_legit'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip('symlinks not supported on this platform/user')

    from snapshots.services.media import _copy_one
    result = _copy_one(
        rel_path='maybe_legit/secret.txt',
        media_root=media_root,
        destination=out_dir,
    )
    assert result is False
    assert list(out_dir.rglob('*')) == []
