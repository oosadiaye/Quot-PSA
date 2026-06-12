"""pg_dump subprocess wrapper — flag construction + error handling + DSN scrubbing."""
from __future__ import annotations

import subprocess

import pytest

from snapshots.services.dump import (
    PgDumpError,
    _split_dsn,
    build_pg_dump_argv,
    run_pg_dump,
)


@pytest.mark.unit
def test_argv_mirrors_backup_sh_flags():
    """Flags must match scripts/backup.sh exactly — equality, not subset."""
    argv = build_pg_dump_argv(
        pg_dump_bin='pg_dump',
        schema='delta_state',
        dsn='postgres://u@host:5432/db',
    )
    assert argv[0] == 'pg_dump'
    assert argv[-1] == 'postgres://u@host:5432/db'
    inner_flags = set(argv[1:-1])
    expected = {
        '--schema=delta_state',
        '--no-owner', '--no-privileges',
        '--clean', '--if-exists',
        '--format=plain',
        '--quote-all-identifiers',
    }
    assert inner_flags == expected, f'extra/missing flags: {inner_flags ^ expected}'


@pytest.mark.unit
def test_argv_rejects_schema_with_quotes():
    with pytest.raises(ValueError):
        build_pg_dump_argv(pg_dump_bin='pg_dump',
                          schema='evil"; DROP TABLE--', dsn='x')


@pytest.mark.unit
def test_split_dsn_extracts_password_into_env():
    clean, env = _split_dsn('postgres://user:s3cret@host:5432/db')
    assert 's3cret' not in clean
    assert env == {'PGPASSWORD': 's3cret'}
    assert clean == 'postgres://user@host:5432/db'


@pytest.mark.unit
def test_split_dsn_returns_original_when_no_password():
    clean, env = _split_dsn('postgres://user@host:5432/db')
    assert clean == 'postgres://user@host:5432/db'
    assert env == {}


@pytest.mark.unit
def test_run_pg_dump_passes_password_via_env_not_argv(tmp_path, monkeypatch):
    """Critical: password must NOT appear in argv. Must be in env."""
    captured = {}

    def fake_run(argv, *args, **kwargs):
        captured['argv'] = list(argv)
        captured['env'] = dict(kwargs.get('env') or {})
        stdout_file = kwargs.get('stdout')
        if stdout_file is not None:
            stdout_file.write(b'-- ok\n')
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=None, stderr=b'')
    monkeypatch.setattr(subprocess, 'run', fake_run)

    target = tmp_path / 'out.sql'
    run_pg_dump(
        schema='delta_state',
        dsn='postgres://user:s3cret@host:5432/db',
        target=target, pg_dump_bin='pg_dump',
    )

    assert not any('s3cret' in arg for arg in captured['argv']), \
        f'password leaked into argv: {captured["argv"]}'
    assert captured['env'].get('PGPASSWORD') == 's3cret'


@pytest.mark.unit
def test_run_pg_dump_raises_on_nonzero_exit(tmp_path, monkeypatch):
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
    payload = b'-- pg dump start\nSELECT 1;\n'

    def fake_run(argv, *args, **kwargs):
        stdout_file = kwargs.get('stdout')
        if stdout_file is not None:
            stdout_file.write(payload)
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=None, stderr=b'')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    target = tmp_path / 'out.sql'
    run_pg_dump(schema='delta_state', dsn='x', target=target,
               pg_dump_bin='pg_dump')
    assert target.read_bytes() == payload


@pytest.mark.unit
def test_run_pg_dump_cleans_up_target_on_failure(tmp_path, monkeypatch):
    """Partial file must be removed on nonzero exit."""
    def fake_run(argv, *args, **kwargs):
        stdout_file = kwargs.get('stdout')
        if stdout_file is not None:
            stdout_file.write(b'-- partial\n')
        return subprocess.CompletedProcess(
            args=argv, returncode=1, stdout=None, stderr=b'boom')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    target = tmp_path / 'out.sql'
    with pytest.raises(PgDumpError):
        run_pg_dump(schema='delta_state', dsn='x', target=target,
                   pg_dump_bin='pg_dump')
    assert not target.exists(), 'partial output file was left on disk'


@pytest.mark.unit
def test_run_pg_dump_wraps_timeout_as_pgdumperror(tmp_path, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd='pg_dump', timeout=1)
    monkeypatch.setattr(subprocess, 'run', fake_run)
    target = tmp_path / 'out.sql'
    with pytest.raises(PgDumpError, match='timed out'):
        run_pg_dump(schema='delta_state', dsn='x', target=target,
                   pg_dump_bin='pg_dump', timeout_sec=1)
    assert not target.exists()


@pytest.mark.unit
def test_run_pg_dump_wraps_missing_binary_as_pgdumperror(tmp_path, monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError(2, 'No such file or directory', 'pg_dump_nope')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    target = tmp_path / 'out.sql'
    with pytest.raises(PgDumpError, match='not found'):
        run_pg_dump(schema='delta_state', dsn='x', target=target,
                   pg_dump_bin='pg_dump_nope')
    assert not target.exists()
