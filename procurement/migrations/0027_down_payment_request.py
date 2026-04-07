from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0026_grn_number_blank'),
        ('accounting', '0049_sync_fiscalperiod_model_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DownPaymentRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('request_number', models.CharField(blank=True, max_length=50, unique=True)),
                ('calc_type', models.CharField(
                    choices=[('percentage', 'Percentage of PO Total'), ('amount', 'Fixed Amount')],
                    default='percentage', max_length=20,
                )),
                ('calc_value', models.DecimalField(decimal_places=4, max_digits=10)),
                ('requested_amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('payment_method', models.CharField(
                    choices=[('Bank', 'Bank Transfer'), ('Cash', 'Cash')],
                    default='Bank', max_length=20,
                )),
                ('status', models.CharField(
                    choices=[
                        ('Pending', 'Pending Review'), ('Approved', 'Approved'),
                        ('Rejected', 'Rejected'), ('Processed', 'Processed'),
                    ],
                    default='Pending', max_length=20,
                )),
                ('notes', models.TextField(blank=True, default='')),
                ('bank_account', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='down_payment_requests',
                    to='accounting.bankaccount',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('payment', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='down_payment_source',
                    to='accounting.payment',
                )),
                ('purchase_order', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='down_payment_request',
                    to='procurement.purchaseorder',
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
