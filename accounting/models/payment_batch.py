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
