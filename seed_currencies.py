import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'quot_pse.settings')
django.setup()

from django_tenants.utils import tenant_context
from tenants.models import Client
from accounting.models import Currency

def seed_base_currency():
    tenant_name = 'dtsg_hq'
    try:
        tenant = Client.objects.get(schema_name=tenant_name)
    except Client.DoesNotExist:
        print(f"Tenant {tenant_name} not found.")
        return

    with tenant_context(tenant):
        print(f"Seeding base currency for {tenant.name}...")
        
        # Create USD as base currency
        usd, created = Currency.objects.get_or_create(
            code='USD',
            defaults={
                'name': 'US Dollar',
                'symbol': '$',
                'exchange_rate': 1.0,
                'is_base_currency': True,
                'is_active': True
            }
        )
        
        if created:
            print(f"✓ Created base currency: {usd}")
        else:
            print(f"✓ Base currency already exists: {usd}")
            
        # Create some common currencies
        currencies_data = [
            {'code': 'EUR', 'name': 'Euro', 'symbol': '€', 'rate': 0.92},
            {'code': 'GBP', 'name': 'British Pound', 'symbol': '£', 'rate': 0.79},
            {'code': 'CAD', 'name': 'Canadian Dollar', 'symbol': 'C$', 'rate': 1.36},
        ]
        
        for curr_data in currencies_data:
            curr, created = Currency.objects.get_or_create(
                code=curr_data['code'],
                defaults={
                    'name': curr_data['name'],
                    'symbol': curr_data['symbol'],
                    'exchange_rate': curr_data['rate'],
                    'is_base_currency': False,
                    'is_active': True
                }
            )
            if created:
                print(f"✓ Created currency: {curr}")

if __name__ == "__main__":
    seed_base_currency()
