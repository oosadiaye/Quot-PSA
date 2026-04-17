"""P6-T2 — denormalise Appropriation.total_committed / .total_expended.

Before: every Appropriation card load triggered 2 × aggregate queries
        per row — the Budget dashboard ran 6N queries for N
        appropriations (commitment Sum + expended Sum × 3 sources).
After:  columns cached; refreshed by ``accounting.services.appropriation_totals``
        on commit/invoice/payment events + a management command for
        full re-sync.

Property accessors in ``Appropriation.total_committed`` / ``.total_expended``
prefer the cached column and fall back to the live aggregate when the
cache column is NULL (so older rows keep working until backfill runs).
"""
from django.db import migrations, models


def backfill_cached_totals(apps, schema_editor):
    """Populate cache columns from live aggregates for every Appropriation."""
    from decimal import Decimal
    from django.db.models import Sum

    Appropriation = apps.get_model('budget', 'Appropriation')
    ProcurementBudgetLink = apps.get_model('procurement', 'ProcurementBudgetLink')

    for appr in Appropriation.objects.iterator(chunk_size=500):
        committed = ProcurementBudgetLink.objects.filter(
            appropriation=appr,
            status__in=['ACTIVE', 'INVOICED'],
        ).aggregate(t=Sum('committed_amount'))['t'] or Decimal('0')

        expended = ProcurementBudgetLink.objects.filter(
            appropriation=appr, status='CLOSED',
        ).aggregate(t=Sum('committed_amount'))['t'] or Decimal('0')

        Appropriation.objects.filter(pk=appr.pk).update(
            cached_total_committed=committed,
            cached_total_expended=expended,
        )


def noop_reverse(apps, schema_editor):
    """Dropping the columns discards the cache — no reverse backfill needed."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ('budget', '0011_appropriation_geographic'),
        ('procurement', '0042_perf_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='appropriation',
            name='cached_total_committed',
            field=models.DecimalField(
                max_digits=20, decimal_places=2, null=True, blank=True,
                help_text='Denormalised sum of open commitments. '
                          'Maintained by accounting.services.appropriation_totals.',
            ),
        ),
        migrations.AddField(
            model_name='appropriation',
            name='cached_total_expended',
            field=models.DecimalField(
                max_digits=20, decimal_places=2, null=True, blank=True,
                help_text='Denormalised sum of CLOSED commitments + direct AP. '
                          'Maintained by accounting.services.appropriation_totals.',
            ),
        ),
        migrations.AddField(
            model_name='appropriation',
            name='cached_totals_refreshed_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.RunPython(backfill_cached_totals, noop_reverse),
    ]
