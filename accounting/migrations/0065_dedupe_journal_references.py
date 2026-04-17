"""
Dedupe JournalHeader.reference_number BEFORE the UniqueConstraint in 0066
can be applied (S1-02 prerequisite).

Legacy data contains duplicate references from the race condition in
JournalSequenceService (fixed in S1-05). For every duplicate group, we
keep the earliest-posted row's reference as-is and suffix every later
duplicate with ``_dup_<pk>`` so auditors can still reconcile them.
"""
from django.db import migrations


def dedupe_refs(apps, schema_editor):
    JournalHeader = apps.get_model('accounting', 'JournalHeader')
    from django.db.models import Count

    dup_refs = (
        JournalHeader.objects
        .exclude(reference_number='')
        .values('reference_number')
        .annotate(n=Count('id'))
        .filter(n__gt=1)
        .values_list('reference_number', flat=True)
    )

    for ref in list(dup_refs):
        rows = list(
            JournalHeader.objects
            .filter(reference_number=ref)
            .order_by('posting_date', 'id')
        )
        for dup in rows[1:]:
            new_ref = f'{ref}_dup_{dup.pk}'[:50]
            JournalHeader.objects.filter(pk=dup.pk).update(reference_number=new_ref)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0064_paymentinstruction_is_reconciled_and_more'),
    ]

    operations = [
        migrations.RunPython(dedupe_refs, noop_reverse),
    ]
