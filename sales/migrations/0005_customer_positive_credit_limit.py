from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('sales', '0004_enhance_sales')]
    operations = [
        migrations.AddField(
            model_name='customer', name='credit_check_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='customer', name='credit_status',
            field=models.CharField(max_length=20, blank=True, default=''),
        ),
    ]
