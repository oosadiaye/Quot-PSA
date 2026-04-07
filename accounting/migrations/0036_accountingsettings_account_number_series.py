from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0035_accounting_complete_features'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountingsettings',
            name='account_number_series',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    'Maps account code prefix to account type. '
                    'E.g. {"1": "Asset", "2": "Liability", "3": "Equity", "4": "Income", "5": "Expense"}'
                ),
            ),
        ),
    ]
