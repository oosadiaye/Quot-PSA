"""
pytest fixtures shared by every accounting test.

Key design choices (read this before writing new tests):

* **Schema-per-test-run, not per-test**: creating a tenant schema is slow in
  ``django-tenants``. We create ONE test tenant (``pytest_schema``) at
  session start and route every test at it. Individual tests are wrapped in
  transactions by ``pytest-django``'s ``db`` fixture, so they see an empty
  database anyway.
* **No business seeding in fixtures**: tests that need NCoA segments, MDAs,
  fiscal periods, etc. create them explicitly in the test body. This makes
  the preconditions obvious and prevents shared mutable state between tests.
* **`make_journal` helper**: most Sprint 1/3 regression tests want to assert
  what happens when you try to post a journal under some condition. The
  ``make_journal`` fixture returns a factory that takes (dr_lines, cr_lines,
  posting_date, status) and returns a saved ``JournalHeader``. It bypasses
  service-layer balance checks by using ``JournalLine.objects.create``
  directly — we need this so we can *construct* unbalanced journals to
  verify the DB constraint rejects them.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db.backends.postgresql.operations import (
    DatabaseOperations as _PgDatabaseOperations,
)


# ---------------------------------------------------------------------------
# Cross-schema flush bridge
# ---------------------------------------------------------------------------
#
# pytest-django teardown for ``TransactionTestCase`` and the
# ``transactional_db`` fixture calls Django's ``flush`` management
# command. ``flush`` issues plain ``TRUNCATE table1, table2, ...`` —
# but in django-tenants, tenant-schema tables (e.g.
# ``accounting_journalheader``) carry foreign keys to public-schema
# tables (``auth_user``). Postgres rejects a TRUNCATE on a referenced
# table without CASCADE, so teardown explodes with
# ``FeatureNotSupported: cannot truncate a table referenced in a
# foreign key constraint``.
#
# Patch ``sql_flush`` to always emit ``CASCADE``. This is safe in a
# test database (we're throwing the data away) and is a no-op against
# tables without inbound FKs.
_ORIGINAL_SQL_FLUSH = _PgDatabaseOperations.sql_flush


def _sql_flush_cascade(self, style, tables, *, reset_sequences=False, allow_cascade=False):
    return _ORIGINAL_SQL_FLUSH(
        self, style, tables,
        reset_sequences=reset_sequences,
        allow_cascade=True,  # force CASCADE for cross-schema FKs
    )


_PgDatabaseOperations.sql_flush = _sql_flush_cascade


# ---------------------------------------------------------------------------
# Tenant / schema setup (django-tenants aware)
# ---------------------------------------------------------------------------
#
# django-tenants splits tables between the public schema (SHARED_APPS —
# tenants, auth, etc.) and per-tenant schemas (TENANT_APPS — accounting,
# budget, procurement, etc.). pytest-django's default ``migrate`` only
# runs against public, so tenant-only tables like
# ``accounting_administrativesegment`` never exist.
#
# To fix this we:
#   1. Extend ``django_db_setup`` to create a single test tenant
#      (``tenants.Client(schema_name='pytest_schema')``) after the normal
#      public-schema migrate completes. ``auto_create_schema=True`` on
#      the Client model fires ``migrate_schemas`` for our new schema
#      when ``.save()`` is called — this brings every tenant-app table
#      into being.
#   2. Create the paired ``tenants.Domain`` row (django-tenants refuses
#      certain operations without one).
#   3. Provide an ``autouse`` fixture that switches the DB connection to
#      the tenant schema for every test that requests ``db`` — but NOT
#      for pure-import smoke tests that never touch the DB.

PYTEST_SCHEMA_NAME = 'pytest_schema'


@pytest.fixture(scope='session')
def django_db_setup(request, django_db_setup, django_db_blocker):
    """Ensure tenant-app tables exist before any DB-touching test runs.

    Chains off the real ``django_db_setup`` from pytest-django so the
    public schema is migrated first. Then creates a Client + Domain
    for ``pytest_schema`` which triggers tenant-schema migration.
    """
    with django_db_blocker.unblock():
        from django.db import connection
        from django_tenants.utils import schema_exists
        from tenants.models import Client, Domain

        connection.set_schema_to_public()

        client = Client.objects.filter(schema_name=PYTEST_SCHEMA_NAME).first()
        if client is None:
            client = Client(
                schema_name=PYTEST_SCHEMA_NAME,
                name='PyTest Tenant',
            )
            # Note: ``Client.auto_create_schema = False`` in this project,
            # so ``client.save()`` only persists the row — it does NOT
            # create the Postgres schema. The schema is materialised
            # explicitly below via ``client.create_schema()`` so we have
            # one canonical creation path that works whether the row is
            # new or partially-recovered from a prior failed run.
            client.save()

            Domain.objects.get_or_create(
                domain='pytest.localhost',
                tenant=client,
                defaults={'is_primary': True},
            )

        # Ensure the Postgres schema exists and is fully migrated.
        #
        # Why the manual sequence below (and not a plain
        # ``client.create_schema()``):
        #
        # ``django-tenants``' ``create_schema()`` runs ``migrate_schemas``
        # in a single shot. The first migration applied is
        # ``contenttypes.0001_initial`` (which creates ``django_content_type``
        # with the legacy ``name NOT NULL`` column). The very next
        # migration that calls ``ContentType.objects.get_for_model()``
        # from a ``RunPython`` seeder OR fires a ``post_save`` audit
        # signal (e.g. ``accounting/migrations/0080_budgetcheckrule.py``
        # → ``log_model_changes`` → ``AuditLog.log_create`` →
        # ``ContentType.get_for_model``) tries to INSERT into
        # ``django_content_type`` with ``name=None`` and trips the NOT
        # NULL constraint — before ``contenttypes.0002`` ever runs.
        #
        # Fix: create an empty schema first, run the contenttypes
        # migrations TO COMPLETION (0001 + 0002 → column dropped), then
        # run the rest of the tenant migrations against an already-
        # corrected ``django_content_type`` table.
        from django.core.management import call_command
        from django_tenants.utils import schema_context

        if not schema_exists(PYTEST_SCHEMA_NAME):
            # 1. Plain ``CREATE SCHEMA`` only — no migrations.
            with connection.cursor() as cur:
                cur.execute(f'CREATE SCHEMA "{PYTEST_SCHEMA_NAME}"')

            # 2. Run contenttypes app migrations to completion against
            #    the new schema. ``0001_initial`` creates the table,
            #    ``0002_remove_content_type_name`` drops the bad column,
            #    so by the time any other migration's seeder calls
            #    ``ContentType.get_for_model()`` the schema is correct.
            with schema_context(PYTEST_SCHEMA_NAME):
                call_command(
                    'migrate',
                    'contenttypes',
                    verbosity=0,
                    interactive=False,
                )

        # 3. Run ALL tenant migrations. ``django_content_type`` is now in
        #    its post-0002 shape (no ``name`` column), so any RunPython
        #    seeder that creates audited rows succeeds. Already-applied
        #    contenttypes migrations are no-ops.
        call_command(
            'migrate_schemas',
            schema_name=PYTEST_SCHEMA_NAME,
            verbosity=0,
        )

        connection.set_schema_to_public()


@pytest.fixture(autouse=True)
def _route_to_pytest_schema(request):
    """Auto-switch to ``pytest_schema`` for every test that touches the DB.

    We detect DB usage by checking if the test consumes the ``db`` or
    ``transactional_db`` fixtures indirectly. Tests that don't (smoke
    tests, pure-import tests) skip this entirely — no DB setup cost.

    Teardown note: pytest-django closes the test-transaction BEFORE
    fixture teardown runs. By the time we try to restore the schema,
    the connection may already be in a closed/aborted state. We catch
    every exception silently during teardown — the connection is about
    to be discarded anyway, so a failed schema-reset is harmless.
    """
    # If this test doesn't ask for the DB fixture (directly or via
    # another fixture), don't touch the connection.
    needs_db = any(
        name in request.fixturenames
        for name in ('db', 'transactional_db', 'django_db_reset_sequences')
    )
    if not needs_db:
        yield
        return

    from django.db import connection
    previous = getattr(connection, 'schema_name', 'public')
    try:
        connection.set_schema(PYTEST_SCHEMA_NAME)
    except Exception:
        # If schema switching fails (public-only connection), still
        # let the test run — it will fail with a clear error if it
        # actually needs tenant tables.
        pass
    try:
        yield
    finally:
        # Restore the public schema on the way out so other fixtures
        # that tear down DB state (e.g. transaction rollback) see a
        # consistent connection. Swallow every error — the connection
        # state during teardown is not guaranteed valid.
        try:
            connection.set_schema_to_public()
        except Exception:
            # Last-ditch: if we can't set public, at least clear the
            # schema_name so the next test's setup picks a clean slate.
            try:
                connection.schema_name = 'public'
                connection.tenant = None
            except Exception:
                pass


# ---------------------------------------------------------------------------
# User fixtures — maker / checker / superuser
# ---------------------------------------------------------------------------

@pytest.fixture
def maker_user(db):
    """Regular user who SUBMITS documents. Cannot self-approve."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username='maker',
        defaults={'email': 'maker@test.local'},
    )
    return user


@pytest.fixture
def checker_user(db):
    """Separate user who APPROVES documents — required to satisfy
    maker-checker separation in ApprovalWorkflowService."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username='checker',
        defaults={'email': 'checker@test.local'},
    )
    return user


@pytest.fixture
def superuser(db):
    """Superuser — bypasses every permission + role gate."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username='super',
        defaults={
            'email': 'super@test.local',
            'is_superuser': True,
            'is_staff': True,
        },
    )
    return user


# ---------------------------------------------------------------------------
# Core accounting fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fund(db):
    from accounting.models import Fund
    fund, _ = Fund.objects.get_or_create(code='01', defaults={'name': 'Consolidated Fund'})
    return fund


@pytest.fixture
def cash_account(db):
    """Default cash/bank account (Asset, normal-debit)."""
    from accounting.models import Account
    acc, _ = Account.objects.get_or_create(
        code='10100000',
        defaults={'name': 'Cash and Bank', 'account_type': 'Asset', 'is_active': True},
    )
    return acc


@pytest.fixture
def expense_account(db):
    """Default expense account (Expense, normal-debit)."""
    from accounting.models import Account
    acc, _ = Account.objects.get_or_create(
        code='50100000',
        defaults={'name': 'Purchase Expense', 'account_type': 'Expense', 'is_active': True},
    )
    return acc


@pytest.fixture
def revenue_account(db):
    """Default revenue account (Income, normal-credit)."""
    from accounting.models import Account
    acc, _ = Account.objects.get_or_create(
        code='40100000',
        defaults={'name': 'Service Revenue', 'account_type': 'Income', 'is_active': True},
    )
    return acc


@pytest.fixture
def accumulated_fund_account(db):
    """The target account for year-end close."""
    from accounting.models import Account
    acc, _ = Account.objects.get_or_create(
        code='43100000',
        defaults={'name': 'Accumulated Fund', 'account_type': 'Equity', 'is_active': True},
    )
    return acc


@pytest.fixture
def open_fiscal_period(db):
    """A currently-open monthly period covering today."""
    from accounting.models import FiscalPeriod
    today = date.today()
    period, _ = FiscalPeriod.objects.get_or_create(
        fiscal_year=today.year,
        period_number=today.month,
        period_type='Monthly',
        defaults={
            'start_date': today.replace(day=1),
            'end_date': today.replace(day=28),  # safe upper bound
            'status': 'Open',
            'is_closed': False,
        },
    )
    return period


@pytest.fixture
def closed_fiscal_period(db):
    """A CLOSED period in a prior year — useful for period-lock tests."""
    from accounting.models import FiscalPeriod
    period, _ = FiscalPeriod.objects.get_or_create(
        fiscal_year=2020,
        period_number=1,
        period_type='Monthly',
        defaults={
            'start_date': date(2020, 1, 1),
            'end_date': date(2020, 1, 31),
            'status': 'Closed',
            'is_closed': True,
        },
    )
    return period


# ---------------------------------------------------------------------------
# Factory: build a journal without going through the service layer
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_journal(db):
    """Factory to build a JournalHeader + lines directly via ORM.

    Returns a function ``(lines, *, posting_date, status, reference) →
    JournalHeader``. ``lines`` is a list of (account, debit, credit)
    tuples. The factory does NOT go through BasePostingService, so it
    can be used to attempt deliberately-unbalanced constructions for
    DB constraint tests.

    The default ``reference`` is generated uniquely per call (``TEST-<id>``
    derived from a counter) so tests that don't care about reference
    values don't collide under the uniqueness constraint added in
    Sprint 1. Tests that want to exercise the uniqueness constraint
    pass an explicit ``reference=``.
    """
    from accounting.models import JournalHeader, JournalLine
    import itertools

    counter = itertools.count(1)

    def _make(lines, *, posting_date=None, status='Draft', reference=None):
        if reference is None:
            reference = f'TEST-AUTO-{next(counter):05d}'
        header = JournalHeader.objects.create(
            posting_date=posting_date or date.today(),
            description='pytest-generated journal',
            reference_number=reference,
            status=status,
        )
        for account, debit, credit in lines:
            # Each line is validated by DB CheckConstraints (S1-01).
            JournalLine.objects.create(
                header=header,
                account=account,
                debit=Decimal(str(debit or 0)),
                credit=Decimal(str(credit or 0)),
            )
        return header

    return _make
