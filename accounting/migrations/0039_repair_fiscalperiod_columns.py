"""
Repair migration: ensure FiscalPeriod columns added by 0019 are present.
Uses IF NOT EXISTS so it is safe to re-run on any schema.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0038_baddebtwriteoff_financialratio_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE accounting_fiscalperiod
                    ADD COLUMN IF NOT EXISTS is_closed boolean NOT NULL DEFAULT false;
                ALTER TABLE accounting_fiscalperiod
                    ADD COLUMN IF NOT EXISTS is_locked boolean NOT NULL DEFAULT false;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
