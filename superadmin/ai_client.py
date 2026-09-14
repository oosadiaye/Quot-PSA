"""
Minimal provider client.

Deliberately small. This is the seam every AI feature will call through,
so the value is in what it *refuses* and what it *records*, not in
covering each provider's full API surface.

Everything runs through :func:`call_model`, which:

  1. refuses unless every switch is on (fail closed);
  2. redacts the payload when the tenant setting requires it;
  3. sends;
  4. writes an :class:`AICall` row with a hash — never the payload;
  5. restores the redacted values into the response.

Synchronous for now. A provider round trip is seconds, so in production
this belongs behind a worker; Celery is not installed yet and adopting it
is a deployment decision, so the seam is written to be movable rather
than pretending the problem is solved.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from decimal import Decimal

import requests

from superadmin.ai_models import AICall, AIProvider, compute_cost, pricing_for
from superadmin.ai_redaction import redact_payload, restore

#: Per-provider chat endpoints. OpenRouter and OpenAI share a schema.
_CHAT_PATH = {
    AIProvider.Key.OPENROUTER: "/chat/completions",
    AIProvider.Key.OPENAI: "/chat/completions",
    AIProvider.Key.ANTHROPIC: "/v1/messages",
    AIProvider.Key.GEMINI: "/v1beta/models",
}

DEFAULT_TIMEOUT = 60


class AIRefused(Exception):
    """Raised when a call is refused before anything is transmitted.

    Distinct from a provider error on purpose: this is the guardrail
    working, and it must not be counted alongside outages.
    """


@dataclass
class AIResult:
    text: str
    model_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    redacted_field_count: int = 0
    cost_usd: Decimal = Decimal("0")
    call_id: int | None = None


def _hash_payload(payload: dict) -> str:
    """SHA-256 of the payload as transmitted, i.e. after redaction."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _headers(provider: AIProvider) -> dict[str, str]:
    key = provider.api_key
    if provider.key == AIProvider.Key.ANTHROPIC:
        return {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    # OpenRouter and OpenAI both take a bearer token.
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def call_model(
    *,
    tenant,
    setting,
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
    subject: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> AIResult:
    """Send one prompt through a tenant's configured provider.

    ``setting`` is a :class:`TenantAISetting`. Its ``is_usable`` is the
    single gate — the tenant toggle, the platform switch and the presence
    of a credential all fold into it.
    """
    if not setting.is_usable:
        # Recorded, because "we refused" is information an operator needs
        # and silence is indistinguishable from a feature nobody used.
        AICall.objects.create(
            tenant=tenant,
            capability=setting.capability,
            provider=setting.provider,
            model_id=setting.model_id,
            request_hash="",
            status=AICall.Status.REFUSED,
            error_message=(
                "Refused before sending: the capability is inactive, the "
                "provider is disabled platform-wide, or no credential is set."
            ),
            subject=subject or {},
        )
        raise AIRefused(
            f"AI is not enabled for {setting.get_capability_display()!r} "
            f"on this tenant."
        )

    provider = setting.provider
    body = {
        "model": setting.model_id,
        "messages": (
            ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}]
        ),
        "max_tokens": max_tokens,
    }

    mapping: dict[str, str] = {}
    if setting.require_redaction:
        body, mapping = redact_payload(body)

    url = provider.base_url.rstrip("/") + _CHAT_PATH.get(provider.key, "/chat/completions")
    started = time.monotonic()
    http_status = None
    error = ""
    text = ""
    prompt_tokens = completion_tokens = 0

    try:
        response = requests.post(
            url, headers=_headers(provider), json=body, timeout=timeout,
        )
        http_status = response.status_code
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if choices:
            text = (choices[0].get("message") or {}).get("content", "") or ""
        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        status = AICall.Status.SUCCESS
    except Exception as exc:            # noqa: BLE001 - recorded, then re-raised
        status = AICall.Status.FAILED
        # Truncated: a provider error body can be large and can echo the
        # request back, which would defeat storing a hash rather than a
        # payload.
        error = str(exc)[:500]
        raise
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        call = AICall.objects.create(
            tenant=tenant,
            capability=setting.capability,
            provider=provider,
            model_id=setting.model_id,
            request_hash=_hash_payload(body),
            redacted_field_count=len(mapping),
            status=status,
            http_status=http_status,
            error_message=error,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=compute_cost(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                pricing=pricing_for(provider, setting.model_id),
            ),
            latency_ms=latency_ms,
            subject=subject or {},
        )

    return AIResult(
        text=restore(text, mapping) if mapping else text,
        model_id=setting.model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        redacted_field_count=len(mapping),
        cost_usd=call.cost_usd,
        call_id=call.pk,
    )
