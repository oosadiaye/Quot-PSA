from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0049_sync_fiscalperiod_model_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountingsettings',
            name='enable_sales_downpayment',
            field=models.BooleanField(
                default=False,
                help_text='Allow downpayment requests to be created on sales orders',
            ),
        ),
        migrations.AddField(
            model_name='accountingsettings',
            name='downpayment_default_type',
            field=models.CharField(
                max_length=20,
                choices=[('percentage', 'Percentage'), ('amount', 'Fixed Amount')],
                default='percentage',
                help_text='Default calculation type for sales downpayment requests',
            ),
        ),
        migrations.AddField(
            model_name='accountingsettings',
            name='downpayment_default_value',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=4,
                default=30,
                help_text='Default downpayment percentage or amount',
            ),
        ),
        migrations.AddField(
            model_name='accountingsettings',
            name='downpayment_gl_account',
            field=models.ForeignKey(
                to='accounting.Account',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='downpayment_settings',
                help_text='GL account to credit when a customer downpayment is posted',
            ),
        ),
    ]
