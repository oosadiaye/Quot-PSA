"""Tenders and bids as a supplier sees them, ``/api/v1/supplier-portal/tenders/``.

A supplier sees tenders open for bids and its own bids; never another bidder's bid or anything a bid says once sealed. Behind the
e-procurement module's switch like the rest of that module.
"""
from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import ModuleEnabled
from procurement.views_portal import IsSupplier

from . import bidding
from .models import Bid


class BidInput(serializers.Serializer):
    price = serializers.DecimalField(max_digits=18, decimal_places=2)
    completion_days = serializers.IntegerField(min_value=1)
    validity_days = serializers.IntegerField(min_value=1)
    technical_note = serializers.CharField(required=False, allow_blank=True, max_length=4000)


class _SupplierView(APIView):
    module_key = 'egp'
    permission_classes = [IsAuthenticated, ModuleEnabled, IsSupplier]


def _bid_summary(bid: Bid) -> dict:
    return {'id': bid.pk, 'tender': bid.tender_id, 'status': bid.status, 'submitted_at': bid.submitted_at, 'receipt': bid.payload_hash}


class Tenders(_SupplierView):
    def get(self, request):
        ok, why = bidding.eligibility(request.vendor)
        reg = bidding.registration_of(request.vendor)
        mine = {b.tender_id: b for b in Bid.objects.filter(bidder=reg)} if reg else {}
        rows = [{
            'id': t.pk, 'reference': t.reference, 'title': t.title, 'description': t.description, 'category': t.category,
            'method': t.get_method_display(), 'published_date': t.published_date, 'closing_date': t.closing_date,
            'my_bid': _bid_summary(mine[t.pk]) if t.pk in mine else None,
        } for t in bidding.open_tenders()]
        return Response({'eligible': ok, 'reason': why, 'registration_status': reg.status if reg else 'none', 'tenders': rows})


class PlaceBid(_SupplierView):
    def post(self, request, pk):
        from .models import TenderNotice
        tender = TenderNotice.objects.filter(pk=pk).first()
        if tender is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        body = BidInput(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            bid = bidding.submit(request.vendor, tender, **body.validated_data)
        except bidding.BiddingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_bid_summary(bid), status=status.HTTP_201_CREATED)


class MyBids(_SupplierView):
    def get(self, request):
        reg = bidding.registration_of(request.vendor)
        rows = Bid.objects.filter(bidder=reg).select_related('tender') if reg else []
        return Response([{**_bid_summary(b), 'tender_reference': b.tender.reference, 'tender_title': b.tender.title,
                          'closing_date': b.tender.closing_date} for b in rows])


class WithdrawBid(_SupplierView):
    def post(self, request, pk):
        bid = Bid.objects.select_related('bidder', 'tender').filter(pk=pk, bidder__vendor=request.vendor).first()
        if bid is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            bid = bidding.withdraw(request.vendor, bid)
        except bidding.BiddingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_bid_summary(bid))


class Registration(_SupplierView):
    def get(self, request):
        reg = bidding.registration_of(request.vendor)
        return Response({'status': reg.status if reg else 'none', 'categories': reg.categories if reg else [],
                         'certificate_expiry': reg.certificate_expiry if reg else None,
                         'tax_clearance_expiry': reg.tax_clearance_expiry if reg else None})

    def post(self, request):
        cats = request.data.get('categories', [])
        if not isinstance(cats, list):
            return Response({'error': 'Categories must be a list.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            reg = bidding.request_registration(request.vendor, categories=[str(c) for c in cats])
        except bidding.BiddingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': reg.status, 'categories': reg.categories}, status=status.HTTP_201_CREATED)
