"""URL wiring for the supplier self-service portal, mounted at ``/api/v1/supplier-portal/``."""
from django.urls import path

from procurement import views_portal as v

urlpatterns = [
    path('me/', v.my_profile, name='supplier-portal-profile'),
    path('bank-changes/', v.my_bank_changes, name='supplier-portal-bank-changes'),
    path('orders/', v.my_orders, name='supplier-portal-orders'),
    path('orders/<int:pk>/', v.my_order, name='supplier-portal-order'),
    path('orders/<int:pk>/acknowledge/', v.acknowledge_order, name='supplier-portal-acknowledge'),
    path('invoices/', v.my_invoices, name='supplier-portal-invoices'),
    path('payments/', v.my_payments, name='supplier-portal-payments'),
]
