"""Scan all Appropriations for broken NCoA -> legacy bridges.

``Appropriation.total_expended`` walks ``administrative.legacy_mda``,
``fund.legacy_fund``, and ``economic.legacy_account_id`` to find matching
journal lines. If ANY of those bridges is null, the computation silently
returns Decimal('0') — which inflates ``available_balance`` and permits
over-commitment.

This management command surfaces broken bridges across every tenant so
operators can resolve them before any Appropriation goes ACTIVE.

Run as a pre-launch checklist item:

    python manage.py check_bridges                # all tenants
    python manage.py check_bridges --schema=delta_state  # single tenant
    python manage.py check_bridges --fail-on-broken      # exit 1 if any

See production-readiness review B7.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context, get_tenant_model

from budget.models import Appropriation


class Command(BaseCommand):
    help = (
        'Scan every Appropriation for broken NCoA-to-legacy bridges. '
        'A broken bridge causes total_expended to silently return zero, '
        'inflating available_balance and permitting over-commitment.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            help='Limit the scan to a single tenant schema. Defaults to all tenants.',
        )
        parser.add_argument(
            '--status',
            default='ACTIVE',
            help=(
                "Limit the scan to appropriations in this status (default 'ACTIVE'). "
                "Pass 'all' to scan every status including DRAFT."
            ),
        )
        parser.add_argument(
            '--fail-on-broken',
            action='store_true',
            help='Exit with status 1 if any broken bridge is found. Useful in CI.',
        )

    def handle(self, *args, **opts):
        schema = opts.get('schema')
        status_filter = opts.get('status')
        fail_on_broken = bool(opts.get('fail_on_broken'))

        tenant_model = get_tenant_model()
        if schema:
            schemas = [schema]
        else:
            schemas = list(
                tenant_model.objects
                .exclude(schema_name='public')
                .values_list('schema_name', flat=True)
            )
        if not schemas:
            self.stderr.write(self.style.WARNING(
                'No tenant schemas found — nothing to check.'
            ))
            return

        total_broken = 0
        total_scanned = 0
        per_tenant_summary: list[tuple[str, int, int]] = []

        for tenant_schema in schemas:
            with schema_context(tenant_schema):
                broken = self._scan_schema(tenant_schema, status_filter)
                scanned = self._count_scanned(status_filter)
            total_broken += len(broken)
            total_scanned += scanned
            per_tenant_summary.append((tenant_schema, scanned, len(broken)))

        self.stdout.write('')
        self.stdout.write('=' * 72)
        self.stdout.write('Bridge check summary')
        self.stdout.write('=' * 72)
        self.stdout.write(
            f'{"Schema":<28} {"Scanned":>10} {"Broken":>10}'
        )
        self.stdout.write('-' * 72)
        for tenant_schema, scanned, broken_count in per_tenant_summary:
            line = f'{tenant_schema:<28} {scanned:>10} {broken_count:>10}'
            if broken_count:
                self.stdout.write(self.style.ERROR(line))
            else:
                self.stdout.write(self.style.SUCCESS(line))
        self.stdout.write('-' * 72)
        self.stdout.write(
            f'{"TOTAL":<28} {total_scanned:>10} {total_broken:>10}'
        )

        if total_broken and fail_on_broken:
            raise SystemExit(1)

    def _count_scanned(self, status_filter: str) -> int:
        qs = Appropriation.objects.all()
        if status_filter != 'all':
            qs = qs.filter(status=status_filter)
        return qs.count()

    def _scan_schema(self, tenant_schema: str, status_filter: str) -> list[int]:
        """Print broken rows in the active schema; return list of broken pks."""
        qs = Appropriation.objects.select_related(
            'administrative', 'fund', 'economic', 'fiscal_year',
        )
        if status_filter != 'all':
            qs = qs.filter(status=status_filter)

        broken_pks: list[int] = []
        for appr in qs.iterator():
            problems = []
            admin_legacy = getattr(appr.administrative, 'legacy_mda', None) if appr.administrative_id else None
            if appr.administrative_id and not admin_legacy:
                problems.append(
                    f'administrative={appr.administrative.code}: legacy_mda is null'
                )
            fund_legacy = getattr(appr.fund, 'legacy_fund', None) if appr.fund_id else None
            if appr.fund_id and not fund_legacy:
                problems.append(
                    f'fund={appr.fund.code}: legacy_fund is null'
                )
            economic_legacy = getattr(appr.economic, 'legacy_account_id', None) if appr.economic_id else None
            if appr.economic_id and not economic_legacy:
                problems.append(
                    f'economic={appr.economic.code}: legacy_account is null'
                )
            if not problems:
                continue
            broken_pks.append(appr.pk)
            self.stdout.write(self.style.ERROR(
                f'[{tenant_schema}] Appropriation #{appr.pk} '
                f'(FY={getattr(appr.fiscal_year, "year", "?")}, '
                f'status={appr.status}, '
                f'amount={appr.amount_approved}): '
                + '; '.join(problems)
            ))
        return broken_pks
