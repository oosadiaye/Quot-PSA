"""
egp — Electronic Government Procurement & Tendering (G2 / FreeBalance PEGP+PEEP).

FUTURE_MODULES §5.2: the *governance* already exists
(``ProcurementThreshold``, ``CertificateOfNoObjection``). The transaction —
tender, bid, evaluation, award — does not. This module provides it.

Security-critical element per spec: the sealed-bid window. Bid contents must
be encrypted at rest and undecryptable before the recorded opening event. We
model an ``encrypted_payload`` (ciphertext at rest) and a separate
``opened_at`` audit marker; decrypting is only authorised after the opening
event is recorded.
"""
from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class TenderNotice(AuditBaseModel):
    """Advertisement of a tender opportunity."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    METHOD_CHOICES = [
        ('open', 'Open Competitive Bidding'),
        ('selective', 'Selective Bidding'),
        ('restricted', 'Restricted Bidding'),
        ('direct', 'Direct Procurement'),
        ('two_stage', 'Two-Stage Bidding'),
    ]

    reference = models.CharField(max_length=60, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=100, blank=True, default='')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='open')
    published_date = models.DateField(default=timezone.now)
    closing_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    documents = models.FileField(upload_to='egp/notices/%Y/', null=True, blank=True)

    class Meta:
        ordering = ['-published_date']


class BidderRegistration(AuditBaseModel):
    """Supplier onboarding with compliance evidence."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('registered', 'Registered'),
        ('suspended', 'Suspended'),
        ('blacklisted', 'Blacklisted'),
    ]

    vendor = models.OneToOneField(
        'procurement.Vendor', on_delete=models.CASCADE, related_name='egp_registration',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    certificate_expiry = models.DateField(null=True, blank=True)
    tax_clearance_expiry = models.DateField(null=True, blank=True)
    pencom_evidence = models.BooleanField(default=False)
    itf_compliance = models.BooleanField(default=False)
    categories = models.JSONField(default=list, blank=True)
    registered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['vendor']


class Bid(AuditBaseModel):
    """A submitted bid, sealed until the recorded opening event."""

    STATUS_CHOICES = [
        ('submitted', 'Submitted (Sealed)'),
        ('opened', 'Opened'),
        ('responsive', 'Responsive'),
        ('non_responsive', 'Non-Responsive'),
        ('disqualified', 'Disqualified'),
        ('withdrawn', 'Withdrawn'),
    ]

    tender = models.ForeignKey(
        TenderNotice, on_delete=models.CASCADE, related_name='bids',
    )
    bidder = models.ForeignKey(
        BidderRegistration, on_delete=models.PROTECT, related_name='bids',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    submitted_at = models.DateTimeField(default=timezone.now)
    encrypted_payload = models.BinaryField(
        null=True, blank=True,
        help_text='Sealed bid ciphertext at rest. Not decryptable before opening.',
    )
    payload_hash = models.CharField(max_length=64, blank=True, default='')
    opened_at = models.DateTimeField(null=True, blank=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['tender', 'bidder']
        constraints = [
            models.UniqueConstraint(
                fields=['tender', 'bidder'], name='unique_bid_per_tender_bidder',
            ),
        ]


class BidDocument(AuditBaseModel):
    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name='documents')
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to='egp/bids/%Y/')

    class Meta:
        ordering = ['bid', 'name']


class BidOpening(AuditBaseModel):
    """Attendance register + opened-in-public record."""

    tender = models.OneToOneField(
        TenderNotice, on_delete=models.CASCADE, related_name='opening',
    )
    opened_at = models.DateTimeField(default=timezone.now)
    attendance = models.JSONField(default=list, blank=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    minutes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-opened_at']


class EvaluationCommittee(AuditBaseModel):
    tender = models.ForeignKey(
        TenderNotice, on_delete=models.CASCADE, related_name='committees',
    )
    name = models.CharField(max_length=200)
    members = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['tender', 'name']


class EvaluationCriterion(AuditBaseModel):
    committee = models.ForeignKey(
        EvaluationCommittee, on_delete=models.CASCADE, related_name='criteria',
    )
    name = models.CharField(max_length=200)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ['committee', 'name']


class BidScore(AuditBaseModel):
    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name='scores')
    criterion = models.ForeignKey(
        EvaluationCriterion, on_delete=models.CASCADE, related_name='scores',
    )
    score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    comment = models.TextField(blank=True, default='')
    scored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    @property
    def weighted_score(self):
        return round(self.score * self.criterion.weight, 2)

    class Meta:
        ordering = ['bid', 'criterion']
        constraints = [
            models.UniqueConstraint(
                fields=['bid', 'criterion'], name='unique_score_per_bid_criterion',
            ),
        ]


class TenderAward(AuditBaseModel):
    """Award decision; generates the Contract and PurchaseOrder."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('contract_created', 'Contract Created'),
        ('cancelled', 'Cancelled'),
    ]

    tender = models.OneToOneField(
        TenderNotice, on_delete=models.CASCADE, related_name='award',
    )
    winning_bid = models.ForeignKey(
        Bid, on_delete=models.PROTECT, related_name='award',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    award_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    contract = models.OneToOneField(
        'contracts.Contract', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='egp_award',
    )
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    awarded_at = models.DateTimeField(null=True, blank=True)
    awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['-awarded_at']
