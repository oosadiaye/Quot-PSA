from django.core.management.base import BaseManagementCommand
from django.utils import timezone
from django_tenants.utils import tenant_context
from tenants.models import Client
from procurement.models import Vendor, PurchaseOrder, PurchaseRequest
from inventory.models import Item, Warehouse
from sales.models import Customer, SalesOrder
from service.models import ServiceAsset, ServiceTicket
from accounting.models import Fund, Function, Program, Geo, Account
import random
from decimal import Decimal

class Command(BaseManagementCommand):
    help = 'Seeds the database with demo data for UAT.'

    def handle(self, *args, **kwargs):
        tenant_name = 'dtsg_hq'
        try:
            tenant = Client.objects.get(schema_name=tenant_name)
        except Client.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Tenant {tenant_name} not found."))
            return

        with tenant_context(tenant):
            self.stdout.write(f"Seeding data for {tenant.name}...")

            # 1. Master Data - Procurement
            vendors = [
                {'name': 'TechCorp Solutions', 'email': 'sales@techcorp.com'},
                {'name': 'Office Supplies Co.', 'email': 'orders@officesupplies.com'},
                {'name': 'Global Logistics', 'email': 'contact@global-log.com'},
            ]
            vendor_objs = []
            for v_data in vendors:
                v, _ = Vendor.objects.get_or_create(name=v_data['name'], defaults={'email': v_data['email']})
                vendor_objs.append(v)
                
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
                    'unit_price': i_data['unit_p'],
                    'total_quantity': 10 if not created else 0, # Initial stock if checking logic manually elsewhere
                    'average_cost': i_data['unit_p']
                })
                item_objs.append(i)

            # 3. Master Data - Sales
            customers = [
                {'name': 'Dept of Transportation', 'email': 'procurement@dot.gov'},
                {'name': 'City Hall Admin', 'email': 'admin@cityhall.gov'},
            ]
            cust_objs = []
            for c_data in customers:
                c, _ = Customer.objects.get_or_create(name=c_data['name'], defaults={'email': c_data['email'], 'phone': '555-0101'})
                cust_objs.append(c)

            # 4. Master Data - Service
            assets = [
                {'serial': 'SRV-HVAC-01', 'name': 'Server Room HVAC'},
                {'serial': 'FLEET-V-102', 'name': 'Ford Transit Van'},
            ]
            for a_data in assets:
                ServiceAsset.objects.get_or_create(serial_number=a_data['serial'], defaults={'name': a_data['name']})

            # 5. Create Transactional Data - Purchase Orders
            if not PurchaseOrder.objects.exists():
                po = PurchaseOrder.objects.create(
                    vendor=vendor_objs[0],
                    order_date=timezone.now().date(),
                    delivery_date=timezone.now().date() + timezone.timedelta(days=7),
                    status='Draft',
                    total_amount=Decimal('2400.00')
                )
                self.stdout.write(f"Created PO: {po.po_number}")

            # 6. Create Transactional Data - Sales Orders
            if not SalesOrder.objects.exists():
                so = SalesOrder.objects.create(
                    customer=cust_objs[0],
                    order_date=timezone.now().date(),
                    status='Draft',
                    total_amount=Decimal('5000.00')
                )
                self.stdout.write(f"Created Sales Order: {so.order_number}")

            self.stdout.write(self.style.SUCCESS("Seeding Completed Successfully."))
