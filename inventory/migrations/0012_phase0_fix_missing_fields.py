"""Phase 0: Restore fields removed by migration 0009 + add missing fields.

- Item: re-add selling_price
- StockMovement: re-add gl_posted, journal_entry; add choices to movement_type
- ItemSerialNumber: add batch, purchase_date, purchase_price, sale_date,
  sales_order_line, warranty_start, warranty_end, current_location, notes, status choices
- BatchExpiryAlert: add warehouse, alert_date
- StockReconciliation: add choices to status, reconciliation_type
"""

import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0011_rename_asset_account_to_clearing_account'),
        ('accounting', '0025_journalline_document_number'),
        ('sales', '0001_initial'),
    ]

    operations = [
        # === Item: re-add selling_price ===
        migrations.AddField(
            model_name='item',
            name='selling_price',
            field=models.DecimalField(
                max_digits=19, decimal_places=4, default=Decimal('0'),
            ),
        ),

        # === StockMovement: re-add gl_posted and journal_entry ===
        migrations.AddField(
            model_name='stockmovement',
            name='gl_posted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='journal_entry',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stock_movements',
                to='accounting.journalheader',
            ),
        ),
        # StockMovement: add choices to movement_type
        migrations.AlterField(
            model_name='stockmovement',
            name='movement_type',
            field=models.CharField(
                max_length=3,
                choices=[
                    ('IN', 'Stock In'),
                    ('OUT', 'Stock Out'),
                    ('ADJ', 'Adjustment'),
                    ('TRF', 'Transfer'),
                ],
            ),
        ),

        # === ItemSerialNumber: add missing fields ===
        migrations.AddField(
            model_name='itemserialnumber',
            name='batch',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='serial_numbers',
                to='inventory.itembatch',
            ),
        ),
        migrations.AddField(
            model_name='itemserialnumber',
            name='purchase_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='itemserialnumber',
            name='purchase_price',
            field=models.DecimalField(
                max_digits=19, decimal_places=4, blank=True, null=True,
            ),
        ),
        migrations.AddField(
            model_name='itemserialnumber',
            name='sale_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='itemserialnumber',
            name='sales_order_line',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='serial_numbers',
                to='sales.salesorderline',
            ),
        ),
        migrations.AddField(
            model_name='itemserialnumber',
            name='warranty_start',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='itemserialnumber',
            name='warranty_end',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='itemserialnumber',
            name='current_location',
            field=models.CharField(max_length=255, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='itemserialnumber',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
        # ItemSerialNumber: add choices to status, update item related_name
        migrations.AlterField(
            model_name='itemserialnumber',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('Available', 'Available'),
                    ('Allocated', 'Allocated'),
                    ('Sold', 'Sold'),
                    ('Returned', 'Returned'),
                    ('Defective', 'Defective'),
                    ('Scrapped', 'Scrapped'),
                ],
                default='Available',
            ),
        ),
        migrations.AlterField(
            model_name='itemserialnumber',
            name='item',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='serial_numbers',
                to='inventory.item',
            ),
        ),

        # === BatchExpiryAlert: add warehouse and alert_date ===
        migrations.AddField(
            model_name='batchexpiryalert',
            name='warehouse',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='inventory.warehouse',
            ),
        ),
        migrations.AddField(
            model_name='batchexpiryalert',
            name='alert_date',
            field=models.DateField(auto_now_add=True, null=True),
        ),
        # BatchExpiryAlert: update batch related_name
        migrations.AlterField(
            model_name='batchexpiryalert',
            name='batch',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='expiry_alerts',
                to='inventory.itembatch',
            ),
        ),

        # === StockReconciliation: add choices ===
        migrations.AlterField(
            model_name='stockreconciliation',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('Draft', 'Draft'),
                    ('In Progress', 'In Progress'),
                    ('Completed', 'Completed'),
                    ('Cancelled', 'Cancelled'),
                ],
                default='Draft',
            ),
        ),
        migrations.AlterField(
            model_name='stockreconciliation',
            name='reconciliation_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('Full', 'Full Count'),
                    ('Partial', 'Partial Count'),
                    ('Cycle', 'Cycle Count'),
                    ('Spot', 'Spot Check'),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='stockreconciliation',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
    ]
