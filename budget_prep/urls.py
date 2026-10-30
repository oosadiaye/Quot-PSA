from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CallCircularViewSet,
    MTEFProjectionViewSet,
    MDACeilingViewSet,
    BudgetSubmissionViewSet,
    SubmissionLineViewSet,
    ReviewCommentViewSet,
)

router = DefaultRouter()
router.register(r'call-circulars', CallCircularViewSet, basename='call-circular')
router.register(r'mtef-projections', MTEFProjectionViewSet, basename='mtef-projection')
router.register(r'mda-ceilings', MDACeilingViewSet, basename='mda-ceiling')
router.register(r'submissions', BudgetSubmissionViewSet, basename='budget-submission')
router.register(r'submission-lines', SubmissionLineViewSet, basename='submission-line')
router.register(r'review-comments', ReviewCommentViewSet, basename='review-comment')

urlpatterns = [
    path('', include(router.urls)),
]
