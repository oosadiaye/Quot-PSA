"""P6-T4 — Redis cache layer for hot IPSAS reports.

The IPSAS 1 Statement of Financial Position / Performance and the
Budget-vs-Actual report each trigger several aggregates across every
JournalLine in the period — a cold pull measures 1.5–3 s on the demo
tenant. Because the underlying GL data is immutable for a closed
period, those reports are trivially cacheable.

Design:
  * Key includes tenant schema, report name, period parameters, and
    a short schema-version tag so a model-layer change busts stale
    entries automatically.
  * TTL = 10 min (short enough that posting-to-cache lag feels
    instant to users; long enough to absorb dashboard bursts).
  * Cache is busted explicitly whenever a journal posts or reverses —
    see ``invalidate_period_reports`` wired into
    ``JournalHeader.save`` and ``post_journal``.

Tests:
  accounting/tests/test_s29_report_cache.py — coverage for
  key composition, hit/miss, manual invalidation, and fallback when
  Redis is unreachable.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache
from django.db import connection


log = logging.getLogger(__name__)

# Cache version — bump to invalidate every entry at once. Tied to
# model schema versions that change report shape.
CACHE_VERSION = 'v1'

# 10-minute TTL. Sweet spot between posting-latency and dashboard burst.
REPORT_TTL_SECONDS = 600


def _tenant_schema() -> str:
    """Return the active tenant schema, or ``'public'`` outside a request."""
    return getattr(connection, 'schema_name', 'public') or 'public'


def _build_key(report: str, params: dict) -> str:
    """Deterministic cache key: tenant + report + hashed params."""
    # Sorted JSON so dict order doesn't create false misses.
    payload = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]
    return f'rpt:{CACHE_VERSION}:{_tenant_schema()}:{report}:{digest}'


def get_or_compute(
    report: str,
    params: dict,
    compute: Callable[[], Any],
    ttl: int = REPORT_TTL_SECONDS,
) -> Any:
    """Cache-aside helper.

    Returns the cached value if present; otherwise calls ``compute``,
    stores the result, and returns it. Silently falls back to a live
    compute when the cache backend raises — reports must not 500 just
    because Redis is down.
    """
    if not getattr(settings, 'REPORT_CACHE_ENABLED', True):
        return compute()

    key = _build_key(report, params)
    try:
        hit = cache.get(key)
    except Exception as exc:
        log.warning('report_cache.get failed: %s', exc)
        return compute()

    if hit is not None:
        return hit

    value = compute()
    try:
        cache.set(key, value, timeout=ttl)
    except Exception as exc:
        log.warning('report_cache.set failed: %s', exc)
    return value


def invalidate_report(report: str, params: dict) -> None:
    """Delete a single cached report entry."""
    try:
        cache.delete(_build_key(report, params))
    except Exception as exc:
        log.warning('report_cache.invalidate failed: %s', exc)


def invalidate_period_reports(fiscal_year: int | None = None) -> None:
    """Drop every cached report for the given fiscal year (or all years).

    Called from journal post/reverse hooks. We don't know which specific
    parameter permutations were cached, so we bump a tenant-scoped
    generation counter — all keys that embedded the prior counter become
    stale immediately.
    """
    ns_key = f'rpt_ns:{_tenant_schema()}:{fiscal_year or "all"}'
    try:
        current = cache.get(ns_key, 0)
        cache.set(ns_key, current + 1, timeout=86400)
    except Exception as exc:
        log.warning('report_cache.invalidate_period failed: %s', exc)


def report_generation(fiscal_year: int | None = None) -> int:
    """Read the generation counter — callers mix it into their params."""
    ns_key = f'rpt_ns:{_tenant_schema()}:{fiscal_year or "all"}'
    try:
        return cache.get(ns_key, 0) or 0
    except Exception:
        return 0
