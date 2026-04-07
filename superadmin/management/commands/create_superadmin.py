import os
import getpass
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings


class Command(BaseCommand):
    help = 'Create default superadmin user'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Superadmin username')
        parser.add_argument('--email', type=str, help='Superadmin email')
        parser.add_argument('--password', type=str, help='Superadmin password (will prompt if not provided)')

    def handle(self, *args, **options):
        username = options.get('username') or os.environ.get('SUPERADMIN_USERNAME', 'superadmin')
        email = options.get('email') or os.environ.get('SUPERADMIN_EMAIL', 'admin@dtsg.gov')
        password = options.get('password') or os.environ.get('SUPERADMIN_PASSWORD')
        
        if not password:
            password = getpass.getpass('Enter password for superadmin: ')
            if not password:
                self.stdout.write(self.style.ERROR('Password is required. Use --password or set SUPERADMIN_PASSWORD env var.'))
                return
        
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User {username} already exists'))
            u = User.objects.get(username=username)
            u.is_superuser = True
            u.is_staff = True
            u.set_password(password)
            u.save()
            self.stdout.write(self.style.SUCCESS(f'Password updated for user {username}'))
            return
        
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        
        # Create superadmin profile
        from superadmin.models import SuperAdminProfile
        SuperAdminProfile.objects.create(
            user=user,
            is_superadmin=True,
            is_active=True
        )
        
        self.stdout.write(self.style.SUCCESS(f'Superadmin created: {username}'))
        self.stdout.write(self.style.WARNING('WARNING: Never share credentials or commit them to version control.'))
