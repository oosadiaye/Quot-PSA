from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0050_accountingsettings_sales_downpayment'),
        ('sales', '0015_customertype'),
    ]

    operations = [
        migrations.AddField(
            model_name='customercategory',
            name='accounts_receivable_account',
            field=models.ForeignKey(
                help_text='AR GL account debited when invoicing customers in this category',
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='customer_category_ar_accounts',
                to='accounting.account',
            ),
        ),
    ]
