from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='CustomerCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, default='')),
            ],
            options={'db_table': 'sales_customercategory'},
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, default='')),
                ('customer_code', models.CharField(max_length=20, blank=True, default='')),
                ('email', models.EmailField(blank=True, default='')),
                ('phone', models.CharField(max_length=20, blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('credit_limit', models.DecimalField(max_digits=15, decimal_places=2, default=0)),
                ('category', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, to='sales.customercategory')),
            ],
            options={'db_table': 'sales_customer'},
        ),
        migrations.CreateModel(
            name='SalesOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(max_length=50, default='')),
                ('customer', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, to='sales.customer')),
            ],
            options={'db_table': 'sales_salesorder'},
        ),
        migrations.CreateModel(
            name='SalesOrderLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sales_order', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='sales.salesorder')),
            ],
            options={'db_table': 'sales_salesorderline'},
        ),
    ]
