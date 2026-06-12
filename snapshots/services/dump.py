"""Subprocess wrapper around pg_dump.

Flags mirror scripts/backup.sh so the in-app pipeline produces
byte-compatible output with the operator-tier nightly cron.

Password handling: any password embedded in ``dsn`` is removed from
the argv vector and passed via the ``PGPASSWORD`` environment variable
to avoid leaking the credential into process listings.
"""
from __future__ import annotations

import os
import subprocess
import urllib.parse
from pathlib import Path

from snapshots.constants import SCHEMA_NAME_RE


class PgDumpError(RuntimeError):
    """pg_dump exited non-zero or could not be started. The message contains
    captured stderr (truncated to ~4 KB) or a descriptive failure reason."""


def _split_dsn(dsn: str) -> tuple[str, dict[str, str]]:
    """Strip a password from ``dsn`` and return (clean_dsn, extra_env).

    If ``dsn`` does not parse as a URL or contains no password, returns
    (dsn, {}) unchanged.
    """
    try:
        parsed = urllib.parse.urlparse(dsn)
    except ValueError:
        return dsn, {}
    if not parsed.password:
        return dsn, {}
    # Rebuild netloc without the password.
    user = parsed.username or ''
    host = parsed.hostname or ''
    port = f':{parsed.port}' if parsed.port else ''
    creds = f'{user}@' if user else ''
    new_netloc = f'{creds}{host}{port}'
    clean = parsed._replace(netloc=new_netloc)
    return urllib.parse.urlunparse(clean), {'PGPASSWORD': parsed.password}


def build_pg_dump_argv(*, pg_dump_bin: str, schema: str, dsn: str) -> list[str]:
    """Construct the argv vector for pg_dump. Refuses unsafe schema names
    even though SnapshotJob.CheckConstraint enforces the same regex at
    write time — defense in depth.

    Note: the DSN here is expected to be password-free. ``run_pg_dump``
    calls :func:`_split_dsn` before invoking this.
    """
    if not SCHEMA_NAME_RE.match(schema):
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
    """Run pg_dump streaming to ``target``. Raises PgDumpError on:
    nonzero exit, missing binary, or timeout.

    On any failure the partial output file is removed so callers cannot
    accidentally consume a corrupt SQL dump.
    """
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    clean_dsn, extra_env = _split_dsn(dsn)
    argv = build_pg_dump_argv(
        pg_dump_bin=pg_dump_bin, schema=schema, dsn=clean_dsn,
    )
    proc_env = {**os.environ, **extra_env}

    try:
        with open(target, 'wb') as out_fh:
            completed = subprocess.run(
                argv, stdout=out_fh, stderr=subprocess.PIPE,
                timeout=timeout_sec, env=proc_env,
            )
    except FileNotFoundError as exc:
        target.unlink(missing_ok=True)
        raise PgDumpError(
            f'pg_dump binary not found: {pg_dump_bin!r}') from exc
    except subprocess.TimeoutExpired as exc:
        target.unlink(missing_ok=True)
        raise PgDumpError(
            f'pg_dump timed out after {timeout_sec}s') from exc

    if completed.returncode != 0:
        target.unlink(missing_ok=True)
        raw = (completed.stderr or b'').decode('utf-8', errors='replace')
        msg = raw[:4096]
        if len(raw) > 4096:
            msg += ' … [truncated]'
        raise PgDumpError(msg)
