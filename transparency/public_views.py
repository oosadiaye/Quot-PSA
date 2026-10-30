"""Public, unauthenticated, read-only transparency portal (FUTURE_MODULES §5.5).

This is the citizen-facing portal.  It deliberately lives in its **own URL
namespace** (``transparency-public``, mounted under ``/public/transparency/``,
not inside the authenticated ``/api/v1/`` tree) so that its on/off state is
enforced at the routing layer.

Behaviour:
  * Unauthenticated — ``authentication_classes = []``, ``AllowAny``.
  * Read-only — ``ReadOnlyModelViewSet``; there is no write surface to attack.
  * Own throttling — ``ScopedRateThrottle`` with scope ``transparency_public``.
  * Served from ``superadmin.PublishedSnapshot`` (public schema), never from
    live transactional tables.
  * Master-switch gated: when ``SuperAdminSettings.transparency_portal_enabled``
    is off every public endpoint returns 404, so no public surface exists.
"""
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from superadmin.models import PublishedSnapshot, transparency_portal_enabled
from .public_serializers import PublishedSnapshotSerializer


class PublicPortalGateMixin:
    """Fail-closed master switch for the public portal routing gate."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not transparency_portal_enabled():
            raise NotFound('The transparency public portal is disabled.')


class PublishedSnapshotViewSet(PublicPortalGateMixin, viewsets.ReadOnlyModelViewSet):
    """Public, read-only list/retrieve of published fiscal datasets."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'transparency_public'

    queryset = PublishedSnapshot.objects.filter(
        is_public=True,
    ).order_by('-published_at')
    serializer_class = PublishedSnapshotSerializer
    filterset_fields = ['dataset_key', 'fiscal_year', 'period']
    search_fields = ['title']
    ordering_fields = ['published_at', 'fiscal_year', 'period']
