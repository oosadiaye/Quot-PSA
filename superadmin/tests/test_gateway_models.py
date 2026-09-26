"""
Payment-gateway credential crypto and the fail-closed usability chain.

No database — these pin the two properties that make a gateway safe to
enable, and both are pure enough to check without one:

  * credentials round-trip under a dedicated KEK, refuse a foreign
    envelope, and fail hard (never silently plaintext) when the KEK is
    unset;
  * ``is_usable`` folds the platform switch, credential presence and the
    tenant toggle into a single gate, so a tenant toggle on while the
    platform switch is off can never move money.
"""
from __future__ import annotations

from cryptography.fernet import InvalidToken
from django.test import SimpleTestCase, override_settings

from superadmin.gateway_crypto import (
    GatewayKeyNotConfigured,
    decrypt_gateway_secret,
    encrypt_gateway_secret,
    is_encrypted,
    mask,
)
from superadmin.gateway_models import (
    PaymentGatewayProvider,
    TenantGatewaySetting,
)

# A throwaway 64-hex (32-byte) KEK for the crypto tests.
_TEST_KEK = "0123456789abcdef" * 4


@override_settings(GATEWAY_KEK_HEX=_TEST_KEK, GATEWAY_KEK_HEX_OLD=None)
class GatewayCryptoTests(SimpleTestCase):
    def test_round_trip(self):
        stored = encrypt_gateway_secret("sk_live_secret_123")
        assert stored.startswith("gwv1:")
        assert is_encrypted(stored)
        assert decrypt_gateway_secret(stored) == "sk_live_secret_123"

    def test_empty_is_unchanged(self):
        # "Unset" must not become a value that looks set.
        assert encrypt_gateway_secret("") == ""
        assert decrypt_gateway_secret("") == ""

    def test_foreign_envelope_is_refused(self):
        # An AI envelope is not a gateway envelope; refuse rather than guess.
        with self.assertRaises(InvalidToken):
            decrypt_gateway_secret("aiv1:not-ours")

    def test_mask_shows_tail_only(self):
        assert mask("supersecretABCD") == "...ABCD"


class GatewayKekMissingTests(SimpleTestCase):
    @override_settings(GATEWAY_KEK_HEX=None)
    def test_encrypt_without_kek_is_a_hard_error(self):
        # A credential store that quietly stops encrypting is worse than one
        # that refuses to operate.
        with self.assertRaises(GatewayKeyNotConfigured):
            encrypt_gateway_secret("anything")


class ProviderUsabilityTests(SimpleTestCase):
    """`is_usable = is_enabled AND is_configured` (both creds present)."""

    def _provider(self, *, enabled, configured):
        creds = "x" if configured else ""
        return PaymentGatewayProvider(
            key=PaymentGatewayProvider.Key.REMITA, display_name="Remita",
            is_enabled=enabled,
            api_key_encrypted=creds, secret_key_encrypted=creds,
        )

    def test_enabled_and_configured_is_usable(self):
        assert self._provider(enabled=True, configured=True).is_usable is True

    def test_disabled_is_not_usable(self):
        assert self._provider(enabled=False, configured=True).is_usable is False

    def test_enabled_but_unconfigured_is_not_usable(self):
        p = self._provider(enabled=True, configured=False)
        assert p.is_configured is False
        assert p.is_usable is False

    def test_half_configured_is_not_usable(self):
        # API key without a secret cannot authenticate a request.
        p = PaymentGatewayProvider(
            key=PaymentGatewayProvider.Key.XPRESSPAY, display_name="Xpresspay",
            is_enabled=True, api_key_encrypted="x", secret_key_encrypted="",
        )
        assert p.is_usable is False


class TenantSettingUsabilityTests(SimpleTestCase):
    """Fail closed: tenant toggle AND provider usable must both hold."""

    def _setting(self, *, active, provider_usable):
        provider = PaymentGatewayProvider(
            key=PaymentGatewayProvider.Key.REMITA, display_name="Remita",
            is_enabled=provider_usable,
            api_key_encrypted="x" if provider_usable else "",
            secret_key_encrypted="x" if provider_usable else "",
        )
        return TenantGatewaySetting(is_active=active, provider=provider)

    def test_both_on_is_usable(self):
        assert self._setting(active=True, provider_usable=True).is_usable is True

    def test_tenant_on_platform_off_is_not_usable(self):
        # The single most important guarantee: a tenant cannot force a
        # capability live against a platform switch that is off.
        assert self._setting(active=True, provider_usable=False).is_usable is False

    def test_tenant_off_is_not_usable(self):
        assert self._setting(active=False, provider_usable=True).is_usable is False
