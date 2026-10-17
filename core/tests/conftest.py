"""Tenant-schema routing for DB-backed tests in ``core``.

Most existing ``core`` tests are pure-Python and never touch the DB, so the
router below yields immediately for them. DB-backed tests (for example
``test_user_mda_assignment``) get routed onto ``pytest_schema``.

The fixtures are reused from ``procurement/tests/conftest.py`` rather than
copied a third time; see that file for why the router must look for
``_django_db_helper`` (the ``django_db`` marker injects it instead of ``db``).
"""
from procurement.tests.conftest import (  # noqa: F401
    django_db_setup,
    _route_to_pytest_schema,
)
