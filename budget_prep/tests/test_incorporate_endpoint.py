"""POST /budget-prep/submissions/<id>/incorporate/: gated by the module switch and the approver permission."""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from budget.models import Appropriation
from budget_prep.models import BudgetSubmission, SubmissionLine
from budget_prep.tests.test_incorporation import YEAR, dims  # noqa: F401  (fixture)
from core.models import TenantModule
from core.permissions import invalidate_module_cache

pytestmark = pytest.mark.django_db
DOMAIN = 'pytest.localhost'


def _tenant():
    from tenants.models import Client, Domain
    with schema_context('public'):
        tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
        Domain.objects.get_or_create(domain=DOMAIN, tenant=tenant, defaults={'is_primary': True})
    return tenant


def _client(role='admin'):
    from tenants.models import UserTenantRole
    tenant = _tenant()
    user, _ = User.objects.get_or_create(username=f'prep_handoff_{role}', defaults={'email': f'{role}@t.test'})
    UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': role, 'is_active': True})
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _module(active):
    TenantModule.objects.update_or_create(module_name='budget_prep', defaults={'is_active': active})
    invalidate_module_cache(_tenant().pk, 'budget_prep')


@pytest.fixture
def ready(dims):  # noqa: F811
    sub = BudgetSubmission.objects.create(fiscal_year=YEAR, mda_name='Prep Test MDA', stage='incorporated')
    SubmissionLine.objects.create(
        submission=sub, line_type='overhead', administrative=dims['admin'], economic=dims['econ'], functional=dims['func'],
        programme=dims['prog'], fund=dims['fund'], proposed_amount=Decimal('250.00'))
    return sub


def url(sub):
    return f'/api/v1/budget-prep/submissions/{sub.pk}/incorporate/'


def test_with_the_module_on_an_admin_creates_the_drafts(ready):
    _module(True)
    r = _client('admin').post(url(ready), {}, format='json')
    assert r.status_code == 200, r.content
    assert r.json()['created'] == 1
    assert Appropriation.objects.filter(source_module='budget_prep', source_reference=f'submission:{ready.pk}',
                                        status='DRAFT', amount_approved=Decimal('250.00')).count() == 1


def test_with_the_module_off_the_hand_off_is_refused_and_nothing_is_created(ready):
    _module(False)
    r = _client('admin').post(url(ready), {}, format='json')
    assert r.status_code == 403 and r.json().get('code') == 'module_disabled'
    assert not Appropriation.objects.filter(source_reference=f'submission:{ready.pk}').exists()


def test_a_submission_still_in_review_is_a_400_with_a_reason(ready):
    _module(True)
    BudgetSubmission.objects.filter(pk=ready.pk).update(stage='in_review')
    r = _client('admin').post(url(ready), {}, format='json')
    assert r.status_code == 400 and 'incorporated' in r.json()['error']


def test_drafts_survive_the_module_being_switched_off(ready):
    _module(True)
    assert _client('admin').post(url(ready), {}, format='json').status_code == 200
    _module(False)
    assert Appropriation.objects.filter(source_reference=f'submission:{ready.pk}').count() == 1


def test_anonymous_callers_are_turned_away(ready):
    _module(True)
    assert APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN).post(url(ready), {}, format='json').status_code in (401, 403)
