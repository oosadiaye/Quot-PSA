"""
The provider client: cost arithmetic and header construction.

No database and no network. The two things worth pinning without either
are the pure ones, and they are the two that quietly cost money or leak
credentials:

  * **cost** decides whether the monthly ceiling is enforceable. Getting
    it wrong by a factor is not a rounding issue, it is a budget that
    never triggers;
  * **headers** carry the API key. A provider whose auth scheme is
    mapped wrongly either fails loudly (fine) or sends a key to the
    wrong header on a shared endpoint (not fine).

The request path itself needs a database for the AICall row, so it is
exercised end to end against a live provider rather than mocked here -
a mock of an HTTP client mostly asserts that the mock was configured.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from superadmin.ai_client import _headers, _hash_payload
from superadmin.ai_models import AIProvider, compute_cost, pricing_for

KEK = "d" * 64


def _provider(key=AIProvider.Key.OPENROUTER, **kw) -> AIProvider:
    p = AIProvider(
        key=key, display_name=str(key), base_url="https://x", is_enabled=True, **kw
    )
    with override_settings(AI_KEK_HEX=KEK):
        p.set_api_key("sk-secret-value")
    return p


class CostTests(SimpleTestCase):
    """Per-token prices arrive as decimal strings and must stay exact."""

    def test_cost_is_tokens_times_rate(self):
        cost = compute_cost(
            prompt_tokens=1000, completion_tokens=500,
            pricing={"prompt": "0.00000003", "completion": "0.00000015"},
        )
        # 1000 * 3e-8 + 500 * 15e-8 = 3e-5 + 7.5e-5
        assert cost == Decimal("0.000105")

    def test_small_calls_are_not_rounded_to_nothing(self):
        # The reason cost_usd carries eight places. At six, this is zero,
        # and a hundred thousand of them are zero too.
        cost = compute_cost(
            prompt_tokens=10, completion_tokens=0,
            pricing={"prompt": "0.00000003"},
        )
        assert cost > 0
        assert cost == Decimal("0.0000003")

    def test_no_pricing_is_zero_not_a_guess(self):
        # A ceiling enforced against invented numbers stops the wrong
        # tenants. A known gap is recoverable; a wrong estimate is not.
        assert compute_cost(prompt_tokens=1000, completion_tokens=1000,
                            pricing=None) == Decimal("0")
        assert compute_cost(prompt_tokens=1000, completion_tokens=1000,
                            pricing={}) == Decimal("0")

    def test_a_free_model_costs_nothing(self):
        assert compute_cost(prompt_tokens=5000, completion_tokens=5000,
                            pricing={"prompt": "0", "completion": "0"}) == Decimal("0")

    def test_a_missing_completion_rate_still_charges_the_prompt(self):
        # Partial pricing must not silently zero the whole call.
        cost = compute_cost(prompt_tokens=1000, completion_tokens=1000,
                            pricing={"prompt": "0.00000003"})
        assert cost == Decimal("0.00003")

    def test_malformed_pricing_does_not_explode(self):
        # Provider catalogues are third-party data; a bad value must not
        # take down the call that was otherwise fine.
        assert compute_cost(prompt_tokens=10, completion_tokens=10,
                            pricing={"prompt": "not-a-number"}) == Decimal("0")

    def test_no_float_in_the_arithmetic(self):
        # 0.1 + 0.2 arithmetic on money is how you get a ceiling that is
        # off by cents and a reconciliation nobody can tie out.
        cost = compute_cost(prompt_tokens=3, completion_tokens=0,
                            pricing={"prompt": "0.1"})
        assert cost == Decimal("0.3")
        assert isinstance(cost, Decimal)


    def test_a_negative_rate_is_a_sentinel_not_a_discount(self):
        # OpenRouter reports "-1" for auto-routed models. Found in live
        # data, not in fixtures: one 19-token call recorded -$19.
        # A negative cost subtracts from the running total, so a tenant
        # on auto-routing would never reach the monthly ceiling.
        cost = compute_cost(
            prompt_tokens=11, completion_tokens=8,
            pricing={"prompt": "-1", "completion": "-1"},
        )
        assert cost == Decimal("0")

    def test_a_negative_rate_does_not_cancel_a_real_one(self):
        # Only the sentinel side is discarded; the priced side still
        # charges, rather than the whole call falling to zero.
        cost = compute_cost(
            prompt_tokens=1000, completion_tokens=1000,
            pricing={"prompt": "0.00000003", "completion": "-1"},
        )
        assert cost == Decimal("0.00003")

    def test_cost_is_never_negative(self):
        # The invariant behind both cases above.
        for rate in ("-1", "-0.5", "-999999"):
            assert compute_cost(prompt_tokens=100, completion_tokens=100,
                                pricing={"prompt": rate, "completion": rate}) >= 0

class PricingLookupTests(SimpleTestCase):

    def test_finds_the_named_model(self):
        p = _provider(available_models=[
            {"id": "a/one", "pricing": {"prompt": "0.001"}},
            {"id": "b/two", "pricing": {"prompt": "0.002"}},
        ])
        assert pricing_for(p, "b/two") == {"prompt": "0.002"}

    def test_unknown_model_returns_none(self):
        p = _provider(available_models=[{"id": "a/one", "pricing": {}}])
        assert pricing_for(p, "not/here") is None

    def test_empty_catalogue_returns_none(self):
        assert pricing_for(_provider(available_models=[]), "x") is None

    def test_malformed_entries_are_skipped(self):
        p = _provider(available_models=["a string", None, {"id": "ok", "pricing": {"prompt": "1"}}])
        assert pricing_for(p, "ok") == {"prompt": "1"}


@override_settings(AI_KEK_HEX=KEK)
class HeaderTests(SimpleTestCase):
    """The key goes in the right header for the right provider."""

    def test_openrouter_uses_a_bearer_token(self):
        h = _headers(_provider(AIProvider.Key.OPENROUTER))
        assert h["Authorization"] == "Bearer sk-secret-value"
        assert "x-api-key" not in h

    def test_openai_uses_a_bearer_token(self):
        h = _headers(_provider(AIProvider.Key.OPENAI))
        assert h["Authorization"] == "Bearer sk-secret-value"

    def test_anthropic_uses_its_own_scheme(self):
        # Anthropic takes x-api-key plus a version header. Sending a
        # bearer token instead fails, which is survivable - but sending
        # both would put the key in an extra place for no reason.
        h = _headers(_provider(AIProvider.Key.ANTHROPIC))
        assert h["x-api-key"] == "sk-secret-value"
        assert "Authorization" not in h
        assert h["anthropic-version"]

    def test_the_key_appears_exactly_once(self):
        for key in (AIProvider.Key.OPENROUTER, AIProvider.Key.ANTHROPIC):
            h = _headers(_provider(key))
            occurrences = sum("sk-secret-value" in v for v in h.values())
            assert occurrences == 1, f"{key}: key present in {occurrences} headers"


class PayloadHashTests(SimpleTestCase):
    """The hash is what the audit trail stores instead of the payload."""

    def test_same_payload_same_hash(self):
        a = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
        assert _hash_payload(a) == _hash_payload(dict(a))

    def test_key_order_does_not_change_the_hash(self):
        # Otherwise two identical requests look different in the log and
        # a replay cannot be recognised.
        assert _hash_payload({"a": 1, "b": 2}) == _hash_payload({"b": 2, "a": 1})

    def test_different_content_different_hash(self):
        assert _hash_payload({"q": "one"}) != _hash_payload({"q": "two"})

    def test_the_hash_does_not_contain_the_content(self):
        # It is stored precisely so the content is not.
        h = _hash_payload({"account": "0123456789"})
        assert "0123456789" not in h
        assert len(h) == 64
