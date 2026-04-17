import os
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'quot_pse.settings')
django.setup()

from tenants.models import Client, Domain

def create_public_tenant():
    # Create the public tenant
    if not Client.objects.filter(schema_name='public').exists():
        tenant = Client(
            schema_name='public',
            name='Public Schema'
        )
        tenant.save()
        
        # Create a domain for the public tenant
        domain = Domain()
        domain.domain = 'localhost' # Or your development domain
        domain.tenant = tenant
        domain.is_primary = True
        domain.save()
        print("Public tenant and domain created successfully.")
    else:
        print("Public tenant already exists.")

if __name__ == "__main__":
    create_public_tenant()
