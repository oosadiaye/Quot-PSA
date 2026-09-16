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

#: Per-provider chat endpoints, relative to ``base_url``.
#:
#: The convention is that ``base_url`` ends at the provider's version
#: segment (``.../v1``, ``.../v1beta``) and everything here is relative to
#: it. That is what makes ``/models`` work uniformly for all four in
#: :func:`models_url` — verified against each live endpoint, where a
#: correct path answers 401/403 and a wrong one answers 404.
#:
#: Gemini is reached through its OpenAI-compatibility layer so it shares
#: the request and response shape with the others. That path is the one
#: piece here not confirmed against a live key; ``/models`` under the same
#: base *is* confirmed, so the Test button still tells the truth about
#: whether a key is accepted.
_CHAT_PATH = {
    AIProvider.Key.OPENROUTER: "/chat/completions",
    AIProvider.Key.OPENAI: "/chat/completions",
    AIProvider.Key.ANTHROPIC: "/messages",
    AIProvider.Key.GEMINI: "/openai/chat/completions",
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


def models_url(provider: AIProvider) -> str:
    """The provider's model-catalogue endpoint.

    Uniform across all four because ``base_url`` carries the version
    segment. Used by the connection test and the catalogue sync, which
    previously each built this themselves.
    """
    return provider.base_url.rstrip("/") + "/models"


def _headers(provider: AIProvider) -> dict[str, str]:
    """Auth headers for one provider.

    Three schemes, not two. Each is what the provider actually accepts,
    checked against the live endpoints rather than assumed:

      * **Anthropic** wants ``x-api-key`` plus a version header.
      * **Gemini** wants ``x-goog-api-key``. Sending its API key as a
        bearer token makes Google look for an *OAuth 2 access token* and
        reject it with 401 no matter how valid the key is — so a Gemini
        key could never have authenticated through the bearer branch.
      * **OpenRouter and OpenAI** take a bearer token.

    This is the single source for all three call sites — the client, the
    connection test and the catalogue sync. They each built their own
    before, which is how the Gemini scheme came to be wrong in all of them.
    """
    key = provider.api_key
    if provider.key == AIProvider.Key.ANTHROPIC:
        return {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    if provider.key == AIProvider.Key.GEMINI:
        return {
            "x-goog-api-key": key,
            "Content-Type": "application/json",
        }
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
    images: list[str] | None = None,
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
    # A user message is either a plain string (text calls) or an
    # OpenAI-compatible multimodal array when images are attached — the
    # instruction text plus one image_url part per page. That shape is
    # accepted by OpenRouter / OpenAI and the Gemini OpenAI-compat layer;
    # Anthropic's native /messages image blocks are not built here.
    user_content: object = prompt
    if images:
        user_content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": u}} for u in images
        ]
    body = {
        "model": setting.model_id,
        "messages": (
            ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": user_content}]
        ),
        "max_tokens": max_tokens,
    }

    mapping: dict[str, str] = {}
    # Redaction rewrites text fields; a scanned document carries its
    # sensitive content in the pixels (governed by the provider's
    # sends_document_images policy), not the fixed instruction prompt, so
    # image calls skip it rather than feed a base64 blob through the matcher.
    if setting.require_redaction and not images:
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
