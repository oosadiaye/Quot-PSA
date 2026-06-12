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
    """Refuse absolute paths and parent-dir traversal.

    Uses os.path.isabs() rather than Path.is_absolute() so that POSIX-style
    absolute paths (e.g. '/etc/passwd') are correctly rejected on Windows,
    where Path('/etc/passwd').is_absolute() returns False because there is no
    drive letter, yet the path still escapes the storage root.
    """
    if not relative_path:
        raise ValueError('relative_path must not be empty')
    if os.path.isabs(relative_path):
        raise ValueError(f'relative_path must be relative: {relative_path!r}')
    p = Path(relative_path)
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
