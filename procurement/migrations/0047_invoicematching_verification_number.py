"""Add verification_number tracking ID to InvoiceMatching.

Allocates a stable in-house tracking number (IV-NNNNNN) for every
Invoice Verification record so users have something to quote when
referring to a specific verification — distinct from the vendor's own
``invoice_reference`` which can collide across vendors.

Backfills existing rows in chronological order so the oldest
verification gets IV-000001, the next IV-000002, etc. The
TransactionSequence row is then advanced past the highest backfilled
number so future allocations don't collide.
"""
from django.db import migrations, models


def backfill_verification_numbers(apps, schema_editor):
    InvoiceMatching = apps.get_model('procurement', 'InvoiceMatching')
    TransactionSequence = apps.get_model('accounting', 'TransactionSequence')

    counter = 0
    qs = InvoiceMatching.objects.filter(
        verification_number=''
    ).order_by('created_at', 'id')
    for matching in qs:
        counter += 1
        matching.verification_number = f"IV-{counter:06d}"
        matching.save(update_fields=['verification_number'])

    # Advance the sequence so future allocations start AFTER the highest
    # backfilled number. Idempotent on re-run.
    if counter > 0:
        seq, _ = TransactionSequence.objects.get_or_create(
            name='invoice_verification',
            defaults={'prefix': 'IV-', 'next_value': counter + 1},
        )
        if seq.next_value <= counter:
            seq.next_value = counter + 1
            seq.prefix = 'IV-'
            seq.save(update_fields=['next_value', 'prefix'])


def reverse_backfill(apps, schema_editor):
    # Non-destructive reverse — keep the numbers, since dropping the
    # column will discard them anyway when this migration is fully
    # rolled back.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0046_widen_invoice_variance_percentage'),
        ('accounting', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoicematching',
            name='verification_number',
            field=models.CharField(
                blank=True, db_index=True, default='',
                help_text='In-house tracking number, e.g. IV-2026-00001.',
                max_length=30,
            ),
        ),
        migrations.RunPython(
            backfill_verification_numbers, reverse_backfill,
        ),
    ]
