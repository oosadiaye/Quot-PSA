"""The revenue lifecycle over HTTP: gated by the module switch and the caller's role."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounting.models import Account, RevenueHead
from core.models import TenantModule
from core.permissions import invalidate_module_cache
from revenue_admin.models import ArrearsLedger, Assessment, BillingRun, CollectionApplication, DemandNotice, Taxpayer

pytestmark = pytest.mark.django_db
DOMAIN = 'pytest.localhost'
BASE = '/api/v1/revenue-admin'


def _tenant():
    from tenants.models import Client, Domain
    with schema_context('public'):
        tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
        Domain.objects.get_or_create(domain=DOMAIN, tenant=tenant, defaults={'is_primary': True})
    return tenant


def _client(role='admin'):
    from tenants.models import UserTenantRole
    tenant = _tenant()
    user, _ = User.objects.get_or_create(username=f'rev_admin_{role}', defaults={'email': f'{role}@t.test'})
    UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': role, 'is_active': True})
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _module(active):
    TenantModule.objects.update_or_create(module_name='revenue_admin', defaults={'is_active': active})
    invalidate_module_cache(_tenant().pk, 'revenue_admin')


@pytest.fixture
def head():
    econ, _ = Account.objects.get_or_create(code="1RE0001", defaults={"name": "Endpoint revenue", "account_type": "Revenue"})
    h, _ = RevenueHead.objects.get_or_create(
        code="RE0001", defaults={"name": "Endpoint head", "economic_segment": econ, "revenue_type": "OTHER"})
    return h


@pytest.fixture
def taxpayer():
    return Taxpayer.objects.create(tin="TIN-RE-1", full_name="Endpoint Payer")


@pytest.fixture
def assessment(taxpayer, head):
    return Assessment.objects.create(taxpayer=taxpayer, revenue_head=head, fiscal_year=2026, assessed_amount=Decimal('800'))


def test_an_admin_issues_an_assessment_and_gets_the_notice(assessment):
    _module(True)
    r = _client('admin').post(f'{BASE}/assessments/{assessment.pk}/issue/', {}, format='json')
    assert r.status_code == 200, r.content
    body = r.json()
    assert body['notice_number'].startswith('DN-') and Decimal(body['amount_due']) == Decimal('800')
    assert DemandNotice.objects.filter(assessment=assessment).count() == 1


def test_issuing_something_that_cannot_be_issued_is_a_400_with_a_reason(taxpayer, head):
    _module(True)
    settled = Assessment.objects.create(taxpayer=taxpayer, revenue_head=head, fiscal_year=2026,
                                        assessed_amount=Decimal('5'), status='settled')
    r = _client('admin').post(f'{BASE}/assessments/{settled.pk}/issue/', {}, format='json')
    assert r.status_code == 400 and 'draft' in r.json()['error']


def test_a_billing_run_is_processed_over_http(assessment, head):
    _module(True)
    run = BillingRun.objects.create(revenue_head=head, fiscal_year=2026)
    r = _client('admin').post(f'{BASE}/billing-runs/{run.pk}/process/', {}, format='json')
    assert r.status_code == 200, r.content
    assert r.json()['notices_created'] == 1 and r.json()['status'] == 'processed'
    again = _client('admin').post(f'{BASE}/billing-runs/{run.pk}/process/', {}, format='json')
    assert again.status_code == 400


def test_update_ageing_marks_overdue_notices(taxpayer):
    _module(True)
    DemandNotice.objects.create(taxpayer=taxpayer, notice_number='DN-E-1', amount_due=Decimal('9'),
                                due_date=date.today() - timedelta(days=4))
    r = _client('admin').post(f'{BASE}/demand-notices/update-ageing/', {}, format='json')
    assert r.status_code == 200 and r.json()['notices_marked_overdue'] == 1


def test_clearance_is_issued_to_a_clean_taxpayer_and_refused_with_a_reason_otherwise(taxpayer, head):
    _module(True)
    ok = _client('admin').post(f'{BASE}/clearance-certificates/issue/',
                               {'taxpayer': taxpayer.pk, 'fiscal_year': 2026}, format='json')
    assert ok.status_code == 201, ok.content
    assert ok.json()['certificate_number'].startswith('TCC-')
    ArrearsLedger.objects.create(taxpayer=taxpayer, revenue_head=head, fiscal_year=2024, amount=Decimal('10'))
    no = _client('admin').post(f'{BASE}/clearance-certificates/issue/',
                               {'taxpayer': taxpayer.pk, 'fiscal_year': 2026}, format='json')
    assert no.status_code == 409 and 'arrears' in no.json()['error'].lower()


def test_how_collections_were_applied_is_readable_but_not_writable(taxpayer):
    _module(True)
    CollectionApplication.objects.create(collection_receipt='R-E-1', line_no=1, taxpayer=taxpayer, amount=Decimal('3'))
    admin = _client('admin')
    listed = admin.get(f'{BASE}/collection-applications/')
    assert listed.status_code == 200 and listed.json()['results'][0]['collection_receipt'] == 'R-E-1'
    assert admin.post(f'{BASE}/collection-applications/', {'collection_receipt': 'X', 'amount': '1'}, format='json').status_code == 405


def test_with_the_module_off_every_action_is_refused_and_nothing_changes(assessment):
    _module(False)
    r = _client('admin').post(f'{BASE}/assessments/{assessment.pk}/issue/', {}, format='json')
    assert r.status_code == 403 and r.json().get('code') == 'module_disabled'
    assert not DemandNotice.objects.filter(assessment=assessment).exists()


def test_a_read_only_viewer_cannot_issue(assessment):
    _module(True)
    r = _client('viewer').post(f'{BASE}/assessments/{assessment.pk}/issue/', {}, format='json')
    assert r.status_code == 403
    assert not DemandNotice.objects.filter(assessment=assessment).exists()


def test_anonymous_callers_are_turned_away(assessment):
    _module(True)
    r = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN).post(f'{BASE}/assessments/{assessment.pk}/issue/', {}, format='json')
    assert r.status_code in (401, 403)
