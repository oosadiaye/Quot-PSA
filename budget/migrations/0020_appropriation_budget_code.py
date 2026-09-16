"""Add the custom budget code column to appropriation line items.

The organisation's own reference for a budget line, as printed in their
appropriation book. Typed by an officer — the six NCoA segments already
identify the line structurally, so this ties a row to an external
document, which nothing derived can do.

Why the column is added conditionally
-------------------------------------
``delta_state`` already has it. That schema was migrated on the
``feat/budget-line-code`` branch, which added the same field under its
own migration name, so a plain ``AddField`` there fails with "column
already exists" and leaves the tenant permanently unmigratable — which
is exactly what happened before this guard.

``SeparateDatabaseAndState`` splits the two halves: Django's migration
*state* always records the field, so every schema agrees about the model;
the *database* half runs the DDL only where the column is genuinely
absent. The seven schemas that took the original form of this migration
are unaffected — an applied migration is not re-run.

The two definitions agree (varchar(50), indexed, nullable-by-default
empty string), so an adopted column needs no alteration.
"""
from django.db import migrations, models


def add_column_if_absent(apps, schema_editor):
    """Add budget_appropriation.budget_code unless the schema has it."""
    schema = schema_editor.connection.schema_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = 'budget_appropriation'
              AND column_name = 'budget_code'
            """,
            [schema],
        )
        if cursor.fetchone():
            print(f'  budget_code already present in {schema} — adopting it.')
            return
        cursor.execute(
            """
            ALTER TABLE budget_appropriation
            ADD COLUMN budget_code varchar(50) NOT NULL DEFAULT ''
            """
        )
        cursor.execute(
            """
            CREATE INDEX budget_appropriation_budget_code_idx
            ON budget_appropriation (budget_code)
            """
        )


def drop_column(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE budget_appropriation DROP COLUMN IF EXISTS budget_code')


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0019_retire_economic_segment"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="appropriation",
                    name="budget_code",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text=(
                            "Your own reference for the budget line this row belongs to "
                            "(e.g. 'BL-2026-0142'). Optional free text — the NCoA segment "
                            "combination is what identifies the line structurally, so "
                            "this is for tracking against an external budget document, "
                            "not a key. Deliberately not unique: several rows may roll up "
                            "to one budget line."
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
