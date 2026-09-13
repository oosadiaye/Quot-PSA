"""
AI provider configuration: the switches that decide whether a call happens.

No database — every property under test is pure logic over unsaved model
instances, so this runs in the no-DB tier with the rest of the AI
foundation.

The cases worth pinning are the ones where being wrong means a call that
should not have happened:

  * a tenant toggle on while the platform switch is off;
  * a provider enabled but holding no credential;
  * "no setting" read as a default rather than as off.

Each of those fails *open* if the logic is written the obvious way, and
failing open here means a State's ledger content reaching a provider
nobody authorised.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from superadmin.ai_models import AICall, AICapability, AIProvider, TenantAISetting

KEK = "c" * 64


def provider(**kw) -> AIProvider:
    base = dict(
        key=AIProvider.Key.ANTHROPIC,
        display_name="Anthropic (Claude)",
        base_url="https://api.anthropic.com",
        is_enabled=True,
    )
    base.update(kw)
    p = AIProvider(**base)
    if "api_key_encrypted" not in kw and kw.get("_with_key", True):
        with override_settings(AI_KEK_HEX=KEK):
            p.set_api_key("sk-ant-test")
    return p


class ProviderUsabilityTests(SimpleTestCase):
    """is_usable is the last gate before a network call."""

    def test_enabled_and_configured_is_usable(self):
        assert provider().is_usable is True

    def test_enabled_but_no_credential_is_not_usable(self):
        # The state right after someone creates a provider row and has
        # not pasted a key yet. Calling would fail at the provider with a
        # 401; refusing here makes the reason legible.
        p = AIProvider(
            key=AIProvider.Key.OPENAI, display_name="OpenAI",
            base_url="https://api.openai.com", is_enabled=True,
        )
        assert p.is_configured is False
        assert p.is_usable is False

    def test_configured_but_disabled_is_not_usable(self):
        # The platform master switch has to win. This is the state after
        # someone disables a provider during an incident while tenant
        # rows still point at it.
        p = provider(is_enabled=False)
        assert p.is_configured is True
        assert p.is_usable is False


class CredentialHandlingTests(SimpleTestCase):

    @override_settings(AI_KEK_HEX=KEK)
    def test_key_round_trips_through_the_model(self):
        p = provider()
        assert p.api_key == "sk-ant-test"

    @override_settings(AI_KEK_HEX=KEK)
    def test_the_stored_column_never_holds_the_plaintext(self):
        p = provider()
        assert "sk-ant-test" not in p.api_key_encrypted

    @override_settings(AI_KEK_HEX=KEK)
    def test_masked_shows_the_tail_only(self):
        p = provider()
        assert p.api_key_masked == "...test"
        assert "sk-ant" not in p.api_key_masked

    def test_masked_is_empty_when_unset(self):
        p = AIProvider(
            key=AIProvider.Key.GEMINI, display_name="Gemini",
            base_url="https://x", is_enabled=True,
        )
        assert p.api_key_masked == ""

    @override_settings(AI_KEK_HEX=None)
    def test_an_unreadable_key_does_not_break_the_admin_page(self):
        # The page that shows this is the page you go to in order to fix
        # a broken key. Raising here would make the problem unfixable
        # through the UI.
        p = AIProvider(
            key=AIProvider.Key.OPENAI, display_name="OpenAI",
            base_url="https://x", is_enabled=True,
            api_key_encrypted="aiv1:garbage",
        )
        assert "unreadable" in p.api_key_masked


class TenantSettingTests(SimpleTestCase):
    """Both switches must be on. Fail closed."""

    def test_active_setting_on_a_usable_provider_is_usable(self):
        s = TenantAISetting(
            capability=AICapability.EXTRACTION,
            provider=provider(), model_id="claude-opus-5", is_active=True,
        )
        assert s.is_usable is True

    def test_inactive_setting_is_not_usable(self):
        s = TenantAISetting(
            capability=AICapability.EXTRACTION,
            provider=provider(), model_id="claude-opus-5", is_active=False,
        )
        assert s.is_usable is False

    def test_platform_disable_overrides_an_active_tenant_toggle(self):
        # The case that matters during an incident: one action at the
        # platform level has to stop every tenant, even those whose own
        # toggle is still on.
        s = TenantAISetting(
            capability=AICapability.EXTRACTION,
            provider=provider(is_enabled=False),
            model_id="claude-opus-5", is_active=True,
        )
        assert s.is_usable is False

    def test_a_provider_without_a_credential_stops_an_active_tenant(self):
        p = AIProvider(
            key=AIProvider.Key.OPENAI, display_name="OpenAI",
            base_url="https://x", is_enabled=True,
        )
        s = TenantAISetting(
            capability=AICapability.RECONCILIATION,
            provider=p, model_id="gpt-x", is_active=True,
        )
        assert s.is_usable is False


class DefaultsTests(SimpleTestCase):
    """Defaults are a security posture, not cosmetics."""

    def test_a_new_provider_is_disabled(self):
        # Creating a row must not enable anything. Someone adding a
        # provider to the catalogue is not thereby authorising traffic.
        p = AIProvider(
            key=AIProvider.Key.OPENROUTER, display_name="OpenRouter",
            base_url="https://openrouter.ai/api",
        )
        assert p.is_enabled is False

    def test_a_new_tenant_setting_is_inactive(self):
        s = TenantAISetting(capability=AICapability.ANALYSIS, model_id="m")
        assert s.is_active is False

    def test_redaction_defaults_on(self):
        # Off should be a documented exception, so the default has to be
        # the safe one.
        s = TenantAISetting(capability=AICapability.ANALYSIS, model_id="m")
        assert s.require_redaction is True

    def test_retains_data_defaults_off_and_must_be_declared(self):
        # A provider that retains submitted content is a materially
        # different proposition for a government tenant; it should have
        # to be stated rather than assumed.
        p = AIProvider(key=AIProvider.Key.GEMINI, display_name="G", base_url="https://x")
        assert p.retains_data is False

    def test_capabilities_cover_the_planned_features(self):
        # Each maps to a feature in AI_FEATURES_PLAN.md. If one is
        # dropped the toggle for that feature silently disappears.
        keys = {c.value for c in AICapability}
        assert {"extraction", "reconciliation", "analysis",
                "classification", "detection", "drafting"} <= keys


class CallLogTests(SimpleTestCase):

    def test_total_tokens_sums_both_directions(self):
        call = AICall(prompt_tokens=1200, completion_tokens=340)
        assert call.total_tokens == 1540

    def test_a_refused_call_is_a_distinct_status(self):
        # "Refused before sending" and "provider returned an error" look
        # the same in a count and mean opposite things: one is the
        # guardrail working, the other is an outage.
        assert AICall.Status.REFUSED != AICall.Status.FAILED
        assert AICall.Status.CAPPED != AICall.Status.FAILED

    def test_cost_precision_survives_small_amounts(self):
        # Per-call costs are fractions of a cent; two decimal places
        # would round almost every call to zero and make the monthly
        # ceiling unenforceable.
        call = AICall(cost_usd=Decimal("0.000123"))
        field = AICall._meta.get_field("cost_usd")
        assert field.decimal_places >= 6
        assert call.cost_usd == Decimal("0.000123")

    def test_the_log_stores_a_hash_not_the_payload(self):
        # The whole point of redaction is undone if the audit log keeps
        # a copy of what was sent.
        field_names = {f.name for f in AICall._meta.get_fields()}
        assert "request_hash" in field_names
        assert "payload" not in field_names
        assert "request_body" not in field_names
