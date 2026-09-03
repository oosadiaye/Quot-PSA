"""
results — Results & Performance Framework (G6 / FreeBalance GPPM).

FUTURE_MODULES §5.6: 'programme-based budgeting' is currently a classification
(``ProgrammeSegment`` on every appropriation; the Programme Performance report
measures naira only). This module anchors an indicator framework to the
existing ``ProgrammeSegment`` so no parallel hierarchy is created, and pairs
physical progress with the existing financial execution.
"""
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class ResultsFramework(AuditBaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    fiscal_year = models.IntegerField(db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']


class Outcome(AuditBaseModel):
    framework = models.ForeignKey(
        ResultsFramework, on_delete=models.CASCADE, related_name='outcomes',
    )
    name = models.CharField(max_length=255)
    programme = models.ForeignKey(
        'accounting.ProgrammeSegment', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['framework', 'name']


class Output(AuditBaseModel):
    outcome = models.ForeignKey(Outcome, on_delete=models.CASCADE, related_name='outputs')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['outcome', 'name']


class Indicator(AuditBaseModel):
    INDICATOR_TYPE_CHOICES = [
        ('output', 'Output'),
        ('outcome', 'Outcome'),
        ('impact', 'Impact'),
    ]

    output = models.ForeignKey(Output, on_delete=models.CASCADE, related_name='indicators')
    name = models.CharField(max_length=255)
    indicator_type = models.CharField(max_length=20, choices=INDICATOR_TYPE_CHOICES, default='output')
    unit = models.CharField(max_length=50, blank=True, default='')
    data_source = models.CharField(max_length=200, blank=True, default='')
    verification_note = models.TextField(blank=True, default='')
    baseline = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['output', 'name']


class IndicatorTarget(AuditBaseModel):
    FREQUENCY_CHOICES = [
        ('annual', 'Annual'),
        ('quarterly', 'Quarterly'),
    ]

    indicator = models.ForeignKey(
        Indicator, on_delete=models.CASCADE, related_name='targets',
    )
    fiscal_year = models.IntegerField(db_index=True)
    period = models.PositiveIntegerField(null=True, blank=True, help_text='1-4 for quarterly')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='annual')
    target_value = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        ordering = ['indicator', 'fiscal_year', 'period']


class IndicatorActual(AuditBaseModel):
    indicator = models.ForeignKey(
        Indicator, on_delete=models.CASCADE, related_name='actuals',
    )
    fiscal_year = models.IntegerField(db_index=True)
    period = models.PositiveIntegerField(null=True, blank=True)
    actual_value = models.DecimalField(max_digits=18, decimal_places=2)
    data_source = models.CharField(max_length=200, blank=True, default='')
    verification_note = models.TextField(blank=True, default='')
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['indicator', 'fiscal_year', 'period']


class PerformanceReport(AuditBaseModel):
    """Physical progress beside financial execution for a unit."""

    REPORT_SCOPE_CHOICES = [
        ('mda', 'MDA'),
        ('programme', 'Programme'),
        ('officer', 'Officer'),
    ]

    scope = models.CharField(max_length=20, choices=REPORT_SCOPE_CHOICES)
    scope_ref = models.CharField(max_length=100, blank=True, default='')
    fiscal_year = models.IntegerField(db_index=True)
    period = models.PositiveIntegerField(null=True, blank=True)
    physical_progress = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    financial_execution = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    narrative = models.TextField(blank=True, default='')
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scope', 'fiscal_year']
