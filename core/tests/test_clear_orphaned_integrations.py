"""
The decision half of ``clear_orphaned_integrations``.

No database. The command drops tables, so what is worth testing is not
that DROP works but **when it refuses** — and that is a pure function
over observed evidence, which can be driven directly.

The refusals matter more than the cleanups here. This command will be
run against tenants nobody has surveyed, where the assumption "these
tables are empty orphans" may simply be false: a customer's schema could
have the same tables carrying real exchange history, or something could
have adopted them. Every case below is one of those.
"""
import ast
import inspect

from django.test import SimpleTestCase

from core.management.commands.clear_orphaned_integrations import (
    CLEAN,
    LEGACY_APP_LABEL,
    LEGACY_TABLES,
    REFUSE,
    SKIP,
    SchemaEvidence,
    decide,
)

def _non_ascii_literals(source: str) -> list[str]:
    """String constants in ``source`` that are not ASCII, docstrings aside.

    Docstrings carry deliberate typography and never reach a terminal;
    everything else in this command might.
    """
    tree = ast.parse(source)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))

    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and not node.value.isascii()
    ]


ALL_TABLES = LEGACY_TABLES
EMPTY_COUNTS = {t: 0 for t in ALL_TABLES}


def evidence(**kw) -> SchemaEvidence:
    base = dict(schema='tenant_x', tables=(), row_counts={}, inbound_refs=(),
                migration_rows=0)
    base.update(kw)
    return SchemaEvidence(**base)


class NothingToDoTests(SimpleTestCase):
    def test_clean_schema_is_skipped(self):
        # Seven of nine schemas here are already in this state. They must
        # not be touched, and must not be reported as work done.
        self.assertEqual(decide(evidence()).outcome, SKIP)

    def test_skip_is_reported_without_alarm(self):
        self.assertEqual(decide(evidence()).reason, 'nothing to do')


class RefusalTests(SimpleTestCase):
    """The cases where the orphan assumption is wrong."""

    def test_refuses_when_any_table_holds_rows(self):
        # A customer tenant may have the same tables with real exchange
        # history. Dropping those would destroy audit evidence.
        ev = evidence(
            tables=ALL_TABLES,
            row_counts={**EMPTY_COUNTS, 'integrations_integrationmessage': 42},
            migration_rows=1,
        )
        decision = decide(ev)
        self.assertEqual(decision.outcome, REFUSE)
        self.assertIn('42', decision.reason)

    def test_refusal_names_every_populated_table(self):
        # An operator reading the refusal should not have to go and query.
        ev = evidence(
            tables=ALL_TABLES,
            row_counts={
                'integrations_integrationmessage': 7,
                'integrations_integrationrun': 3,
                'integrations_integrationendpoint': 0,
            },
            migration_rows=1,
        )
        reason = decide(ev).reason
        self.assertIn('integrations_integrationmessage=7', reason)
        self.assertIn('integrations_integrationrun=3', reason)
        # The empty one is not noise worth printing.
        self.assertNotIn('integrations_integrationendpoint=0', reason)

    def test_one_row_is_enough_to_refuse(self):
        # No threshold. "Mostly empty" is not empty.
        ev = evidence(
            tables=ALL_TABLES,
            row_counts={**EMPTY_COUNTS, 'integrations_integrationrun': 1},
            migration_rows=1,
        )
        self.assertEqual(decide(ev).outcome, REFUSE)

    def test_refuses_when_something_outside_references_the_tables(self):
        # If another table has a foreign key into these, they are no
        # longer orphan residue — something adopted them, and dropping
        # would break that something.
        ev = evidence(
            tables=ALL_TABLES,
            row_counts=EMPTY_COUNTS,
            inbound_refs=(('accounting_paymentbatch', 'integrations_integrationrun'),),
            migration_rows=1,
        )
        decision = decide(ev)
        self.assertEqual(decision.outcome, REFUSE)
        self.assertIn('accounting_paymentbatch', decision.reason)

    def test_data_is_refused_ahead_of_references(self):
        # Both wrong at once: the data refusal is the more alarming one
        # and is the message an operator should see first.
        ev = evidence(
            tables=ALL_TABLES,
            row_counts={**EMPTY_COUNTS, 'integrations_integrationrun': 5},
            inbound_refs=(('x', 'integrations_integrationrun'),),
            migration_rows=1,
        )
        self.assertIn('hold data', decide(ev).reason)


class CleanupTests(SimpleTestCase):
    """The state actually observed in this database."""

    def test_empty_tables_with_a_migration_record_are_cleaned(self):
        ev = evidence(tables=ALL_TABLES, row_counts=EMPTY_COUNTS, migration_rows=1)
        decision = decide(ev)
        self.assertEqual(decision.outcome, CLEAN)
        self.assertIn('3 empty table(s)', decision.reason)
        self.assertIn('1 migration record(s)', decision.reason)

    def test_tables_without_a_migration_record_are_still_cleaned(self):
        # Half-torn-down state: someone dropped the record but not the
        # tables. Leaving the tables would still shadow a fresh build.
        ev = evidence(tables=ALL_TABLES, row_counts=EMPTY_COUNTS, migration_rows=0)
        self.assertEqual(decide(ev).outcome, CLEAN)

    def test_a_migration_record_without_tables_is_still_cleaned(self):
        # The dangerous half: the record alone is what makes Django skip
        # a fresh 0001_initial, so it must go even with no tables to drop.
        ev = evidence(tables=(), row_counts={}, migration_rows=1)
        decision = decide(ev)
        self.assertEqual(decision.outcome, CLEAN)
        self.assertIn('migration record', decision.reason)

    def test_a_partial_set_of_tables_is_cleaned(self):
        ev = evidence(
            tables=('integrations_integrationrun',),
            row_counts={'integrations_integrationrun': 0},
            migration_rows=1,
        )
        self.assertEqual(decide(ev).outcome, CLEAN)


class ConstantsTests(SimpleTestCase):
    """Cheap guards on things that are easy to get wrong later."""

    def test_drop_order_is_child_first(self):
        # message -> run -> endpoint. Dropping a parent first would fail
        # on its foreign keys.
        self.assertEqual(
            LEGACY_TABLES,
            (
                'integrations_integrationmessage',
                'integrations_integrationrun',
                'integrations_integrationendpoint',
            ),
        )

    def test_app_label_matches_the_table_prefix(self):
        # The migration records cleared and the tables dropped have to
        # belong to the same app, or the command half-works.
        for table in LEGACY_TABLES:
            self.assertTrue(table.startswith(f'{LEGACY_APP_LABEL}_'))


class ConsoleOutputTests(SimpleTestCase):
    """Operator-facing text must survive a Windows console.

    The default Windows code page is cp1252, and this command is run by
    an administrator at a terminal, not by a web request. An em dash or
    a middot in a printed string arrives as a replacement character,
    which in a tool that drops tables reads like corruption rather than
    typography.
    """

    def test_no_non_ascii_reaches_the_console(self):
        # Parsed rather than pattern-matched. A regex over source has to
        # re-implement Python string literals - prefixes, escapes, triple
        # quotes - and a regex that is subtly wrong here passes by finding
        # nothing, which is worse than having no test at all.
        from core.management.commands import clear_orphaned_integrations as mod

        offenders = _non_ascii_literals(inspect.getsource(mod))
        self.assertEqual(offenders, [], f'non-ASCII in printed strings: {offenders}')

    def test_the_ascii_guard_would_catch_a_violation(self):
        # A guard that has never fired is an assertion about code, not
        # protection. Drive the same helper over source that does contain
        # a printed non-ASCII literal and require it to be found.
        newline = chr(10)
        em_dash = chr(8212)
        source = (
            'def f():' + newline
            + '    """Docstring typography is deliberate."""' + newline
            + '    return "printed em dash ' + em_dash + ' not fine"' + newline
        )
        self.assertEqual(len(_non_ascii_literals(source)), 1,
                         'the guard failed to catch a violation')

    def test_decide_reasons_are_ascii(self):
        # The reasons are the part an operator reads when the command
        # refuses, which is exactly when clarity matters most.
        cases = [
            evidence(),
            evidence(tables=ALL_TABLES, row_counts={**EMPTY_COUNTS,
                                                   'integrations_integrationrun': 3},
                     migration_rows=1),
            evidence(tables=ALL_TABLES, row_counts=EMPTY_COUNTS,
                     inbound_refs=(('other', 'integrations_integrationrun'),),
                     migration_rows=1),
            evidence(tables=ALL_TABLES, row_counts=EMPTY_COUNTS, migration_rows=1),
        ]
        for ev in cases:
            reason = decide(ev).reason
            self.assertTrue(reason.isascii(), f'non-ASCII reason: {reason!r}')
