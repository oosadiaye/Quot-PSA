"""Tenant-schema routing for cash_planning tests (re-exports the one shared definition, see budget/tests/conftest.py)."""
from accounting.tests.conftest import (  # noqa: F401  (re-exported as fixtures)
    django_db_setup,
    _route_to_pytest_schema,
)
