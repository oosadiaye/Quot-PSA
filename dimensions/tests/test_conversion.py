"""Converting an approved purchase request into an order carries the request's custom dimensions onto the order."""
from datetime import date

import pytest
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounting.models import Account, FiscalYear, Fund, Function, Geo, Program
from dimensions import services
from procurement.models import PurchaseRequest, PurchaseRequestLine, Vendor, VendorCategory

pytestmark = pytest.mark.django_db(transaction=True)
DOMAIN = 'pytest.localhost'


def _admin_client():
    from tenants.models import Client, Domain, UserTenantRole
    with schema_context('public'):
        tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
        Domain.objects.get_or_create(domain=DOMAIN, tenant=tenant, defaults={'is_primary': True})
    user, _ = User.objects.get_or_create(username='dim_conv_admin', defaults={'email': 'a@t.test'})
    UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': 'admin', 'is_active': True})
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _vendor():
    payable, _ = Account.objects.get_or_create(
        code='21009111', defaults=dict(name='AP dim conv', account_type='Liability',
                                       reconciliation_type='accounts_payable', is_active=True))
    category, _ = VendorCategory.objects.get_or_create(
        name='Dim conversion category', defaults=dict(code='DIM-CONV', reconciliation_account=payable))
    fiscal_year = FiscalYear.objects.order_by('-id').first() or FiscalYear.objects.create(
        year=date.today().year, name=str(date.today().year), start_date=date(date.today().year, 1, 1),
        end_date=date(date.today().year, 12, 31))
    vendor, _ = Vendor.objects.get_or_create(
        code='DIM-V-1', defaults=dict(
            name='Dim Vendor', category=category, is_active=True, registration_fiscal_year=fiscal_year,
            registration_date=date.today(), expiry_date=date(date.today().year + 1, 12, 31)))
    return vendor


def test_the_order_made_from_a_request_carries_its_zone_and_ward(zone_ward):
    for dimension in (zone_ward['zone'], zone_ward['ward']):
        dimension.applies_to = ['journal_line', 'purchase_request', 'purchase_order']
        dimension.save()
    dims = [m.objects.get_or_create(code='DIMC', defaults={'name': 'Dim'})[0] for m in (Fund, Function, Program, Geo)]
    request = PurchaseRequest.objects.create(
        request_number=f'PR-DIM-CONV-{PurchaseRequest.objects.count() + 1}-{date.today():%H%M%S}', description='Borehole', status='Pending',
        fund=dims[0], function=dims[1], program=dims[2], geo=dims[3])
    expense, _ = Account.objects.get_or_create(
        code='29990777', defaults=dict(name='Dim conv expense', account_type='Expense', is_active=True))
    PurchaseRequestLine.objects.create(
        request=request, item_description='Pump', quantity=1, estimated_unit_price=500, account=expense)
    services.set_tags('purchase_request', request.pk, {'ward': 'W1'})
    PurchaseRequest.objects.filter(pk=request.pk).update(status='Approved')

    response = _admin_client().post(
        f'/api/v1/procurement/requests/{request.pk}/convert_to_po/',
        {'vendor_id': _vendor().pk, 'order_date': date.today().isoformat()}, format='json')
    assert response.status_code == 200, response.content
    assert services.get_tags('purchase_order', response.json()['po_id']) == {'zone': 'Z1', 'ward': 'W1'}
