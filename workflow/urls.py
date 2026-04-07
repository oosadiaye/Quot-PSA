from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ApprovalGroupViewSet, ApprovalTemplateViewSet, ApprovalViewSet,
    ApprovalStepViewSet, ApprovalLogViewSet, ApprovalDelegationViewSet,
    WorkflowDefinitionViewSet, WorkflowInstanceViewSet,
    GlobalApprovalSettingsViewSet
)

router = DefaultRouter()
router.register(r'approval-groups', ApprovalGroupViewSet)
router.register(r'approval-templates', ApprovalTemplateViewSet)
router.register(r'approvals', ApprovalViewSet)
router.register(r'approval-steps', ApprovalStepViewSet)
router.register(r'approval-logs', ApprovalLogViewSet)
router.register(r'definitions', WorkflowDefinitionViewSet)
router.register(r'instances', WorkflowInstanceViewSet)
router.register(r'settings', GlobalApprovalSettingsViewSet, basename='approval-settings')
router.register(r'delegations', ApprovalDelegationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
