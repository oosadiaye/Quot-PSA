"""
Core utility helpers shared across all modules.

Usage:
    from core.utils import api_response

    # Success
    return api_response(data={'id': 1, 'name': 'foo'})

    # Paginated list
    return api_response(data=serializer.data, meta={'total': queryset.count(), 'page': page})

    # Error
    return api_response(error='Validation failed', status=400)
"""

import logging
import re

from rest_framework.response import Response


# =============================================================================
# Sensitive Data Logging Filter
# =============================================================================
_SENSITIVE_PATTERNS = re.compile(
    r'(?i)(password|passwd|secret|token|api[_-]?key|authorization|credential|'
    r'credit[_-]?card|cvv|ssn|signing[_-]?key)(["\']?\s*[:=]\s*["\']?)([^\s,;"\'\}]{3,})',
)
_MASK = '***REDACTED***'


class SensitiveDataFilter(logging.Filter):
    """Masks passwords, tokens, API keys, and other secrets in log records.

    Add to LOGGING['filters'] and reference in handlers:
        'sensitive': {'()': 'core.utils.SensitiveDataFilter'},
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SENSITIVE_PATTERNS.sub(r'\1\2' + _MASK, record.msg)
        if record.args:
            sanitized = []
            for arg in (record.args if isinstance(record.args, tuple) else (record.args,)):
                if isinstance(arg, str):
                    sanitized.append(_SENSITIVE_PATTERNS.sub(r'\1\2' + _MASK, arg))
                else:
                    sanitized.append(arg)
            record.args = tuple(sanitized)
        return True


def api_response(data=None, error=None, meta=None, status: int = 200) -> Response:
    """
    Standardised API response envelope.

    All responses share the same top-level shape:
        {
            "data":  <payload or null>,
            "error": <error message or null>,
            "meta":  <pagination / extra info or {}>
        }

    Args:
        data:   The response payload (serialized dict, list, or None).
        error:  Human-readable error string (or None on success).
        meta:   Optional dict with pagination or supplementary info.
        status: HTTP status code (default 200).

    Returns:
        DRF Response object.
    """
    return Response(
        {
            'data': data,
            'error': error,
            'meta': meta if meta is not None else {},
        },
        status=status,
    )


def paginated_response(serializer_data, paginator, request, queryset) -> Response:
    """
    Helper for paginated list endpoints.

    Usage:
        from core.utils import paginated_response
        from rest_framework.pagination import PageNumberPagination

        class MyPaginator(PageNumberPagination):
            page_size = 20

        paginator = MyPaginator()
        page = paginator.paginate_queryset(queryset, request)
        serializer = MySerializer(page, many=True)
        return paginated_response(serializer.data, paginator, request, queryset)
    """
    return api_response(
        data=serializer_data,
        meta={
            'count': paginator.page.paginator.count if hasattr(paginator, 'page') and paginator.page else len(serializer_data),
            'next': paginator.get_next_link() if hasattr(paginator, 'get_next_link') else None,
            'previous': paginator.get_previous_link() if hasattr(paginator, 'get_previous_link') else None,
        },
    )
