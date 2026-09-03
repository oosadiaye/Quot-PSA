"""
integrations — Integration Gateway (G7 / FreeBalance data services).

FUTURE_MODULES §5.7: Remita, NIBSS, GIFMIS and IPPIS are today reference
fields and seed data, not connectors. This module turns them into switchable
connectors with configuration, run logging and message-level idempotency.

Scope:
  * IntegrationEndpoint — per-connector config; credentials held in the
    existing encrypted store (superadmin/encryption.py); environment flag.
  * IntegrationRun      — every exchange logged, with payload hash, status
    and retry count.
  * IntegrationMessage  — every message logged with payload hash, idempotency
    key, status and operator-visible failure reason.
  * Replay & idempotency — a re-delivered message (same message_key) must
    never double-post.

Each connector is independently switchable; dependency is declared per
connector (CONNECTOR_SOURCES), not per module. Connector workers are
stubs/contracts here — the transport implementations are added incrementally.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class IntegrationEndpoint(AuditBaseModel):
    """Per-connector configuration."""

    CONNECTOR_CHOICES = [
        ('remita', 'Remita'),
        ('nibss', 'NIBSS / Bank'),
        ('gifmis', 'GIFMIS'),
        ('ippis', 'IPPIS'),
        ('bvn_tin', 'BVN / TIN Verification'),
    ]

    ENV_CHOICES = [
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ]

    # Declare the app(s) a connector reads/writes: per-connector dependency,
    # so disabling one source module never breaks unrelated connectors.
    CONNECTOR_SOURCES = {
        'remita': ['revenue', 'accounting'],
        'nibss': ['treasury', 'accounting'],
        'gifmis': ['accounting'],
        'ippis': ['hrm'],
        'bvn_tin': ['procurement', 'hrm'],
    }

    name = models.CharField(max_length=100, unique=True)
    connector_type = models.CharField(max_length=20, choices=CONNECTOR_CHOICES, db_index=True)
    environment = models.CharField(max_length=20, choices=ENV_CHOICES, default='sandbox')
    base_url = models.URLField(blank=True, default='')
    credentials_ref = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Key into superadmin/encryption.py encrypted store.',
    )
    is_enabled = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    timeout_seconds = models.PositiveIntegerField(default=30)
    retry_limit = models.PositiveIntegerField(default=0)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['connector_type', 'name']

    @property
    def sources(self):
        return self.CONNECTOR_SOURCES.get(self.connector_type, [])


class IntegrationRun(AuditBaseModel):
    """One execution of a connector."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ]

    endpoint = models.ForeignKey(
        IntegrationEndpoint, on_delete=models.CASCADE, related_name='runs',
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    messages_sent = models.PositiveIntegerField(default=0)
    messages_received = models.PositiveIntegerField(default=0)
    messages_failed = models.PositiveIntegerField(default=0)
    payload_hash = models.CharField(max_length=64, blank=True, default='')
    trigger = models.CharField(max_length=100, blank=True, default='')
    operator_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-started_at']


class IntegrationMessage(AuditBaseModel):
    """Every exchanged message, logged with idempotency and failure reason."""

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('received', 'Received'),
        ('replayed', 'Replayed (idempotent)'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped (duplicate message_key)'),
    ]

    run = models.ForeignKey(
        IntegrationRun, on_delete=models.CASCADE, related_name='messages',
    )
    direction = models.CharField(max_length=10, choices=[('out', 'Outbound'), ('in', 'Inbound')], default='out')
    message_key = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Idempotency key — a re-delivered message with the same key '
                  'must never double-post.',
    )
    payload_hash = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    retry_count = models.PositiveIntegerField(default=0)
    failure_reason = models.TextField(blank=True, default='')
    source_model = models.CharField(max_length=100, blank=True, default='')
    source_id = models.PositiveIntegerField(null=True, blank=True)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['message_key']),
            models.Index(fields=['run', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['run', 'message_key'],
                condition=models.Q(message_key__gt=''),
                name='unique_message_key_per_run',
            ),
        ]
