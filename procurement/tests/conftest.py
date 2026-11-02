"""Tenant-schema plumbing for procurement DB-backed tests.

Procurement tables (``procurement_vendor``, …) live in ``TENANT_APPS``, so any
test that touches the DB must run inside a tenant schema. Reuse the shared
session-scoped ``django_db_setup`` (it builds ``pytest_schema`` once, via
``migrate_schemas``) and route each DB-touching test onto that schema.

Note: the ``@pytest.mark.django_db`` marker injects ``_django_db_helper`` into
the fixture closure rather than the bare name ``db``, so the DB detection must
look for that too — otherwise a marker-only test never gets routed.
"""
import pytest

# Session-scoped schema build (creates ``pytest_schema`` if missing).
from contracts.tests.conftest import django_db_setup  # noqa: F401

PYTEST_SCHEMA_NAME = "pytest_schema"

_DB_FIXTURE_NAMES = (
    "db",
    "transactional_db",
    "django_db_reset_sequences",
    "_django_db_helper",  # injected by the @pytest.mark.django_db marker
)


@pytest.fixture(autouse=True)
def _route_to_pytest_schema(request):
    """Switch the connection to ``pytest_schema`` for DB-touching tests."""
    if not any(name in request.fixturenames for name in _DB_FIXTURE_NAMES):
        yield
        return

    from django.db import connection
    # Re-assert the tenant + domain on public first (a preceding transaction=True
    # test can flush them on CI); get_or_create is a no-op once present.
    try:
        connection.set_schema_to_public()
        from tenants.models import Client, Domain
        client, _ = Client.objects.get_or_create(
            schema_name=PYTEST_SCHEMA_NAME, defaults={"name": "PyTest Tenant"},
        )
        Domain.objects.get_or_create(
            domain="pytest.localhost", tenant=client, defaults={"is_primary": True},
        )
    except Exception:
        pass
    try:
        connection.set_schema(PYTEST_SCHEMA_NAME)
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            connection.set_schema_to_public()
        except Exception:
            pass
