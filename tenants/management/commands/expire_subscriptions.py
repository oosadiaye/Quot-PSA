"""Management command to auto-expire subscriptions past their end_date.

Usage:
    python manage.py expire_subscriptions
    python manage.py expire_subscriptions --dry-run

Recommended: Run daily via cron or celery beat.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from tenants.models import TenantSubscription


class Command(BaseCommand):
    help = 'Expire subscriptions that have passed their end_date'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview which subscriptions would be expired without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()

        with schema_context('public'):
            expired_subs = TenantSubscription.objects.filter(
                status='active',
                end_date__lt=today,
                auto_renew=False,
            ).select_related('tenant', 'plan')

            count = expired_subs.count()

            if dry_run:
                self.stdout.write(f'Would expire {count} subscriptions:')
                for sub in expired_subs:
                    self.stdout.write(
                        f'  - {sub.tenant.name} (plan: {sub.plan.name if sub.plan else "None"}, '
                        f'ended: {sub.end_date})'
                    )
                return

            if count == 0:
                self.stdout.write(self.style.SUCCESS('No subscriptions to expire.'))
                return

            for sub in expired_subs:
                sub.status = 'expired'
                sub.save(update_fields=['status'])
                self.stdout.write(
                    f'  Expired: {sub.tenant.name} (ended {sub.end_date})'
                )

            self.stdout.write(
                self.style.SUCCESS(f'Successfully expired {count} subscriptions.')
            )

            # Also handle auto-renew subscriptions: extend them
            auto_renew_subs = TenantSubscription.objects.filter(
                status='active',
                end_date__lt=today,
                auto_renew=True,
            ).select_related('tenant', 'plan')

            from datetime import timedelta
            for sub in auto_renew_subs:
                billing_days = {'monthly': 30, 'quarterly': 90, 'yearly': 365}
                days = billing_days.get(
                    sub.plan.billing_cycle if sub.plan else 'monthly', 30
                )
                sub.end_date = today + timedelta(days=days)
                sub.save(update_fields=['end_date'])
                self.stdout.write(
                    f'  Auto-renewed: {sub.tenant.name} (new end: {sub.end_date})'
                )

            renew_count = auto_renew_subs.count()
            if renew_count:
                self.stdout.write(
                    self.style.SUCCESS(f'Auto-renewed {renew_count} subscriptions.')
                )
