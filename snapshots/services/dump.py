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
        stderr = (completed.stderr or b'').decode('utf-8', errors='replace')
        raise PgDumpError(stderr[:4096])
