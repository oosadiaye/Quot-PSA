from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Allow grn_number to be blank at the Python/form level.
    No DB column change — the column stays NOT NULL UNIQUE.
    Auto-generation happens in GoodsReceivedNote.save() before insert.
    """

    dependencies = [
        ('procurement', '0025_repair_purchase_request_columns'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goodsreceivednote',
            name='grn_number',
            field=models.CharField(blank=True, max_length=50, unique=True),
        ),
    ]
