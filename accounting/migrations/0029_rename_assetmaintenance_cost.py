from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0028_alter_assetmaintenance_options_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='assetmaintenance',
            old_name='cost',
            new_name='total_cost',
        ),
    ]
