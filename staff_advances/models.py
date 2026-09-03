"""
staff_advances — Staff Advances, Imprest & Travel (G10 / FreeBalance PFAA+CSTS).

FUTURE_MODULES §5.10: ``VendorAdvance`` handles the vendor side with a
special-GL reconciliation account and automatic recovery. There is no staff
equivalent, so touring advances, estacode and imprest retirement leave the
system and return as spreadsheets.  This module adds the staff side.

Scope:
  * StaffAdvance        — reuses the proven VendorAdvance special-GL pattern
    against an hrm employee rather than a vendor.
  * ImprestAccount      — issue, expenditure, retirement, replenishment, with
    an outstanding-retirement block on further issue.
  * TravelRequest → TravelAdvance → TravelRetirement, with estacode/per-diem
    table by grade and destination.
  * Automatic payroll recovery via hrm.SalaryComponent.
  * Ageing report of outstanding retirements.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class StaffAdvance(AuditBaseModel):
    """A cash advance to an employee, recorded with a Special-GL recon
    account (``Account.reconciliation_type='staff_advance'``) mirroring the
    proven VendorAdvance pattern."""

    STATUS_CHOICES = [
        ('OUTSTANDING', 'Outstanding'),
        ('PARTIAL', 'Partially Recovered'),
        ('CLEARED', 'Fully Cleared'),
    ]

    PURPOSE_CHOICES = [
        ('travel', 'Travel'),
        ('estacode', 'Estacode / Per-diem'),
        ('imprest', 'Imprest'),
        ('welfare', 'Welfare'),
        ('other', 'Other'),
    ]

    employee = models.ForeignKey(
        'hrm.Employee', on_delete=models.PROTECT, related_name='staff_advances',
        db_index=True,
    )
    recon_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT, related_name='+',
        help_text='Special-GL recon account (reconciliation_type=staff_advance).',
    )
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='travel')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    advance_date = models.DateField(default=timezone.now)
    recovery_start = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OUTSTANDING')
    recovered_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    journal = models.ForeignKey(
        'accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
        help_text='Disbursement journal pin (invariant 2: stays in the GL even '
                  'if the module is later disabled).',
    )
    reference = models.CharField(max_length=60, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    @property
    def outstanding(self):
        return self.amount - self.recovered_amount

    class Meta:
        ordering = ['-advance_date']
        indexes = [models.Index(fields=['employee', 'status'])]


class ImprestAccount(AuditBaseModel):
    """Imprest: issue, expenditure, retirement, replenishment."""

    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('FROZEN', 'Frozen — retirement outstanding'),
        ('CLOSED', 'Closed'),
    ]

    employee = models.ForeignKey(
        'hrm.Employee', on_delete=models.PROTECT, related_name='imprest_accounts',
    )
    reference = models.CharField(max_length=60, blank=True, default='')
    issued_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    retired_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    replenished_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    issue_date = models.DateField(default=timezone.now)
    retirement_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')

    @property
    def outstanding_retirement(self):
        return max(self.issued_amount - self.retired_amount, 0)

    class Meta:
        ordering = ['-issue_date']


class ImprestRetirement(AuditBaseModel):
    """A retirement event against an imprest account."""

    imprest = models.ForeignKey(
        ImprestAccount, on_delete=models.CASCADE, related_name='retirements',
    )
    retirement_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    supporting_docs = models.TextField(blank=True, default='')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    journal = models.ForeignKey(
        'accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )


class PerDiemTable(AuditBaseModel):
    """Estacode / per-diem rate by grade (and optional destination)."""

    GRADE_CHOICES = [
        ('Entry', 'Entry Level'), ('Mid', 'Mid Level'), ('Senior', 'Senior Level'),
        ('Manager', 'Manager'), ('Director', 'Director'), ('Executive', 'Executive'),
    ]

    grade = models.CharField(max_length=20, choices=GRADE_CHOICES)
    destination = models.CharField(max_length=200, blank=True, default='Local')
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['grade', 'destination']


class TravelRequest(AuditBaseModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('submitted', 'Submitted'), ('approved', 'Approved'),
        ('advanced', 'Advanced'), ('retired', 'Retired'), ('rejected', 'Rejected'),
    ]

    employee = models.ForeignKey(
        'hrm.Employee', on_delete=models.PROTECT, related_name='travel_requests',
    )
    destination = models.CharField(max_length=200)
    purpose = models.TextField(blank=True, default='')
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    days = models.PositiveIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    class Meta:
        ordering = ['-start_date']


class TravelAdvance(AuditBaseModel):
    travel_request = models.OneToOneField(
        TravelRequest, on_delete=models.CASCADE, related_name='advance',
    )
    staff_advance = models.OneToOneField(
        StaffAdvance, on_delete=models.PROTECT, null=True, blank=True,
        related_name='travel_advance',
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    advance_date = models.DateField(default=timezone.now)


class TravelRetirement(AuditBaseModel):
    travel_advance = models.ForeignKey(
        TravelAdvance, on_delete=models.CASCADE, related_name='retirements',
    )
    retired_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_returned = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    documents = models.TextField(blank=True, default='')
