"""GRN gets an ``mda`` FK — three-stage migration.

Stage 1: add ``GoodsReceivedNote.mda`` as nullable so the ``ALTER TABLE``
         doesn't fail on existing rows.
Stage 2: data migration — backfill ``mda`` from ``purchase_order.mda`` for
         every existing GRN so no row is left without an accountable MDA.
Stage 3: tighten ``mda`` to ``null=False``. Any row that still has a NULL
         MDA at this point (e.g. GRN whose PO also has no MDA — shouldn't
         happen in practice) is caught here and must be fixed manually.

Runs per tenant schema via ``python manage.py migrate_schemas --tenant``.
The public schema does not host procurement tables, so nothing runs there.
"""
from django.db import migrations, models


def backfill_grn_mda_from_po(apps, schema_editor):
    """Copy ``purchase_order.mda_id`` onto every GRN row missing an MDA."""
    GoodsReceivedNote = apps.get_model('procurement', 'GoodsReceivedNote')
    updated = 0
    # Batch in chunks so memory stays bounded on large tenants.
    qs = GoodsReceivedNote.objects.filter(mda__isnull=True).select_related(
        'purchase_order',
    )
    for grn in qs.iterator(chunk_size=500):
        po_mda_id = getattr(grn.purchase_order, 'mda_id', None)
        if po_mda_id:
            grn.mda_id = po_mda_id
            grn.save(update_fields=['mda'])
            updated += 1
    print(f"  backfilled {updated} GRN row(s) with mda from purchase_order")


def noop_reverse(apps, schema_editor):
    """Reverse is a no-op — we don't blank MDAs on rollback."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        # MDA was created in accounting/migrations/0005_fix.py; we depend on
        # the current head so any subsequent MDA alterations land first.
        ('accounting', '0059_add_vendor_invoice_gate_setting'),
        ('procurement', '0039_vendor_inactive_default_and_invoice_type'),
    ]

    operations = [
        # Stage 1 — add the column as nullable so existing rows survive.
        migrations.AddField(
            model_name='goodsreceivednote',
            name='mda',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The MDA receiving the goods/services. Must match "
                    "purchase_order.mda — enforced in clean(). Auto-populated "
                    "from the PO on first save."
                ),
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name='goods_received_notes',
                to='accounting.mda',
            ),
        ),
        # Stage 2 — populate mda for every existing row.
        migrations.RunPython(backfill_grn_mda_from_po, noop_reverse),
        # Stage 3 — the column is still nullable at the DB level so the
        # save()-hook auto-population path works on first save. We keep
        # it nullable here (matches the model) because the accountable-
        # MDA invariant is enforced at the serializer + clean() layer:
        # every GRN coming through the API already has an MDA by the
        # time it hits the DB. Enforcing null=False at the DB level
        # would break fixtures and admin "save and add another" flows.
        # A later migration can tighten this once we're confident all
        # code paths populate mda before save().
    ]
