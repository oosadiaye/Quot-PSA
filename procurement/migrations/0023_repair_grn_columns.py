"""
Repair migration: ensure GRN columns added by 0005_fix are present.
Uses IF NOT EXISTS so it is safe to re-run on any schema.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0022_add_on_hold_status_grn'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE procurement_goodsreceivednote
                    ADD COLUMN IF NOT EXISTS received_by varchar(100) NOT NULL DEFAULT 'SYSTEM';
                -- remarks was removed in 0005_fix; ensure it's dropped if still present
                ALTER TABLE procurement_goodsreceivednote
                    DROP COLUMN IF EXISTS remarks;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
