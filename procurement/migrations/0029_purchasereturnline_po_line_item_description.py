from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Adds PO-line traceability and text description fields to PurchaseReturnLine,
    and makes return_number auto-generatable (blank=True).

    Changes:
    - PurchaseReturn.return_number: add blank=True (auto-generated in save())
    - PurchaseReturnLine.po_line: new nullable FK → PurchaseOrderLine
    - PurchaseReturnLine.item: make nullable (optional when po_line present)
    - PurchaseReturnLine.item_description: new CharField for display text
    - PurchaseReturn: add missing purchase_order index
    """

    dependencies = [
        ('procurement', '0028_invoicematching_down_payment_applied'),
    ]

    operations = [
        # 1. return_number: allow blank so save() can auto-generate it
        migrations.AlterField(
            model_name='purchasereturn',
            name='return_number',
            field=models.CharField(blank=True, max_length=50, unique=True),
        ),

        # 2. New FK: PurchaseReturnLine → PurchaseOrderLine (nullable, traceability)
        migrations.AddField(
            model_name='purchasereturnline',
            name='po_line',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='return_lines',
                to='procurement.purchaseorderline',
                help_text='Original PO line being returned. Used for quantity validation against the GRN.',
            ),
        ),

        # 3. item FK: make nullable so returns can be created without an inventory item
        migrations.AlterField(
            model_name='purchasereturnline',
            name='item',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='inventory.item',
            ),
        ),

        # 4. item_description: text fallback when item FK is not set
        migrations.AddField(
            model_name='purchasereturnline',
            name='item_description',
            field=models.CharField(blank=True, default='', max_length=255),
            preserve_default=False,
        ),

        # 5. Add the purchase_order index that exists in Meta but was never migrated
        migrations.AddIndex(
            model_name='purchasereturn',
            index=models.Index(fields=['purchase_order'], name='procurement_purchas_da7e1c_idx'),
        ),
    ]
