"""Django system checks for the hrm app.

Run with::

    python manage.py check --tag=data

These checks intentionally hit the database, so they are tagged ``data``
and skipped during the default ``manage.py check`` run.
"""
from __future__ import annotations

from django.core.checks import Tags, Warning, register
from django.db import DatabaseError, OperationalError, ProgrammingError, connection


@register(Tags.database)
def employees_missing_organization(app_configs, **kwargs):
    """Warn when active employees still lack an ``organization`` FK.

    Surfaces residual rows the ``hrm.0017`` backfill could not resolve.
    Skips cleanly in the pre-migration window when the Employee table
    does not yet exist.
    """
    from hrm.models import Employee

    table_name = Employee._meta.db_table
    if table_name not in connection.introspection.table_names():
        return []

    try:
        missing = Employee.objects.filter(
            status__in=['Active', 'Probation'],
            organization__isnull=True,
        ).count()
    except (DatabaseError, OperationalError, ProgrammingError):
        # Schema not ready (e.g. column missing pre-migrate) — silent skip.
        return []

    if missing == 0:
        return []

    return [
        Warning(
            f'{missing} active employee(s) have no organization assigned. '
            'Payroll runs scoped by organization will skip these rows. '
            'Resolve by populating UserOrganization for the employee.user '
            'and re-running hrm.0017, or by editing the employee directly.',
            hint='SELECT id, employee_number FROM hrm_employee '
                 "WHERE organization_id IS NULL AND status IN ('Active','Probation');",
            id='hrm.W001',
        )
    ]
