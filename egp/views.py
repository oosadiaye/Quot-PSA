"""
egp viewsets — module_key = 'egp'.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from . import awarding, bidding
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
        if self.action in ('open_bids', 'award'):
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
    def ranking(self, request, pk=None):
        """The opened bids by price, with their assessment and evaluation score."""
        try:
            return Response(awarding.ranking(self.get_object()))
        except awarding.AwardingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def award(self, request, pk=None):
        """Award the tender to a responsive bid; raises a draft purchase order, which then needs the usual order approval."""
        from accounting.models import Account, Fund, Function, Geo, MDA, Program
        tender = self.get_object()

        def pk(value):
            """An id from the request, or None when it is blank or not a number (never an error: it just counts as not chosen)."""
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        try:
            bid = Bid.objects.filter(pk=pk(request.data.get('bid')), tender=tender).first()
            if bid is None:
                raise awarding.AwardingError('Choose the bid to award.')
            parts = {}
            for key, model, label in (('mda', MDA, 'MDA'), ('fund', Fund, 'fund'), ('function', Function, 'function'), ('program', Program, 'programme'),
                                      ('geo', Geo, 'location')):
                parts[key] = model.objects.filter(pk=pk(request.data.get(key))).first()
                if parts[key] is None:
                    raise awarding.AwardingError(f'Choose the {label} the order is charged to.')
            given = pk(request.data.get('account'))
            parts['account'] = (Account.objects.filter(pk=given).first() if given is not None
                                else Account.objects.filter(code=str(request.data.get('account_code', '')).strip()).first())
            if parts['account'] is None:
                raise awarding.AwardingError('Choose the expense account for the order line.')
            result = awarding.award(tender, bid, request.user, **parts)
        except awarding.AwardingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'award': result.pk, 'amount': str(result.award_amount), 'purchase_order': result.purchase_order_id,
                         'po_number': result.purchase_order.po_number}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def bids(self, request, pk=None):
        """The tender's bids. Who bid and when is visible to the office from the start; what a bid says only after the opening."""
        tender = self.get_object()
        rows = []
        for bid in tender.bids.select_related('bidder__vendor'):
            row = {'id': bid.pk, 'bidder': bid.bidder.vendor.name, 'status': bid.status, 'submitted_at': bid.submitted_at,
                   'receipt': bid.payload_hash, 'sealed': True, 'contents': None, 'note': bid.assessment_note}
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


class BidViewSet(viewsets.ReadOnlyModelViewSet):
    """Bids are made by suppliers and sealed on submission, so the office cannot create or edit one here; it can rule on an
    opened bid with ``assess``."""
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Bid.objects.all()
    serializer_class = BidSerializer
    filterset_fields = ['tender', 'bidder', 'status']

    @action(detail=True, methods=['post'])
    def assess(self, request, pk=None):
        bid = self.get_object()
        try:
            awarding.assess(bid, str(request.data.get('status', '')), request.user, note=str(request.data.get('note', '')))
        except awarding.AwardingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(bid).data)


class BidDocumentViewSet(viewsets.ModelViewSet):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BidDocument.objects.all()
    serializer_class = BidDocumentSerializer


class BidOpeningViewSet(viewsets.ReadOnlyModelViewSet):
    """The record of an opening is made by opening the bids, never typed in."""
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


class TenderAwardViewSet(viewsets.ReadOnlyModelViewSet):
    """An award is made from the tender's bids (``award``), which also raises the draft purchase order."""
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TenderAward.objects.all()
    serializer_class = TenderAwardSerializer
