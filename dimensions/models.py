"""
Tenant-defined analytical dimensions ("Ward", "Zone", "Polling Unit", ...).

A DimensionType is the object the tenant defines; DimensionValues are its members (a type may name a parent type, so a
value of the child type must sit under a value of the parent type). Tags attach values to a record by (record_type,
record_id) so no existing table gains a column: with no types defined, nothing in the system changes.
"""
from django.db import models

from core.models import AuditBaseModel

# Records a dimension can be switched on for. One place, so a form, a report and the rules agree on the names.
JOURNAL_LINE = 'journal_line'
PURCHASE_REQUEST = 'purchase_request'
PURCHASE_ORDER = 'purchase_order'
APPROPRIATION = 'appropriation'
RECORD_TYPES = (JOURNAL_LINE, PURCHASE_REQUEST, PURCHASE_ORDER, APPROPRIATION)
RECORD_TYPE_CHOICES = [
    (JOURNAL_LINE, 'Journal line'),
    (PURCHASE_REQUEST, 'Purchase request'),
    (PURCHASE_ORDER, 'Purchase order'),
    (APPROPRIATION, 'Appropriation'),
]


class DimensionType(AuditBaseModel):
    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    parent_type = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT, related_name='child_types',
        help_text='A value of this type must sit under a value of the parent type (e.g. Ward under Zone).')
    applies_to = models.JSONField(default=list, blank=True, help_text='Record types this dimension appears on.')
    required_on = models.JSONField(default=list, blank=True, help_text='Record types where a value is mandatory.')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class DimensionValue(AuditBaseModel):
    dimension_type = models.ForeignKey(DimensionType, on_delete=models.PROTECT, related_name='values')
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT, related_name='children',
        help_text='A value of the parent dimension type.')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['dimension_type', 'code']
        constraints = [models.UniqueConstraint(fields=['dimension_type', 'code'], name='uniq_dimension_value_code')]

    def __str__(self):
        return f'{self.dimension_type.code}:{self.code}'


class DimensionTag(models.Model):
    """One value of one dimension on one record (a journal line, a purchase request, ...)."""
    record_type = models.CharField(max_length=30, choices=RECORD_TYPE_CHOICES, db_index=True)
    record_id = models.PositiveBigIntegerField(db_index=True)
    dimension_type = models.ForeignKey(DimensionType, on_delete=models.PROTECT, related_name='tags')
    value = models.ForeignKey(DimensionValue, on_delete=models.PROTECT, related_name='tags')

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=['record_type', 'record_id', 'dimension_type'], name='uniq_dimension_tag_per_record')]
        indexes = [models.Index(fields=['record_type', 'record_id'])]
