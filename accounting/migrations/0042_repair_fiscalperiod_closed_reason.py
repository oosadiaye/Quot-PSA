"""Repair: add closed_reason to fiscal period and any other missing close-related columns."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0041_repair_period_closed_date'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE accounting_fiscalperiod
                    ADD COLUMN IF NOT EXISTS closed_reason text NOT NULL DEFAULT '';
                ALTER TABLE accounting_fiscalyear
                    ADD COLUMN IF NOT EXISTS closed_reason text NOT NULL DEFAULT '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
