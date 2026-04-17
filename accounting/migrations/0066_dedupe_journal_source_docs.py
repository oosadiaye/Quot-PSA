"""
Dedupe Posted-journal (source_module, source_document_id) pairs BEFORE
the UniqueConstraint in 0067 can be applied.

Legacy data contains cases where the same source document produced two
Posted JournalHeaders — typically the race condition in
``_check_duplicate_posting`` (not atomic). The later duplicate(s) had no
actual business effect beyond inflating the GL; we flip them to 'Reversed'
status and mark them `is_reversed=True` so:

  * The uniqueness constraint in 0067 applies only to the single survivor.
  * Downstream reports that filter `status='Posted'` automatically exclude
    the dupes.
  * Auditors can still discover the dupes via reference_number search.

If your deployment has none of these (fresh install), this migration is a
no-op.
"""
from django.db import migrations


def dedupe_source_docs(apps, schema_editor):
    JournalHeader = apps.get_model('accounting', 'JournalHeader')
    from django.db.models import Count

    # Duplicate groups on (source_module, source_document_id) for Posted rows.
    dup_keys = (
        JournalHeader.objects
        .filter(status='Posted')
        .exclude(source_module__isnull=True)
        .exclude(source_document_id__isnull=True)
        .values('source_module', 'source_document_id')
        .annotate(n=Count('id'))
        .filter(n__gt=1)
    )

    for key in list(dup_keys):
        rows = list(
            JournalHeader.objects
            .filter(
                status='Posted',
                source_module=key['source_module'],
                source_document_id=key['source_document_id'],
            )
            .order_by('posting_date', 'id')
        )
        # Keep the first, mark the rest as Reversed.
        for dup in rows[1:]:
            JournalHeader.objects.filter(pk=dup.pk).update(
                status='Rejected',       # neutral; keeps it out of Posted reports
                is_reversed=True,
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0065_dedupe_journal_references'),
    ]

    operations = [
        migrations.RunPython(dedupe_source_docs, noop_reverse),
    ]
