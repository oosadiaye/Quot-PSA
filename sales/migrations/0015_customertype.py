import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0014_customercategory'),
        ('accounting', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Remove AR account from CustomerCategory — GL moves to CustomerType
        migrations.RemoveField(
            model_name='customercategory',
            name='accounts_receivable_account',
        ),

        # 2. Create the CustomerType model
        migrations.CreateModel(
            name='CustomerType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('code', models.CharField(max_length=20, unique=True)),
                ('description', models.TextField(blank=True, default='')),
                ('accounts_receivable_account', models.ForeignKey(
                    help_text='AR GL account debited when invoicing customers of this type',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='customer_type_ar_accounts',
                    to='accounting.account',
                )),
                ('revenue_account', models.ForeignKey(
                    blank=True,
                    help_text='Default revenue GL account credited on sales for this type',
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='customer_type_revenue_accounts',
                    to='accounting.account',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='customertype_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='customertype_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name_plural': 'Customer Types',
                'ordering': ['name'],
            },
        ),

        # 3. Remove the old customer_type CharField
        migrations.RemoveField(
            model_name='customer',
            name='customer_type',
        ),

        # 4. Add the new customer_type FK (nullable so existing rows aren't rejected)
        migrations.AddField(
            model_name='customer',
            name='customer_type',
            field=models.ForeignKey(
                blank=True,
                help_text='Determines GL accounts used when posting transactions for this customer',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='customers',
                to='sales.customertype',
            ),
        ),
    ]
