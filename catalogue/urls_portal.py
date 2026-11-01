"""The supplier's catalogue endpoints, mounted at ``/api/v1/supplier-portal/catalogue/``."""
from django.urls import path

from . import views_portal as v

urlpatterns = [
    path('', v.MyCatalogue.as_view(), name='supplier-portal-catalogue'),
    path('items/', v.ItemSearch.as_view(), name='supplier-portal-catalogue-items'),
    path('proposals/', v.MyProposals.as_view(), name='supplier-portal-catalogue-proposals'),
]
