"""
Tenant-schema fixtures for the debt tests.

``Client.auto_create_schema = False`` in this project (tenants/models.py),
so django-tenants' own ``TenantTestCase`` / ``FastTenantTestCase`` cannot
be used for anything that touches a tenant table: they create the tenant
*row* by calling ``save()`` and rely on the schema being materialised as
a side effect, which never happens here. The tenant appears, the tables
do not, and every query fails with ``relation ... does not exist``.

The one working setup in this repository lives in
``accounting/tests/conftest.py``, which creates ``pytest_schema`` and
calls ``client.create_schema()`` explicitly. It is re-exported here
rather than copied — a second 490-line transcription of schema setup
would drift from the original the first time either changed.

``django_db_setup`` builds the schema once per session;
``_route_to_pytest_schema`` is autouse and switches the connection for
any test that asks for the ``db`` fixture, which ``@pytest.mark.django_db``
does.

Promoting these two fixtures to a repository-root ``conftest.py`` would
let the other thirteen future modules be tested the same way. That is a
larger change than this one and is noted in the PR rather than done here.
"""
from accounting.tests.conftest import (  # noqa: F401  (re-exported fixtures)
    _route_to_pytest_schema,
    django_db_setup,
    open_fiscal_period,
)
