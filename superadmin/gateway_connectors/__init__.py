"""
Payment-gateway connectors.

One connector per PSP, each translating the platform's uniform
:class:`~superadmin.gateway_connectors.base.DisburseRequest` /
``WebhookEvent`` into that provider's own request shape, signature scheme
and response format. The seam in :mod:`superadmin.gateway_client` speaks
only the uniform shapes and never a provider's specifics, so a new PSP is
a new connector, not a change to the seam.
"""
from __future__ import annotations

from superadmin.gateway_connectors.base import (
    CollectRequest,
    ConnectorError,
    DisburseRequest,
    GatewayConnector,
    ConnectorResult,
    WebhookEvent,
)


def get_connector(provider) -> GatewayConnector:
    """Resolve the connector for a provider by its ``key``.

    Imported lazily so a connector module that pulls a heavy SDK does not
    load until it is actually used, and so a misconfigured provider raises
    a clear error at use rather than at import.
    """
    from superadmin.gateway_models import PaymentGatewayProvider

    key = provider.key
    if key == PaymentGatewayProvider.Key.REMITA:
        from superadmin.gateway_connectors.remita import RemitaConnector
        return RemitaConnector()
    if key == PaymentGatewayProvider.Key.XPRESSPAY:
        from superadmin.gateway_connectors.xpresspay import XpresspayConnector
        return XpresspayConnector()
    raise ConnectorError(f"No connector is registered for gateway {key!r}.")


__all__ = [
    "CollectRequest",
    "ConnectorError",
    "ConnectorResult",
    "DisburseRequest",
    "GatewayConnector",
    "WebhookEvent",
    "get_connector",
]
