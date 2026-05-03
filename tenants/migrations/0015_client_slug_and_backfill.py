"""Add ``slug`` field to Client + backfill subdomain Domain rows.

Two responsibilities:
  1. Add the ``slug`` column on ``tenants_client`` so future tenant
     subdomains can be derived from a short URL-safe identifier (e.g.
     ``oag-delta`` → ``oag-delta.erp.tryquot.com``).
  2. Backfill existing tenants by:
       a. Generating a slug from each tenant's ``name``
          (or ``schema_name`` if ``name`` doesn't yield a useful slug).
       b. Creating a ``<slug>.<SUBDOMAIN_BASE>`` Domain row for each
          tenant — non-primary so existing primary Domain rows remain
          valid and DNS-routable.

The backfill is idempotent: re-running the migration is safe because
each step uses ``get_or_create`` / ``filter().exists()`` guards.
"""
from django.db import migrations, models
from django.core.validators import RegexValidator


def _slugify(name: str, max_length: int = 30) -> str:
    """Inline copy of ``slugify_tenant_name`` so the migration is
    self-contained and doesn't reach into the live model module
    (which can drift). DNS-label safe."""
    import re
    s = (name or '').lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return (s or 'tenant')[:max_length].rstrip('-') or 'tenant'


def backfill_slugs_and_domains(apps, schema_editor):
    Client = apps.get_model('tenants', 'Client')
    Domain = apps.get_model('tenants', 'Domain')

    from django.conf import settings
    base = getattr(settings, 'TENANT_SUBDOMAIN_BASE', None) or 'erp.tryquot.com'

    used_slugs: set[str] = set(
        Client.objects.exclude(slug='').values_list('slug', flat=True)
    )

    for tenant in Client.objects.filter(slug=''):
        # Prefer ``name``; fall back to ``schema_name`` for tenants with
        # auto-generated test names (e.g. ``async_test_1777047406369``).
        candidate_base = _slugify(tenant.name or tenant.schema_name)
        candidate = candidate_base
        n = 2
        while candidate in used_slugs:
            suffix = f'-{n}'
            candidate = candidate_base[: 30 - len(suffix)] + suffix
            n += 1
        used_slugs.add(candidate)
        tenant.slug = candidate
        tenant.save(update_fields=['slug'])

        # Add the new subdomain Domain row only if it's not already
        # present (idempotent on re-run).
        domain_value = f'{candidate}.{base}'
        if not Domain.objects.filter(domain=domain_value).exists():
            Domain.objects.create(
                domain=domain_value,
                tenant=tenant,
                # Don't override the existing primary; the legacy
                # ``*.dtsg.test`` row stays primary until ops cuts over.
                is_primary=False,
            )


def reverse_noop(apps, schema_editor):
    """Reversal leaves the data in place — slugs and domain rows are
    forward-only. Removing them on reverse would silently break URLs
    that downstream environments may have already cached."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0014_client_provisioning_completed_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='slug',
            field=models.CharField(
                blank=True, default='',
                help_text=('Short URL slug used as subdomain prefix '
                           '(e.g. "oag-delta").'),
                max_length=30,
                validators=[RegexValidator(
                    regex=r'^[a-z0-9](?:[a-z0-9-]{0,28}[a-z0-9])?$',
                    message=(
                        'Tenant slug must be lowercase letters, digits, '
                        'or hyphens, 2-30 characters, and may not start '
                        'or end with a hyphen.'
                    ),
                )],
            ),
        ),
        migrations.RunPython(backfill_slugs_and_domains, reverse_noop),
        # Promote to UNIQUE only AFTER backfill so existing rows don't
        # collide on the empty default. Two tenants with empty slugs
        # would otherwise violate the unique constraint mid-migration.
        migrations.AlterField(
            model_name='client',
            name='slug',
            field=models.CharField(
                blank=True, default='', unique=True,
                help_text=('Short URL slug used as subdomain prefix '
                           '(e.g. "oag-delta").'),
                max_length=30,
                validators=[RegexValidator(
                    regex=r'^[a-z0-9](?:[a-z0-9-]{0,28}[a-z0-9])?$',
                    message=(
                        'Tenant slug must be lowercase letters, digits, '
                        'or hyphens, 2-30 characters, and may not start '
                        'or end with a hyphen.'
                    ),
                )],
            ),
        ),
    ]
