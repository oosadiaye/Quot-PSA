"""Tenant-schema routing for dimensions tests (see debt/tests/conftest.py for the schema notes)."""
import pytest

from accounting.tests.conftest import (  # noqa: F401  (re-exported fixtures)
    _route_to_pytest_schema,
    django_db_setup,
)
from dimensions.models import DimensionType, DimensionValue


@pytest.fixture
def zone_ward(db):
    """Zone (parent type) and Ward (child type), both on for journal lines, with two zones and a ward under each."""
    zone, _ = DimensionType.objects.get_or_create(
        code='zone', defaults=dict(name='Zone', applies_to=['journal_line'], required_on=[]))
    ward, _ = DimensionType.objects.get_or_create(
        code='ward', defaults=dict(name='Ward', parent_type=zone, applies_to=['journal_line'], required_on=[]))
    # The fixture is get-or-create because the tenant tables are not flushed between tests: reset what tests change.
    for t in (zone, ward):
        t.is_active, t.required_on, t.applies_to = True, [], ['journal_line']
        t.save()
    z1, _ = DimensionValue.objects.get_or_create(dimension_type=zone, code='Z1', defaults=dict(name='North Zone'))
    z2, _ = DimensionValue.objects.get_or_create(dimension_type=zone, code='Z2', defaults=dict(name='South Zone'))
    w1, _ = DimensionValue.objects.get_or_create(dimension_type=ward, code='W1', defaults=dict(name='Ward One', parent=z1))
    w2, _ = DimensionValue.objects.get_or_create(dimension_type=ward, code='W2', defaults=dict(name='Ward Two', parent=z2))
    DimensionValue.objects.filter(pk__in=[z1.pk, z2.pk, w1.pk, w2.pk]).update(is_active=True)
    return dict(zone=zone, ward=ward, z1=z1, z2=z2, w1=w1, w2=w2)
