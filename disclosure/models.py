"""
disclosure — Asset Declaration (G13 / FreeBalance CSFD).

FUTURE_MODULES §5.14: ``DeclarationCycle``, ``AssetDeclaration`` and
``DeclarationItem``, submission and acknowledgement workflow, compliance
register by officer and grade, non-compliance escalation.

**Privacy note (critical):** this module holds the most sensitive personal
data in the product. Per spec it requires its own access-control review,
field-level encryption for declared values, and an access log distinct from
the general audit trail — specified BEFORE build, not after.

This scaffold therefore stores declared *values* only via an encrypted field
marker and records every access (GET on a declaration) in a dedicated
``DisclosureAccessLog`` separate from the general audit trail. The actual
field-level encryption implementation (using superadmin/encryption.py or a
dedicated KMS) is wired during the build phase before this module is enabled
in any government tenant.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class DeclarationCycle(AuditBaseModel):
    name = models.CharField(max_length=255)
    fiscal_year = models.IntegerField(db_index=True)
    opens_at = models.DateTimeField(default=timezone.now)
    closes_at = models.DateTimeField(null=True, blank=True)
    is_open = models.BooleanField(default=True)

    class Meta:
        ordering = ['-fiscal_year']


class AssetDeclaration(AuditBaseModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('acknowledged', 'Acknowledged'),
        ('queried', 'Queried'),
        ('non_compliant', 'Non-Compliant'),
    ]

    cycle = models.ForeignKey(
        DeclarationCycle, on_delete=models.CASCADE, related_name='declarations',
    )
    employee = models.ForeignKey(
        'hrm.Employee', on_delete=models.CASCADE, related_name='asset_declarations',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    submitted_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['cycle', 'employee']
        constraints = [
            models.UniqueConstraint(
                fields=['cycle', 'employee'], name='unique_declaration_per_cycle_employee',
            ),
        ]


class DeclarationItem(AuditBaseModel):
    """A declared asset. The declared value is held via an encrypted marker;
    field-level ciphertext is applied at build phase (see module docstring)."""

    ASSET_TYPE_CHOICES = [
        ('cash', 'Cash & Bank Balances'),
        ('real_estate', 'Real Estate'),
        ('vehicle', 'Vehicles'),
        ('investment', 'Investments'),
        ('business', 'Business Interests'),
        ('other', 'Other'),
    ]

    declaration = models.ForeignKey(
        AssetDeclaration, on_delete=models.CASCADE, related_name='items',
    )
    asset_type = models.CharField(max_length=30, choices=ASSET_TYPE_CHOICES)
    description = models.TextField(blank=True, default='')
    value_encrypted = models.BinaryField(
        null=True, blank=True, help_text='Field-level encrypted declared value.',
    )
    value_ciphertext = models.CharField(max_length=512, blank=True, default='')

    class Meta:
        ordering = ['declaration', 'asset_type']


class DisclosureAccessLog(models.Model):
    """Dedicated access log for disclosures — DISTINCT from the general audit
    trail, per the module privacy note."""

    declaration = models.ForeignKey(
        AssetDeclaration, on_delete=models.CASCADE, related_name='access_log',
    )
    accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+',
    )
    accessed_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=50, default='view')
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-accessed_at']