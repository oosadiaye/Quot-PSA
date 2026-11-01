"""
egp viewsets — module_key = 'egp'.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from . import bidding
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

    def get_permissions(self):
        # Opening releases every sealed bid, so it is an approver's recorded act.
        if self.action == 'open_bids':
            return [IsAuthenticated(), ModuleEnabled(), RBACPermission(), IsApprover('post')]
        return super().get_permissions()

    @action(detail=True, methods=['post'], url_path='open-bids')
    def open_bids(self, request, pk=None):
        tender = self.get_object()
        attendance = request.data.get('attendance') or []
        if isinstance(attendance, str):
            attendance = [a for a in attendance.splitlines()]
        try:
            opening = bidding.open_bids(tender, request.user, attendance=list(attendance), minutes=str(request.data.get('minutes', '')))
        except bidding.BiddingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'opened_at': opening.opened_at, 'attendance': opening.attendance, 'bids_opened': tender.bids.filter(status='opened').count()},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def bids(self, request, pk=None):
        """The tender's bids. Who bid and when is visible to the office from the start; what a bid says only after the opening."""
        tender = self.get_object()
        rows = []
        for bid in tender.bids.select_related('bidder__vendor'):
            row = {'id': bid.pk, 'bidder': bid.bidder.vendor.name, 'status': bid.status, 'submitted_at': bid.submitted_at,
                   'receipt': bid.payload_hash, 'sealed': True, 'contents': None}
            try:
                row['contents'], row['sealed'] = bidding.contents(bid), False
            except bidding.BiddingError:
                pass
            rows.append(row)
        return Response({'opened': hasattr(tender, 'opening'), 'bids': rows})


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
