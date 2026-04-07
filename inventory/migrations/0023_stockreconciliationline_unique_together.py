from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0022_inventorysettings_item_preferred_vendor'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='stockreconciliationline',
            unique_together={('reconciliation', 'item')},
        ),
    ]
