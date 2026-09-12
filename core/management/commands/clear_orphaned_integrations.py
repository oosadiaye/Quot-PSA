"""
clear_orphaned_integrations
===========================
Remove the residue of an abandoned ``integrations`` app build.

Background
----------
An earlier attempt at the Integration Gateway was built, migrated into
tenant schemas, and then had its source removed without being unapplied.
What survives is three tables and a ``django_migrations`` row per
affected schema, with no code behind them.

That residue is not inert. Django records migrations **per schema**, so a
fresh ``integrations/0001_initial`` is *skipped* in exactly the schemas
that still carry the old record, while applying normally everywhere else.
``showmigrations`` then reports the app as applied while the tables do not
match the models, and the failure surfaces at runtime as
``relation ... does not exist`` — on whichever tenants happen to be the
oldest, which are usually the ones in use.

So this has to be cleared before any code is written under that app label.

Safety
------
Dry run by default; ``--apply`` is required to change anything. Each
schema is judged on its own evidence, gathered at run time rather than
trusted from a previous survey:

* tables carrying rows are **refused** — this command deletes no data;
* tables referenced from outside ``integrations_*`` are **refused** —
  something adopted them and this is no longer orphan residue;
* anything else is cleaned, children before parents.

A refusal for one schema never stops the others. Re-running is harmless:
a schema with nothing left to do reports ``nothing to do`` and is skipped.

Usage
-----
    # Show what would happen across every tenant (default, changes nothing)
    python manage.py clear_orphaned_integrations

    # Do it
    python manage.py clear_orphaned_integrations --apply

    # One schema
    python manage.py clear_orphaned_integrations --schema delta_state --apply
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

#: Child-first, so foreign keys inside the group never block a drop.
LEGACY_TABLES: tuple[str, ...] = (
    'integrations_integrationmessage',
    'integrations_integrationrun',
    'integrations_integrationendpoint',
)

#: The app label whose migration records are being cleared.
LEGACY_APP_LABEL = 'integrations'

# Outcomes.
SKIP = 'skip'
CLEAN = 'clean'
REFUSE = 'refuse'


@dataclass(frozen=True)
class SchemaEvidence:
    """What was observed in one schema. Gathered from the database."""

    schema: str
    tables: tuple[str, ...] = ()
    #: table name -> row count, for the tables that exist.
    row_counts: dict[str, int] = field(default_factory=dict)
    #: (referencing_table, referenced_table) where the referencing table
    #: is NOT one of ours — i.e. something outside adopted these tables.
    inbound_refs: tuple[tuple[str, str], ...] = ()
    migration_rows: int = 0


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str


def decide(evidence: SchemaEvidence) -> Decision:
    """Judge one schema. Pure — the tests drive this directly.

    Deliberately conservative: this command exists to unblock a build,
    which is never a good enough reason to delete someone's rows.
    """
    if not evidence.tables and not evidence.migration_rows:
        return Decision(SKIP, 'nothing to do')

    populated = {t: n for t, n in evidence.row_counts.items() if n}
    if populated:
        detail = ', '.join(f'{t}={n}' for t, n in sorted(populated.items()))
        return Decision(
            REFUSE,
            f'tables hold data ({detail}) - this is not orphan residue, '
            f'and nothing here deletes rows',
        )

    if evidence.inbound_refs:
        detail = ', '.join(f'{a} -> {b}' for a, b in sorted(evidence.inbound_refs))
        return Decision(
            REFUSE,
            f'referenced from outside the group ({detail}) - something '
            f'adopted these tables',
        )

    parts = []
    if evidence.tables:
        parts.append(f'{len(evidence.tables)} empty table(s)')
    if evidence.migration_rows:
        parts.append(f'{evidence.migration_rows} migration record(s)')
    return Decision(CLEAN, 'remove ' + ' and '.join(parts))


def gather(cursor, schema: str) -> SchemaEvidence:
    """Read one schema's current state. Called inside that schema's context."""
    cursor.execute(
        "SELECT tablename FROM pg_tables "
        "WHERE schemaname = %s AND tablename = ANY(%s) ORDER BY tablename",
        [schema, list(LEGACY_TABLES)],
    )
    tables = tuple(r[0] for r in cursor.fetchall())

    row_counts: dict[str, int] = {}
    for table in tables:
        # Identifier is from LEGACY_TABLES, never from user input.
        cursor.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
        row_counts[table] = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT tc.table_name, ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %s
          AND ccu.table_name = ANY(%s)
          AND NOT (tc.table_name = ANY(%s))
        """,
        [schema, list(LEGACY_TABLES), list(LEGACY_TABLES)],
    )
    inbound = tuple((a, b) for a, b in cursor.fetchall())

    migration_rows = 0
    try:
        cursor.execute(
            'SELECT count(*) FROM django_migrations WHERE app = %s',
            [LEGACY_APP_LABEL],
        )
        migration_rows = cursor.fetchone()[0]
    except Exception:
        # A schema without django_migrations is not a tenant schema we
        # need to care about; treat it as having no records.
        migration_rows = 0

    return SchemaEvidence(
        schema=schema,
        tables=tables,
        row_counts=row_counts,
        inbound_refs=inbound,
        migration_rows=migration_rows,
    )


def apply_cleanup(cursor, evidence: SchemaEvidence) -> None:
    """Drop the tables and clear the migration records for one schema."""
    for table in LEGACY_TABLES:          # child-first order
        if table in evidence.tables:
            cursor.execute(f'DROP TABLE IF EXISTS "{evidence.schema}"."{table}"')
    if evidence.migration_rows:
        cursor.execute(
            'DELETE FROM django_migrations WHERE app = %s', [LEGACY_APP_LABEL]
        )


class Command(BaseCommand):
    help = (
        'Remove orphaned integrations_* tables and migration records left '
        'by an abandoned app build. Dry run unless --apply is given.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually drop. Without this the command only reports.',
        )
        parser.add_argument(
            '--schema', default=None,
            help='Limit to one schema. Default: every schema in the database.',
        )

    def handle(self, *args, **options):
        from django_tenants.utils import schema_context

        apply_changes: bool = options['apply']
        only: str | None = options['schema']

        schemas = self._schemas(only)
        if not schemas:
            raise CommandError(
                f'No such schema: {only}' if only else 'No schemas found.'
            )

        header = 'APPLYING' if apply_changes else 'DRY RUN - nothing will change'
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'clear_orphaned_integrations | {header} | {len(schemas)} schema(s)'
        ))

        tallies = {SKIP: 0, CLEAN: 0, REFUSE: 0}

        for schema in schemas:
            with schema_context(schema):
                with connection.cursor() as cursor:
                    evidence = gather(cursor, schema)
                    decision = decide(evidence)
                    tallies[decision.outcome] += 1

                    if decision.outcome == CLEAN and apply_changes:
                        # One transaction per schema: a failure part-way
                        # leaves that schema exactly as it was found.
                        with transaction.atomic():
                            apply_cleanup(cursor, evidence)

            self._report(schema, decision, applied=apply_changes)

        self.stdout.write('')
        self.stdout.write(
            f'  cleaned {tallies[CLEAN]} | refused {tallies[REFUSE]} '
            f'| nothing to do {tallies[SKIP]}'
        )
        if tallies[CLEAN] and not apply_changes:
            self.stdout.write(self.style.WARNING(
                '  Dry run. Re-run with --apply to make these changes.'
            ))
        if tallies[REFUSE]:
            self.stdout.write(self.style.ERROR(
                '  Refused schemas need a human decision - see the reasons above.'
            ))

    # ---- helpers ----------------------------------------------------

    def _schemas(self, only: str | None) -> list[str]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name NOT IN ('information_schema')
                  AND schema_name NOT LIKE 'pg\\_%%'
                ORDER BY schema_name
                """
            )
            found = [r[0] for r in cursor.fetchall()]
        return [s for s in found if s == only] if only else found

    def _report(self, schema: str, decision: Decision, *, applied: bool) -> None:
        if decision.outcome == SKIP:
            self.stdout.write(f'  {schema:46} {decision.reason}')
        elif decision.outcome == CLEAN:
            verb = 'cleaned' if applied else 'would clean'
            self.stdout.write(self.style.SUCCESS(
                f'  {schema:46} {verb}: {decision.reason}'
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f'  {schema:46} REFUSED: {decision.reason}'
            ))
