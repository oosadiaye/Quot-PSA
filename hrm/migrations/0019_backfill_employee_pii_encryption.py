"""Backfill: encrypt existing Employee PII in place + populate HMAC hashes.

Idempotent (skips rows where ``<field>_encrypted=True``) and batched
(500-row chunks via :meth:`~django.db.models.QuerySet.iterator`) so it is
safe to re-run on a large table.

Reverse op is a no-op: un-encrypting requires deliberate operator
intervention (decrypt + rewrite) and is not something an accidental
``migrate <app> <prev>`` should perform.

DEPLOYMENT WARNING
------------------
Take a verified database backup before running on production. Once a
column is encrypted under the current ``SECRET_KEY``, losing or rotating
that key without a separate decrypt-and-rewrite pass renders the data
unrecoverable.
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

SEARCHABLE_FIELDS = {
    'national_id_number',
    'tax_identification_number',
    'bank_account',
}

BATCH_SIZE = 500

logger = logging.getLogger(__name__)


def forwards(apps, schema_editor):
    # Import inside the function so the helper is only resolved at
    # migrate-time (and the migration can be loaded by older code).
    from core.security.pii_crypto import encrypt_pii, pii_hash

    Employee = apps.get_model('hrm', 'Employee')

    update_fields = []
    for name in PII_FIELDS:
        update_fields.append(name)
        update_fields.append(f'{name}_encrypted')
        if name in SEARCHABLE_FIELDS:
            update_fields.append(f'{name}_hash')

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
        logger.info('hrm.0019: encrypted batch %s (%s rows total)', batch_no, total)
        batch = []

    for emp in Employee.objects.all().iterator(chunk_size=BATCH_SIZE):
        changed = False
        for name in PII_FIELDS:
            already = getattr(emp, f'{name}_encrypted', False)
            if already:
                continue
            value = getattr(emp, name, '') or ''
            if not value:
                continue
            setattr(emp, name, encrypt_pii(value))
            setattr(emp, f'{name}_encrypted', True)
            if name in SEARCHABLE_FIELDS:
                setattr(emp, f'{name}_hash', pii_hash(value))
            changed = True

        if changed:
            batch.append(emp)

        if len(batch) >= BATCH_SIZE:
            flush()

    flush()
    logger.info('hrm.0019: backfill complete (%s employees encrypted)', total)


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0018_employee_pii_encrypted_columns'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
