"""
Repair: sync accounting_bankaccount and accounting_costcenter with current model state.

BankAccount — add columns present in the model but absent from the DB:
  is_default, swift_code, iban, advance_customer_balance, advance_supplier_balance

CostCenter — drop budget_allocation (removed from model in 0019 but still in DB
             with a NOT NULL constraint, causing IntegrityError on every INSERT).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0043_repair_fiscalperiod_all_missing'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                -- BankAccount: add columns the model defines that the DB is missing
                ALTER TABLE accounting_bankaccount
                    ADD COLUMN IF NOT EXISTS is_default               boolean      NOT NULL DEFAULT false;
                ALTER TABLE accounting_bankaccount
                    ADD COLUMN IF NOT EXISTS swift_code               varchar(20)  NOT NULL DEFAULT '';
                ALTER TABLE accounting_bankaccount
                    ADD COLUMN IF NOT EXISTS iban                     varchar(50)  NOT NULL DEFAULT '';
                ALTER TABLE accounting_bankaccount
                    ADD COLUMN IF NOT EXISTS advance_customer_balance numeric(15,2) NOT NULL DEFAULT 0;
                ALTER TABLE accounting_bankaccount
                    ADD COLUMN IF NOT EXISTS advance_supplier_balance numeric(15,2) NOT NULL DEFAULT 0;

                -- CostCenter: drop budget_allocation (model removed it; NOT NULL constraint
                -- prevents any INSERT because Django no longer supplies a value for it)
                ALTER TABLE accounting_costcenter
                    DROP COLUMN IF EXISTS budget_allocation;
            """,
            reverse_sql="""
                -- Reverse: remove the added BankAccount columns
                ALTER TABLE accounting_bankaccount DROP COLUMN IF EXISTS is_default;
                ALTER TABLE accounting_bankaccount DROP COLUMN IF EXISTS swift_code;
                ALTER TABLE accounting_bankaccount DROP COLUMN IF EXISTS iban;
                ALTER TABLE accounting_bankaccount DROP COLUMN IF EXISTS advance_customer_balance;
                ALTER TABLE accounting_bankaccount DROP COLUMN IF EXISTS advance_supplier_balance;

                -- Reverse: restore budget_allocation as nullable (cannot restore NOT NULL safely)
                ALTER TABLE accounting_costcenter
                    ADD COLUMN IF NOT EXISTS budget_allocation numeric(15,2) NULL;
            """,
        ),
    ]
