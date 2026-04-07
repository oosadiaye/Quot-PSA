import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0013_alter_deliverynoteline_delivery_note_and_more'),
        ('accounting', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('code', models.CharField(max_length=20, unique=True)),
                ('description', models.TextField(blank=True, default='')),
                ('accounts_receivable_account', models.ForeignKey(
                    help_text='Default AR GL account for customers in this category',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='customer_category_ar_accounts',
                    to='accounting.account',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='customercategory_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='customercategory_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name_plural': 'Customer Categories',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='customer',
            name='category',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='customers',
                to='sales.customercategory',
            ),
        ),
        # Remove the old unnamed related_name on accounts_receivable_account
        # and add the explicit related_name='customer_ar_accounts'
        migrations.AlterField(
            model_name='customer',
            name='accounts_receivable_account',
            field=models.ForeignKey(
                blank=True,
                help_text='Override AR GL account. If blank, inherits from customer category.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='customer_ar_accounts',
                to='accounting.account',
            ),
        ),
    ]
