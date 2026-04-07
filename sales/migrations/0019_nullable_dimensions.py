from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0018_alter_customer_accounts_receivable_account_and_more'),
        ('accounting', '0050_accountingsettings_sales_downpayment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quotation',
            name='fund',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.fund',
            ),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='function',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.function',
            ),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='program',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.program',
            ),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='geo',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.geo',
            ),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='fund',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.fund',
            ),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='function',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.function',
            ),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='program',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.program',
            ),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='geo',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.geo',
            ),
        ),
    ]
