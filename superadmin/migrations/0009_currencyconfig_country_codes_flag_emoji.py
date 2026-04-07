from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin', '0008_encrypt_smtp_passwords'),
    ]

    operations = [
        migrations.AddField(
            model_name='currencyconfig',
            name='country_codes',
            field=models.JSONField(
                blank=True, default=list,
                help_text='List of ISO country codes mapped to this currency, e.g. ["NG","GH"]',
            ),
        ),
        migrations.AddField(
            model_name='currencyconfig',
            name='flag_emoji',
            field=models.CharField(
                blank=True, default='', max_length=10,
                help_text='Flag emoji for display, e.g. \U0001f1f3\U0001f1ec',
            ),
        ),
    ]
