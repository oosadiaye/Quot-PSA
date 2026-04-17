import os
import django
from decimal import Decimal
from django.utils import timezone
import random

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'quot_pse.settings')
django.setup()

from django_tenants.utils import tenant_context
from tenants.models import Client
from procurement.models import Vendor, PurchaseOrder, PurchaseOrderLine
from inventory.models import Item, Warehouse
from accounting.models import Fund, Function, Program, Geo, Account

def seed_demo_data():
    tenant_name = 'dtsg_hq'
    try:
        tenant = Client.objects.get(schema_name=tenant_name)
    except Client.DoesNotExist:
        print(f"Tenant {tenant_name} not found.")
        return

    with tenant_context(tenant):
        print(f"Seeding data for {tenant.name}...")

        # 0. Master Data - Dimensions & Accounts (Prerequisites)
        fund = Fund.objects.first() or Fund.objects.create(name='General Fund', code='100')
        function = Function.objects.first() or Function.objects.create(name='General Govt', code='1000')
        program = Program.objects.first() or Program.objects.create(name='Administration', code='001')
        geo = Geo.objects.first() or Geo.objects.create(name='Headquarters', code='HQ')

        # Ensure Accounts
        acc_inv, _ = Account.objects.get_or_create(code='1200', defaults={'name': 'Inventory Asset', 'account_type': 'Asset'})
        acc_exp, _ = Account.objects.get_or_create(code='5000', defaults={'name': 'Office Supplies Expense', 'account_type': 'Expense'})
        acc_rev, _ = Account.objects.get_or_create(code='4000', defaults={'name': 'Sales Revenue', 'account_type': 'Income'})
        acc_ar, _ = Account.objects.get_or_create(code='1100', defaults={'name': 'Accounts Receivable', 'account_type': 'Asset'})

        print("Dimensions and Accounts ready.")

        # 1. Master Data - Procurement
        vendors = [
            {'code': 'V-TECH', 'name': 'TechCorp Solutions', 'email': 'sales@techcorp.com'},
            {'code': 'V-OFFICE', 'name': 'Office Supplies Co.', 'email': 'orders@officesupplies.com'},
            {'code': 'V-LOGISTIC', 'name': 'Global Logistics', 'email': 'contact@global-log.com'},
        ]
        vendor_objs = []
        for v_data in vendors:
            v, _ = Vendor.objects.get_or_create(code=v_data['code'], defaults={
                'name': v_data['name'],
                'email': v_data['email']
            })
            vendor_objs.append(v)
            print(f"Vendor: {v.name} ({v.code})")

        # 2. Master Data - Inventory
        warehouse, _ = Warehouse.objects.get_or_create(name='Main Warehouse', location='HQ Basement')
        items = [
            {'sku': 'LP-001', 'name': 'Latitude 5000 Laptop', 'unit_p': 1200.00},
            {'sku': 'PR-X99', 'name': 'LaserJet Pro Printer', 'unit_p': 450.00},
            {'sku': 'PPR-A4', 'name': 'A4 Paper (Box)', 'unit_p': 45.00},
        ]

        item_objs = []
        for i_data in items:
            i, created = Item.objects.get_or_create(sku=i_data['sku'], defaults={
                'name': i_data['name'],
                'description': 'Standard Issue',
                'inventory_account': acc_inv,
                'expense_account': acc_exp,
                'total_quantity': 100,
                'total_value': i_data['unit_p'] * 100
            })
            item_objs.append(i)
            print(f"Item: {i.name}")

        # 3. Create Transactional Data - Purchase Orders
        po, created = PurchaseOrder.objects.get_or_create(
            po_number='PO-DEMO-001',
            defaults={
                'vendor': vendor_objs[0], # TechCorp
                'order_date': timezone.now().date(),
                'fund': fund,
                'function': function,
                'program': program,
                'geo': geo,
                'status': 'Draft',
            }
        )
        if created:
            # Add Line Item
            PurchaseOrderLine.objects.create(
                order=po,
                item_description=item_objs[0].name, # Laptop
                quantity=2,
                unit_price=1200.00,
                account=acc_exp
            )
            print(f"Created PO: {po.po_number}")

        print("Seeding Completed Successfully.")

if __name__ == "__main__":
    seed_demo_data()
