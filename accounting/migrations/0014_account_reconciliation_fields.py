from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0013_accountingsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='is_reconciliation',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='account',
            name='reconciliation_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('accounts_payable', 'Account Payable'),
                    ('accounts_receivable', 'Account Receivable'),
                    ('inventory', 'Inventory'),
                    ('asset_accounting', 'Asset Accounting'),
                    ('bank_accounting', 'Bank Accounting'),
                ],
                default='',
                max_length=30,
            ),
        ),
    ]
