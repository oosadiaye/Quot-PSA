"""P6-T4 — Redis cache layer tests for hot IPSAS reports.

Uses Django's LocMem backend (no Redis required in CI).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _flush_cache():
    cache.clear()
    yield
    cache.clear()


class TestKeyBuilding:

    def test_params_order_invariant(self):
        """Two dicts with same keys in different order produce the same cache key."""
        from accounting.services.report_cache import _build_key
        k1 = _build_key('sofp', {'fy': 2026, 'period': 3})
        k2 = _build_key('sofp', {'period': 3, 'fy': 2026})
        assert k1 == k2

    def test_different_params_produce_different_keys(self):
        from accounting.services.report_cache import _build_key
        a = _build_key('sofp', {'fy': 2026})
        b = _build_key('sofp', {'fy': 2027})
        assert a != b

    def test_different_reports_produce_different_keys(self):
        from accounting.services.report_cache import _build_key
        a = _build_key('sofp', {'fy': 2026})
        b = _build_key('sofperf', {'fy': 2026})
        assert a != b


class TestGetOrCompute:

    def test_miss_invokes_compute(self):
        from accounting.services.report_cache import get_or_compute
        calls = []
        def compute():
            calls.append(1)
            return {'answer': 42}
        result = get_or_compute('sofp', {'fy': 2026}, compute)
        assert result == {'answer': 42}
        assert len(calls) == 1

    def test_second_call_hits_cache(self):
        from accounting.services.report_cache import get_or_compute
        calls = []
        def compute():
            calls.append(1)
            return {'answer': 42}
        get_or_compute('sofp', {'fy': 2026}, compute)
        get_or_compute('sofp', {'fy': 2026}, compute)
        assert len(calls) == 1  # compute invoked only once

    def test_distinct_params_miss_independently(self):
        from accounting.services.report_cache import get_or_compute
        calls = []
        def compute_fy(fy):
            def _c():
                calls.append(fy)
                return {'fy': fy}
            return _c
        get_or_compute('sofp', {'fy': 2026}, compute_fy(2026))
        get_or_compute('sofp', {'fy': 2027}, compute_fy(2027))
        assert calls == [2026, 2027]

    def test_cache_failure_falls_back_to_compute(self):
        """Redis down must NOT 500 the report."""
        from accounting.services import report_cache

        with patch.object(report_cache.cache, 'get', side_effect=RuntimeError('redis down')):
            result = report_cache.get_or_compute(
                'sofp', {'fy': 2026}, lambda: {'live': True},
            )
        assert result == {'live': True}


class TestInvalidation:

    def test_invalidate_report_forces_recompute(self):
        from accounting.services.report_cache import get_or_compute, invalidate_report
        calls = []
        def compute():
            calls.append(1)
            return {'v': len(calls)}
        get_or_compute('sofp', {'fy': 2026}, compute)
        invalidate_report('sofp', {'fy': 2026})
        get_or_compute('sofp', {'fy': 2026}, compute)
        assert len(calls) == 2

    def test_period_invalidation_bumps_generation(self):
        """invalidate_period_reports() advances the generation counter."""
        from accounting.services.report_cache import (
            invalidate_period_reports, report_generation,
        )
        start = report_generation(2026)
        invalidate_period_reports(fiscal_year=2026)
        invalidate_period_reports(fiscal_year=2026)
        assert report_generation(2026) == start + 2

    def test_callers_mixing_generation_get_fresh_data(self):
        """Embedding report_generation() in params means a cache-bust
        produces a new key and therefore a fresh compute."""
        from accounting.services.report_cache import (
            get_or_compute, invalidate_period_reports, report_generation,
        )
        calls = []
        def compute():
            calls.append(1)
            return {'v': len(calls)}

        def do_read():
            params = {'fy': 2026, 'gen': report_generation(2026)}
            return get_or_compute('sofp', params, compute)

        do_read(); do_read()             # one miss, one hit
        invalidate_period_reports(2026)  # bust
        do_read()                        # miss again -> recompute

        assert len(calls) == 2


class TestDisableFlag:

    def test_disabling_short_circuits_cache(self, settings):
        from accounting.services.report_cache import get_or_compute
        settings.REPORT_CACHE_ENABLED = False
        calls = []
        def compute():
            calls.append(1)
            return {'v': 1}
        get_or_compute('sofp', {'fy': 2026}, compute)
        get_or_compute('sofp', {'fy': 2026}, compute)
        assert len(calls) == 2  # no caching
