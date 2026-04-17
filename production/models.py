"""
Production module — STUB for Quot PSE (public sector).
Minimal models to satisfy historical migration FK references only.
"""
from django.db import models


class WorkCenter(models.Model):
    """Stub."""
    name = models.CharField(max_length=100, default='')
    class Meta:
        db_table = 'production_workcenter'


class BillOfMaterials(models.Model):
    """Stub — referenced by inventory.Item.production_bom FK (historical)."""
    name = models.CharField(max_length=200, default='')
    is_active = models.BooleanField(default=True)
    class Meta:
        db_table = 'production_billofmaterials'


class BOMLine(models.Model):
    """Stub."""
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'production_bomline'


class ProductionOrder(models.Model):
    """Stub."""
    order_number = models.CharField(max_length=50, default='')
    class Meta:
        db_table = 'production_productionorder'


class MaterialIssue(models.Model):
    """Stub."""
    class Meta:
        db_table = 'production_materialissue'


class MaterialReceipt(models.Model):
    """Stub."""
    class Meta:
        db_table = 'production_materialreceipt'


class MaterialReservation(models.Model):
    """Stub."""
    class Meta:
        db_table = 'production_materialreservation'


class JobCard(models.Model):
    """Stub."""
    class Meta:
        db_table = 'production_jobcard'


class Routing(models.Model):
    """Stub."""
    class Meta:
        db_table = 'production_routing'
