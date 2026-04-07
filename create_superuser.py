import os
import sys
import getpass
import django
# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dtsg_erp.settings')
django.setup()

from django.contrib.auth.models import User
from django_tenants.utils import tenant_context
from tenants.models import Client

def create_super_admin():
    tenant_name = os.environ.get('DEFAULT_TENANT', 'dtsg_hq')
    try:
        tenant = Client.objects.get(schema_name=tenant_name)
    except Client.DoesNotExist:
        print(f"Tenant {tenant_name} not found.")
        return

    with tenant_context(tenant):
        print(f"Creating Superuser for {tenant.name}...")
        
        username = os.environ.get('ADMIN_USERNAME', 'admin_all')
        email = os.environ.get('ADMIN_EMAIL', 'admin@dtsg.gov')
        password = os.environ.get('ADMIN_PASSWORD')
        
        if not password:
            password = getpass.getpass('Enter password for superuser (leave empty to skip): ')
            if not password:
                print("No password provided. Skipping user creation.")
                return
        
        if User.objects.filter(username=username).exists():
            print(f"User {username} already exists. Resetting privileges.")
            u = User.objects.get(username=username)
            u.is_superuser = True
            u.is_staff = True
            u.set_password(password)
            u.save()
            print(f"Password updated for user {username}.")
        else:
            User.objects.create_superuser(username=username, email=email, password=password)
            print(f"Superuser {username} created.")
            
        print(f"Username: {username}")
        print("WARNING: Never share credentials or commit them to version control.")

if __name__ == "__main__":
    create_super_admin()
