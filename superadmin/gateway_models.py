"""
Payment-gateway configuration and transaction log.

The disbursement/collection sibling of :mod:`superadmin.ai_models`. It
reuses that module's proven three-layer shape verbatim, because the
governance requirement is identical: the platform holds the credentials
and the master switch; each tenant only toggles a gateway on or off; and
every exchange is logged without the log becoming a second copy of the
money it moved.

    PaymentGatewayProvider (catalogue, platform switch + encrypted creds)
    TenantGatewaySetting   (per-tenant on/off toggle, fail-closed)
    GatewayTransaction     (append-only log, hash not payload)

These live in the ``superadmin`` (SHARED/public) app on purpose: an
inbound PSP webhook arrives with no tenant context, so it must resolve
which tenant + payment a callback belongs to from a row every tenant's
DB session can see — exactly as :class:`AICall` is placed.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from superadmin.gateway_crypto import (
    decrypt_gateway_secret,
    encrypt_gateway_secret,
    mask,
)


class GatewayService(models.TextChoices):
    """Which direction of money movement a gateway is used for.

    Kept explicit because the two directions post opposite journals and
    hit different domain objects: a disbursement settles a ``Payment``
    (money out), a collection confirms a ``RevenueCollection`` (money in).
    A provider may support one or both.
    """

    DISBURSEMENT = "disbursement", "Disbursement (payments out)"
    COLLECTION = "collection", "Revenue collection (money in)"


class PaymentGatewayProvider(models.Model):
    """One row per gateway. Platform-wide catalogue, like :class:`AIProvider`."""

    class Key(models.TextChoices):
        REMITA = "remita", "Remita"
        XPRESSPAY = "xpresspay", "Xpresspay"

    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        PRODUCTION = "production", "Production"

    key = models.CharField(max_length=32, choices=Key.choices, unique=True)
    display_name = models.CharField(max_length=64)
    base_url = models.URLField(
        help_text="API base. Overridable for sandbox or a regional endpoint.",
    )
    environment = models.CharField(
        max_length=16, choices=Environment.choices, default=Environment.SANDBOX,
    )

    # ── Credentials (encrypted under GATEWAY_KEK, never SECRET_KEY) ───────
    #
    # PSPs vary: some sign with a secret key, some send an API key header,
    # some both. Merchant/biller identifiers are not secret and stay plain
    # so they can be shown and filtered. Never read the *_encrypted fields
    # directly — use the properties below.

    #: Public / API key, sent to identify the merchant.
    api_key_encrypted = models.TextField(blank=True, default="")
    #: Secret / private key, used to sign outbound requests.
    secret_key_encrypted = models.TextField(blank=True, default="")
    #: Shared secret used to verify inbound webhook signatures. May differ
    #: from the request-signing secret; kept separate so it can be rotated
    #: independently.
    webhook_secret_encrypted = models.TextField(blank=True, default="")
    #: Merchant / biller identifier — not a secret.
    merchant_id = models.CharField(max_length=128, blank=True, default="")

    #: Free-form provider config: service/product ids, fee schedule, etc.
    #: e.g. {"service_type_id": "...", "fee": {"flat": "50.00", "pct": "0"}}
    config = models.JSONField(default=dict, blank=True)

    supports_disbursement = models.BooleanField(default=False)
    supports_collection = models.BooleanField(default=False)

    is_enabled = models.BooleanField(
        default=False,
        help_text="Platform-wide master switch. Off means no tenant may use it.",
    )
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "display_name"]
        verbose_name = "Payment Gateway Provider"

    def __str__(self) -> str:
        return self.display_name

    # ── Credential access ────────────────────────────────────────────────

    @property
    def api_key(self) -> str:
        """Decrypted API key. Raises if GATEWAY_KEK_HEX is not configured."""
        return decrypt_gateway_secret(self.api_key_encrypted)

    def set_api_key(self, plaintext: str) -> None:
        self.api_key_encrypted = encrypt_gateway_secret(plaintext)

    @property
    def secret_key(self) -> str:
        return decrypt_gateway_secret(self.secret_key_encrypted)

    def set_secret_key(self, plaintext: str) -> None:
        self.secret_key_encrypted = encrypt_gateway_secret(plaintext)

    @property
    def webhook_secret(self) -> str:
        return decrypt_gateway_secret(self.webhook_secret_encrypted)

    def set_webhook_secret(self, plaintext: str) -> None:
        self.webhook_secret_encrypted = encrypt_gateway_secret(plaintext)

    def _masked(self, encrypted: str, reader) -> str:
        if not encrypted:
            return ""
        try:
            return mask(reader)
        except Exception:
            # An unreadable credential must not break the admin page that
            # exists to fix it.
            return "(unreadable - check GATEWAY_KEK_HEX)"

    @property
    def api_key_masked(self) -> str:
        return self._masked(self.api_key_encrypted, self.api_key)

    @property
    def secret_key_masked(self) -> str:
        return self._masked(self.secret_key_encrypted, self.secret_key)

    @property
    def is_configured(self) -> bool:
        """Holds the credentials it needs to authenticate a request."""
        return bool(self.api_key_encrypted and self.secret_key_encrypted)

    @property
    def is_usable(self) -> bool:
        """Enabled by the platform and actually holding credentials."""
        return self.is_enabled and self.is_configured


class TenantGatewaySetting(models.Model):
    """Whether a tenant has a gateway switched on.

    Keyed on (tenant, provider). A tenant with no row for a provider has
    that gateway off; absence is 'off', never a silent default. Mirrors
    :class:`TenantAISetting` — the platform provisions, the tenant toggles.
    """

    tenant = models.ForeignKey(
        "tenants.Client", on_delete=models.CASCADE, related_name="gateway_settings",
    )
    provider = models.ForeignKey(
        PaymentGatewayProvider, on_delete=models.PROTECT,
        related_name="tenant_settings",
    )
    is_active = models.BooleanField(default=False)

    #: When more than one active gateway can serve a direction, the default
    #: one is used unless the operator picks another at dispatch time.
    is_default = models.BooleanField(default=False)

    #: Optional per-transaction ceiling in NGN. 0 disables the cap.
    per_transaction_cap = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Per-transaction ceiling in NGN. 0 disables the cap.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("tenant", "provider")]
        ordering = ["tenant", "provider"]
        verbose_name = "Tenant Gateway Setting"

    def __str__(self) -> str:
        return f"{self.tenant} · {self.provider}"

    @property
    def is_usable(self) -> bool:
        """Fail closed: a tenant toggle on with the platform switch off
        (or the provider unconfigured) must not move any money."""
        return self.is_active and self.provider.is_usable


class GatewayTransaction(models.Model):
    """One row per gateway exchange. Append-only audit trail, like
    :class:`AICall`.

    Records a **hash** of what was sent, never the payload, and — because
    it lives in the shared schema — is the anchor an unauthenticated PSP
    webhook uses to find the tenant and the payment a callback belongs to.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending (created, not yet sent)"
        SENT = "sent", "Sent to gateway, awaiting settlement"
        SUCCESS = "success", "Settled successfully"
        FAILED = "failed", "Failed / rejected"
        REFUSED = "refused", "Refused before sending"
        REVERSED = "reversed", "Reversed after settlement"

    tenant = models.ForeignKey(
        "tenants.Client", on_delete=models.CASCADE, related_name="gateway_transactions",
    )
    provider = models.ForeignKey(
        PaymentGatewayProvider, on_delete=models.PROTECT, related_name="transactions",
    )
    direction = models.CharField(max_length=16, choices=GatewayService.choices)

    #: Our idempotency key, set before dispatch. A retried dispatch with the
    #: same key must never move money twice.
    idempotency_key = models.CharField(max_length=64, unique=True)
    #: The gateway's own reference, learned on dispatch/callback. The webhook
    #: resolves this row by it.
    gateway_reference = models.CharField(
        max_length=128, blank=True, default="", db_index=True,
    )

    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    fee = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="NGN")

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING,
    )
    #: SHA-256 of the request body as transmitted. Never the body itself.
    request_hash = models.CharField(max_length=64, blank=True, default="")
    http_status = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    #: What the exchange was about, traceable without storing content, e.g.
    #: {"model": "Payment", "id": 512} or {"model": "RevenueCollection", ...}.
    subject = models.JSONField(default=dict, blank=True)

    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Gateway Transaction"
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["tenant", "direction", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_direction_display()} · {self.provider_id} · {self.status}"
