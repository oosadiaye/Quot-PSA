"""Re-encrypt UserMFA.secret v1 → v2 (HKDF + per-row salt + domain info).

V1 envelope was a bare Fernet token under a SHA-256-derived key (no
salt, no KDF cost, no domain separation). V2 wraps the ciphertext as
``v2:<base64-salt>:<base64-fernet-token>`` with the key derived via
HKDF-SHA256 over (SECRET_KEY, per-row salt, info=``b'mfa-encryption-v1'``).

Idempotent: rows whose ``secret`` already starts with ``v2:`` are
skipped. Reverse op is a no-op (decrypting back to v1 would be a
security regression).

DEPLOYMENT WARNING
------------------
Take a verified database backup before running on production. The
re-encryption is in-place; if SECRET_KEY changes between forward and
this migration, v1 rows become unrecoverable.
"""

from __future__ import annotations

import logging

from django.db import migrations


BATCH_SIZE = 500
V2_PREFIX = 'v2:'

logger = logging.getLogger(__name__)


def forwards(apps, schema_editor):
    # Import inside the function so the helpers are only resolved at
    # migrate-time (and the migration can be loaded by older code).
    from core.security.mfa_crypto import decrypt_secret, encrypt_secret

    UserMFA = apps.get_model('core', 'UserMFA')

    qs = (
        UserMFA.objects
        .filter(secret_encrypted=True)
        .exclude(secret='')
        .exclude(secret__startswith=V2_PREFIX)
    )

    total = 0
    for row in qs.iterator(chunk_size=BATCH_SIZE):
        try:
            plaintext = decrypt_secret(row.secret)
        except Exception:  # noqa: BLE001 — log and skip; do not abort.
            logger.exception(
                'core.0015: failed to decrypt UserMFA.pk=%s; leaving as-is',
                row.pk,
            )
            continue
        if not plaintext:
            # Empty plaintext under v1 is a degenerate case; clear flag.
            row.secret = ''
            row.secret_encrypted = False
        else:
            row.secret = encrypt_secret(plaintext)
            row.secret_encrypted = True
        row.save(update_fields=['secret', 'secret_encrypted'])
        total += 1
        if total % BATCH_SIZE == 0:
            logger.info('core.0015: re-encrypted %s MFA secrets so far', total)

    logger.info('core.0015: re-encryption complete (%s rows)', total)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_usermfa_secret_encrypted_alter_usermfa_secret'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
