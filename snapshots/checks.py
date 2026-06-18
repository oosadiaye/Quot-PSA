"""Django startup checks: refuse to boot without a valid KEK in production."""
from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning

_HEX_RE = re.compile(r'[0-9a-fA-F]+')


def check_snapshot_kek(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Validate SNAPSHOTS_KEK_HEX. In DEBUG, downgrade missing-key to Warning."""
    errors: list[CheckMessage] = []
    kek_raw = getattr(settings, 'SNAPSHOTS_KEK_HEX', None)
    debug = getattr(settings, 'DEBUG', False)

    if not kek_raw:
        if debug:
            errors.append(Warning(
                'SNAPSHOTS_KEK_HEX is not set. Snapshot creation will fail.',
                hint='Set SNAPSHOTS_KEK_HEX to a 64-char hex string (32 bytes).',
                id='snapshots.W001',
            ))
        else:
            errors.append(Error(
                'SNAPSHOTS_KEK_HEX must be set in non-DEBUG environments.',
                hint='Set SNAPSHOTS_KEK_HEX to a 64-char hex string (32 bytes).',
                id='snapshots.E001',
            ))
        return errors

    kek = kek_raw.strip()  # tolerate operator-supplied leading/trailing whitespace

    if len(kek) != 64:
        errors.append(Error(
            f'SNAPSHOTS_KEK_HEX must be exactly 64 hex chars after stripping '
            f'whitespace (got {len(kek)}).',
            id='snapshots.E002',
        ))
    elif not _HEX_RE.fullmatch(kek):
        errors.append(Error(
            'SNAPSHOTS_KEK_HEX must contain only hex characters (0-9 a-f).',
            id='snapshots.E003',
        ))
    return errors
