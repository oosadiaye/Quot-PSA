"""
fleet — Fleet Management (G13 / FreeBalance PFFM).

FUTURE_MODULES §5.12: ``Vehicle`` extends ``FixedAsset`` rather than
duplicating it, with assignment/custody, fuel and mileage logs, maintenance
schedule/history, and licence/insurance/roadworthiness expiry alerts. Running
cost report per vehicle and per MDA.
"""
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class Vehicle(AuditBaseModel):
    """Extends the fixed-asset record with fleet-specific data."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('assigned', 'Assigned'),
        ('maintenance', 'Under Maintenance'),
        ('offroad', 'Off Road'),
        ('disposed', 'Disposed'),
    ]

    fixed_asset = models.OneToOneField(
        'accounting.FixedAsset', on_delete=models.PROTECT, related_name='vehicle',
    )
    registration_number = models.CharField(max_length=30, unique=True, db_index=True)
    chassis_number = models.CharField(max_length=60, blank=True, default='')
    make = models.CharField(max_length=100, blank=True, default='')
    model = models.CharField(max_length=100, blank=True, default='')
    year = models.PositiveIntegerField(null=True, blank=True)
    fuel_type = models.CharField(max_length=30, default='Petrol')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    licence_expiry = models.DateField(null=True, blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    roadworthiness_expiry = models.DateField(null=True, blank=True)

    @property
    def is_expiring(self):
        today = timezone.now().date()
        for d in (self.licence_expiry, self.insurance_expiry, self.roadworthiness_expiry):
            if d and (d - today).days <= 30:
                return True
        return False

    class Meta:
        ordering = ['registration_number']


class VehicleAssignment(AuditBaseModel):
    """Assignment and custody of a vehicle."""

    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name='assignments',
    )
    assigned_to = models.CharField(max_length=200)
    department = models.CharField(max_length=200, blank=True, default='')
    assigned_from = models.DateField(default=timezone.now)
    assigned_to_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-assigned_from']


class FuelLog(AuditBaseModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='fuel_logs')
    log_date = models.DateField(default=timezone.now)
    litres = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    odometer_reading = models.PositiveIntegerField(default=0)
    vendor = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-log_date']


class MileageLog(AuditBaseModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='mileage_logs')
    log_date = models.DateField(default=timezone.now)
    odometer_reading = models.PositiveIntegerField(default=0)
    trip_purpose = models.TextField(blank=True, default='')
    driver = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-log_date']


class MaintenanceRecord(AuditBaseModel):
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name='maintenance_records',
    )
    service_date = models.DateField(default=timezone.now)
    next_due_date = models.DateField(null=True, blank=True)
    service_type = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_provider = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-service_date']