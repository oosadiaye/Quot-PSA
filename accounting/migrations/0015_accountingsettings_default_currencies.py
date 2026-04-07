import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0014_account_reconciliation_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountingsettings',
            name='default_currency_1',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='Local / base currency',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='settings_slot1',
                to='accounting.currency',
            ),
        ),
        migrations.AddField(
            model_name='accountingsettings',
            name='default_currency_2',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='Document currency',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='settings_slot2',
                to='accounting.currency',
            ),
        ),
        migrations.AddField(
            model_name='accountingsettings',
            name='default_currency_3',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='Reporting currency (optional)',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='settings_slot3',
                to='accounting.currency',
            ),
        ),
        migrations.AddField(
            model_name='accountingsettings',
            name='default_currency_4',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='Reporting currency (optional)',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='settings_slot4',
                to='accounting.currency',
            ),
        ),
    ]
