# Phase 1-7 SuperAdmin enhancements
# Adds: CommissionPayout, TicketAttachment, TenantLanguageSetting,
#        TenantCurrencySetting, WebhookDelivery, TenantUsage, Invoice
# Updates: TenantAPIKey (api_secret), WebhookConfig (retry_count, last_status_code, created_by),
#          Announcement (content_html, target_plans M2M, target_tenants M2M),
#          TenantNotification (announcement FK),
#          CurrencyConfig (decimal_separator, thousand_separator, symbol_position, auto_update)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0004_role'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('superadmin', '0003_currencyconfig_languageconfig_referrer_and_more'),
    ]

    operations = [
        # ---- Phase 1: CommissionPayout ----
        migrations.CreateModel(
            name='CommissionPayout',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('total_commissions', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('commissions_count', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('Draft', 'Draft'), ('Processing', 'Processing'), ('Completed', 'Completed'), ('Failed', 'Failed')], default='Draft', max_length=20)),
                ('payout_date', models.DateField(blank=True, null=True)),
                ('payout_reference', models.CharField(blank=True, max_length=100)),
                ('payment_method', models.CharField(blank=True, max_length=50)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('referrer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payouts', to='superadmin.referrer')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-period_end']},
        ),

        # ---- Phase 2: TicketAttachment ----
        migrations.CreateModel(
            name='TicketAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='support/attachments/')),
                ('file_name', models.CharField(max_length=255)),
                ('file_size', models.PositiveIntegerField(default=0)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='superadmin.supportticket')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-uploaded_at']},
        ),

        # ---- Phase 3: TenantLanguageSetting, TenantCurrencySetting ----
        migrations.CreateModel(
            name='TenantLanguageSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allow_user_override', models.BooleanField(default=True)),
                ('tenant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='language_setting', to='tenants.client')),
                ('language', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='superadmin.languageconfig')),
            ],
        ),
        migrations.CreateModel(
            name='TenantCurrencySetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allow_user_override', models.BooleanField(default=False)),
                ('tenant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='currency_setting', to='tenants.client')),
                ('currency', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='superadmin.currencyconfig')),
            ],
        ),

        # CurrencyConfig additions
        migrations.AddField(model_name='currencyconfig', name='decimal_separator', field=models.CharField(default='.', max_length=1)),
        migrations.AddField(model_name='currencyconfig', name='thousand_separator', field=models.CharField(default=',', max_length=1)),
        migrations.AddField(model_name='currencyconfig', name='symbol_position', field=models.CharField(choices=[('prefix', 'Before Amount'), ('suffix', 'After Amount')], default='prefix', max_length=10)),
        migrations.AddField(model_name='currencyconfig', name='auto_update', field=models.BooleanField(default=False)),

        # ---- Phase 5: TenantAPIKey.api_secret, WebhookConfig updates, WebhookDelivery ----
        migrations.AddField(model_name='tenantapikey', name='api_secret', field=models.CharField(blank=True, max_length=128)),

        migrations.AddField(model_name='webhookconfig', name='retry_count', field=models.PositiveIntegerField(default=3)),
        migrations.AddField(model_name='webhookconfig', name='last_status_code', field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name='webhookconfig', name='created_by', field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),

        migrations.CreateModel(
            name='WebhookDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.CharField(max_length=50)),
                ('payload', models.JSONField()),
                ('status', models.CharField(choices=[('Pending', 'Pending'), ('Success', 'Success'), ('Failed', 'Failed')], default='Pending', max_length=20)),
                ('status_code', models.IntegerField(blank=True, null=True)),
                ('response_body', models.TextField(blank=True)),
                ('error_message', models.TextField(blank=True)),
                ('attempted_at', models.DateTimeField(auto_now_add=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('duration_ms', models.IntegerField(blank=True, null=True)),
                ('retry_attempt', models.PositiveIntegerField(default=0)),
                ('webhook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='superadmin.webhookconfig')),
            ],
            options={'ordering': ['-attempted_at']},
        ),

        # ---- Phase 6: Announcement updates, TenantNotification.announcement ----
        migrations.AddField(model_name='announcement', name='content_html', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='announcement', name='target_plans', field=models.ManyToManyField(blank=True, related_name='announcements', to='superadmin.subscriptionplan')),
        migrations.AddField(model_name='announcement', name='target_tenants', field=models.ManyToManyField(blank=True, related_name='targeted_announcements', to='tenants.client')),
        migrations.AddField(model_name='tenantnotification', name='announcement', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='superadmin.announcement')),

        # ---- Phase 7: TenantUsage, Invoice ----
        migrations.CreateModel(
            name='TenantUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('billing_period_start', models.DateField()),
                ('billing_period_end', models.DateField()),
                ('users_count', models.PositiveIntegerField(default=0)),
                ('storage_mb', models.BigIntegerField(default=0)),
                ('api_calls', models.BigIntegerField(default=0)),
                ('transactions_count', models.BigIntegerField(default=0)),
                ('overage_users', models.PositiveIntegerField(default=0)),
                ('overage_storage_mb', models.BigIntegerField(default=0)),
                ('overage_api_calls', models.BigIntegerField(default=0)),
                ('base_cost', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('overage_cost', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('total_cost', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('is_billed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='usage_records', to='tenants.client')),
            ],
            options={
                'ordering': ['-billing_period_start'],
                'unique_together': {('tenant', 'billing_period_start')},
            },
        ),
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_number', models.CharField(max_length=50, unique=True)),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('subscription_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('usage_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('tax_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('discount_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('status', models.CharField(choices=[('Draft', 'Draft'), ('Pending', 'Pending'), ('Paid', 'Paid'), ('Overdue', 'Overdue'), ('Cancelled', 'Cancelled')], default='Draft', max_length=20)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('payment_method', models.CharField(blank=True, max_length=50)),
                ('payment_reference', models.CharField(blank=True, max_length=100)),
                ('issue_date', models.DateField(auto_now_add=True)),
                ('due_date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='tenants.client')),
            ],
            options={'ordering': ['-issue_date']},
        ),
    ]
