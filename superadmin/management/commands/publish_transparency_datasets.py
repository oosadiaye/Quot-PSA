"""
Materialize approved transparency publications into the public portal.

The transparency public portal (FUTURE_MODULES §5.5) serves only from the
public-schema ``superadmin.PublishedSnapshot`` table, never from live
transactional tables.  ``Publication`` and ``ReportSnapshot`` are tenant-schema
models, so a superadmin runs this command against a tenant to copy its
approved, snapshot-backed publications into the public store the
unauthenticated portal reads from.

Usage:
    python manage.py publish_transparency_datasets --tenant=<schema_name>
    python manage.py publish_transparency_datasets --tenant=<schema_name> --retract

``--tenant`` is the tenant *schema name* (e.g. the public-facing slug).
``--retract`` removes any public rows that no longer correspond to an approved,
snapshot-backed publication for that tenant (i.e. publications that were
retracted or whose snapshot is missing).

The command is idempotent: re-running for the same tenant creates no duplicate
``PublishedSnapshot`` rows (see the model's unique constraint).
"""
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = (
        'Materialize approved, snapshot-backed transparency publications from '
        'a tenant schema into the public PublishedSnapshot portal store.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--tenant', required=True,
                            help='Tenant schema name to publish from.')
        parser.add_argument('--retract', action='store_true',
                            help='Remove public rows for this tenant that no '
                                 'longer have an approved snapshot-backed '
                                 'publication.')

    def handle(self, *args, **options):
        tenant_schema = options['tenant']

        # Validate the tenant schema exists before doing any work.
        from tenants.models import Domain
        from django_tenants.utils import get_tenant_domain_model
        domain_model = get_tenant_domain_model()
        try:
            domain_model.objects.get(schema_name=tenant_schema)
        except domain_model.DoesNotExist:
            raise CommandError(
                f'No tenant domain/schema "{tenant_schema}" found. '
                'Pass --tenant as the tenant schema name.'
            )

        # Lazy imports to keep import-time lightweight and avoid pulling the
        # tenant transparency models into the public-schema command scope.
        from superadmin.models import PublishedSnapshot

        published = 0
        with schema_context(tenant_schema):
            from transparency.models import Publication, RedactionRule
            qs = Publication.objects.filter(
                status='published', snapshot__isnull=False,
            ).select_related('snapshot')

            rows = []
            for pub in qs.iterator():
                payload = pub.snapshot.payload
                rows.append({
                    'dataset_key': pub.dataset_key,
                    'title': pub.title,
                    'aggregation': '',
                    'fiscal_year': pub.fiscal_year,
                    'period': pub.period,
                    'payload': payload,
                    'content_hash': pub.snapshot.content_hash,
                    'source_publication_id': pub.pk,
                    'published_at': pub.published_at,
                })

            retractable = {r['source_publication_id'] for r in rows}

        with schema_context('public'):
            for r in rows:
                _, created = PublishedSnapshot.objects.update_or_create(
                    dataset_key=r['dataset_key'],
                    fiscal_year=r['fiscal_year'],
                    period=r['period'],
                    content_hash=r['content_hash'],
                    defaults={
                        'title': r['title'],
                        'aggregation': r['aggregation'],
                        'payload': r['payload'],
                        'source_publication_id': r['source_publication_id'],
                        'published_at': r['published_at'],
                        'is_public': True,
                    },
                )
                if created:
                    published += 1

            if options['retract']:
                removed, _ = PublishedSnapshot.objects.filter(
                    source_publication_id__in=retractable or [-1],
                ).delete()
            else:
                removed = 0

        self.stdout.write(self.style.SUCCESS(
            f'Published snapshot materialization: {published} created from '
            f'tenant "{tenant_schema}".'
        ))
        if options['retract']:
            self.stdout.write(self.style.SUCCESS(
                f'Retraction pass removed {removed} now-invalid public rows.'
            ))
