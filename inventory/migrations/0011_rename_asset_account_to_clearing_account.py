from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0010_alter_item_valuation_method_reservation'),
    ]

    operations = [
        migrations.RenameField(
            model_name='producttype',
            old_name='asset_account',
            new_name='clearing_account',
        ),
    ]
