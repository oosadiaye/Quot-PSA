from django.db import migrations, models
import django.db.models.deletion


def delete_returns_without_po(apps, schema_editor):
    """Remove any existing PurchaseReturn records with no purchase_order."""
    PurchaseReturn = apps.get_model('procurement', 'PurchaseReturn')
    PurchaseReturn.objects.filter(purchase_order__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0017_add_inventory_to_purchaserequestline'),
    ]

    operations = [
        migrations.RunPython(delete_returns_without_po, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='purchasereturn',
            name='purchase_order',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='procurement.purchaseorder',
            ),
        ),
    ]
