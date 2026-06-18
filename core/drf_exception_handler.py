"""DRF exception handler — translates project-wide exceptions to HTTP.

Wired in via ``REST_FRAMEWORK['EXCEPTION_HANDLER']`` in settings.

Why we need a custom handler:

    The default DRF handler already covers ``APIException``, ``Http404``,
    ``PermissionDenied`` (Django auth) and ``ValidationError``. It does
    NOT know about project-specific exceptions raised by service-layer
    code such as ``core.services.sod_evaluator.SoDViolation`` — those
    would otherwise bubble out as a 500 with the bare repr, losing the
    structured per-rule payload that the React UI uses to render a
    "you can't both create and approve this PR" banner.

The handler is intentionally narrow: it only adds translations for
exceptions whose payload semantics matter to the client. Everything
else falls through to DRF's default behaviour so we never accidentally
swallow an unrelated error.
"""
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_exception_handler

logger = logging.getLogger(__name__)


def project_exception_handler(exc, context):
    """Translate domain exceptions to structured HTTP responses.

    Recognised exceptions (others fall through to DRF default):

    * ``core.services.sod_evaluator.SoDViolation`` → ``403 Forbidden``
      with a ``violations`` array so the client can render one banner
      per rule. Each entry carries ``rule_code``, ``rule_name``,
      ``severity``, the two permission codes/labels, and a ``reason``
      string.
    """
    # Lazy import so the handler module can be loaded before app
    # registry boot (settings import order).
    from core.services.sod_evaluator import SoDViolation

    if isinstance(exc, SoDViolation):
        # Log at WARNING with the actor / document context the caller
        # provided so audit reports can correlate blocked actions.
        request = context.get('request') if context else None
        user_id = getattr(getattr(request, 'user', None), 'pk', None)
        path = getattr(request, 'path', None) if request else None
        logger.warning(
            'SoD blocking violation: user_id=%s path=%s rule_codes=%s',
            user_id, path,
            ','.join(v.rule_code for v in exc.violations),
        )
        return Response(
            {
                'detail': 'Action blocked by segregation-of-duties policy.',
                'error': str(exc),
                'violations': [
                    {
                        'rule_id': v.rule_id,
                        'rule_code': v.rule_code,
                        'rule_name': v.rule_name,
                        'scope': v.scope,
                        'severity': v.severity,
                        'permission_a': {
                            'code': v.permission_a_code,
                            'label': v.permission_a_label,
                        },
                        'permission_b': {
                            'code': v.permission_b_code,
                            'label': v.permission_b_label,
                        },
                        'reason': v.reason,
                    }
                    for v in exc.violations
                ],
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # Fall through to DRF's default for everything else.
    return drf_default_exception_handler(exc, context)
