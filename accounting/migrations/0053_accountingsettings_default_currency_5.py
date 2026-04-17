import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0052_add_journal_source_soft_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountingsettings',
            name='default_currency_5',
            field=models.ForeignKey(
                blank=True,
                help_text='Reporting currency (optional)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='settings_slot5',
                to='accounting.currency',
            ),
        ),
    ]
