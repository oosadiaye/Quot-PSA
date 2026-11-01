"""Back-end helpers for the supplier-portal E2E, run from the repository root with the project's own Python.

  token   <tenant-domain> <email>                 -> prints an API token for the user with that email
  reset-link <tenant-domain> <email>              -> prints `uid token`, as the emailed choose-a-password link carries them
  module  <tenant-domain> <name> [on|off]         -> prints a module's state (on / off / none), and switches it when told to
  item    <tenant-domain> <sku> <name>            -> creates (or refreshes) an inventory item
  activate <tenant-domain> <vendor-code>          -> marks the supplier's registration as paid
  po      <tenant-domain> <vendor-code> <number>  -> creates an approved purchase order for the supplier
  cleanup <tenant-domain> <vendor-code>           -> removes the supplier, its sign-in, orders and bank-change requests

The portal itself is driven through the app; these exist only for what a browser cannot do (a supplier's password is
chosen from an emailed link, and a purchase order has no simple form).
"""
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'quot_pse.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django_tenants.utils import schema_context  # noqa: E402
from rest_framework.authtoken.models import Token  # noqa: E402

from tenants.models import Domain  # noqa: E402


def schema_for(domain: str) -> str:
    with schema_context('public'):
        return Domain.objects.select_related('tenant').get(domain=domain).tenant.schema_name


def token(domain: str, email: str) -> None:
    with schema_context('public'):
        user = get_user_model().objects.get(email__iexact=email)
        print(Token.objects.get_or_create(user=user)[0].key)


def activate(domain: str, code: str) -> None:
    """Mark the supplier's registration as paid, so it shows in the register and an order may be raised on it."""
    from procurement.models import Vendor

    with schema_context(schema_for(domain)):
        Vendor.objects.filter(code=code).update(is_active=True)
        print('ok')


def reset_link(domain: str, email: str) -> None:
    """Print the uid and token an emailed password link carries, as ``uid token``."""
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    with schema_context('public'):
        user = get_user_model().objects.get(email__iexact=email)
        print(urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user))


def module(domain: str, name: str, state: str = '') -> None:
    """Print whether a module is on (on / off / none) and, given on|off, switch it. The running server caches the answer for up
    to a minute, so a change is seen by it after that."""
    from core.models import TenantModule

    with schema_context(schema_for(domain)):
        row = TenantModule.objects.filter(module_name=name).first()
        print('none' if row is None else 'on' if row.is_active else 'off')
        if state in ('on', 'off'):
            TenantModule.objects.update_or_create(module_name=name, defaults={'is_active': state == 'on'})


def item(domain: str, sku: str, name: str) -> None:
    from inventory.models import Item

    with schema_context(schema_for(domain)):
        row, _ = Item.objects.update_or_create(sku=sku, defaults={'name': name, 'description': name, 'unit_of_measure': 'bag', 'barcode': sku, 'is_active': True})
        print(row.pk)


def po(domain: str, code: str, number: str) -> None:
    from accounting.models.gl import Account, Fund, Function, Geo, MDA, Program
    from procurement.models import PurchaseOrder, PurchaseOrderLine, Vendor

    with schema_context(schema_for(domain)):
        vendor = Vendor.objects.get(code=code)
        Vendor.objects.filter(pk=vendor.pk).update(is_active=True)      # an order cannot be raised on a supplier who has not paid registration
        vendor.refresh_from_db()
        fund, _ = Fund.objects.get_or_create(code='E2E1', defaults={'name': 'E2E Fund'})
        fn, _ = Function.objects.get_or_create(code='E2E1', defaults={'name': 'E2E Function'})
        pr, _ = Program.objects.get_or_create(code='E2E1', defaults={'name': 'E2E Programme'})
        geo, _ = Geo.objects.get_or_create(code='E2E1', defaults={'name': 'E2E Geo'})
        acct, _ = Account.objects.get_or_create(code='22100993', defaults={'name': 'E2E Expense', 'account_type': 'Expense'})
        mda, _ = MDA.objects.get_or_create(code='E2E-MDA', defaults={'name': 'E2E MDA', 'short_name': 'E2E'})
        order = PurchaseOrder.objects.create(mda=mda, vendor=vendor, order_date=date.today(), fund=fund, function=fn, program=pr, geo=geo,
                                             status='Pending', po_number=number)
        PurchaseOrderLine.objects.create(po=order, item_description='Borehole pump', quantity=Decimal('2'), unit_price=Decimal('150000.00'), account=acct)
        PurchaseOrder.objects.filter(pk=order.pk).update(status='Approved')
        print(order.pk)


def cleanup(domain: str, code: str) -> None:
    from procurement.models import PurchaseOrder, Vendor, VendorUser

    emails = [f'{code.lower()}@example.test']      # the test convention; also catches a sign-in left by an earlier failed run
    with schema_context(schema_for(domain)):
        for vendor in Vendor.objects.filter(code=code):
            emails += [vu.user.email for vu in VendorUser.objects.filter(vendor=vendor).select_related('user')]
            PurchaseOrder.objects.filter(vendor=vendor).delete()   # acknowledgements go with them
            try:                                                   # the catalogue is optional; its rows protect the supplier
                from catalogue.models import CatalogueItem, PriceHistory, SupplierCatalogue
                CatalogueItem.objects.filter(catalogue__supplier=vendor).delete()
                SupplierCatalogue.objects.filter(supplier=vendor).delete()
                PriceHistory.objects.filter(supplier=vendor).delete()
            except ImportError:
                pass
            vendor.delete()                                        # sign-in link and bank-change requests go with it
    from core.models import PasswordHistory, UserSession          # a supplier who chose a password has these; they protect the user
    from tenants.models import UserTenantRole
    with schema_context('public'):
        users = get_user_model().objects.filter(email__in=emails)
        UserTenantRole.objects.filter(user__in=users).delete()
        Token.objects.filter(user__in=users).delete()
        PasswordHistory.objects.filter(user__in=users).delete()
        UserSession.objects.filter(user__in=users).delete()
    # Deleted from inside the tenant schema, where the tables that point at a user (some per-tenant) can all be reached.
    with schema_context(schema_for(domain)):
        get_user_model().objects.filter(email__in=emails).delete()
    print('ok')


if __name__ == '__main__':
    command, *args = sys.argv[1:]
    {'token': token, 'po': po, 'activate': activate, 'cleanup': cleanup, 'module': module, 'item': item, 'reset-link': reset_link}[command](*args)
