from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AuditUniverseViewSet,
    AuditPlanViewSet,
    AuditEngagementViewSet,
    WorkingPaperViewSet,
    AuditFindingViewSet,
    FollowUpViewSet,
    ContinuousAuditRuleViewSet,
)

router = DefaultRouter()
router.register(r'universe', AuditUniverseViewSet, basename='audit-universe')
router.register(r'plans', AuditPlanViewSet, basename='audit-plan')
router.register(r'engagements', AuditEngagementViewSet, basename='audit-engagement')
router.register(r'working-papers', WorkingPaperViewSet, basename='working-paper')
router.register(r'findings', AuditFindingViewSet, basename='audit-finding')
router.register(r'follow-ups', FollowUpViewSet, basename='follow-up')
router.register(r'continuous-rules', ContinuousAuditRuleViewSet, basename='continuous-audit-rule')

urlpatterns = [
    path('', include(router.urls)),
]
