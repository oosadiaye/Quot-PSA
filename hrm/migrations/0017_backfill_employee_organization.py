"""Backfill ``Employee.organization`` from the user's organization assignment.

The proxy chain ``Employee.department.cost_center.organization`` does not
exist in this codebase (CostCenter has no ``organization`` FK), so the
backfill falls back to the user-level mapping:

    Employee.user -> UserOrganization (is_default=True, else first) -> Organization

Rows that cannot be resolved stay NULL; the ``hrm.W001`` system check
surfaces the residual count after migration. The reverse op is a no-op so
the schema migration can be unwound without re-clearing FKs.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def backfill_employee_organization(apps, schema_editor):
    Employee = apps.get_model('hrm', 'Employee')
    UserOrganization = apps.get_model('core', 'UserOrganization')

    employees_without_org = list(
        Employee.objects.filter(organization__isnull=True)
        .only('id', 'user_id')
    )
    total = len(employees_without_org)
    if total == 0:
        logger.info('hrm.0017: no employees need organization backfill.')
        return

    # Map user_id -> organization_id using UserOrganization (prefer default).
    user_ids = {e.user_id for e in employees_without_org if e.user_id}
    assignments = (
        UserOrganization.objects
        .filter(user_id__in=user_ids)
        .order_by('user_id', '-is_default', 'id')
        .values('user_id', 'organization_id')
    )
    user_to_org: dict[int, int] = {}
    for row in assignments:
        # First row per user wins thanks to ordering above.
        user_to_org.setdefault(row['user_id'], row['organization_id'])

    to_update = []
    for emp in employees_without_org:
        org_id = user_to_org.get(emp.user_id)
        if org_id is not None:
            emp.organization_id = org_id
            to_update.append(emp)

    backfilled = 0
    for start in range(0, len(to_update), BATCH_SIZE):
        chunk = to_update[start:start + BATCH_SIZE]
        Employee.objects.bulk_update(chunk, ['organization'])
        backfilled += len(chunk)

    remaining_null = (
        Employee.objects.filter(organization__isnull=True).count()
    )
    logger.warning(
        'hrm.0017 backfill complete: %s rows backfilled, %s rows still NULL '
        '(no user_organizations row found). See hrm.W001.',
        backfilled, remaining_null,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0016_employee_organization'),
    ]

    operations = [
        migrations.RunPython(
            backfill_employee_organization,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
