"""
Health-check endpoints for load balancers and Kubernetes probes.

  * ``GET /healthz`` — liveness probe. Returns 200 if the process is
    alive. No DB/external-service dependency — designed to be cheap
    and fast so probe failures only mean "restart me".

  * ``GET /readyz``  — readiness probe. Returns 200 only when the app
    is ready to accept traffic: DB reachable, no pending migrations,
    cache reachable (if configured). A failure means the load
    balancer should pull this pod out of rotation.

Both endpoints are intentionally public (no auth required) so the
probe pod can hit them without credentials.
"""
from __future__ import annotations

import time

from django.conf import settings
from django.db import connection, OperationalError
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.http import JsonResponse


@require_GET
@never_cache
def healthz(request):
    """Liveness probe — cheap, dependency-free."""
    return JsonResponse({
        'status':       'ok',
        'service':      'quot-pse',
        'timestamp':    int(time.time()),
    })


@require_GET
@never_cache
def readyz(request):
    """Readiness probe — verifies DB + migrations + cache if set.

    Returns 200 only when every check passes. Probe failures include
    which checks failed so operators can diagnose without tailing logs.
    """
    checks: dict[str, dict] = {}
    overall_ok = True

    # ── DB ping ──
    db_start = time.monotonic()
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
        checks['database'] = {
            'ok': True,
            'latency_ms': int((time.monotonic() - db_start) * 1000),
        }
    except OperationalError as exc:
        overall_ok = False
        checks['database'] = {'ok': False, 'error': str(exc)[:200]}

    # ── Pending migrations ──
    try:
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        pending = len(plan)
        checks['migrations'] = {
            'ok':      pending == 0,
            'pending': pending,
        }
        if pending > 0:
            overall_ok = False
    except Exception as exc:
        overall_ok = False
        checks['migrations'] = {'ok': False, 'error': str(exc)[:200]}

    # ── Cache ping (if configured) ──
    cache_backend = (
        settings.CACHES.get('default', {}).get('BACKEND', '')
        if hasattr(settings, 'CACHES') else ''
    )
    if cache_backend and 'locmem' not in cache_backend.lower():
        try:
            from django.core.cache import cache
            cache_start = time.monotonic()
            cache.set('__readyz_probe__', '1', 10)
            roundtrip = cache.get('__readyz_probe__')
            checks['cache'] = {
                'ok': roundtrip == '1',
                'latency_ms': int((time.monotonic() - cache_start) * 1000),
            }
            if roundtrip != '1':
                overall_ok = False
        except Exception as exc:
            overall_ok = False
            checks['cache'] = {'ok': False, 'error': str(exc)[:200]}

    status_code = 200 if overall_ok else 503
    return JsonResponse({
        'status':  'ready' if overall_ok else 'not-ready',
        'checks':  checks,
    }, status=status_code)
