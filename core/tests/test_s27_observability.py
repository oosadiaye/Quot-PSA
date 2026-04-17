"""
Phase 3 tests — JSON logging, health endpoints, metrics shape.

No-DB fast tier: contract + formatter behaviour only. Integration
runs happen via the CI backend job (which has a live Postgres).
"""
from __future__ import annotations

import json
import logging


class TestJsonFormatter:

    def test_formatter_emits_valid_json(self):
        from core.logging import JsonFormatter
        rec = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='hello %s', args=('world',), exc_info=None,
        )
        out = JsonFormatter().format(rec)
        parsed = json.loads(out)
        assert parsed['level'] == 'INFO'
        assert parsed['logger'] == 'test'
        assert parsed['message'] == 'hello world'
        assert 'timestamp' in parsed

    def test_formatter_includes_request_context(self):
        from core.logging import JsonFormatter, set_request_context, clear_request_context
        clear_request_context()
        set_request_context(
            tenant='delta_state', user='alice',
            request_id='abc-123', operation='POST /foo',
        )
        rec = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='hi', args=(), exc_info=None,
        )
        parsed = json.loads(JsonFormatter().format(rec))
        assert parsed['tenant'] == 'delta_state'
        assert parsed['user'] == 'alice'
        assert parsed['request_id'] == 'abc-123'
        assert parsed['operation'] == 'POST /foo'
        clear_request_context()

    def test_formatter_includes_extra_kwargs(self):
        from core.logging import JsonFormatter
        rec = logging.LogRecord(
            name='test', level=logging.WARNING, pathname='', lineno=0,
            msg='slow', args=(), exc_info=None,
        )
        rec.duration_ms = 4200
        rec.tenant_id = 5
        out = JsonFormatter().format(rec)
        parsed = json.loads(out)
        assert parsed['duration_ms'] == 4200
        assert parsed['tenant_id'] == 5

    def test_formatter_includes_exception_traceback(self):
        from core.logging import JsonFormatter
        import sys
        try:
            raise ValueError('boom')
        except ValueError:
            exc_info = sys.exc_info()
        rec = logging.LogRecord(
            name='test', level=logging.ERROR, pathname='', lineno=0,
            msg='oops', args=(), exc_info=exc_info,
        )
        parsed = json.loads(JsonFormatter().format(rec))
        assert 'exception' in parsed
        assert 'ValueError' in parsed['exception']
        assert 'boom' in parsed['exception']


class TestRequestContextMiddleware:

    def test_middleware_sets_and_clears_context(self):
        from core.logging import RequestContextMiddleware, get_request_context
        from unittest.mock import MagicMock

        calls = []

        def inner(req):
            calls.append(dict(get_request_context()))
            resp = MagicMock()
            resp.__setitem__ = MagicMock()
            return resp

        mw = RequestContextMiddleware(inner)
        req = MagicMock()
        req.method = 'GET'
        req.path = '/healthz'
        req.headers = {'X-Request-Id': 'probe-xyz'}
        user = MagicMock()
        user.is_authenticated = True
        user.username = 'alice'
        req.user = user
        tenant = MagicMock()
        tenant.schema_name = 'delta_state'
        req.tenant = tenant

        mw(req)
        # During the request, the inner function saw the populated context.
        assert calls[0]['tenant'] == 'delta_state'
        assert calls[0]['user'] == 'alice'
        assert calls[0]['request_id'] == 'probe-xyz'
        assert calls[0]['operation'] == 'GET /healthz'
        # After the request, the context is cleared.
        post = get_request_context()
        assert post == {'tenant': '', 'user': '', 'request_id': '', 'operation': ''}


class TestHealthEndpointsImportable:

    def test_healthz_importable(self):
        from core.views.health import healthz
        assert callable(healthz)

    def test_readyz_importable(self):
        from core.views.health import readyz
        assert callable(readyz)


class TestMetricsExporter:

    def test_metrics_view_importable(self):
        from core.views.metrics import prometheus_metrics, CONTENT_TYPE
        assert callable(prometheus_metrics)
        assert 'text/plain' in CONTENT_TYPE

    def test_escape_handles_special_chars(self):
        from core.views.metrics import _escape
        assert _escape('a"b') == 'a\\"b'
        assert _escape('a\nb') == 'a\\nb'
        assert _escape('a\\b') == 'a\\\\b'


class TestURLsRegistered:
    """Fail the build if a refactor drops the probe paths."""

    def test_healthz_path(self):
        from django.urls import reverse
        assert reverse('healthz') == '/healthz'

    def test_readyz_path(self):
        from django.urls import reverse
        assert reverse('readyz') == '/readyz'

    def test_metrics_path(self):
        from django.urls import reverse
        assert reverse('prometheus-metrics') == '/metrics'
