"""Tenant-schema routing and shared fixtures for staff_advances tests (see debt/tests/conftest.py for the schema notes)."""
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.tests.conftest import (  # noqa: F401  (re-exported fixtures)
    _route_to_pytest_schema,
    django_db_setup,
    open_fiscal_period,
)


@pytest.fixture
def actor(db):
    user, _ = User.objects.get_or_create(username="adv_officer", defaults={"email": "adv@example.com"})
    return user


@pytest.fixture
def gl(db):
    """The three accounts an advance touches. Tagged, so the service prefers them over its settings fallback; get-or-create
    because accounting_account is not flushed between transactional tests."""
    Account.objects.filter(reconciliation_type="staff_advance").exclude(code="1900100").update(reconciliation_type="")
    recon, _ = Account.objects.update_or_create(
        code="1900100", defaults=dict(name="Staff Advances Recon", account_type="Asset",
                                      reconciliation_type="staff_advance", is_active=True))
    cash, _ = Account.objects.update_or_create(
        code="3100900", defaults=dict(name="Advances Test Cash", account_type="Asset", is_active=True))
    # The debit leg of a recovery. A clearing account outside the strictly budget-controlled expenditure range, so these
    # tests are about the shape of the journal; the budget control itself is tested separately with a real expense code.
    expense, _ = Account.objects.update_or_create(
        code="3900100", defaults=dict(name="Advances Recovery Clearing", account_type="Asset", is_active=True))
    return SimpleNamespace(recon=recon, cash=cash, expense=expense, bank=SimpleNamespace(gl_account=cash))


@pytest.fixture
def employee(db):
    from hrm.models import Department, Employee, Position
    user, _ = User.objects.get_or_create(username="adv_employee", defaults={"email": "emp@example.com"})
    dept, _ = Department.objects.get_or_create(code="ADV-D", defaults={"name": "Advances Dept"})
    pos, _ = Position.objects.get_or_create(code="ADV-P", defaults={"title": "Officer", "department": dept, "grade": "Mid"})
    emp, _ = Employee.objects.get_or_create(
        employee_number="EMP-ADV-1", defaults={"user": user, "department": dept, "position": pos, "hire_date": "2025-01-01"})
    return emp
