"""
Repair migration: add missing mda_id column to procurement_purchaserequest.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0024_repair_po_columns'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE procurement_purchaserequest
                    ADD COLUMN IF NOT EXISTS mda_id bigint
                    REFERENCES accounting_mda(id) DEFERRABLE INITIALLY DEFERRED;
                CREATE INDEX IF NOT EXISTS procurement_pr_mda_id ON procurement_purchaserequest(mda_id);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
