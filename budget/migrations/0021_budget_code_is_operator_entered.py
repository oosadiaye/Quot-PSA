"""Clear the derived budget codes, and settle the column at varchar(50).

The first cut of ``budget_code`` generated a value from the line's own
dimensions — ``2026/010000000000/25100100/01200`` — and backfilled every
appropriation with it. That was the wrong design: the field is the
organisation's own reference from their appropriation book, so a value
nobody typed is not data, it is noise that looks like data. An officer
searching Budget Check for their real code would find nothing, while
every line already appeared to "have a code".

Two things to put right, and both are database-only. The migration
*state* is already correct — ``0020`` was rewritten to declare the field
at its final definition — so altering state again would make Django see
drift where there is none.

  1. Blank any value matching the generated shape. Scoped by regex
     rather than clearing the column outright: on this branch nothing
     else could have written it, but a blanket wipe would destroy real
     references the moment this runs somewhere it was not expected.

  2. Narrow varchar(80) to varchar(50). The seven schemas that took the
     original migration got 80; ``delta_state``, which already had the
     column from ``feat/budget-line-code``, has 50. Both must end up the
     same or the model's max_length means something different per
     tenant. Safe after step 1 — the longest generated code was 31
     characters and they are gone by then anyway.
"""
from django.db import migrations

# 2026/010000000000/25100100/01200 — the shape the old backfill wrote.
DERIVED_CODE_PATTERN = r'^[0-9]{4}/[0-9]+/[0-9]+/[0-9]+$'


def forwards(apps, schema_editor):
    schema = schema_editor.connection.schema_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "UPDATE budget_appropriation SET budget_code = '' "
            "WHERE budget_code ~ %s",
            [DERIVED_CODE_PATTERN],
        )
        cleared = cursor.rowcount

        cursor.execute(
            """
            SELECT character_maximum_length FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = 'budget_appropriation'
              AND column_name = 'budget_code'
            """,
            [schema],
        )
        row = cursor.fetchone()
        current = row[0] if row else None
        if current is not None and current != 50:
            cursor.execute(
                'ALTER TABLE budget_appropriation '
                'ALTER COLUMN budget_code TYPE varchar(50)'
            )

    if cleared:
        print(f'  Cleared {cleared} generated budget code(s) in {schema} — '
              f'the field is operator-entered.')


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0020_appropriation_budget_code"),
    ]

    operations = [
        # Database-only: state already describes the field correctly.
        # No reverse — restoring generated values would re-introduce the
        # very thing this removes.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
