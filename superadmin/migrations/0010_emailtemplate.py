from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('superadmin', '0009_currencyconfig_country_codes_flag_emoji'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(
                    help_text='Stable identifier (e.g. welcome, password_reset, payment_received).',
                    max_length=100,
                )),
                ('language', models.CharField(
                    choices=[
                        ('en', 'English'), ('fr', 'French'), ('es', 'Spanish'),
                        ('de', 'German'), ('ar', 'Arabic'), ('pt', 'Portuguese'),
                        ('zh', 'Chinese'), ('ja', 'Japanese'),
                    ],
                    default='en', max_length=10,
                )),
                ('category', models.CharField(
                    choices=[
                        ('auth', 'Authentication'),
                        ('billing', 'Billing & Subscription'),
                        ('support', 'Support'),
                        ('notification', 'Notification'),
                        ('marketing', 'Marketing'),
                        ('system', 'System'),
                    ],
                    default='notification', max_length=30,
                )),
                ('display_name', models.CharField(help_text='Human-friendly label for SuperAdmin UI.', max_length=200)),
                ('description', models.TextField(blank=True, help_text='When this template fires and who receives it.')),
                ('subject', models.CharField(max_length=255)),
                ('body_html', models.TextField(help_text='Inline-styled HTML body. Supports {placeholder} substitution.')),
                ('body_text', models.TextField(blank=True, help_text='Plain-text fallback. If blank, HTML is stripped at send time.')),
                ('variables', models.JSONField(blank=True, default=list)),
                ('is_active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False, help_text='System templates cannot be deleted, only edited.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='email_templates_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Email Template',
                'verbose_name_plural': 'Email Templates',
                'ordering': ['category', 'key', 'language'],
                'unique_together': {('key', 'language')},
            },
        ),
    ]
