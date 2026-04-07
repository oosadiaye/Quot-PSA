"""
Repair: add all boolean permission columns that FiscalPeriod model defines
but that are absent from the tenant DB schema.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0042_repair_fiscalperiod_closed_reason'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                -- FiscalPeriod boolean access-control fields
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS allow_journal_entry boolean NOT NULL DEFAULT true;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS allow_invoice     boolean NOT NULL DEFAULT true;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS allow_payment     boolean NOT NULL DEFAULT true;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS allow_procurement boolean NOT NULL DEFAULT true;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS allow_inventory   boolean NOT NULL DEFAULT true;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS allow_sales       boolean NOT NULL DEFAULT true;
                -- Audit fields if missing
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS created_at  timestamp with time zone NULL;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS updated_at  timestamp with time zone NULL;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS created_by_id integer NULL REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS updated_by_id integer NULL REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED;
                ALTER TABLE accounting_fiscalperiod ADD COLUMN IF NOT EXISTS name varchar(100) NOT NULL DEFAULT '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
