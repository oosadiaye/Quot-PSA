"""
Migration for superadmin audit fixes:
- M13: Change SuperAdminProfile.is_superadmin default from True to False
- L8: Add MaxValueValidator(60) to WebhookConfig.timeout_seconds
"""

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin', '0004_phase1_to_phase7_enhancements'),
    ]

    operations = [
        # M13: Change is_superadmin default to False
        migrations.AlterField(
            model_name='superadminprofile',
            name='is_superadmin',
            field=models.BooleanField(default=False),
        ),

        # L8: Add timeout validator to WebhookConfig
        migrations.AlterField(
            model_name='webhookconfig',
            name='timeout_seconds',
            field=models.PositiveIntegerField(
                default=30,
                validators=[MinValueValidator(1), MaxValueValidator(60)],
            ),
        ),
    ]
