"""URL routing for the snapshots feature. Wired into the project urls.py by Task 23."""
from __future__ import annotations

from rest_framework.routers import DefaultRouter

from snapshots.views import SnapshotJobViewSet


router = DefaultRouter()
router.register(r'snapshots', SnapshotJobViewSet, basename='snapshot')
urlpatterns = router.urls
