"""The supplier's tenders and bids, mounted at ``/api/v1/supplier-portal/tenders/``."""
from django.urls import path

from . import views_portal as v

urlpatterns = [
    path('', v.Tenders.as_view(), name='supplier-portal-tenders'),
    path('<int:pk>/bid/', v.PlaceBid.as_view(), name='supplier-portal-place-bid'),
    path('bids/', v.MyBids.as_view(), name='supplier-portal-my-bids'),
    path('bids/<int:pk>/withdraw/', v.WithdrawBid.as_view(), name='supplier-portal-withdraw-bid'),
    path('registration/', v.Registration.as_view(), name='supplier-portal-bidder-registration'),
]
