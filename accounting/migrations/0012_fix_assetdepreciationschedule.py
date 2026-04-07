import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0011_rename_created_at_accountingdocument_uploaded_at'),
    ]

    operations = [
        # Remove unique_together first
        migrations.AlterUniqueTogether(
            name='assetdepreciationschedule',
            unique_together=set(),
        ),
        # Remove old fields
        migrations.RemoveField(model_name='assetdepreciationschedule', name='created_at'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='updated_at'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='method'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='opening_value'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='closing_value'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='notes'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='created_by'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='updated_by'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='journal_entry'),
        migrations.RemoveField(model_name='assetdepreciationschedule', name='period'),
        # Add new field
        migrations.AddField(
            model_name='assetdepreciationschedule',
            name='period_date',
            field=models.DateField(default='2026-01-01'),
            preserve_default=False,
        ),
        # Update asset FK related_name
        migrations.AlterField(
            model_name='assetdepreciationschedule',
            name='asset',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='asset_depreciation_schedules',
                to='accounting.fixedasset',
            ),
        ),
        # Update ordering
        migrations.AlterModelOptions(
            name='assetdepreciationschedule',
            options={'ordering': ['period_date']},
        ),
    ]
