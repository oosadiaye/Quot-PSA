from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0030_add_vendor_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendor',
            name='balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=19),
        ),
    ]
