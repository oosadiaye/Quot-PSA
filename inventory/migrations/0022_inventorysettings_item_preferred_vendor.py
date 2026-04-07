from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0021_alter_producttype_goods_in_transit_account_and_more'),
        ('procurement', '0001_initial'),  # adjust if procurement has a later migration
    ]

    operations = [
        # ── InventorySettings singleton ────────────────────────────────────────
        migrations.CreateModel(
            name='InventorySettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('auto_po_enabled', models.BooleanField(
                    default=False,
                    help_text="When enabled, a Draft Purchase Order is automatically created the moment stock falls at or below an item's reorder point.",
                )),
                ('auto_po_draft_only', models.BooleanField(
                    default=True,
                    help_text='Auto-generated POs are always created as Draft (require human review before submission). Strongly recommended to keep this on.',
                )),
            ],
            options={
                'verbose_name': 'Inventory Settings',
                'verbose_name_plural': 'Inventory Settings',
            },
        ),

        # ── preferred_vendor FK on Item ────────────────────────────────────────
        migrations.AddField(
            model_name='item',
            name='preferred_vendor',
            field=models.ForeignKey(
                blank=True,
                help_text='Default vendor used when automatically generating Purchase Orders from reorder alerts.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preferred_items',
                to='procurement.vendor',
            ),
        ),
    ]
