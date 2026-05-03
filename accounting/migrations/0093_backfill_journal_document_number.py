"""Backfill JournalHeader.document_number for journals that were
created before the auto-allocation logic landed in JournalHeader.save().

Background
----------
The Journal Entries list shows ``document_number`` in its DOCUMENT NO
column. ~60 journal-creation sites across the codebase historically
set ``reference_number`` only (e.g. ``JE-000006`` for vendor-
registration revenue postings) and never populated ``document_number``,
leaving the column rendered as ``-``.

The model-level fix in ``JournalHeader.save()`` auto-allocates a
``JV-####`` number on first save going forward. This migration applies
the same allocation retroactively to any existing journal where
``document_number`` is null or empty so historical rows display
properly in the list.

Idempotent
----------
Only fills blank/null values; never overwrites a populated
``document_number``. Safe to re-run if you ``--fake`` it or restore
from a snapshot.
"""
from django.db import migrations
from django.db.models import Q


def backfill_document_numbers(apps, schema_editor):
    JournalHeader = apps.get_model('accounting', 'JournalHeader')
    TransactionSequence = apps.get_model('accounting', 'TransactionSequence')

    # The historical model class lacks the ``get_next`` classmethod
    # (apps.get_model returns a frozen schema-only class). Replicate
    # the sequence-allocation logic inline. The actual model field is
    # ``next_value`` (PositiveIntegerField, default=1) — the value to
    # be HANDED OUT on the next allocation, then incremented.
    blank_qs = JournalHeader.objects.filter(
        Q(document_number__isnull=True) | Q(document_number='')
    ).order_by('id')

    if not blank_qs.exists():
        return

    seq, _ = TransactionSequence.objects.get_or_create(
        name='journal_voucher',
        defaults={'prefix': 'JV-', 'next_value': 1},
    )
    # Make sure prefix is sane on legacy rows.
    if not seq.prefix:
        seq.prefix = 'JV-'
        seq.save(update_fields=['prefix'])

    n = seq.next_value or 1
    to_update = []
    for jh in blank_qs:
        jh.document_number = f"{seq.prefix}{n:06d}"
        to_update.append(jh)
        n += 1

    # Bulk-update in chunks of 500 to avoid a giant single statement.
    BATCH = 500
    for i in range(0, len(to_update), BATCH):
        JournalHeader.objects.bulk_update(
            to_update[i:i + BATCH], ['document_number']
        )

    seq.next_value = n
    seq.save(update_fields=['next_value'])


def reverse_backfill(apps, schema_editor):
    """Best-effort reverse — clears document_number on rows that look
    like the legacy backfill (have a JV- prefix + reference_number not
    starting with JV-, indicating the doc number wasn't manually set).
    Pure data correction, not destructive.
    """
    JournalHeader = apps.get_model('accounting', 'JournalHeader')
    JournalHeader.objects.filter(
        document_number__startswith='JV-',
    ).exclude(reference_number__startswith='JV-').update(document_number='')


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0092_widen_default_budget_rule'),
    ]

    operations = [
        migrations.RunPython(backfill_document_numbers, reverse_backfill),
    ]
