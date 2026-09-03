"""
debt — Public Debt Management (G4 / FreeBalance DBNT).

FUTURE_MODULES §5.4: ``Loan`` and ``LoanRepayment`` exist as inert stubs in
``accounting.models.advanced`` (lines ~330) — no debt instruments, no service
schedules, no DSA, no integration with payments. This module provides the full
public-debt ledger and governance control.

Scope:
  * DebtInstrument        — loan/security instrument (creditor, currency,
    commitment type, fees, terms). Migratable to a hardened DSA/DMS later.
  * AmortisationSchedule  — computed coupon (principal + interest) schedule
    per instrument; disposal on instrument close.
  * AmortisationCoupon    — a specific scheduled payment, transitioned to a
    payment warrant via the existing Warrant flow.
  * AmortisationLedger    — audit trail of every coupon lifecycle event,
    incl. paid-with-warrant entries.
  * DebtServiceCost       — fiscal-year actuals of principal + interest,
    feeding ``cash_planning`` and the GFS/IPSAS disclosures.
  * DebtAversionStatement — annual DSA / debt-sustainability snapshot.

External integration: payment is executed through the existing ``budget``
Warrant process and stays in the GL (invariant 2) even if the module is later
disabled.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class DebtInstrument(AuditBaseModel):
    """A public debt instrument (loan or security)."""

    INSTRUMENT_TYPE_CHOICES = [
        ('loan', 'Loan'),
        ('bond', 'Bond / Security'),
        ('treasury_bill', 'Treasury Bill'),
        ('guarantee', 'Guarantee'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
    ]

    instrument_number = models.CharField(max_length=60, db_index=True, unique=True)
    instrument_type = models.CharField(max_length=20, choices=INSTRUMENT_TYPE_CHOICES, default='loan')
    creditor = models.CharField(max_length=255, db_index=True)
    currency = models.ForeignKey(
        'accounting.Currency', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    principal_amount = models.DecimalField(max_digits=18, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    commitment_fee_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    start_date = models.DateField(default=timezone.now)
    maturity_date = models.DateField(null=True, blank=True)
    grace_period = models.PositiveIntegerField(default=0, help_text='Grace period in months.')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_concessional = models.BooleanField(default=False)

    @property
    def outstanding_principal(self):
        coupons = self.coupons.filter(is_paid=True)
        paid = sum(c.principal_amount or 0 for c in coupons)
        return self.principal_amount - paid

    class Meta:
        ordering = ['instrument_number']


class AmortisationSchedule(AuditBaseModel):
    """Computed coupon schedule for an instrument."""

    instrument = models.ForeignKey(
        DebtInstrument, on_delete=models.CASCADE, related_name='schedules',
    )
    coupon_date = models.DateField()
    principal_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    interest_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    commitment_fee = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_released = models.BooleanField(default=False)

    @property
    def total_amount(self):
        return self.principal_amount + self.interest_amount + self.commitment_fee

    class Meta:
        ordering = ['instrument', 'coupon_date']


class AmortisationCoupon(AuditBaseModel):
    """A specific scheduled debt-service payment."""

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('approved', 'Approved for Payment'),
        ('paid', 'Paid'),
        ('defaulted', 'Defaulted'),
        ('closed', 'Closed'),
    ]

    schedule = models.ForeignKey(
        AmortisationSchedule, on_delete=models.CASCADE, related_name='coupons',
    )
    principal_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    interest_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    commitment_fee = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    warrant = models.ForeignKey(
        'budget.Warrant', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    @property
    def total_amount(self):
        return self.principal_amount + self.interest_amount + self.commitment_fee

    class Meta:
        ordering = ['schedule']


class AmortisationLedger(AuditBaseModel):
    """Audit trail of coupon lifecycle events (incl. paid-with-warrant)."""

    EVENT_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('approved', 'Approved'),
        ('paid', 'Paid via Warrant'),
        ('defaulted', 'Defaulted'),
        ('closed', 'Closed'),
    ]

    coupon = models.ForeignKey(
        AmortisationCoupon, on_delete=models.CASCADE, related_name='ledger_events',
    )
    event = models.CharField(max_length=20, choices=EVENT_CHOICES)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    warrant = models.ForeignKey(
        'budget.Warrant', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    description = models.CharField(max_length=255, blank=True, default='')
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['recorded_at']


class DebtServiceCost(AuditBaseModel):
    """Fiscal-year debt-service actuals (principal + interest), feeding
    cash_planning and IPSAS/GFS disclosures."""

    fiscal_year = models.IntegerField(db_index=True)
    month = models.PositiveIntegerField(null=True, blank=True)
    instrument = models.ForeignKey(
        DebtInstrument, on_delete=models.CASCADE, null=True, blank=True, related_name='+',
    )
    principal_paid = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    interest_paid = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    fees_paid = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        ordering = ['fiscal_year', 'month']


class DebtAversionStatement(AuditBaseModel):
    """Annual debt-sustainability assessment snapshot."""

    PILLAR_CHOICES = [
        ('domestic', 'Domestic Debt'),
        ('external', 'External Debt'),
        ('guarantees', 'Guarantees & Contingent'),
    ]

    fiscal_year = models.IntegerField(db_index=True)
    pillar = models.CharField(max_length=20, choices=PILLAR_CHOICES, default='domestic')
    outstanding_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    gdp = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    revenue = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    debt_to_gdp = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    debt_service_to_revenue = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    assessment = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['fiscal_year', 'pillar']
