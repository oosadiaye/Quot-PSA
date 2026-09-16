"""Add the custom budget code to revenue budget lines too.

A revenue line carries the organisation's own reference for the same
reason an expenditure line does, and ``feat/budget-line-code`` had it
first. The field is taken verbatim from that branch so the two cannot
drift into meaning different things.

Conditional for the same reason as ``0020``: ``delta_state`` was migrated
on that branch and already has the column, so a plain ``AddField`` fails
there with "column already exists" and leaves the tenant unmigratable.
``SeparateDatabaseAndState`` keeps Django's state correct everywhere
while running the DDL only where the column is genuinely absent.
"""
from django.db import migrations, models


def add_column_if_absent(apps, schema_editor):
    schema = schema_editor.connection.schema_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = 'budget_revenuebudget'
              AND column_name = 'budget_code'
            """,
            [schema],
        )
        if cursor.fetchone():
            print(f'  revenuebudget.budget_code already present in {schema} — adopting it.')
            return
        cursor.execute(
            """
            ALTER TABLE budget_revenuebudget
            ADD COLUMN budget_code varchar(50) NOT NULL DEFAULT ''
            """
        )
        cursor.execute(
            """
            CREATE INDEX budget_revenuebudget_budget_code_idx
            ON budget_revenuebudget (budget_code)
            """
        )


def drop_column(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE budget_revenuebudget DROP COLUMN IF EXISTS budget_code'
        )


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0021_budget_code_is_operator_entered"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="revenuebudget",
                    name="budget_code",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text=(
                            "Your own reference for the budget line this row belongs to "
                            "(e.g. 'BL-2026-0142'). Optional and free text: the NCoA "
                            "segment combination is what identifies the line "
                            "structurally, so this is for tracking against an external "
                            "budget document, not a key. Deliberately not unique — "
                            "several rows may roll up to one budget line."
                        ),
                        max_length=50,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_column_if_absent, drop_column),
            ],
        ),
    ]
