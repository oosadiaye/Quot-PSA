"""Tenant-schema routing for revenue_admin tests (re-exports the one shared definition, see debt/tests/conftest.py)."""
from accounting.tests.conftest import (  # noqa: F401  (re-exported fixtures)
    _route_to_pytest_schema,
    django_db_setup,
)
