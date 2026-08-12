"""
Payment batching — the OAG BANK PAYMENT(S)/CONFIRMATION(S) letter.

A ``PaymentBatch`` groups already-Posted AP payments that are drawn on
ONE government bank account into a single numbered instruction letter
addressed to that bank's manager.

The batch is a pure document layer: it never posts, voids, or edits a
``Payment``. Existing AP logic is untouched by construction.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import AuditBaseModel

# NOTE: this project does NOT set AUTH_USER_MODEL — it resolves to the
# stock ``auth.User``. Always reference it as settings.AUTH_USER_MODEL;
# there is no ``core.User``.


class BankLetterSettings(AuditBaseModel):
    """Singleton per tenant — letterhead + the three signatories.

    Deliberately independent of ``budget.WarrantPrintoutSettings``: that
    model's three signatories are Governor / Commissioner / AG, whereas
    this letter is signed by AG / Director Treasury / Director Management
    Accounts. Keeping them separate means changing one document's
    settings can never alter the other. The cost — logo and address are
    maintained in two places — was accepted explicitly.
    """

    ministry_name = models.CharField(max_length=200, default='Ministry of Finance')
    office_name = models.CharField(max_length=200, default='Office of the Accountant General')
    office_address = models.CharField(max_length=200, blank=True, default='')
    letterhead_logo = models.ImageField(
        upload_to='bank_letters/logos/', null=True, blank=True,
        help_text='State coat of arms (PNG/JPG, ~200px tall).',
    )

    accountant_general_name = models.CharField(max_length=200, blank=True, default='')
    accountant_general_title = models.CharField(
        max_length=200, default='Permanent Secretary/Accountant General')
    accountant_general_signature = models.ImageField(
        upload_to='bank_letters/signatures/', null=True, blank=True)

    director_treasury_name = models.CharField(max_length=200, blank=True, default='')
    director_treasury_title = models.CharField(max_length=200, default='Director Treasurer')
    director_treasury_signature = models.ImageField(
        upload_to='bank_letters/signatures/', null=True, blank=True)

    director_mgmt_acct_name = models.CharField(max_length=200, blank=True, default='')
    director_mgmt_acct_title = models.CharField(
        max_length=200, default='Director Management Acct')
    director_mgmt_acct_signature = models.ImageField(
        upload_to='bank_letters/signatures/', null=True, blank=True)

    class Meta:
        verbose_name = 'Bank Letter Settings'
        verbose_name_plural = 'Bank Letter Settings'

    def __str__(self):
        return f'Bank letter settings ({self.office_name})'

    @classmethod
    def get_singleton(cls) -> 'BankLetterSettings':
        """Return (creating if needed) the single settings row.

        Same pk=1 convention as WarrantPrintoutSettings — one row per
        tenant schema thanks to django-tenants.
        """
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PaymentBatch(AuditBaseModel):
    """A numbered bank instruction letter over already-Posted payments."""

    STATUS_DRAFT = 'Draft'
    STATUS_DISPATCHED = 'Dispatched'
    STATUS_CONFIRMED = 'Confirmed'
    STATUS_CANCELLED = 'Cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_DISPATCHED, 'Dispatched'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    batch_number = models.CharField(max_length=30, unique=True, db_index=True)
    batch_date = models.DateField(default=date.today)
    source_bank_account = models.ForeignKey(
        'accounting.BankAccount', on_delete=models.PROTECT,
        related_name='payment_batches',
        help_text='The government account the bank is instructed to debit.',
    )
    # Snapshotted at creation: the letter must reprint what was signed even
    # if the BankAccount record is later renamed or renumbered.
    addressee_bank_name = models.CharField(max_length=100)
    addressee_account_no = models.CharField(max_length=50)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dispatched_payment_batches')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='confirmed_payment_batches')
    cancelled_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-batch_date', '-batch_number']
        verbose_name = 'Payment Batch'
        verbose_name_plural = 'Payment Batches'
        indexes = [models.Index(fields=['status', 'batch_date'])]

    def __str__(self):
        return f'{self.batch_number} ({self.status})'

    @property
    def total_amount(self) -> Decimal:
        agg = self.lines.filter(is_active_membership=True).aggregate(
            total=models.Sum('amount'))
        return agg['total'] or Decimal('0')


class PaymentBatchLine(models.Model):
    """One vendor row on the letter. All payee data is frozen at add-time."""

    batch = models.ForeignKey(PaymentBatch, on_delete=models.CASCADE, related_name='lines')
    payment = models.ForeignKey(
        'accounting.Payment', on_delete=models.PROTECT,
        related_name='batch_lines', null=True, blank=True)
    sequence = models.PositiveIntegerField(help_text='The S/N column.')

    # ── Frozen snapshots — never re-read from source after creation ──
    payee_name = models.CharField(max_length=200)
    payee_bank = models.CharField(max_length=100)
    payee_account = models.CharField(max_length=20)
    purpose = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=20, decimal_places=2)

    # Denormalised membership flag. The critical failure mode is a payment
    # appearing in two live batches — the bank is instructed twice and the
    # vendor is paid twice. unique_together('batch','payment') would only
    # stop duplicates WITHIN one batch, and a UniqueConstraint condition
    # cannot join to batch__status. So membership is denormalised here and
    # a partial unique index enforces "at most one active membership per
    # payment" at the database level. Cancelling a batch flips this False,
    # releasing its payments back into the eligible pool.
    is_active_membership = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['sequence']
        constraints = [
            models.UniqueConstraint(
                fields=['payment'],
                condition=models.Q(is_active_membership=True),
                name='uniq_active_payment_batch_membership',
            ),
        ]

    def __str__(self):
        return f'{self.batch.batch_number} #{self.sequence} {self.payee_name}'
