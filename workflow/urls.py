from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ApprovalGroupViewSet, ApprovalTemplateViewSet, ApprovalViewSet,
    ApprovalStepViewSet, ApprovalLogViewSet, ApprovalDelegationViewSet,
    WorkflowDefinitionViewSet, WorkflowInstanceViewSet,
    GlobalApprovalSettingsViewSet
)

# Namespace lets ``reverse('workflow:approvals-detail', args=[pk])`` resolve
# unambiguously even if another app ever registers a route with the same
# name. Currently no callers reverse into workflow URLs, so adding the
# namespace is purely additive.
app_name = 'workflow'

router = DefaultRouter()
router.register(r'approval-groups', ApprovalGroupViewSet)
router.register(r'approval-templates', ApprovalTemplateViewSet)
router.register(r'approvals', ApprovalViewSet)
router.register(r'approval-steps', ApprovalStepViewSet)
router.register(r'approval-logs', ApprovalLogViewSet)
# Legacy WorkflowDefinition / WorkflowInstance endpoints. Kept for
# backward compatibility with any deployed clients that still call
# them. New code MUST use ``approvals/`` instead. See V14 in the audit:
# WorkflowLog uses a charfield for the actor, which is unreliable for
# audit-trail purposes — that's the single biggest reason these are
# deprecated.
router.register(r'definitions', WorkflowDefinitionViewSet)
router.register(r'instances', WorkflowInstanceViewSet)
router.register(r'settings', GlobalApprovalSettingsViewSet, basename='approval-settings')
router.register(r'delegations', ApprovalDelegationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
