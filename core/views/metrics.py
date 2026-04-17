"""
Prometheus-format ``/metrics`` exporter.

Lightweight implementation — no external dependency. Exposes:

  * ``quotpse_journal_headers_total{status=…}`` — count of journal
    headers by status across the active tenant schema.
  * ``quotpse_approval_instances_total{status=…}`` — count of approval
    instances by status.
  * ``quotpse_role_assignments_total{active=…}`` — role-assignment rows.
  * ``quotpse_appropriations_total{status=…}`` — budget appropriations.
  * ``quotpse_tenants_total`` — total active tenant schemas.
  * ``quotpse_db_latency_seconds`` — latency of a `SELECT 1` probe.
  * ``quotpse_app_info{version=…}`` — info metric carrying the release
    version via label so aggregators can correlate metrics with
    deploys.

The endpoint is permissioned as `AllowAny` because Prometheus scrape
jobs run against the pod network without credentials. Gate it at the
load-balancer or via an IP allow-list in production.
"""
from __future__ import annotations

import os
import time

from django.conf import settings
from django.db import connection, OperationalError
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


CONTENT_TYPE = 'text/plain; version=0.0.4; charset=utf-8'


@require_GET
@never_cache
def prometheus_metrics(request):
    """Render the current metrics snapshot in Prometheus exposition format."""
    lines: list[str] = []

    def _metric(name: str, help_text: str, metric_type: str = 'gauge'):
        lines.append(f'# HELP {name} {help_text}')
        lines.append(f'# TYPE {name} {metric_type}')

    def _sample(name: str, value, labels: dict | None = None):
        if labels:
            label_str = ','.join(
                f'{k}="{_escape(str(v))}"' for k, v in sorted(labels.items())
            )
            lines.append(f'{name}{{{label_str}}} {value}')
        else:
            lines.append(f'{name} {value}')

    # ── App info ──
    _metric('quotpse_app_info', 'Application info', 'gauge')
    _sample('quotpse_app_info', 1, {
        'version':     os.getenv('APP_VERSION', 'dev'),
        'environment': os.getenv('SENTRY_ENVIRONMENT', 'development'),
    })

    # ── DB latency ──
    _metric(
        'quotpse_db_latency_seconds',
        'Latency of a SELECT 1 probe against the configured DB',
        'gauge',
    )
    db_start = time.monotonic()
    db_ok = True
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
    except OperationalError:
        db_ok = False
    _sample('quotpse_db_latency_seconds', f'{(time.monotonic() - db_start):.6f}')
    _metric('quotpse_db_up', 'DB reachable (1 = yes, 0 = no)', 'gauge')
    _sample('quotpse_db_up', 1 if db_ok else 0)

    if not db_ok:
        # Short-circuit — model queries below will fail.
        lines.append('')
        return HttpResponse('\n'.join(lines), content_type=CONTENT_TYPE)

    # ── JournalHeader by status (current tenant schema) ──
    try:
        from accounting.models import JournalHeader
        _metric(
            'quotpse_journal_headers_total',
            'Journal headers grouped by status',
            'gauge',
        )
        counts = (
            JournalHeader.objects
            .values('status')
            .order_by()
            .annotate_count()
            if hasattr(JournalHeader.objects, 'annotate_count')
            else JournalHeader.objects.values_list('status')
        )
        # Fall back to Django's Count() aggregate.
        from django.db.models import Count
        rows = (
            JournalHeader.objects
            .values('status')
            .order_by()
            .annotate(n=Count('id'))
        )
        for row in rows:
            _sample(
                'quotpse_journal_headers_total',
                row['n'],
                {'status': row['status'] or 'unknown'},
            )
    except Exception as exc:
        lines.append(f'# quotpse_journal_headers_total error: {_escape(str(exc))[:100]}')

    # ── ApprovalInstance by status ──
    try:
        from accounting.models.audit import ApprovalInstance
        from django.db.models import Count
        _metric(
            'quotpse_approval_instances_total',
            'Approval instances grouped by status',
            'gauge',
        )
        for row in (
            ApprovalInstance.objects
            .values('status')
            .order_by()
            .annotate(n=Count('id'))
        ):
            _sample(
                'quotpse_approval_instances_total',
                row['n'],
                {'status': row['status'] or 'unknown'},
            )
    except Exception as exc:
        lines.append(f'# quotpse_approval_instances_total error: {_escape(str(exc))[:100]}')

    # ── RoleAssignment by is_active ──
    try:
        from core.models import RoleAssignment
        from django.db.models import Count
        _metric(
            'quotpse_role_assignments_total',
            'Role assignments grouped by active state',
            'gauge',
        )
        for row in (
            RoleAssignment.objects
            .values('is_active')
            .order_by()
            .annotate(n=Count('id'))
        ):
            _sample(
                'quotpse_role_assignments_total',
                row['n'],
                {'active': 'true' if row['is_active'] else 'false'},
            )
    except Exception as exc:
        lines.append(f'# quotpse_role_assignments_total error: {_escape(str(exc))[:100]}')

    # ── Appropriation by status ──
    try:
        from budget.models import Appropriation
        from django.db.models import Count
        _metric(
            'quotpse_appropriations_total',
            'Budget appropriations grouped by status',
            'gauge',
        )
        for row in (
            Appropriation.objects
            .values('status')
            .order_by()
            .annotate(n=Count('id'))
        ):
            _sample(
                'quotpse_appropriations_total',
                row['n'],
                {'status': row['status'] or 'unknown'},
            )
    except Exception as exc:
        lines.append(f'# quotpse_appropriations_total error: {_escape(str(exc))[:100]}')

    # ── Tenants total (public schema only) ──
    try:
        from django_tenants.utils import get_tenant_model
        T = get_tenant_model()
        _metric('quotpse_tenants_total', 'Active tenants on the platform', 'gauge')
        _sample('quotpse_tenants_total', T.objects.count())
    except Exception as exc:
        lines.append(f'# quotpse_tenants_total error: {_escape(str(exc))[:100]}')

    lines.append('')  # trailing newline
    return HttpResponse('\n'.join(lines), content_type=CONTENT_TYPE)


def _escape(v: str) -> str:
    return v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
