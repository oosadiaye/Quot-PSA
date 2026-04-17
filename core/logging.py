"""
Structured JSON logging for Quot PSE.

When ``DEBUG=False`` (production) every log line is emitted as a single
JSON object with these mandatory fields:

    {
      "timestamp": "2026-04-17T14:35:01.234+00:00",
      "level":     "INFO",
      "logger":    "accounting.services.period_close",
      "message":   "Posted period close for FY 2026",
      "tenant":    "delta_state",
      "user":      "aminu@delta.gov.ng",
      "request_id":"b5a0c1f2-4c83-4e0e-b3c1-…",
      "operation": "POST /api/v1/accounting/period-close/",
      "duration_ms": 142,
    }

The ``tenant`` / ``user`` / ``request_id`` / ``operation`` fields are
populated by ``RequestContextMiddleware``; arbitrary extra fields passed
via ``logger.info('msg', extra={'foo': 'bar'})`` are included verbatim.

In DEBUG mode we still emit plain text — JSON is noisy for local dev.
"""
from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any


# Request-scoped context populated by RequestContextMiddleware and
# consumed by JsonFormatter. Using contextvars so async views work
# correctly; falls back safely in sync views.
_tenant_ctx: ContextVar[str] = ContextVar('_tenant_ctx', default='')
_user_ctx: ContextVar[str] = ContextVar('_user_ctx', default='')
_request_id_ctx: ContextVar[str] = ContextVar('_request_id_ctx', default='')
_operation_ctx: ContextVar[str] = ContextVar('_operation_ctx', default='')


def set_request_context(
    *,
    tenant: str = '',
    user: str = '',
    request_id: str = '',
    operation: str = '',
) -> None:
    """Populate the context vars the JSON formatter reads. Called once
    per request by the middleware; tests can call it directly to lock
    expected fields for assertion."""
    if tenant:
        _tenant_ctx.set(tenant)
    if user:
        _user_ctx.set(user)
    if request_id:
        _request_id_ctx.set(request_id)
    if operation:
        _operation_ctx.set(operation)


def get_request_context() -> dict[str, str]:
    return {
        'tenant':     _tenant_ctx.get(),
        'user':       _user_ctx.get(),
        'request_id': _request_id_ctx.get(),
        'operation':  _operation_ctx.get(),
    }


def clear_request_context() -> None:
    _tenant_ctx.set('')
    _user_ctx.set('')
    _request_id_ctx.set('')
    _operation_ctx.set('')


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    _STANDARD_ATTRS = frozenset({
        'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
        'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
        'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
        'processName', 'process', 'message', 'asctime', 'taskName',
    })

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'),
            'level':     record.levelname,
            'logger':    record.name,
            'message':   record.getMessage(),
        }

        ctx = get_request_context()
        for key, val in ctx.items():
            if val:
                payload[key] = val

        # Any extra={'…': …} kwargs — preserve them.
        for key, val in record.__dict__.items():
            if key in self._STANDARD_ATTRS or key.startswith('_'):
                continue
            if key in payload:
                continue
            try:
                json.dumps(val, default=str)  # ensure serialisable
                payload[key] = val
            except (TypeError, ValueError):
                payload[key] = repr(val)

        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


class RequestContextMiddleware:
    """Populate the per-request logging context vars.

    Reads the tenant from ``request.tenant`` (set by django-tenants'
    middleware if the chain is in the right order), the user from
    ``request.user``, generates a UUID ``request_id``, and composes the
    operation string from ``method + path``.

    Emits the request_id back to the client via the ``X-Request-Id``
    response header so client-side errors can be correlated with server
    logs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import time

        tenant_name = ''
        tenant = getattr(request, 'tenant', None)
        if tenant is not None:
            tenant_name = (
                getattr(tenant, 'schema_name', None)
                or getattr(tenant, 'name', '')
                or ''
            )

        user_name = ''
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            user_name = getattr(user, 'username', '') or getattr(user, 'email', '')

        req_id = (
            request.headers.get('X-Request-Id')
            or str(uuid.uuid4())
        )
        op = f'{request.method} {request.path}'

        set_request_context(
            tenant=tenant_name,
            user=user_name,
            request_id=req_id,
            operation=op,
        )

        start = time.monotonic()
        try:
            response = self.get_response(request)
        finally:
            # Clear context so background tasks using the same thread
            # don't inherit stale values.
            duration_ms = int((time.monotonic() - start) * 1000)
            logging.getLogger('quot_pse.request').info(
                f'{request.method} {request.path} completed',
                extra={'duration_ms': duration_ms},
            )
            clear_request_context()

        try:
            response['X-Request-Id'] = req_id
        except Exception:
            # Some response types (streaming, file) don't accept header
            # mutation late in the chain — that's fine.
            pass
        return response
