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
