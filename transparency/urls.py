from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PublicationPolicyViewSet,
    PublicationViewSet,
    RedactionRuleViewSet,
    DataExportViewSet,
)

router = DefaultRouter()
router.register(r'policies', PublicationPolicyViewSet, basename='publication-policy')
router.register(r'publications', PublicationViewSet, basename='publication')
router.register(r'redaction-rules', RedactionRuleViewSet, basename='redaction-rule')
router.register(r'exports', DataExportViewSet, basename='data-export')

urlpatterns = [
    path('', include(router.urls)),
]
