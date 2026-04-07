"""
Repair migration: add closed_date columns to fiscal period/year tables
and budget period table — all missing from tenant schema.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0040_repair_missing_tables'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE accounting_fiscalperiod
                    ADD COLUMN IF NOT EXISTS closed_date timestamp with time zone NULL;
                ALTER TABLE accounting_fiscalyear
                    ADD COLUMN IF NOT EXISTS closed_date timestamp with time zone NULL;
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'accounting_budgetperiod'
                    ) THEN
                        ALTER TABLE accounting_budgetperiod
                            ADD COLUMN IF NOT EXISTS closed_date timestamp with time zone NULL;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'accounting_periodstatus'
                    ) THEN
                        ALTER TABLE accounting_periodstatus
                            ADD COLUMN IF NOT EXISTS closed_date timestamp with time zone NULL;
                    END IF;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
