import os
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dtsg_erp.settings')
django.setup()

from django_tenants.utils import tenant_context
from tenants.models import Client, Domain
from accounting.models import Fund, Function, Program, Geo, Account

def create_test_tenant():
    schema_name = 'dtsg_hq'
    if not Client.objects.filter(schema_name=schema_name).exists():
        tenant = Client(
            schema_name=schema_name,
            name='DTSG Headquarters'
        )
        tenant.save()
        
        domain = Domain()
        domain.domain = 'hq.dtsg.test'
        domain.tenant = tenant
        domain.is_primary = True
        domain.save()
        print(f"Tenant {schema_name} created.")
    else:
        tenant = Client.objects.get(schema_name=schema_name)
        print(f"Tenant {schema_name} already exists.")

    # Populate data within the tenant context
    with tenant_context(tenant):
        # 1. Create Dimensions
        fund, _ = Fund.objects.get_or_create(code='1001', name='General Fund')
        func, _ = Function.objects.get_or_create(code='PS01', name='Public Safety')
        prog, _ = Program.objects.get_or_create(code='PR01', name='Community Policing')
        geo, _ = Geo.objects.get_or_create(code='NW01', name='North West Region')
        
        # 2. Create Accounts
        cash_account, _ = Account.objects.get_or_create(
            code='10001001', 
            name='Cash in Hand', 
            account_type='Asset'
        )
        revenue_account, _ = Account.objects.get_or_create(
            code='40001001', 
            name='Tax Revenue', 
            account_type='Income'
        )
        
        print(f"Master data populated for {tenant.name}.")

if __name__ == "__main__":
    create_test_tenant()
