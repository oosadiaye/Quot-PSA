from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0016_customercategory_ar_account'),
    ]

    operations = [
        # Remove FK from Customer first (references CustomerType)
        migrations.RemoveField(
            model_name='customer',
            name='customer_type',
        ),
        migrations.RemoveField(
            model_name='customer',
            name='revenue_account',
        ),
        # Remove the index that referenced customer_type
        migrations.RemoveIndex(
            model_name='customer',
            name='sales_custo_custome_890109_idx',
        ),
        # Now safe to delete the CustomerType model
        migrations.DeleteModel(
            name='CustomerType',
        ),
    ]
