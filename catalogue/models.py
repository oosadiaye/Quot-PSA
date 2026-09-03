"""
catalogue — Supplier Catalogue (G13 / FreeBalance PECT).

FUTURE_MODULES §5.13: ``SupplierCatalogue`` and ``CatalogueItem`` with
validity dates and framework-agreement pricing, catalogue-driven requisition
that pre-fills price and specification, and price-history comparison across
suppliers. When off, requisition lines are entered free-text as today.
"""
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class SupplierCatalogue(AuditBaseModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
    ]

    name = models.CharField(max_length=255)
    supplier = models.ForeignKey(
        'procurement.Vendor', on_delete=models.PROTECT, related_name='catalogues',
    )
    reference = models.CharField(max_length=100, blank=True, default='')
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    framework_agreement = models.ForeignKey(
        'procurement.VendorContract', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    @property
    def is_current(self):
        today = timezone.now().date()
        return self.status == 'active' and (self.valid_to is None or self.valid_to >= today)

    class Meta:
        ordering = ['name']


class CatalogueItem(AuditBaseModel):
    """A catalogue product line at framework pricing."""

    catalogue = models.ForeignKey(
        SupplierCatalogue, on_delete=models.CASCADE, related_name='items',
    )
    item = models.ForeignKey(
        'inventory.Item', on_delete=models.PROTECT, related_name='+',
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    specification = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    price_effective_date = models.DateField(default=timezone.now)

    class Meta:
        ordering = ['catalogue', 'item']
        constraints = [
            models.UniqueConstraint(
                fields=['catalogue', 'item'], name='unique_catalogue_item',
            ),
        ]


class PriceHistory(AuditBaseModel):
    """Price history for cross-supplier comparison."""

    item = models.ForeignKey(
        'inventory.Item', on_delete=models.CASCADE, related_name='price_history',
    )
    supplier = models.ForeignKey(
        'procurement.Vendor', on_delete=models.PROTECT, related_name='+',
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    effective_date = models.DateField(default=timezone.now)

    class Meta:
        ordering = ['item', '-effective_date']