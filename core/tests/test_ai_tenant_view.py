"""
The tenant-facing AI view: scoping, and what it declines to expose.

No database. These pin the two properties that make the endpoint safe,
and both are pure enough to check without one:

  * the tenant is taken from ``connection.tenant`` and nothing else, so a
    tenant id in a query parameter cannot widen the queryset. This matters
    more here than in most views — ``TenantAISetting`` and ``AICall`` live
    in the *public* schema, so every tenant's database session can already
    see every row. The filter is the only thing standing between them;
  * the serializers name their fields, so a credential added to the
    provider model later cannot start reaching tenants by default.

The querysets themselves are exercised against live data rather than
mocked — a mock of a queryset mostly asserts the mock was configured.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from core.views.ai import TenantAICallSerializer, TenantAIStatusSerializer


class _FakeTenant:
    def __init__(self, schema_name="delta_state", name="Delta"):
        self.schema_name = schema_name
        self.name = name


class TenantResolutionTests(SimpleTestCase):
    """``_tenant()`` is the single source of scope for every endpoint."""

    def _tenant_with(self, value):
        from django.db import connection

        from core.views import ai

        original = getattr(connection, "tenant", None)
        try:
            connection.tenant = value
            return ai._tenant()
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

    def test_the_public_schema_is_not_a_tenant(self):
        # Superadmin requests land on public. Treating that as "a tenant"
        # would make the queryset filter on the platform row and quietly
        # return nothing, which reads like "no AI configured" rather than
        # "wrong place" — a confusing answer to give an operator.
        assert self._tenant_with(_FakeTenant(schema_name="public")) is None

    def test_no_tenant_on_the_connection_resolves_to_none(self):
        assert self._tenant_with(None) is None


class StatusFieldExposureTests(SimpleTestCase):
    """What a tenant may see about the provider serving it."""

    fields = set(TenantAIStatusSerializer.Meta.fields)

    def test_no_credential_field_is_exposed(self):
        # The superadmin serializer carries api_key_masked and base_url.
        # Neither belongs to the tenant, and base_url is a deployment
        # detail that would leak a proxy or regional endpoint choice.
        for banned in (
            "api_key", "api_key_masked", "api_key_encrypted",
            "base_url", "available_models",
        ):
            assert banned not in self.fields, banned

    def test_the_tenant_foreign_key_is_not_exposed(self):
        # Every row returned is already this tenant's. Echoing the id back
        # only invites a client to start passing it somewhere.
        assert "tenant" not in self.fields

    def test_the_data_policy_travels_with_the_row(self):
        # The point of naming the provider to a tenant is so they can
        # judge the arrangement, and the name alone does not say whether
        # content is retained or brokered onward.
        for needed in (
            "provider_name", "provider_retains_data", "provider_is_broker",
            "sends_document_images", "sends_ledger_amounts",
        ):
            assert needed in self.fields, needed

    def test_everything_is_read_only(self):
        # Enable and disable are their own POST views; they never write
        # through this serializer. It declares the whole surface read-only
        # so the status read can't become a mutation path if a field turns
        # writable later.
        assert set(TenantAIStatusSerializer.Meta.read_only_fields) == self.fields


class EnableEndpointWiringTests(SimpleTestCase):
    """The one write a tenant may make is guarded like the reads are.

    ``ai_enable`` re-enables an already-provisioned capability — the only
    mutating tenant endpoint. It must stay POST and admin-only; a GET or an
    unauthenticated caller flipping ``is_active`` would be the same
    horizontal hole the read scoping guards against. Pinned here so a later
    refactor can't quietly widen it, in the spirit of the read-only check
    above.
    """

    def test_enable_requires_authenticated_tenant_admin(self):
        from rest_framework.permissions import IsAuthenticated

        from core.permissions import IsTenantAdmin
        from core.views.ai import ai_enable

        classes = set(ai_enable.cls.permission_classes)
        assert IsTenantAdmin in classes
        assert IsAuthenticated in classes

    def test_enable_is_post_only(self):
        from core.views.ai import ai_enable

        # @api_view(["POST"]) installs a post handler and no get handler, so
        # a GET can never reach the is_active flip — it 405s before the view
        # body runs.
        view = ai_enable.cls
        assert hasattr(view, "post")
        assert not hasattr(view, "get")


class CallLogFieldExposureTests(SimpleTestCase):
    """The audit trail proves a call happened without copying its content."""

    fields = set(TenantAICallSerializer.Meta.fields)

    def test_the_fingerprint_is_exposed_and_the_payload_is_not(self):
        assert "request_hash" in self.fields
        for banned in ("payload", "prompt", "messages", "response", "completion"):
            assert banned not in self.fields, banned

    def test_redaction_count_is_visible(self):
        # A tenant checking that redaction actually ran needs a number,
        # not an assurance.
        assert "redacted_field_count" in self.fields

    def test_cost_and_outcome_are_visible(self):
        for needed in ("cost_usd", "status", "total_tokens", "created_at"):
            assert needed in self.fields, needed

    def test_the_log_is_read_only(self):
        assert set(TenantAICallSerializer.Meta.read_only_fields) == self.fields
