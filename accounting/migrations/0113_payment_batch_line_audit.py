"""Give PaymentBatchLine the standard audit columns.

A batch line IS the instruction to pay one named vendor one named sum.
"Who put this vendor on the letter, and when?" is the first question asked
about a disputed payment, and the model could not answer it — it subclassed
plain ``models.Model`` while its parent batch was audited.

Backfill: existing lines take their parent batch's ``created_at`` (the
closest true value available) and a NULL ``created_by``. NULL is honest —
the actor genuinely was not recorded at the time and inventing one would be
worse than admitting the gap.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_line_timestamps(apps, schema_editor):
    """Copy each batch's created_at onto its lines."""
    PaymentBatchLine = apps.get_model('accounting', 'PaymentBatchLine')
    for line in PaymentBatchLine.objects.select_related('batch').iterator():
        stamp = getattr(line.batch, 'created_at', None)
        if stamp is None:
            continue
        PaymentBatchLine.objects.filter(pk=line.pk).update(
            created_at=stamp, updated_at=stamp,
        )


def noop_reverse(apps, schema_editor):
    """Reversing just drops the columns; nothing to undo here."""


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounting', '0112_journal_balance_guard_case_insensitive'),
    ]

    operations = [
        # auto_now_add cannot be added without a default for existing rows;
        # add it nullable, backfill from the parent batch, then tighten.
        migrations.AddField(
            model_name='paymentbatchline',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='paymentbatchline',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name='paymentbatchline',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='%(class)s_created',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='paymentbatchline',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='%(class)s_updated',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_line_timestamps, noop_reverse),
        migrations.AlterField(
            model_name='paymentbatchline',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='paymentbatchline',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
