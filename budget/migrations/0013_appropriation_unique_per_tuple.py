"""Enforce one active Appropriation per (MDA, Economic, Fund, FiscalYear).

Before the constraint can be added, we must collapse existing duplicates.
Per the business rule: a second entry for the same dimension tuple is
conceptually a supplementary appropriation, not a distinct row. Merge
strategy:

  1. Group ACTIVE appropriations by (administrative, economic, fund,
     fiscal_year). For each group with >1 row:
  2. Keep the oldest pk as the canonical row.
  3. Sum ``amount_approved`` and ``original_amount`` from the duplicates
     into the canonical row.
  4. Re-parent every FK dependent (procurement.ProcurementBudgetLink,
     budget.Warrant, accounting.PaymentVoucher) from the duplicate pks
     to the canonical pk.
  5. Delete the duplicate rows.
  6. Add UniqueConstraint so this state cannot regress.

If duplicates exist in non-ACTIVE status they are left alone — those
represent historical/closed appropriations that legitimately coexist
with a new active row.
"""
from django.db import migrations, models


def merge_duplicate_active_appropriations(apps, schema_editor):
    Appropriation = apps.get_model('budget', 'Appropriation')
    ProcurementBudgetLink = apps.get_model('procurement', 'ProcurementBudgetLink')
    Warrant = apps.get_model('budget', 'Warrant')
    # The model that carries the appropriation FK is PaymentVoucherGov
    # (the public-sector variant). The older PaymentVoucher has no such
    # field, so we only need to re-parent rows on the Gov model.
    PaymentVoucherGov = apps.get_model('accounting', 'PaymentVoucherGov')

    duplicate_keys = (
        Appropriation.objects.filter(status='ACTIVE')
        .values('administrative_id', 'economic_id', 'fund_id', 'fiscal_year_id')
        .annotate(n=models.Count('id'))
        .filter(n__gt=1)
    )

    for key in duplicate_keys:
        rows = list(
            Appropriation.objects.filter(
                status='ACTIVE',
                administrative_id=key['administrative_id'],
                economic_id=key['economic_id'],
                fund_id=key['fund_id'],
                fiscal_year_id=key['fiscal_year_id'],
            ).order_by('pk')
        )
        canonical = rows[0]
        extras = rows[1:]

        # Sum amount_approved and original_amount into canonical
        total_approved = sum((r.amount_approved or 0) for r in rows)
        total_original = sum((r.original_amount or r.amount_approved or 0) for r in rows)
        canonical.amount_approved = total_approved
        if canonical.original_amount is not None or any(r.original_amount for r in rows):
            canonical.original_amount = total_original

        # Reset denormalised totals — will be rebuilt by
        # accounting.services.appropriation_totals.refresh_totals on next read.
        canonical.cached_total_committed = None
        canonical.cached_total_expended = None
        canonical.save(update_fields=[
            'amount_approved', 'original_amount',
            'cached_total_committed', 'cached_total_expended',
        ])

        extra_pks = [r.pk for r in extras]
        # Re-parent all FK dependents
        ProcurementBudgetLink.objects.filter(appropriation_id__in=extra_pks).update(
            appropriation_id=canonical.pk,
        )
        Warrant.objects.filter(appropriation_id__in=extra_pks).update(
            appropriation_id=canonical.pk,
        )
        PaymentVoucherGov.objects.filter(appropriation_id__in=extra_pks).update(
            appropriation_id=canonical.pk,
        )

        # Delete the duplicate appropriations
        Appropriation.objects.filter(pk__in=extra_pks).delete()


def no_op_reverse(apps, schema_editor):
    """Reverse is a no-op — we cannot reconstruct the original rows."""
    pass


class Migration(migrations.Migration):
    # Non-atomic: the RunPython step re-parents FK rows and deletes
    # duplicates. PostgreSQL refuses to create the UniqueConstraint index
    # in the same transaction because the FK trigger events are still
    # pending on the updated rows. Splitting the RunPython and the
    # AddConstraint across transaction boundaries avoids that.
    atomic = False

    dependencies = [
        ('budget', '0012_appropriation_denormalised_totals'),
        ('procurement', '0001_initial'),
        ('accounting', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_active_appropriations, no_op_reverse),
        migrations.AddConstraint(
            model_name='appropriation',
            constraint=models.UniqueConstraint(
                fields=['administrative', 'economic', 'fund', 'fiscal_year'],
                condition=models.Q(status='ACTIVE'),
                name='uniq_active_appropriation_per_dimension_tuple',
            ),
        ),
    ]
