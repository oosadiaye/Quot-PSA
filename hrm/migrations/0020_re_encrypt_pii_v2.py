"""Re-encrypt Employee PII v1 → v2 (HKDF + per-row salt + domain info).

V1 envelope was a bare Fernet token under a SHA-256-derived key (no
salt, no KDF cost, no domain separation). V2 wraps the ciphertext as
``v2:<base64-salt>:<base64-fernet-token>`` with the key derived via
HKDF-SHA256 over (SECRET_KEY, per-row salt, info=``b'pii-encryption-v1'``).

Iterates in 500-row chunks. Idempotent: rows whose column already
starts with ``v2:`` are skipped. Reverse op is a no-op (decrypting back
to v1 would be a security regression).

The ``<field>_hash`` columns are **not** touched — the HMAC key and
normalisation rules have not changed, so search-by-hash continues to
work across the migration boundary.

DEPLOYMENT WARNING
------------------
Take a verified database backup before running on production. The
re-encryption is in-place; if SECRET_KEY changes between forward and
this migration, v1 rows become unrecoverable.
"""

from __future__ import annotations

import logging

from django.db import migrations


PII_FIELDS = [
    'national_id_number',
    'tax_identification_number',
    'social_security_number',
    'bank_account',
    'bank_routing',
]

BATCH_SIZE = 500
V2_PREFIX = 'v2:'

logger = logging.getLogger(__name__)


def forwards(apps, schema_editor):
    from core.security.pii_crypto import decrypt_pii, encrypt_pii

    Employee = apps.get_model('hrm', 'Employee')

    update_fields = list(PII_FIELDS)  # ``_encrypted`` flag and ``_hash`` unchanged.

    batch: list = []
    total = 0
    batch_no = 0

    def flush():
        nonlocal batch, batch_no, total
        if not batch:
            return
        Employee.objects.bulk_update(batch, update_fields)
        total += len(batch)
        batch_no += 1
        logger.info(
            'hrm.0020: re-encrypted batch %s (%s rows total)',
            batch_no,
            total,
        )
        batch = []

    for emp in Employee.objects.all().iterator(chunk_size=BATCH_SIZE):
        changed = False
        for name in PII_FIELDS:
            if not getattr(emp, f'{name}_encrypted', False):
                continue
            raw = getattr(emp, name, '') or ''
            if not raw:
                continue
            if raw.startswith(V2_PREFIX):
                continue  # Already v2.
            try:
                plaintext = decrypt_pii(raw)
            except Exception:  # noqa: BLE001 — log and skip; do not abort.
                logger.exception(
                    'hrm.0020: failed to decrypt Employee.pk=%s field=%s; '
                    'leaving as-is',
                    emp.pk,
                    name,
                )
                continue
            if not plaintext:
                continue
            setattr(emp, name, encrypt_pii(plaintext))
            changed = True

        if changed:
            batch.append(emp)

        if len(batch) >= BATCH_SIZE:
            flush()

    flush()
    logger.info('hrm.0020: re-encryption complete (%s employees)', total)


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0019_backfill_employee_pii_encryption'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
