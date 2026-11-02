from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TenderNoticeViewSet,
    BidderRegistrationViewSet,
    BidViewSet,
    BidDocumentViewSet,
    BidOpeningViewSet,
    EvaluationCommitteeViewSet,
    EvaluationCriterionViewSet,
    BidScoreViewSet,
    TenderAwardViewSet,
)

router = DefaultRouter()
router.register(r'tenders', TenderNoticeViewSet, basename='tender')
router.register(r'bidder-registrations', BidderRegistrationViewSet, basename='bidder-registration')
router.register(r'bids', BidViewSet, basename='bid')
router.register(r'bid-documents', BidDocumentViewSet, basename='bid-document')
router.register(r'bid-openings', BidOpeningViewSet, basename='bid-opening')
router.register(r'evaluation-committees', EvaluationCommitteeViewSet, basename='evaluation-committee')
router.register(r'evaluation-criteria', EvaluationCriterionViewSet, basename='evaluation-criterion')
router.register(r'bid-scores', BidScoreViewSet, basename='bid-score')
router.register(r'awards', TenderAwardViewSet, basename='tender-award')

urlpatterns = [
    path('', include(router.urls)),
]
