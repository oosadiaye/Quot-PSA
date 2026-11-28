"""The dimensions API: a tenant admin defines a type and its values, forms read what to show, tags are set (refusals are
409s with a reason) and the report answers. A user with no role on the tenant gets nothing."""
import pytest
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, JournalLine

pytestmark = pytest.mark.django_db(transaction=True)
DOMAIN = 'pytest.localhost'
BASE = '/api/v1/dimensions'


def _tenant():
    from tenants.models import Client, Domain
    with schema_context('public'):
        tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
        Domain.objects.get_or_create(domain=DOMAIN, tenant=tenant, defaults={'is_primary': True})
    return tenant


def _client(role='admin'):
    from tenants.models import UserTenantRole
    tenant = _tenant()
    user, _ = User.objects.get_or_create(username=f'dim_api_{role}', defaults={'email': f'{role}@t.test'})
    UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': role, 'is_active': True})
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _line():
    acct, _ = Account.objects.get_or_create(
        code='29990001', defaults=dict(name='Dim test expense', account_type='Expense', is_active=True))
    header = JournalHeader.objects.create(description='dim api', status='Draft')
    return JournalLine.objects.create(header=header, account=acct, debit=100, credit=0)


def test_an_admin_defines_a_ward_under_a_zone_and_forms_see_it(zone_ward):
    admin = _client()
    made = admin.post(f'{BASE}/types/', {
        'code': 'polling', 'name': 'Polling Unit', 'parent_type': zone_ward['ward'].pk,
        'applies_to': ['journal_line'], 'required_on': []}, format='json')
    assert made.status_code == 201, made.content
    value = admin.post(f'{BASE}/values/', {
        'dimension_type': made.json()['id'], 'code': 'P1', 'name': 'Unit One', 'parent': zone_ward['w1'].pk}, format='json')
    assert value.status_code == 201, value.content

    form = admin.get(f'{BASE}/types/for-record/', {'record_type': 'journal_line'}).json()
    by_code = {d['code']: d for d in form}
    assert {'zone', 'ward', 'polling'} <= set(by_code)
    assert by_code['polling']['parent_type'] == 'ward'
    assert by_code['ward']['values'][0]['parent'] in {'Z1', 'Z2'}
    assert admin.get(f'{BASE}/types/for-record/', {'record_type': 'nonsense'}).status_code == 400


def test_a_value_must_sit_under_a_value_of_the_parent_type(zone_ward):
    admin = _client()
    wrong = admin.post(f'{BASE}/values/', {
        'dimension_type': zone_ward['ward'].pk, 'code': 'W9', 'name': 'Bad', 'parent': zone_ward['w1'].pk}, format='json')
    assert wrong.status_code == 400 and 'parent' in wrong.json()
    top = admin.post(f'{BASE}/values/', {
        'dimension_type': zone_ward['zone'].pk, 'code': 'Z9', 'name': 'Top', 'parent': zone_ward['z1'].pk}, format='json')
    assert top.status_code == 400


def test_mandatory_needs_the_dimension_switched_on_and_record_types_are_checked(zone_ward):
    admin = _client()
    url = f'{BASE}/types/{zone_ward["zone"].pk}/'
    assert admin.patch(url, {'required_on': ['purchase_order']}, format='json').status_code == 400
    assert admin.patch(url, {'applies_to': ['spaceship']}, format='json').status_code == 400
    assert admin.patch(url, {'applies_to': ['journal_line', 'purchase_order'],
                             'required_on': ['purchase_order']}, format='json').status_code == 200


def test_tags_are_set_read_and_refused_with_a_reason(zone_ward):
    admin = _client()
    line = _line()
    ok = admin.post(f'{BASE}/tags/set/', {'record_type': 'journal_line', 'record_id': line.pk,
                                          'tags': {'zone': 'Z1', 'ward': 'W1'}}, format='json')
    assert ok.status_code == 200 and ok.json() == {'zone': 'Z1', 'ward': 'W1'}
    assert admin.get(f'{BASE}/tags/', {'record_type': 'journal_line', 'record_id': line.pk}).json() == {
        'zone': 'Z1', 'ward': 'W1'}
    bad = admin.post(f'{BASE}/tags/set/', {'record_type': 'journal_line', 'record_id': line.pk,
                                           'tags': {'zone': 'Z1', 'ward': 'W2'}}, format='json')
    assert bad.status_code == 409 and 'not in' in bad.json()['error']
    assert admin.post(f'{BASE}/tags/set/', {'record_type': 'journal_line'}, format='json').status_code == 400


def test_the_report_answers_and_an_unknown_dimension_is_a_404(zone_ward):
    admin = _client()
    body = admin.get(f'{BASE}/tags/report/ward/').json()
    assert body['dimension'] == 'ward' and any(r['code'] == '(untagged)' for r in body['rows'])
    assert admin.get(f'{BASE}/tags/report/nothing/').status_code == 404


def test_someone_with_no_role_on_the_tenant_gets_nothing(zone_ward):
    outsider = User.objects.get_or_create(username='dim_outsider', defaults={'email': 'o@t.test'})[0]
    token, _ = Token.objects.get_or_create(user=outsider)
    client = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    assert client.get(f'{BASE}/types/').status_code == 403
