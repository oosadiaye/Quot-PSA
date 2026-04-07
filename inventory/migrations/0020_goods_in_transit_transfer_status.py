from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0001_initial'),
        ('inventory', '0019_fix_cost_standard_price_validators'),
    ]

    operations = [
        # ── ProductType: Goods in Transit clearing account ─────────────────────
        migrations.AddField(
            model_name='producttype',
            name='goods_in_transit_account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='producttype_git_account_set',
                to='accounting.account',
                help_text='Clearing GL account used as intermediary during inter-warehouse stock transfers.',
            ),
        ),

        # ── StockMovement: two-step transfer lifecycle ─────────────────────────
        migrations.AddField(
            model_name='stockmovement',
            name='transfer_status',
            field=models.CharField(
                blank=True,
                default='',
                max_length=20,
                choices=[
                    ('In Transit', 'In Transit'),
                    ('Received',   'Received'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='receive_journal_entry',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stock_transfer_receipts',
                to='accounting.journalheader',
                help_text='Journal entry created when Warehouse B receives the transfer (Step 2).',
            ),
        ),
    ]
