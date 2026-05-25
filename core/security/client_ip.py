"""Trusted-proxy aware client-IP extraction.

``HTTP_X_FORWARDED_FOR`` is set by upstream proxies and is **completely
controlled by the remote client** unless we explicitly only honor it
when the request reached us via a proxy we trust. Blindly using XFF
lets attackers spoof IPs in audit logs, rate-limit buckets, and
geolocation lookups.

Use this single helper from every audit/security/geolocation call site
so the trust list is configured once.
"""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings

logger = logging.getLogger('security')

DEFAULT_TRUSTED_PROXIES = ['127.0.0.1', '::1']


def _trusted_networks() -> list[ipaddress._BaseNetwork]:
    """Parse ``settings.TRUSTED_PROXY_IPS`` into network objects.

    Each entry may be a single IP (``"10.0.0.5"``) or a CIDR
    (``"10.0.0.0/8"``).
    """
    raw = getattr(settings, 'TRUSTED_PROXY_IPS', DEFAULT_TRUSTED_PROXIES)
    nets: list[ipaddress._BaseNetwork] = []
    for entry in raw:
        try:
            nets.append(ipaddress.ip_network(entry, strict=False))
        except (ValueError, TypeError):
            logger.warning('Invalid TRUSTED_PROXY_IPS entry: %r', entry)
    return nets


def _is_trusted_proxy(remote_addr: str) -> bool:
    if not remote_addr:
        return False
    try:
        ip = ipaddress.ip_address(remote_addr)
    except (ValueError, TypeError):
        return False
    return any(ip in net for net in _trusted_networks())


def get_trusted_client_ip(request) -> str:
    """Return the best-effort client IP.

    Only honors ``X-Forwarded-For`` when the request actually came from
    a proxy in ``TRUSTED_PROXY_IPS``. Otherwise falls back to
    ``REMOTE_ADDR``.
    """
    remote_addr = request.META.get('REMOTE_ADDR', '') or ''
    if _is_trusted_proxy(remote_addr):
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if xff:
            # Left-most entry is the original client per RFC 7239.
            return xff.split(',')[0].strip() or remote_addr
    return remote_addr or 'unknown'


__all__ = ['get_trusted_client_ip']
