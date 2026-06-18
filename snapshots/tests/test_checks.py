"""System checks: refuse to start without a valid KEK."""
from __future__ import annotations

import pytest
from django.core.checks import ERROR
from django.test import override_settings

from snapshots.checks import check_snapshot_kek


@pytest.mark.unit
def test_kek_missing_raises_error_in_production():
    with override_settings(DEBUG=False, SNAPSHOTS_KEK_HEX=None):
        errors = check_snapshot_kek(app_configs=None)
        assert any(e.id == 'snapshots.E001' for e in errors)


@pytest.mark.unit
def test_kek_wrong_length_raises_error():
    bad = '00' * 16  # 32 hex chars = 16 bytes; we need 32 bytes (64 hex chars)
    with override_settings(DEBUG=False, SNAPSHOTS_KEK_HEX=bad):
        errors = check_snapshot_kek(app_configs=None)
        assert any(e.id == 'snapshots.E002' for e in errors)


@pytest.mark.unit
def test_kek_non_hex_raises_error():
    bad = 'ZZ' * 32  # right length, wrong alphabet
    with override_settings(DEBUG=False, SNAPSHOTS_KEK_HEX=bad):
        errors = check_snapshot_kek(app_configs=None)
        assert any(e.id == 'snapshots.E003' for e in errors)


@pytest.mark.unit
def test_kek_valid_returns_no_errors():
    good = 'aa' * 32  # 64 hex chars = 32 bytes
    with override_settings(DEBUG=False, SNAPSHOTS_KEK_HEX=good):
        errors = check_snapshot_kek(app_configs=None)
        assert errors == []


@pytest.mark.unit
def test_kek_missing_is_warning_in_debug():
    """In DEBUG, missing KEK is a warning, not an error — keeps dev loop fast."""
    with override_settings(DEBUG=True, SNAPSHOTS_KEK_HEX=None):
        errors = check_snapshot_kek(app_configs=None)
        # Either no error, or only Warning-level entries.
        assert all(e.level < ERROR for e in errors)
