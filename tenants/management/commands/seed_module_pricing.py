"""
Seed the commercial module catalogue (ModulePricing).

Creates (or updates-in-place) a ``ModulePricing`` row for every key in
``AVAILABLE_MODULES`` so the superadmin pricing page has a catalogue to price.
The registry (``AVAILABLE_MODULES``) is the source of truth for keys — a
pricing row is never created for a key that is not in the registry, and no key
is ever dropped.

ModulePricing lives in the **public (shared) PostgreSQL schema** — the pricing
catalogue is global, not per-tenant — so this command wraps every write in
``schema_context('public')``.

Prices default to 0 / month; the superadmin sets real prices through the UI or
the ``module_pricing`` API.  Running the command is idempotent: existing rows
are updated with the current registry title/description but their prices are
left untouched.

Usage:
    python manage.py seed_module_pricing
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Seed ModulePricing catalogue rows for every AVAILABLE_MODULES key'

    def handle(self, *args, **options):
        from tenants.models import AVAILABLE_MODULES, ModulePricing

        created_count = 0
        updated_count = 0
        with schema_context('public'):
            for index, (key, title, desc) in enumerate(AVAILABLE_MODULES):
                obj, created = ModulePricing.objects.update_or_create(
                    module_name=key,
                    defaults={
                        'title': title,
                        'tagline': desc,
                        'description': desc,
                        'sort_order': index,
                        'is_active': True,
                    },
                )
                if created:
                    created_count += 1
                else:
                    # Never overwrite a superadmin's price/features; only keep
                    # title/description/sort in sync with the registry.
                    if (obj.title != title or obj.tagline != desc
                            or obj.sort_order != index):
                        obj.save(update_fields=['title', 'tagline', 'sort_order'])
                        updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Module pricing seeded: {created_count} created, '
            f'{updated_count} updated, {len(AVAILABLE_MODULES)} total'
        ))
