"""Routing for the public, unauthenticated transparency portal.

Mounted separately at ``/public/transparency/`` — a distinct URL namespace from
the authenticated tenant API — so that the portal's on/off state is enforced at
the routing layer (FUTURE_MODULES §5.5).
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .public_views import PublishedSnapshotViewSet

router = DefaultRouter()
router.register(
    r'datasets', PublishedSnapshotViewSet, basename='public-dataset',
)

app_name = 'transparency-public'

urlpatterns = [
    path('', include(router.urls)),
]
