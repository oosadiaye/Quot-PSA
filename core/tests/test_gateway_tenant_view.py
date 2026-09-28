"""
The tenant-facing payment-gateway view: scoping, credential non-exposure,
and the guarded write. Mirrors test_ai_tenant_view.py — no database needed
to pin the properties that make the endpoint safe.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from core.views.gateway import TenantGatewayStatusSerializer


class _FakeTenant:
    def __init__(self, schema_name="delta_state", name="Delta"):
        self.schema_name = schema_name
        self.name = name


class TenantResolutionTests(SimpleTestCase):
    def _tenant_with(self, value):
        from django.db import connection
        from core.views import gateway

        original = getattr(connection, "tenant", None)
        try:
            connection.tenant = value
            return gateway._tenant()
        finally:
            if original is None:
                try:
                    del connection.tenant
                except AttributeError:
                    pass
            else:
                connection.tenant = original

    def test_a_tenant_schema_resolves(self):
        tenant = _FakeTenant()
        assert self._tenant_with(tenant) is tenant

    def test_public_schema_is_not_a_tenant(self):
        assert self._tenant_with(_FakeTenant(schema_name="public")) is None

    def test_no_tenant_resolves_to_none(self):
        assert self._tenant_with(None) is None


class StatusFieldExposureTests(SimpleTestCase):
    """A tenant sees which gateway is on — never its credentials."""

    fields = set(TenantGatewayStatusSerializer.Meta.fields)

    def test_no_credential_field_is_exposed(self):
        for banned in (
            "api_key", "api_key_encrypted", "api_key_masked",
            "secret_key", "secret_key_encrypted", "secret_key_masked",
            "webhook_secret", "webhook_secret_encrypted",
            "base_url", "merchant_id", "config",
        ):
            assert banned not in self.fields, banned

    def test_the_useful_status_travels(self):
        for needed in (
            "provider_key", "provider_name", "is_active", "is_usable",
            "supports_disbursement", "supports_collection",
        ):
            assert needed in self.fields, needed

    def test_everything_is_read_only(self):
        # Enable/disable go through their own POST views, never this
        # serializer — so the whole surface is read-only.
        assert set(TenantGatewayStatusSerializer.Meta.read_only_fields) == self.fields


class EnableEndpointWiringTests(SimpleTestCase):
    """The mutating tenant endpoints stay POST + admin-only."""

    def test_enable_and_disable_are_admin_only_post(self):
        from rest_framework.permissions import IsAuthenticated

        from core.permissions import IsTenantAdmin
        from core.views.gateway import gateway_disable_all, gateway_enable

        for view in (gateway_enable, gateway_disable_all):
            classes = set(view.cls.permission_classes)
            assert IsTenantAdmin in classes
            assert IsAuthenticated in classes
            assert hasattr(view.cls, "post")
            assert not hasattr(view.cls, "get")
