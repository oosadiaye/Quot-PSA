"""
``transparency`` finding-5 tests — the public, unauthenticated citizen portal.

FUTURE_MODULES §5.5 requires:
  * a separate URL namespace for the public portal (outside the authed API),
  * its own throttle scope,
  * a read-only, unauthenticated surface served from ``PublicSnapshot``,
  * "off" enforced so no public surface is exposed.

These are DB-free checks (``SimpleTestCase``) so they run in the fast tier.
DB-backed behaviour (portal serving materialized rows) is covered by the
integration tier and deferred to CI.
"""
from django.test import SimpleTestCase


class TestPublishedSnapshotViewSetConfig:
    """Structural guarantees that hold without a live database."""

    def test_is_read_only_modelviewset(self):
        from rest_framework import viewsets
        from transparency.public_views import PublishedSnapshotViewSet
        assert issubclass(PublishedSnapshotViewSet, viewsets.ReadOnlyModelViewSet)

    def test_unauthenticated_and_allow_any(self):
        from rest_framework.permissions import AllowAny
        from transparency.public_views import PublishedSnapshotViewSet
        assert PublishedSnapshotViewSet.authentication_classes == []
        assert AllowAny in PublishedSnapshotViewSet.permission_classes

    def test_own_throttle_scope(self):
        from rest_framework.throttling import ScopedRateThrottle
        from transparency.public_views import PublishedSnapshotViewSet
        assert ScopedRateThrottle in PublishedSnapshotViewSet.throttle_classes
        assert PublishedSnapshotViewSet.throttle_scope == 'transparency_public'

    def test_serializer_serves_public_snapshot_model(self):
        from superadmin.models import PublishedSnapshot
        from transparency.public_serializers import PublishedSnapshotSerializer
        assert PublishedSnapshotSerializer.Meta.model is PublishedSnapshot

    def test_public_serializer_is_read_only(self):
        from transparency.public_serializers import PublishedSnapshotSerializer
        fields = set(PublishedSnapshotSerializer.Meta.fields)
        assert set(PublishedSnapshotSerializer.Meta.read_only_fields) == fields


class TestPortalGate:
    """The master switch must fail closed."""

    def test_helper_fails_closed_on_error(self):
        from unittest import mock
        import superadmin.models as m

        with mock.patch.object(m.SuperAdminSettings, 'load', side_effect=Exception('boom')):
            assert m.transparency_portal_enabled() is False


class TestPublicUrlNamespace:
    """The portal lives in its own namespace, outside the authed tree."""

    def test_namespace_list_resolves(self):
        from django.urls import resolve, reverse
        path = reverse('transparency-public:public-dataset-list')
        assert path.startswith('/public/transparency/')
        resolver = resolve(path)
        assert resolver.url_name == 'public-dataset-list'

    def test_namespace_detail_resolves(self):
        from django.urls import resolve, reverse
        path = reverse('transparency-public:public-dataset-detail', kwargs={'pk': 1})
        resolver = resolve(path)
        assert resolver.url_name == 'public-dataset-detail'

    def test_gate_mixin_is_used_by_viewset(self):
        from transparency.public_views import PublicPortalGateMixin, PublishedSnapshotViewSet
        assert issubclass(PublishedSnapshotViewSet, PublicPortalGateMixin)
