"""
Repair migration: fix procurement columns that failed to apply on existing schemas.
- Renames purchaseorderline.order_id -> po_id (from 0005_fix rename)
- Adds purchaseorder.mda_id FK (from 0005_fix)
Uses IF EXISTS / IF NOT EXISTS for idempotency.
"""
from django.db import migrations


FORWARD_SQL = """
-- Rename order_id -> po_id on purchaseorderline (migration 0005_fix rename)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'procurement_purchaseorderline'
          AND column_name = 'order_id'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'procurement_purchaseorderline'
          AND column_name = 'po_id'
    ) THEN
        ALTER TABLE procurement_purchaseorderline RENAME COLUMN order_id TO po_id;
    END IF;
END $$;

-- Add mda_id to purchaseorder (migration 0005_fix AddField)
ALTER TABLE procurement_purchaseorder
    ADD COLUMN IF NOT EXISTS mda_id bigint
    REFERENCES accounting_mda(id) DEFERRABLE INITIALLY DEFERRED;

-- Add vendor_invoice_id to goodsreceivednote if missing (from later migration)
ALTER TABLE procurement_goodsreceivednote
    ADD COLUMN IF NOT EXISTS vendor_invoice_id bigint
    REFERENCES accounting_vendorinvoice(id) DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX IF NOT EXISTS procurement_po_mda_id ON procurement_purchaseorder(mda_id);
CREATE INDEX IF NOT EXISTS procurement_grn_vendor_invoice_id ON procurement_goodsreceivednote(vendor_invoice_id);
"""


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0023_repair_grn_columns'),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
