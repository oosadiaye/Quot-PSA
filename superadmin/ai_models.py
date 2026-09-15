"""
AI provider configuration and call log.

Follows the shape superadmin already uses twice::

    LanguageConfig (catalogue) -> TenantLanguageSetting (per-tenant choice)
    WebhookConfig  (config)    -> WebhookDelivery       (per-attempt log)

so :class:`AIProvider` / :class:`TenantAISetting` / :class:`AICall` should
read as familiar to anyone who knows those.

Imported into ``superadmin/models.py`` rather than defined there: that
module is already ~700 lines, and the AI layer is a coherent unit that
benefits from its own file. Django does not care where a model class is
defined as long as its app is right.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from superadmin.ai_crypto import decrypt_ai_secret, encrypt_ai_secret, mask


class AICapability(models.TextChoices):
    """What a model is being asked to do.

    Toggles key on capability, not on tenant alone, because the tasks
    genuinely want different models: vision for extraction, something
    cheap and fast for high-volume matching, long context for narrative.
    A single "which provider" switch would force one compromise across
    all three.
    """

    EXTRACTION = "extraction", "Document extraction (scan to draft)"
    RECONCILIATION = "reconciliation", "Reconciliation matching"
    ANALYSIS = "analysis", "Report analysis and narrative"
    CLASSIFICATION = "classification", "Coding and classification"
    DETECTION = "detection", "Anomaly and duplicate detection"
    DRAFTING = "drafting", "Document drafting"


class AIProvider(models.Model):
    """One row per provider. Platform-wide catalogue, like LanguageConfig."""

    class Key(models.TextChoices):
        ANTHROPIC = "anthropic", "Anthropic (Claude)"
        OPENAI = "openai", "OpenAI"
        GEMINI = "gemini", "Google (Gemini)"
        OPENROUTER = "openrouter", "OpenRouter"

    key = models.CharField(max_length=32, choices=Key.choices, unique=True)
    display_name = models.CharField(max_length=64)
    base_url = models.URLField(
        help_text="API base. Overridable for a proxy or a regional endpoint.",
    )

    #: Credential, encrypted under AI_KEK (not SECRET_KEY). Never read this
    #: attribute directly — use api_key / set_api_key below.
    api_key_encrypted = models.TextField(blank=True, default="")

    #: Models this provider offers, e.g.
    #: [{"id": "claude-opus-5", "label": "Opus 5", "vision": true}]
    available_models = models.JSONField(default=list, blank=True)

    #: Which of those to reach for by default.
    #:
    #: Advisory, not binding. The model a call actually uses is
    #: ``TenantAISetting.model_id``, which is pinned per capability — so
    #: changing this does not silently re-point live capabilities at a
    #: different model, and an operator who deliberately set a cheap model
    #: for matching keeps it. It pre-fills the capability form and gives
    #: the provider row something to show besides a count of 445.
    default_model_id = models.CharField(
        max_length=128, blank=True, default='',
        help_text=(
            "Pre-selected when configuring a new capability. Existing "
            "capabilities keep the model they were saved with."
        ),
    )

    is_enabled = models.BooleanField(
        default=False,
        help_text="Platform-wide master switch. Off means no tenant may use it.",
    )
    sort_order = models.PositiveIntegerField(default=0)

    # ── Data policy ──────────────────────────────────────────────────
    #
    # Surfaced beside the toggle in the admin UI. Whoever enables a
    # provider for a government tenant should see what that implies at
    # the moment of the decision, not in a document nobody reopens.

    sends_document_images = models.BooleanField(
        default=True,
        help_text="Scanned invoices and contracts are transmitted to this provider.",
    )
    sends_ledger_amounts = models.BooleanField(
        default=True,
        help_text="Transaction amounts and references are transmitted.",
    )
    retains_data = models.BooleanField(
        default=False,
        help_text="Provider retains submitted content beyond the request.",
    )
    is_broker = models.BooleanField(
        default=False,
        help_text=(
            "Routes to upstream providers rather than serving the model "
            "itself, so its data policy is the union of its upstreams. "
            "True for OpenRouter."
        ),
    )
    data_policy_url = models.URLField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "display_name"]
        verbose_name = "AI Provider"

    def __str__(self) -> str:
        return self.display_name

    # ── Credential access ────────────────────────────────────────────

    @property
    def api_key(self) -> str:
        """Decrypted credential. Raises if AI_KEK_HEX is not configured."""
        return decrypt_ai_secret(self.api_key_encrypted)

    def set_api_key(self, plaintext: str) -> None:
        """Encrypt and store. Does not save."""
        self.api_key_encrypted = encrypt_ai_secret(plaintext)

    @property
    def api_key_masked(self) -> str:
        """Tail of the key, for display. Empty when unset."""
        if not self.api_key_encrypted:
            return ""
        try:
            return mask(self.api_key)
        except Exception:
            # An unreadable credential must not break the admin page that
            # exists to fix it.
            return "(unreadable - check AI_KEK_HEX)"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key_encrypted)

    @property
    def is_usable(self) -> bool:
        """Enabled by the platform and actually holding a credential."""
        return self.is_enabled and self.is_configured


class TenantAISetting(models.Model):
    """Which provider a tenant uses for one capability.

    Keyed on (tenant, capability) rather than tenant alone — see
    :class:`AICapability`. A tenant with no row for a capability has that
    capability switched off; absence is 'off', never a silent default to
    some provider nobody chose.
    """

    tenant = models.ForeignKey(
        "tenants.Client", on_delete=models.CASCADE, related_name="ai_settings",
    )
    capability = models.CharField(max_length=32, choices=AICapability.choices)
    provider = models.ForeignKey(
        AIProvider, on_delete=models.PROTECT, related_name="tenant_settings",
    )
    model_id = models.CharField(
        max_length=128,
        help_text="Model identifier as the provider names it, e.g. claude-opus-5.",
    )
    is_active = models.BooleanField(default=False)

    #: Monthly ceiling. Crossing it disables the capability and alerts,
    #: rather than continuing to bill. Zero means no ceiling, which should
    #: be a deliberate choice rather than the default.
    monthly_cost_cap = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Monthly spend ceiling in USD. 0 disables the cap.",
    )

    require_redaction = models.BooleanField(
        default=True,
        help_text=(
            "Strip bank accounts, BVN/TIN and contact details before "
            "transmission. Off should be a documented exception."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("tenant", "capability")]
        ordering = ["tenant", "capability"]
        verbose_name = "Tenant AI Setting"

    def __str__(self) -> str:
        return f"{self.tenant} · {self.get_capability_display()}"

    @property
    def is_usable(self) -> bool:
        """Every switch between the request and the provider must be on.

        Fail closed: a tenant toggle on with the platform switch off must
        not call anything.
        """
        return self.is_active and self.provider.is_usable


class AICall(models.Model):
    """One row per provider call. The audit trail, like WebhookDelivery.

    Records a **hash** of what was sent, never the payload. The point is
    to prove what happened without the log becoming a second, less
    protected copy of the ledger content that redaction just removed.
    """

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        REFUSED = "refused", "Refused before sending"
        CAPPED = "capped", "Blocked by cost cap"

    tenant = models.ForeignKey(
        "tenants.Client", on_delete=models.CASCADE, related_name="ai_calls",
    )
    capability = models.CharField(max_length=32, choices=AICapability.choices)
    provider = models.ForeignKey(
        AIProvider, on_delete=models.PROTECT, related_name="calls",
    )
    model_id = models.CharField(max_length=128)

    #: SHA-256 of the payload as transmitted, i.e. after redaction.
    request_hash = models.CharField(max_length=64, db_index=True)
    redacted_field_count = models.PositiveIntegerField(
        default=0,
        help_text="Identifiers tokenised before transmission.",
    )

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.SUCCESS,
    )
    http_status = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    #: Eight places, not six. OpenRouter's cheapest models price around
    #: 3e-8 USD per token, so a short call costs ~3e-7 - which rounds to
    #: zero at six places. Individually irrelevant; across a hundred
    #: thousand calls it is money the monthly ceiling never counts.
    cost_usd = models.DecimalField(
        max_digits=12, decimal_places=8, default=Decimal("0.00000000"),
    )
    latency_ms = models.PositiveIntegerField(default=0)

    #: What the call was about, so a proposal can be traced back without
    #: storing the content, e.g. {"model": "VendorInvoice", "id": 4821}.
    subject = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AI Call"
        indexes = [
            models.Index(fields=["tenant", "capability", "-created_at"]),
            models.Index(fields=["tenant", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_capability_display()} · {self.provider_id} · {self.status}"

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

def compute_cost(
    *, prompt_tokens: int, completion_tokens: int, pricing: dict | None,
) -> Decimal:
    """USD for one call from token counts and per-token prices.

    ``pricing`` is the provider's own shape, e.g.
    ``{"prompt": "0.00000003", "completion": "0.00000015"}`` - strings,
    because these are decimal fractions that must not pass through a
    float on the way to money.

    Unknown pricing returns zero rather than guessing. A wrong estimate
    is worse than a known gap: a ceiling enforced against invented
    numbers stops the wrong tenants.
    """
    if not pricing:
        return Decimal("0")
    def _rate(key: str) -> Decimal:
        raw = pricing.get(key)
        if raw in (None, ""):
            return Decimal("0")
        try:
            rate = Decimal(str(raw))
        except (ArithmeticError, ValueError):
            return Decimal("0")
        # A negative rate is a sentinel, not a price. OpenRouter
        # reports "-1" for auto-routed models, where the model and
        # therefore the cost are chosen per request. Multiplying it
        # through yields a negative cost, which does not merely
        # mis-state spend - it SUBTRACTS from the running total, so a
        # tenant on auto-routing would drive recorded spend downward
        # and never reach the monthly ceiling. Unknown, not free.
        if rate < 0:
            return Decimal("0")
        return rate
    return (
        Decimal(prompt_tokens) * _rate("prompt")
        + Decimal(completion_tokens) * _rate("completion")
    )


def pricing_for(provider, model_id: str) -> dict | None:
    """Find a model's pricing in ``provider.available_models``."""
    for entry in provider.available_models or []:
        if isinstance(entry, dict) and entry.get("id") == model_id:
            return entry.get("pricing")
    return None
