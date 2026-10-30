"""
egp viewsets — module_key = 'egp'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    TenderNotice,
    BidderRegistration,
    Bid,
    BidDocument,
    BidOpening,
    EvaluationCommittee,
    EvaluationCriterion,
    BidScore,
    TenderAward,
)
from .serializers import (
    TenderNoticeSerializer,
    BidderRegistrationSerializer,
    BidSerializer,
    BidDocumentSerializer,
    BidOpeningSerializer,
    EvaluationCommitteeSerializer,
    EvaluationCriterionSerializer,
    BidScoreSerializer,
    TenderAwardSerializer,
)


class TenderNoticeViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TenderNotice.objects.all()
    serializer_class = TenderNoticeSerializer
    filterset_fields = ['status', 'category', 'method']


class BidderRegistrationViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BidderRegistration.objects.all()
    serializer_class = BidderRegistrationSerializer
    filterset_fields = ['status', 'vendor']


class BidViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Bid.objects.all()
    serializer_class = BidSerializer
    filterset_fields = ['tender', 'bidder', 'status']


class BidDocumentViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BidDocument.objects.all()
    serializer_class = BidDocumentSerializer


class BidOpeningViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BidOpening.objects.all()
    serializer_class = BidOpeningSerializer


class EvaluationCommitteeViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = EvaluationCommittee.objects.all()
    serializer_class = EvaluationCommitteeSerializer


class EvaluationCriterionViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = EvaluationCriterion.objects.all()
    serializer_class = EvaluationCriterionSerializer


class BidScoreViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BidScore.objects.all()
    serializer_class = BidScoreSerializer


class TenderAwardViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TenderAward.objects.all()
    serializer_class = TenderAwardSerializer
