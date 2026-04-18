"""Backfill legacy Fund / Function / Program / Geo tables from NCoA segments.

The JournalForm (and several other pre-NCoA UIs) still queries the legacy
dimension endpoints ``/accounting/funds/`` etc. For tenants seeded via
``seed_ncoa_as_coa`` / ``seed_ncoa`` the NCoA segment tables are populated
but the legacy tables are empty — result: empty dropdowns on forms.

This command walks every NCoA segment and:
  · looks up or creates a matching row in the legacy table (keyed by code)
  · links them via the OneToOne ``legacy_fund`` / ``legacy_function`` /
    ``legacy_program`` / ``legacy_geo`` bridges.

Idempotent. Safe to run on all tenants. Safe to re-run.

Usage:
    ./manage.py tenant_command backfill_legacy_dims --schema=<tenant>
    ./manage.py backfill_legacy_dims --all-tenants
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Create legacy Fund/Function/Program/Geo rows from NCoA segments.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all-tenants', action='store_true',
            help='Run against every tenant schema (excluding public).',
        )

    def handle(self, *args, **opts):
        if opts['all_tenants']:
            from tenants.models import Client
            from django_tenants.utils import schema_context
            for tenant in Client.objects.exclude(schema_name='public'):
                with schema_context(tenant.schema_name):
                    self._backfill_current_schema(tenant.schema_name)
        else:
            # Current schema (set via tenant_command --schema=...)
            self._backfill_current_schema('(current)')

    def _backfill_current_schema(self, label: str) -> None:
        from accounting.models import Fund, Function, Program, Geo, MDA
        from accounting.models.ncoa import (
            AdministrativeSegment,
            FundSegment, FunctionalSegment, ProgrammeSegment, GeographicSegment,
        )

        created = {'mda': 0, 'fund': 0, 'function': 0, 'program': 0, 'geo': 0}

        with transaction.atomic():
            # ── MDA (Administrative) ─────────────────────────────
            # MDA.mda_type is required with choices [MINISTRY, DEPARTMENT,
            # AGENCY, PARASTATAL]. NCoA AdministrativeSegment.mda_type has
            # overlapping choices — fall back to MINISTRY when source row
            # hasn't classified itself (common at the sector root level).
            VALID_TYPES = {'MINISTRY', 'DEPARTMENT', 'AGENCY', 'PARASTATAL'}
            for seg in AdministrativeSegment.objects.select_related('legacy_mda').all():
                if seg.legacy_mda_id:
                    continue
                source_type = (getattr(seg, 'mda_type', '') or '').upper()
                mda_type = source_type if source_type in VALID_TYPES else 'MINISTRY'
                mda, mda_created = MDA.objects.get_or_create(
                    code=seg.code,
                    defaults={
                        'name': seg.name,
                        'short_name': seg.name[:50],
                        'mda_type': mda_type,
                        'is_active': getattr(seg, 'is_active', True),
                    },
                )
                seg.legacy_mda = mda
                seg.save(update_fields=['legacy_mda'])
                if mda_created:
                    created['mda'] += 1

            # ── Fund ─────────────────────────────────────────────
            for seg in FundSegment.objects.select_related('legacy_fund').all():
                if seg.legacy_fund_id:
                    continue
                fund, fund_created = Fund.objects.get_or_create(
                    code=seg.code,
                    defaults={
                        'name': seg.name,
                        'description': getattr(seg, 'description', '') or '',
                        'is_active': getattr(seg, 'is_active', True),
                    },
                )
                seg.legacy_fund = fund
                seg.save(update_fields=['legacy_fund'])
                if fund_created:
                    created['fund'] += 1

            # ── Function ─────────────────────────────────────────
            for seg in FunctionalSegment.objects.select_related('legacy_function').all():
                if seg.legacy_function_id:
                    continue
                fn, fn_created = Function.objects.get_or_create(
                    code=seg.code,
                    defaults={
                        'name': seg.name,
                        'description': getattr(seg, 'description', '') or '',
                        'is_active': getattr(seg, 'is_active', True),
                    },
                )
                seg.legacy_function = fn
                seg.save(update_fields=['legacy_function'])
                if fn_created:
                    created['function'] += 1

            # ── Programme ────────────────────────────────────────
            for seg in ProgrammeSegment.objects.select_related('legacy_program').all():
                if seg.legacy_program_id:
                    continue
                prog, prog_created = Program.objects.get_or_create(
                    code=seg.code,
                    defaults={
                        'name': seg.name,
                        'description': getattr(seg, 'description', '') or '',
                        'is_active': getattr(seg, 'is_active', True),
                    },
                )
                seg.legacy_program = prog
                seg.save(update_fields=['legacy_program'])
                if prog_created:
                    created['program'] += 1

            # ── Geographic ───────────────────────────────────────
            for seg in GeographicSegment.objects.select_related('legacy_geo').all():
                if seg.legacy_geo_id:
                    continue
                geo, geo_created = Geo.objects.get_or_create(
                    code=seg.code,
                    defaults={
                        'name': seg.name,
                        'description': getattr(seg, 'description', '') or '',
                        'is_active': getattr(seg, 'is_active', True),
                    },
                )
                seg.legacy_geo = geo
                seg.save(update_fields=['legacy_geo'])
                if geo_created:
                    created['geo'] += 1

        self.stdout.write(self.style.SUCCESS(
            f'[{label}] created MDA={created["mda"]} Fund={created["fund"]} '
            f'Function={created["function"]} Program={created["program"]} '
            f'Geo={created["geo"]}'
        ))
