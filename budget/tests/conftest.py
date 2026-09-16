"""Tenant-schema routing for budget tests.

``budget_appropriation`` and friends live in TENANT_APPS, so a test that
touches them needs the connection pointed at ``pytest_schema`` — on the
public schema the tables simply are not there, and the failure reads as
``relation "accounting_fiscalyear" does not exist`` rather than anything
about tenancy.

``accounting/tests/conftest.py`` and ``contracts/tests/conftest.py`` each
carry their own copy of the two fixtures that arrange this. This one
imports them instead of writing a third: they are infrastructure, not
fixtures about budgets, and three hand-kept copies drift. Re-exporting
keeps one definition and gives pytest the same two names it would find
in a local copy.

  django_db_setup          session-scoped; creates pytest_schema and
                           migrates the tenant apps into it
  _route_to_pytest_schema  autouse; switches the connection for any test
                           that asks for the ``db`` fixture, and leaves
                           tests that do not alone
"""
from accounting.tests.conftest import (  # noqa: F401  (re-exported as fixtures)
    django_db_setup,
    _route_to_pytest_schema,
)
