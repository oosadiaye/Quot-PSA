from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_tenantmodule_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantSetupProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('setup_completed', models.BooleanField(default=False)),
                ('current_step', models.PositiveIntegerField(default=0)),
                ('completed_steps', models.JSONField(blank=True, default=list)),
                ('company_name', models.CharField(blank=True, default='', max_length=200)),
                ('company_email', models.EmailField(blank=True, default='', max_length=254)),
                ('company_phone', models.CharField(blank=True, default='', max_length=30)),
                ('company_address', models.TextField(blank=True, default='')),
                ('company_city', models.CharField(blank=True, default='', max_length=100)),
                ('company_state', models.CharField(blank=True, default='', max_length=100)),
                ('company_country', models.CharField(blank=True, default='', max_length=100)),
                ('company_website', models.URLField(blank=True, default='')),
                ('tax_id', models.CharField(blank=True, default='', help_text='TIN / VAT / Tax ID', max_length=50)),
                ('registration_number', models.CharField(blank=True, default='', max_length=100)),
                ('fiscal_year_start', models.PositiveIntegerField(default=1, help_text='Month number (1=Jan, 4=Apr, 7=Jul, 10=Oct)')),
                ('default_currency', models.CharField(blank=True, default='USD', max_length=10)),
                ('timezone', models.CharField(blank=True, default='UTC', max_length=50)),
                ('business_category', models.CharField(blank=True, default='other', max_length=50)),
                ('employee_count_range', models.CharField(blank=True, default='', help_text='e.g. 1-10, 11-50, 51-200, 201-500, 500+', max_length=30)),
                ('annual_revenue_range', models.CharField(blank=True, default='', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Tenant Setup Profile',
                'verbose_name_plural': 'Tenant Setup Profiles',
            },
        ),
    ]
